"""
코칭 비디오 컴포저
자세 분석 텍스트 → LLM 대본 생성 → TTS → 영상 편집 → 최종 합성

파이프라인:
1. 입력 텍스트 → LLM으로 영상 길이에 맞는 대본 생성
2. 대본 → TTS 음성 생성
3. TTS 총 길이에 맞춰 영상 편집 (슬로우모션 + 줌)
4. 편집된 영상 + 자막 + TTS 합성
"""
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import subprocess
import json
from rich.console import Console
from rich.progress import Progress

from .tts_engine import TTSEngine, TTSResult
from .subtitle_generator import (
    SubtitleGenerator,
    SubtitleRenderer,
    SubtitleSegment,
    SubtitleStyle
)
from .script_writer import CoachingScriptWriter, CoachingScript
from .video_editor import CoachingVideoEditor


@dataclass
class CoachingSegment:
    """코칭 세그먼트 (텍스트 + TTS + 자막 통합)"""
    text: str
    tts_result: Optional[TTSResult] = None
    subtitle: Optional[SubtitleSegment] = None


class CoachingComposer:
    """
    코칭 영상 합성기 (Enhanced Pipeline)

    입력:
        - 원본 영상
        - 자세 분석 텍스트

    처리:
        1. LLM으로 영상 길이에 맞는 코칭 대본 생성 (±2초 오차)
        2. 대본을 TTS로 변환
        3. TTS 총 길이에 맞춰 영상 편집 (슬로우모션 + 줌)
        4. 편집된 영상 + 자막 + TTS 합성

    출력:
        - 코칭 영상 (TTS 길이와 영상 길이가 정확히 일치)
    """

    def __init__(
        self,
        tts_enabled: bool = True,
        subtitle_enabled: bool = True,
        tts_engine: str = "gtts",
        use_llm_script: bool = True,
        llm_model: str = "qwen2.5vl:7b",
        console: Optional[Console] = None
    ):
        self.tts_enabled = tts_enabled
        self.subtitle_enabled = subtitle_enabled
        self.use_llm_script = use_llm_script
        self.console = console or Console()

        # TTS 엔진 초기화
        if tts_enabled:
            self.tts = TTSEngine(engine=tts_engine, console=self.console)
        else:
            self.tts = None

        # LLM 대본 생성기 초기화
        if use_llm_script:
            self.script_writer = CoachingScriptWriter(
                model=llm_model,
                console=self.console
            )
        else:
            self.script_writer = None

        # 영상 편집기 초기화
        self.video_editor = CoachingVideoEditor(console=self.console)

        # 자막 생성기 초기화
        self.subtitle_gen = SubtitleGenerator(console=self.console)
        self.subtitle_renderer = SubtitleRenderer(
            generator=self.subtitle_gen,
            console=self.console
        )

    def parse_coaching_text(self, text: str) -> List[str]:
        """
        코칭 텍스트 파싱

        다양한 입력 형식 지원:
        - 줄바꿈으로 구분된 문장
        - JSON 형식
        - 단일 문자열

        Args:
            text: 입력 텍스트

        Returns:
            문장 리스트
        """
        text = text.strip()

        # JSON 형식 시도
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item) for item in data]
            elif isinstance(data, dict):
                # {"texts": [...]} 또는 {"coaching": [...]} 형식
                for key in ["texts", "coaching", "sentences", "lines"]:
                    if key in data:
                        return [str(item) for item in data[key]]
            return [str(data)]
        except json.JSONDecodeError:
            pass

        # 줄바꿈 구분
        lines = text.split('\n')
        sentences = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # "3.2초: 내용" 형식 처리 (시간 정보 무시)
            if ':' in line and line.split(':')[0].replace('초', '').replace('.', '').isdigit():
                line = ':'.join(line.split(':')[1:]).strip()

            if line:
                sentences.append(line)

        # 줄바꿈이 없으면 문장부호로 분리
        if len(sentences) <= 1 and text:
            # 마침표, 물음표, 느낌표로 분리
            import re
            sentences = re.split(r'[.?!]\s*', text)
            sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def compose(
        self,
        input_video: str,
        coaching_text: str,
        output_video: Optional[str] = None,
        video_start_time: float = 0.0,
        subtitle_gap: float = 0.5,
        duration_tolerance: float = 2.0
    ) -> str:
        """
        코칭 영상 합성 (Enhanced Pipeline)

        Args:
            input_video: 원본 영상 경로
            coaching_text: 코칭 텍스트 (자세 분석 등)
            output_video: 출력 경로 (None이면 자동 생성)
            video_start_time: 자막 시작 시간 (초)
            subtitle_gap: 자막 간 간격 (초)
            duration_tolerance: TTS-영상 길이 허용 오차 (초)

        Returns:
            출력 영상 경로
        """
        input_path = Path(input_video)
        if not input_path.exists():
            raise FileNotFoundError(f"영상 파일 없음: {input_video}")

        # 출력 경로 설정
        if output_video is None:
            output_video = str(
                input_path.parent / f"{input_path.stem}_coaching{input_path.suffix}"
            )

        self.console.print(f"[bold cyan]═══ 코칭 영상 생성 파이프라인 ═══[/bold cyan]")

        # 0. 영상 길이 확인
        video_duration = self._get_video_duration(input_video)
        self.console.print(f"[dim]원본 영상 길이: {video_duration:.1f}초[/dim]")

        # 1. LLM으로 대본 생성 (또는 직접 파싱)
        if self.use_llm_script and self.script_writer:
            self.console.print(f"\n[cyan]1. LLM 코칭 대본 생성 중...[/cyan]")
            script = self.script_writer.generate_script(
                analysis_text=coaching_text,
                video_duration=video_duration,
                tolerance=duration_tolerance
            )
            sentences = script.get_texts()
            self.console.print(f"  ✓ {len(sentences)}개 문장 생성 (예상 {script.total_duration:.1f}초)")
        else:
            self.console.print(f"\n[cyan]1. 텍스트 파싱...[/cyan]")
            sentences = self.parse_coaching_text(coaching_text)
            self.console.print(f"  문장 수: {len(sentences)}개")

        for i, s in enumerate(sentences):
            self.console.print(f"    {i+1}. {s[:40]}{'...' if len(s) > 40 else ''}")

        # 2. TTS 생성
        tts_results = []
        tts_total_duration = 0.0

        if self.tts_enabled and self.tts:
            self.console.print(f"\n[cyan]2. TTS 음성 생성 중...[/cyan]")
            tts_results = self.tts.generate_batch(sentences)

            success_count = sum(1 for r in tts_results if r.success)
            tts_total_duration = sum(r.duration for r in tts_results if r.success)
            tts_total_duration += subtitle_gap * (len(tts_results) - 1)  # 간격 추가

            self.console.print(f"  ✓ {success_count}/{len(tts_results)}개 생성")
            self.console.print(f"  ✓ TTS 총 길이: {tts_total_duration:.1f}초")
        else:
            self.console.print(f"[dim]TTS 비활성화됨[/dim]")

        # 3. 영상 편집 (TTS 길이에 맞춤)
        if tts_total_duration > 0:
            self.console.print(f"\n[cyan]3. 영상 편집 (TTS 길이 맞춤)...[/cyan]")

            # 자막 세그먼트 먼저 생성 (TTS 길이 기반)
            tts_durations = [r.duration for r in tts_results if r.success]
            segments = self.subtitle_gen.create_segments(
                texts=sentences,
                tts_durations=tts_durations,
                gap=subtitle_gap
            )

            # 시작 시간 오프셋 적용
            for seg in segments:
                seg.start_time += video_start_time
                seg.end_time += video_start_time

            # 영상 편집 (슬로우모션 + 줌)
            edited_video = str(Path(output_video).with_suffix('.edited.mp4'))
            self.video_editor.edit_video_for_tts(
                input_video=input_video,
                output_video=edited_video,
                tts_total_duration=tts_total_duration,
                subtitle_segments=segments
            )
            current_video = edited_video
        else:
            current_video = input_video
            # TTS 없이 균등 분배
            segments = self._create_even_segments(
                sentences, input_video, video_start_time, subtitle_gap
            )

        # 4. 자막 렌더링
        if self.subtitle_enabled and segments:
            self.console.print(f"\n[cyan]4. 자막 렌더링 중...[/cyan]")

            self.console.print(f"  ✓ {len(segments)}개 자막 세그먼트")
            for seg in segments[:3]:  # 처음 3개만 미리보기
                self.console.print(
                    f"    [{seg.start_time:.1f}s - {seg.end_time:.1f}s] {seg.text[:25]}..."
                )
            if len(segments) > 3:
                self.console.print(f"    ... 외 {len(segments) - 3}개")

            temp_video = str(Path(output_video).with_suffix('.subtitle.mp4'))
            self.subtitle_renderer.render_video_with_subtitles(
                input_video=current_video,
                output_video=temp_video,
                segments=segments
            )

            # 편집 영상 정리
            if current_video != input_video:
                Path(current_video).unlink(missing_ok=True)
            current_video = temp_video
        else:
            self.console.print(f"[dim]자막 비활성화됨[/dim]")

        # 5. TTS 오디오 합성
        if self.tts_enabled and tts_results and any(r.success for r in tts_results):
            self.console.print(f"\n[cyan]5. 오디오 합성 중...[/cyan]")
            self._merge_audio(
                video_path=current_video,
                tts_results=tts_results,
                segments=segments,
                output_path=output_video
            )

            # 임시 파일 정리
            if current_video != input_video:
                Path(current_video).unlink(missing_ok=True)
        else:
            # TTS 없으면 그대로 출력
            if current_video != output_video:
                import shutil
                if current_video != input_video:
                    shutil.move(current_video, output_video)
                else:
                    shutil.copy(current_video, output_video)

        self.console.print(f"\n[green]✓ 코칭 영상 생성 완료: {output_video}[/green]")

        # 최종 영상 길이 확인
        final_duration = self._get_video_duration(output_video)
        self.console.print(f"[dim]최종 영상 길이: {final_duration:.1f}초[/dim]")

        return output_video

    def _get_video_duration(self, video_path: str) -> float:
        """영상 길이 확인"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 video_path],
                capture_output=True,
                text=True
            )
            return float(result.stdout.strip())
        except Exception:
            return 10.0  # 기본값

    def _create_even_segments(
        self,
        sentences: List[str],
        video_path: str,
        start_time: float,
        gap: float
    ) -> List[SubtitleSegment]:
        """영상 길이에 맞게 균등 분배된 자막 세그먼트 생성"""
        import cv2

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = total_frames / fps if fps > 0 else 10.0
        cap.release()

        # 사용 가능한 시간
        available_time = duration - start_time
        segment_time = available_time / len(sentences)

        segments = []
        current = start_time

        for text in sentences:
            display_time = segment_time - gap
            segments.append(SubtitleSegment(
                text=text,
                start_time=current,
                end_time=current + display_time,
                duration=display_time
            ))
            current += segment_time

        return segments

    def _merge_audio(
        self,
        video_path: str,
        tts_results: List[TTSResult],
        segments: List[SubtitleSegment],
        output_path: str
    ):
        """TTS 오디오를 영상에 합성 (ffmpeg 사용)"""
        import shutil

        # 유효한 TTS 파일만 필터링
        valid_tts = [
            (tts, seg) for tts, seg in zip(tts_results, segments)
            if tts.success and Path(tts.audio_file).exists()
        ]

        if not valid_tts:
            shutil.copy(video_path, output_path)
            return

        # 영상 길이 확인
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            video_duration = float(result.stdout.strip())
        except Exception:
            video_duration = 30.0  # 기본값

        # 원본 영상에 오디오가 있는지 확인
        probe_audio_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            video_path
        ]
        try:
            result = subprocess.run(probe_audio_cmd, capture_output=True, text=True)
            has_audio = "audio" in result.stdout
        except Exception:
            has_audio = False

        # 모든 TTS를 하나의 오디오 트랙으로 합치기
        temp_audio = Path(output_path).with_suffix('.temp_audio.aac')

        # 방법: 각 TTS를 개별적으로 지연시킨 후 침묵과 함께 믹스
        input_args = []
        filter_parts = []

        # 입력 0: 영상 길이만큼의 침묵 (lavfi)
        input_args.extend(["-f", "lavfi", "-t", str(video_duration), "-i", "anullsrc=r=44100:cl=stereo"])

        # 나머지 입력: TTS 파일들
        for i, (tts, seg) in enumerate(valid_tts):
            input_args.extend(["-i", tts.audio_file])

        # 각 TTS에 딜레이 적용
        for i, (tts, seg) in enumerate(valid_tts):
            delay_ms = int(seg.start_time * 1000)
            # 입력 인덱스는 i+1 (0은 침묵)
            filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[d{i}]")

        # 모든 오디오 믹스 (침묵 + 딜레이된 TTS들)
        delayed_labels = "".join(f"[d{i}]" for i in range(len(valid_tts)))
        filter_parts.append(f"[0:a]{delayed_labels}amix=inputs={len(valid_tts)+1}:duration=first:dropout_transition=0[aout]")

        filter_complex = ";".join(filter_parts)

        # TTS 믹스 오디오 생성
        mix_cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:a", "aac",
            "-b:a", "192k",
            str(temp_audio)
        ]

        self.console.print(f"[dim]TTS 믹스 명령 실행 중...[/dim]")

        try:
            result = subprocess.run(mix_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                self.console.print(f"[yellow]TTS 믹스 실패: {result.stderr[:500]}[/yellow]")
                shutil.copy(video_path, output_path)
                return
        except Exception as e:
            self.console.print(f"[yellow]TTS 믹스 오류: {e}[/yellow]")
            shutil.copy(video_path, output_path)
            return

        # 생성된 오디오 길이 확인
        try:
            check_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(temp_audio)],
                capture_output=True, text=True
            )
            audio_duration = float(check_result.stdout.strip())
            self.console.print(f"[dim]TTS 오디오 길이: {audio_duration:.1f}초[/dim]")
        except Exception:
            pass

        # 2. 비디오 + 믹스된 오디오 합성
        if has_audio:
            # 원본 오디오와 TTS 믹스
            final_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", str(temp_audio),
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                output_path
            ]
        else:
            # TTS만 추가 (오디오를 비디오 길이에 맞춤)
            final_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", str(temp_audio),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(video_duration),  # 비디오 길이로 제한
                output_path
            ]

        try:
            result = subprocess.run(final_cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0:
                self.console.print(f"[yellow]최종 합성 경고: {result.stderr[:300]}[/yellow]")
                # 오디오 없이 비디오만 복사
                shutil.copy(video_path, output_path)
        except Exception as e:
            self.console.print(f"[yellow]최종 합성 실패: {e}[/yellow]")
            shutil.copy(video_path, output_path)
        finally:
            # 임시 파일 정리
            temp_audio.unlink(missing_ok=True)


def create_coaching_video(
    input_video: str,
    coaching_text: str,
    output_video: Optional[str] = None,
    tts_enabled: bool = True,
    subtitle_enabled: bool = True,
    use_llm_script: bool = True,
    duration_tolerance: float = 2.0
) -> str:
    """
    편의 함수: 코칭 영상 생성

    Args:
        input_video: 원본 영상 경로
        coaching_text: 코칭 텍스트 (자세 분석 등)
        output_video: 출력 경로
        tts_enabled: TTS 활성화
        subtitle_enabled: 자막 활성화
        use_llm_script: LLM으로 대본 생성 (영상 길이 맞춤)
        duration_tolerance: TTS-영상 길이 허용 오차 (초)

    Returns:
        출력 영상 경로
    """
    composer = CoachingComposer(
        tts_enabled=tts_enabled,
        subtitle_enabled=subtitle_enabled,
        use_llm_script=use_llm_script
    )

    return composer.compose(
        input_video=input_video,
        coaching_text=coaching_text,
        output_video=output_video,
        duration_tolerance=duration_tolerance
    )
