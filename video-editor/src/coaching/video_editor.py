"""
코칭 영상 편집기
TTS 길이에 맞춰 영상을 편집 (슬로우모션, 줌인)
"""
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
import subprocess
import cv2
import numpy as np
from rich.console import Console

from .subtitle_generator import SubtitleSegment


@dataclass
class EditSegment:
    """편집 세그먼트"""
    start_time: float  # 원본 시작 시간
    end_time: float    # 원본 끝 시간
    speed: float       # 재생 속도 (0.5 = 슬로우모션)
    zoom: float        # 줌 레벨 (1.0 = 원본, 1.2 = 20% 확대)
    subtitle_text: Optional[str] = None  # 해당 구간 자막


class CoachingVideoEditor:
    """
    코칭 영상 편집기

    TTS 길이에 맞춰 영상 길이 조절:
    - TTS가 영상보다 길면: 슬로우모션으로 늘림
    - TTS가 영상보다 짧으면: 일부 구간만 사용
    - 각 대사 구간에 줌인 효과 적용
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def calculate_edit_plan(
        self,
        video_duration: float,
        tts_total_duration: float,
        subtitle_segments: List[SubtitleSegment]
    ) -> List[EditSegment]:
        """
        TTS 길이에 맞는 편집 계획 생성

        규칙:
        - 배속 금지 (speed > 1.0 불가)
        - 슬로우모션만 사용 (speed <= 1.0)
        - 영상 길이 > TTS 총 길이 유지

        Args:
            video_duration: 원본 영상 길이
            tts_total_duration: TTS 총 길이
            subtitle_segments: 자막 세그먼트 리스트

        Returns:
            EditSegment 리스트
        """
        if not subtitle_segments:
            return []

        self.console.print(f"[dim]편집 계획:[/dim]")
        self.console.print(f"  원본 영상: {video_duration:.1f}초")
        self.console.print(f"  TTS 총 길이: {tts_total_duration:.1f}초")

        # 영상이 TTS보다 짧으면 슬로우모션 필요
        if video_duration < tts_total_duration:
            # 슬로우모션으로 영상을 늘려야 함
            speed = video_duration / tts_total_duration
            speed = max(0.5, speed)  # 최소 0.5x (2배 느리게)
            self.console.print(f"  → 슬로우모션 적용: {speed:.2f}x")
        else:
            # 영상이 충분히 김 → 그대로 사용 (속도 1.0)
            speed = 1.0
            self.console.print(f"  → 원본 속도 유지 (영상이 더 김)")

        # 편집 세그먼트 생성
        segments = []
        current_video_time = 0.0

        for i, sub in enumerate(subtitle_segments):
            # 이 자막 구간에 할당할 영상 길이
            sub_duration = sub.duration

            # speed < 1.0 이면: 더 많은 영상 소스 필요 (sub_duration / speed)
            # speed = 1.0 이면: 동일
            video_segment_duration = sub_duration / speed if speed < 1.0 else sub_duration

            # 영상 끝을 넘지 않도록 제한
            end_time = min(current_video_time + video_segment_duration, video_duration)

            # 줌 레벨: 첫 문장과 마지막 문장은 약간 더 줌
            if i == 0 or i == len(subtitle_segments) - 1:
                zoom = 1.15
            else:
                zoom = 1.1

            segments.append(EditSegment(
                start_time=current_video_time,
                end_time=end_time,
                speed=speed,
                zoom=zoom,
                subtitle_text=sub.text
            ))

            current_video_time = end_time

            # 영상이 끝나면 중단
            if current_video_time >= video_duration:
                break

        return segments

    def apply_edits(
        self,
        input_video: str,
        output_video: str,
        segments: List[EditSegment],
        target_duration: float
    ) -> str:
        """
        편집 적용하여 새 영상 생성

        규칙:
        - 배속 금지 (speed > 1.0 불가)
        - 슬로우모션만 허용 (speed <= 1.0)
        - 영상 길이가 TTS보다 길게 유지

        Args:
            input_video: 입력 영상
            output_video: 출력 영상
            segments: 편집 세그먼트
            target_duration: TTS 총 길이 (영상은 이보다 길어야 함)

        Returns:
            출력 영상 경로
        """
        if not segments:
            # 편집 없이 그대로 복사
            import shutil
            shutil.copy(input_video, output_video)
            return output_video

        # 전체 적용할 속도 계산
        avg_speed = segments[0].speed if segments else 1.0

        # 배속 금지: speed > 1.0 이면 1.0으로 고정
        if avg_speed > 1.0:
            avg_speed = 1.0
            self.console.print(f"[dim]  배속 금지 → 원본 속도 사용[/dim]")

        self.console.print(f"[cyan]영상 편집 적용 중...[/cyan]")
        if avg_speed < 1.0:
            self.console.print(f"  슬로우모션: {avg_speed:.2f}x ({1/avg_speed:.1f}배 느리게)")
        else:
            self.console.print(f"  속도: 원본 유지")

        # ffmpeg로 속도 조절 + 줌 적용
        filter_complex = []

        # 슬로우모션만 적용 (speed < 1.0)
        if avg_speed < 1.0:
            # setpts: 값이 클수록 느려짐
            pts_factor = 1.0 / avg_speed
            filter_complex.append(f"setpts={pts_factor}*PTS")

            # 오디오도 속도 조절 (atempo는 0.5~2.0 범위)
            if avg_speed >= 0.5:
                audio_filter = f"atempo={avg_speed}"
            else:
                # 0.5 미만이면 체인으로
                audio_filter = f"atempo=0.5,atempo={avg_speed/0.5}"
        else:
            audio_filter = None

        # 줌 효과 (평균 줌 적용)
        avg_zoom = sum(s.zoom for s in segments) / len(segments) if segments else 1.0
        if avg_zoom > 1.0:
            zoom_factor = avg_zoom
            filter_complex.append(
                f"scale=iw*{zoom_factor}:ih*{zoom_factor},"
                f"crop=iw/{zoom_factor}:ih/{zoom_factor}"
            )

        # ffmpeg 명령 구성
        video_filter = ",".join(filter_complex) if filter_complex else "null"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-filter:v", video_filter,
        ]

        if audio_filter:
            cmd.extend(["-filter:a", audio_filter])

        # 영상 길이는 자르지 않음 (TTS보다 길게 유지)
        # target_duration은 참고용으로만 사용
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            output_video
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180
            )

            if result.returncode != 0:
                self.console.print(f"[yellow]편집 경고: {result.stderr[:300]}[/yellow]")
                # 실패 시 원본 복사
                import shutil
                shutil.copy(input_video, output_video)

        except Exception as e:
            self.console.print(f"[yellow]편집 실패: {e}[/yellow]")
            import shutil
            shutil.copy(input_video, output_video)

        return output_video

    def edit_video_for_tts(
        self,
        input_video: str,
        output_video: str,
        tts_total_duration: float,
        subtitle_segments: List[SubtitleSegment]
    ) -> str:
        """
        TTS 길이에 맞춰 영상 편집 (통합 메서드)

        Args:
            input_video: 입력 영상
            output_video: 출력 영상
            tts_total_duration: TTS 총 길이
            subtitle_segments: 자막 세그먼트

        Returns:
            편집된 영상 경로
        """
        # 영상 길이 확인
        video_duration = self._get_video_duration(input_video)

        self.console.print(f"[cyan]TTS 맞춤 영상 편집[/cyan]")
        self.console.print(f"  원본: {video_duration:.1f}초 → 목표: {tts_total_duration:.1f}초")

        # 편집 계획 생성
        segments = self.calculate_edit_plan(
            video_duration=video_duration,
            tts_total_duration=tts_total_duration,
            subtitle_segments=subtitle_segments
        )

        # 편집 적용
        return self.apply_edits(
            input_video=input_video,
            output_video=output_video,
            segments=segments,
            target_duration=tts_total_duration
        )

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
