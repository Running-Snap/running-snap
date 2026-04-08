"""
메인 비디오 렌더러
EditScript를 받아 최종 영상 생성
"""
from pathlib import Path
from typing import Optional, List
import random
import numpy as np
import cv2
from moviepy import (
    VideoFileClip,
    concatenate_videoclips,
)
from rich.console import Console
from rich.progress import Progress

from ..core.config_loader import ConfigLoader
from ..core.models import EditScript, EditSegment, OutputConfig
from ..core.exceptions import RenderError
from .effects import (
    apply_speed_change,
    apply_speed_ramp,
    apply_lut_style,
    apply_transition
)
from .effects.reframe import SubjectTracker, SmartReframer, STYLE_DEFAULT_RATIOS


class VideoRenderer:
    """메인 비디오 렌더러"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        console: Optional[Console] = None
    ):
        self.config = config_loader
        self.console = console or Console()
        self._subject_tracker: Optional[SubjectTracker] = None
        self._reframer: Optional[SmartReframer] = None

    def render(
        self,
        video_path: str,
        script: EditScript,
        output_path: str,
        output_specs: Optional[dict] = None,
        output_config: Optional[OutputConfig] = None,
        show_progress: bool = True
    ) -> str:
        """
        영상 렌더링

        Args:
            video_path: 원본 영상 경로
            script: 편집 대본
            output_path: 출력 경로
            output_specs: 출력 사양 (None이면 설정에서 로드)
            output_config: 출력 설정 (비율 등, None이면 스타일에서 자동)
            show_progress: 진행률 표시

        Returns:
            렌더링된 영상 경로
        """
        video_path_obj = Path(video_path)
        output_path_obj = Path(output_path)

        if not video_path_obj.exists():
            raise RenderError(f"원본 영상이 없습니다: {video_path}")

        # 출력 디렉토리 생성
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # 출력 사양
        if output_specs is None:
            output_specs = self.config.get_output_specs("default")

        # 출력 설정 (비율)
        if output_config is None:
            output_config = OutputConfig.from_style(script.style_applied, self.config)

        self.console.print(f"[cyan]렌더링 시작: {len(script.segments)}개 세그먼트[/cyan]")
        self.console.print(f"[dim]출력 비율: {output_config.ratio} ({output_config.width}x{output_config.height})[/dim]")

        try:
            # 원본 로드 (iPhone Spatial Audio 등 특수 코덱 대응)
            source_clip = self._load_video_safe(str(video_path_obj))

            # Smart Reframe: 피사체 추적
            subject_positions = None
            needs_reframe = self._needs_reframe(source_clip, output_config)

            if needs_reframe:
                self.console.print("[cyan]스마트 리프레임: 피사체 추적 중...[/cyan]")
                subject_positions = self._track_subject(str(video_path_obj))

            # 세그먼트별 처리
            processed_clips = []

            if show_progress:
                with Progress() as progress:
                    task = progress.add_task(
                        "[cyan]세그먼트 처리 중...",
                        total=len(script.segments)
                    )

                    for segment in script.segments:
                        clip = self._process_segment(
                            source_clip, segment,
                            output_config, subject_positions
                        )
                        processed_clips.append(clip)
                        progress.advance(task)
            else:
                for segment in script.segments:
                    clip = self._process_segment(
                        source_clip, segment,
                        output_config, subject_positions
                    )
                    processed_clips.append(clip)

            # 트랜지션 적용하며 연결
            self.console.print("[dim]클립 연결 중...[/dim]")
            final_clip = self._concatenate_with_transitions(
                processed_clips,
                script.segments
            )

            # 컬러 그레이딩
            if script.color_grade and script.color_grade != "default":
                self.console.print(f"[dim]컬러 그레이딩 적용: {script.color_grade}[/dim]")
                final_clip = apply_lut_style(final_clip, script.color_grade)

            # 비네팅 (선택적)
            # final_clip = apply_vignette(final_clip, strength=0.2)

            # 오디오 처리
            final_clip = self._process_audio(final_clip, script.audio_config)

            # 출력
            self.console.print("[dim]파일 쓰기 중...[/dim]")
            video_specs = output_specs.get("video", {})

            # 최종 해상도 적용
            if needs_reframe:
                final_clip = final_clip.resized(
                    (output_config.width, output_config.height)
                )

            final_clip.write_videofile(
                str(output_path_obj),
                codec=video_specs.get("codec", "libx264"),
                audio_codec=video_specs.get("audio_codec", "aac"),
                fps=video_specs.get("fps", 30),
                preset=video_specs.get("preset", "medium"),
                threads=4,
                logger=None  # MoviePy 로깅 비활성화
            )

            # 정리
            final_clip.close()
            source_clip.close()
            for clip in processed_clips:
                clip.close()

            self.console.print(f"[green]✓ 렌더링 완료: {output_path}[/green]")
            return str(output_path_obj)

        except Exception as e:
            raise RenderError(f"렌더링 실패: {e}")

    def _process_segment(
        self,
        source: VideoFileClip,
        segment: EditSegment,
        output_config: Optional[OutputConfig] = None,
        subject_positions: Optional[List] = None
    ) -> VideoFileClip:
        """단일 세그먼트 처리"""

        # 1. 구간 추출
        try:
            clip = source.subclipped(segment.source_start, segment.source_end)
        except Exception as e:
            raise RenderError(
                f"구간 추출 실패 ({segment.source_start}-{segment.source_end}): {e}"
            )

        # 2. Smart Reframe 적용 (비율 변환이 필요한 경우)
        if output_config and subject_positions and self._reframer:
            # 세그먼트 시간대의 피사체 위치만 추출
            segment_positions = [
                p for p in subject_positions
                if segment.source_start <= p.time <= segment.source_end
            ]
            if segment_positions:
                clip = self._reframer.reframe_clip(
                    clip, output_config.ratio, segment_positions
                )

        # 3. 속도 조절
        if segment.speed != 1.0:
            if "speed_ramp" in segment.effects:
                # 스피드 램프: 시작과 끝 속도 다르게
                # 간단히 구현: 처음 1.0에서 segment.speed로
                clip = apply_speed_ramp(clip, 1.0, segment.speed, "ease_in_out")
            else:
                clip = apply_speed_change(clip, segment.speed)

        # 4. 이펙트 적용
        for effect in segment.effects:
            clip = self._apply_effect(clip, effect)

        return clip

    def _apply_effect(
        self,
        clip: VideoFileClip,
        effect_name: str
    ) -> VideoFileClip:
        """이펙트 적용"""

        if effect_name == "zoom_in":
            return self._apply_zoom(clip, 1.0, 1.2)
        elif effect_name == "zoom_out":
            return self._apply_zoom(clip, 1.2, 1.0)
        elif effect_name == "shake":
            return self._apply_shake(clip)
        elif effect_name == "flash":
            # 플래시는 트랜지션에서 처리
            return clip
        elif effect_name == "speed_ramp":
            # 이미 속도 조절에서 처리됨
            return clip
        else:
            # 알 수 없는 이펙트는 무시
            return clip

    def _apply_zoom(
        self,
        clip: VideoFileClip,
        start_scale: float,
        end_scale: float
    ) -> VideoFileClip:
        """점진적 줌 효과"""

        def zoom_effect(get_frame, t):
            frame = get_frame(t)
            progress = t / clip.duration if clip.duration > 0 else 0
            scale = start_scale + (end_scale - start_scale) * progress

            if scale == 1.0:
                return frame

            h, w = frame.shape[:2]
            new_h, new_w = int(h * scale), int(w * scale)

            zoomed = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            # 중앙 크롭
            start_y = max(0, (new_h - h) // 2)
            start_x = max(0, (new_w - w) // 2)

            return zoomed[start_y:start_y + h, start_x:start_x + w]

        return clip.transform(zoom_effect, apply_to=['video'])

    def _apply_shake(
        self,
        clip: VideoFileClip,
        intensity: float = 5.0
    ) -> VideoFileClip:
        """카메라 흔들림 효과"""
        # 시드 고정 (재현 가능하도록)
        random.seed(42)

        # 프레임별 오프셋 미리 계산
        num_frames = int(clip.duration * clip.fps) if clip.fps else 100
        offsets = [
            (random.uniform(-intensity, intensity),
             random.uniform(-intensity, intensity))
            for _ in range(num_frames)
        ]

        def shake_effect(get_frame, t):
            frame = get_frame(t)
            frame_idx = int(t * clip.fps) % len(offsets)
            dx, dy = offsets[frame_idx]

            h, w = frame.shape[:2]

            # 이동 변환
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            return cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

        return clip.transform(shake_effect, apply_to=['video'])

    def _concatenate_with_transitions(
        self,
        clips: List[VideoFileClip],
        segments: List[EditSegment]
    ) -> VideoFileClip:
        """트랜지션 적용하며 클립 연결"""

        if not clips:
            raise RenderError("연결할 클립이 없습니다")

        if len(clips) == 1:
            return clips[0]

        result = clips[0]

        for i in range(1, len(clips)):
            # 이전 세그먼트의 transition_out 또는 현재의 transition_in
            prev_segment = segments[i - 1]
            curr_segment = segments[i]

            transition_type = prev_segment.transition_out or curr_segment.transition_in or "cut"

            result = apply_transition(
                result,
                clips[i],
                transition_type,
                duration=0.3
            )

        return result

    def _process_audio(
        self,
        clip: VideoFileClip,
        audio_config: dict
    ) -> VideoFileClip:
        """오디오 처리 (MoviePy 2.x 호환)"""

        if not clip.audio:
            return clip

        # 페이드 인/아웃
        fade_in = audio_config.get("fade_in", 0)
        fade_out = audio_config.get("fade_out", 0)

        try:
            # MoviePy 2.x 방식
            if fade_in > 0:
                clip = clip.with_audio_fadein(fade_in)

            if fade_out > 0:
                clip = clip.with_audio_fadeout(fade_out)
        except AttributeError:
            # MoviePy 2.x에서 메서드가 없으면 audio_fadein/fadeout 직접 적용
            try:
                from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

                if fade_in > 0 and clip.audio:
                    clip = clip.with_audio(
                        clip.audio.with_effects([AudioFadeIn(fade_in)])
                    )
                if fade_out > 0 and clip.audio:
                    clip = clip.with_audio(
                        clip.audio.with_effects([AudioFadeOut(fade_out)])
                    )
            except Exception:
                # 오디오 페이드 실패해도 계속 진행
                pass

        return clip

    def _needs_reframe(
        self,
        clip: VideoFileClip,
        output_config: OutputConfig
    ) -> bool:
        """리프레임이 필요한지 확인"""
        if not output_config:
            return False

        # 원본 비율 계산
        source_ratio = clip.w / clip.h
        # 타겟 비율 계산
        target_ratio = output_config.width / output_config.height

        # 비율 차이가 10% 이상이면 리프레임 필요
        ratio_diff = abs(source_ratio - target_ratio) / target_ratio
        return ratio_diff > 0.1

    def _track_subject(self, video_path: str) -> List:
        """영상에서 피사체 추적"""
        if self._subject_tracker is None:
            self._subject_tracker = SubjectTracker()
        if self._reframer is None:
            self._reframer = SmartReframer()

        positions = self._subject_tracker.extract_positions(video_path)
        return positions

    def _load_video_safe(self, video_path: str) -> VideoFileClip:
        """
        안전하게 영상 로드 (iPhone HDR/Spatial Audio 등 특수 코덱 대응)

        Apple 기기로 촬영된 영상에는 다음과 같은 문제가 있을 수 있음:
        - Spatial Audio (apac 코덱)
        - HEVC 10-bit HDR (bt2020, HLG)
        - Ambient Viewing Environment 메타데이터

        이런 경우 MoviePy가 파싱에 실패하므로 ffmpeg로 호환 형식으로 변환 후 로드.
        """
        import subprocess
        import tempfile

        try:
            # 먼저 일반 로드 시도
            return VideoFileClip(video_path)
        except Exception as e:
            error_msg = str(e).lower()

            # 다양한 iPhone 관련 오류 패턴 체크
            iphone_issues = any(keyword in error_msg for keyword in [
                'codec', 'apac', 'audio', 'ambient', 'float', 'metadata',
                'hevc', 'hdr', 'bt2020', 'parse', 'unsupported operand'
            ])

            if iphone_issues:
                self.console.print("[yellow]iPhone 영상 감지 - 호환 형식으로 변환 중...[/yellow]")

                # 임시 파일로 변환
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
                    temp_video = f.name

                try:
                    # ffmpeg로 완전 재인코딩 (HEVC 10-bit HDR → H.264 8-bit SDR)
                    result = subprocess.run([
                        'ffmpeg', '-y',
                        '-i', video_path,
                        '-map', '0:v:0',           # 첫 번째 비디오 스트림
                        '-map', '0:a:0?',          # 첫 번째 오디오 스트림 (있으면)
                        '-c:v', 'libx264',         # H.264로 재인코딩
                        '-preset', 'fast',         # 빠른 인코딩
                        '-crf', '18',              # 고품질 유지
                        '-pix_fmt', 'yuv420p',     # 8-bit로 변환
                        '-colorspace', 'bt709',    # SDR 색공간
                        '-color_primaries', 'bt709',
                        '-color_trc', 'bt709',
                        '-c:a', 'aac',             # 오디오는 AAC로 변환
                        '-map_metadata', '-1',     # 메타데이터 제거 (Ambient 등)
                        '-movflags', '+faststart',
                        temp_video
                    ], capture_output=True, text=True, timeout=180)

                    if result.returncode == 0:
                        self.console.print("[green]✓ 영상 변환 완료[/green]")
                        # 변환된 영상 로드
                        clip = VideoFileClip(temp_video)
                        # 임시 파일 경로 저장 (정리용)
                        if not hasattr(self, '_temp_files'):
                            self._temp_files = []
                        self._temp_files.append(temp_video)
                        return clip
                    else:
                        self.console.print(f"[red]변환 실패: {result.stderr[:200]}[/red]")
                        raise RenderError(f"영상 변환 실패: {result.stderr[:200]}")

                except subprocess.TimeoutExpired:
                    self.console.print("[red]영상 변환 타임아웃[/red]")
                    raise RenderError("영상 변환 타임아웃")

            # 다른 종류의 에러는 그대로 전파
            raise

    def render_preview(
        self,
        video_path: str,
        script: EditScript,
        output_path: str,
        scale: float = 0.5
    ) -> str:
        """
        빠른 미리보기 렌더링 (저해상도)
        """
        preview_specs = {
            "video": {
                "codec": "libx264",
                "preset": "ultrafast",
                "fps": 24
            }
        }

        return self.render(
            video_path,
            script,
            output_path,
            output_specs=preview_specs,
            show_progress=False
        )
