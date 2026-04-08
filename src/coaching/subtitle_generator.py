"""
자막 생성기 모듈
TTS와 동기화된 자막 클립 생성
PIL 기반 한글 자막 렌더링
"""
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import numpy as np
import cv2
from rich.console import Console

# PIL for Korean text rendering
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL 미설치 - pip install pillow")


@dataclass
class SubtitleSegment:
    """자막 세그먼트"""
    text: str
    start_time: float  # 시작 시간 (초)
    end_time: float    # 끝 시간 (초)
    duration: float    # 표시 시간 (초)
    audio_file: Optional[str] = None  # 연결된 TTS 파일


@dataclass
class SubtitleStyle:
    """자막 스타일 설정"""
    font: str = "AppleGothic"  # macOS 기본 한글 폰트
    fontsize: int = 50
    color: Tuple[int, int, int] = (255, 255, 255)  # RGB (흰색)
    stroke_color: Tuple[int, int, int] = (0, 0, 0)  # RGB (검정)
    stroke_width: int = 3
    position: str = "bottom"  # bottom, center, top
    margin_bottom: int = 120
    margin_sides: int = 50
    background_color: Optional[Tuple[int, int, int, int]] = (0, 0, 0, 180)  # RGBA 반투명 검정


class SubtitleGenerator:
    """
    영상에 자막을 추가하는 생성기
    PIL 기반으로 한글 자막 렌더링
    """

    def __init__(
        self,
        style: Optional[SubtitleStyle] = None,
        console: Optional[Console] = None
    ):
        self.style = style or SubtitleStyle()
        self.console = console or Console()

        # 폰트 로드
        self._font = self._load_font()

    def _load_font(self) -> Optional[ImageFont.FreeTypeFont]:
        """한글 폰트 로드"""
        if not PIL_AVAILABLE:
            return None

        # macOS/Linux/Windows 폰트 경로들
        font_paths = [
            # macOS
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/Library/Fonts/AppleGothic.ttf",
            # Linux
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            # Windows
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/gulim.ttc",
        ]

        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    return ImageFont.truetype(font_path, self.style.fontsize)
                except Exception:
                    continue

        # 기본 폰트 (한글 지원 안될 수 있음)
        try:
            return ImageFont.truetype(self.style.font, self.style.fontsize)
        except Exception:
            self.console.print("[yellow]한글 폰트 로드 실패 - 기본 폰트 사용[/yellow]")
            return ImageFont.load_default()

    def create_segments(
        self,
        texts: List[str],
        tts_durations: Optional[List[float]] = None,
        start_times: Optional[List[float]] = None,
        gap: float = 0.5
    ) -> List[SubtitleSegment]:
        """
        자막 세그먼트 리스트 생성

        Args:
            texts: 자막 텍스트 리스트
            tts_durations: TTS 음성 길이 리스트 (None이면 텍스트 길이로 추정)
            start_times: 각 자막 시작 시간 (None이면 순차적으로)
            gap: 자막 간 간격 (초)

        Returns:
            SubtitleSegment 리스트
        """
        segments = []
        current_time = 0.0

        for i, text in enumerate(texts):
            # 시작 시간
            if start_times and i < len(start_times):
                start = start_times[i]
            else:
                start = current_time

            # 지속 시간 (TTS 길이 + 여유 시간)
            if tts_durations and i < len(tts_durations):
                duration = tts_durations[i] + 0.5
            else:
                duration = self._estimate_duration(text)

            end = start + duration

            segments.append(SubtitleSegment(
                text=text,
                start_time=start,
                end_time=end,
                duration=duration
            ))

            current_time = end + gap

        return segments

    def _estimate_duration(self, text: str, chars_per_second: float = 5.0) -> float:
        """텍스트 읽기 시간 추정"""
        estimated = len(text) / chars_per_second
        return max(2.0, estimated + 0.5)

    def render_subtitle_on_frame(
        self,
        frame: np.ndarray,
        text: str,
        alpha: float = 1.0
    ) -> np.ndarray:
        """
        프레임에 자막 렌더링 (PIL 사용)

        Args:
            frame: 원본 프레임 (BGR)
            text: 자막 텍스트
            alpha: 투명도 (0.0 ~ 1.0)

        Returns:
            자막이 추가된 프레임
        """
        if not text or not PIL_AVAILABLE:
            return frame

        # OpenCV BGR -> PIL RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        # RGBA로 변환 (투명도 지원)
        pil_image = pil_image.convert("RGBA")

        h, w = frame.shape[:2]

        # 텍스트 크기 계산
        draw = ImageDraw.Draw(pil_image)

        # 텍스트 바운딩 박스
        if hasattr(draw, 'textbbox'):
            bbox = draw.textbbox((0, 0), text, font=self._font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            text_w, text_h = draw.textsize(text, font=self._font)

        # 위치 계산
        x = (w - text_w) // 2
        if self.style.position == "bottom":
            y = h - self.style.margin_bottom - text_h
        elif self.style.position == "top":
            y = 50
        else:  # center
            y = (h - text_h) // 2

        # 배경 박스 (반투명 레이어)
        if self.style.background_color:
            overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)

            padding = 20
            box_coords = [
                x - padding,
                y - padding,
                x + text_w + padding,
                y + text_h + padding
            ]

            # 배경 색상 (알파 적용)
            bg_color = list(self.style.background_color)
            bg_color[3] = int(bg_color[3] * alpha)

            overlay_draw.rounded_rectangle(
                box_coords,
                radius=10,
                fill=tuple(bg_color)
            )

            pil_image = Image.alpha_composite(pil_image, overlay)

        # 텍스트 레이어
        text_layer = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)

        # 외곽선 (stroke) - 8방향으로 그리기
        stroke_color = (*self.style.stroke_color, int(255 * alpha))
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if dx != 0 or dy != 0:
                    text_draw.text(
                        (x + dx, y + dy),
                        text,
                        font=self._font,
                        fill=stroke_color
                    )

        # 메인 텍스트
        text_color = (*self.style.color, int(255 * alpha))
        text_draw.text(
            (x, y),
            text,
            font=self._font,
            fill=text_color
        )

        # 합성
        pil_image = Image.alpha_composite(pil_image, text_layer)

        # PIL RGB -> OpenCV BGR
        result = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)

        return result

    def get_active_subtitle(
        self,
        segments: List[SubtitleSegment],
        time: float
    ) -> Optional[SubtitleSegment]:
        """
        특정 시간에 표시할 자막 찾기

        Args:
            segments: 자막 세그먼트 리스트
            time: 현재 시간 (초)

        Returns:
            활성 자막 세그먼트 (없으면 None)
        """
        for seg in segments:
            if seg.start_time <= time < seg.end_time:
                return seg
        return None

    def calculate_alpha(
        self,
        segment: SubtitleSegment,
        time: float,
        fade_duration: float = 0.3
    ) -> float:
        """
        페이드 인/아웃 알파값 계산

        Args:
            segment: 자막 세그먼트
            time: 현재 시간
            fade_duration: 페이드 시간 (초)

        Returns:
            알파값 (0.0 ~ 1.0)
        """
        elapsed = time - segment.start_time
        remaining = segment.end_time - time

        # 페이드 인
        if elapsed < fade_duration:
            return elapsed / fade_duration

        # 페이드 아웃
        if remaining < fade_duration:
            return remaining / fade_duration

        return 1.0


class SubtitleRenderer:
    """
    영상 파일에 자막을 렌더링하는 클래스
    """

    def __init__(
        self,
        generator: Optional[SubtitleGenerator] = None,
        console: Optional[Console] = None
    ):
        self.generator = generator or SubtitleGenerator()
        self.console = console or Console()

    def render_video_with_subtitles(
        self,
        input_video: str,
        output_video: str,
        segments: List[SubtitleSegment],
        show_progress: bool = True
    ) -> str:
        """
        영상에 자막 렌더링

        Args:
            input_video: 입력 영상 경로
            output_video: 출력 영상 경로
            segments: 자막 세그먼트 리스트
            show_progress: 진행률 표시

        Returns:
            출력 영상 경로
        """
        cap = cv2.VideoCapture(input_video)

        if not cap.isOpened():
            raise ValueError(f"영상을 열 수 없습니다: {input_video}")

        # 영상 정보
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # 출력 설정
        output_path = Path(output_video)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                current_time = frame_idx / fps

                # 현재 시간의 자막 찾기
                active_sub = self.generator.get_active_subtitle(segments, current_time)

                if active_sub:
                    alpha = self.generator.calculate_alpha(active_sub, current_time)
                    frame = self.generator.render_subtitle_on_frame(
                        frame, active_sub.text, alpha
                    )

                out.write(frame)
                frame_idx += 1

                if show_progress and frame_idx % 30 == 0:
                    progress = frame_idx / total_frames * 100
                    self.console.print(f"\r  자막 렌더링: {progress:.1f}%", end="")

        finally:
            cap.release()
            out.release()

        if show_progress:
            self.console.print()  # 줄바꿈

        return str(output_path)
