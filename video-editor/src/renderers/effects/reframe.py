"""
Smart Reframe 모듈
피사체(러너)를 추적하며 영상을 목표 비율로 스마트 크롭

핵심 기능:
1. MediaPipe로 피사체 위치 추출 (얼굴 + 포즈)
2. 피사체 중심으로 크롭 영역 계산
3. 프레임 간 부드러운 보간 (떨림 방지)
4. 스타일별 기본 비율 적용
"""
import numpy as np
import cv2
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from moviepy import VideoFileClip
from rich.console import Console
from rich.progress import Progress

# MediaPipe 임포트 (설치 안 되어 있으면 폴백)
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False


# ============================================================
# 비율 정의
# ============================================================

TARGET_RATIOS = {
    "9:16": (9, 16),     # Instagram Reels, TikTok, Story
    "4:5": (4, 5),       # Instagram Feed (세로)
    "1:1": (1, 1),       # Instagram Feed (정사각)
    "16:9": (16, 9),     # YouTube, 원본 유지
    "21:9": (21, 9),     # Cinematic letterbox
}

# 스타일별 기본 비율
STYLE_DEFAULT_RATIOS = {
    "action": "9:16",
    "instagram": "9:16",
    "tiktok": "9:16",
    "humor": "9:16",
    "documentary": "16:9",
}


@dataclass
class SubjectPosition:
    """프레임별 피사체 위치"""
    time: float
    x: float  # 정규화된 x 좌표 (0-1)
    y: float  # 정규화된 y 좌표 (0-1)
    confidence: float
    source: str  # "face", "pose", "fallback"


@dataclass
class CropRegion:
    """크롭 영역"""
    x: int
    y: int
    width: int
    height: int


class SubjectTracker:
    """MediaPipe 기반 피사체 추적기 (Tasks API 0.10.x)"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.landmarker = None

        if not MEDIAPIPE_AVAILABLE:
            self.console.print("[yellow]MediaPipe 미설치 - 중앙 크롭 모드로 폴백[/yellow]")
            return

        # Tasks API: PoseLandmarker (IMAGE 모드)
        candidates = [
            Path(__file__).parents[3] / "backend" / "pose_landmarker_heavy.task",
            Path("/home/ubuntu/backend/pose_landmarker_heavy.task"),
            Path("models/pose_landmarker_full.task"),
        ]
        model_path = next((p for p in candidates if p.exists()), None)
        if not model_path:
            self.console.print(
                "[yellow]모델 파일 없음 - 중앙 크롭 모드로 폴백[/yellow]"
            )
            return

        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import (
                PoseLandmarker, PoseLandmarkerOptions, RunningMode,
            )

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.landmarker = PoseLandmarker.create_from_options(options)
        except Exception as e:
            self.console.print(
                f"[yellow]MediaPipe 초기화 실패: {e} - 중앙 크롭 모드로 폴백[/yellow]"
            )
            self.landmarker = None

    def extract_positions(
        self,
        video_path: str,
        sample_fps: float = 5.0,
        show_progress: bool = True
    ) -> List[SubjectPosition]:
        """
        영상에서 프레임별 피사체 위치 추출

        Args:
            video_path: 영상 파일 경로
            sample_fps: 샘플링 FPS (기본 5fps = 0.2초 간격)
            show_progress: 진행률 표시

        Returns:
            프레임별 SubjectPosition 리스트
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.console.print(f"[red]영상 열기 실패: {video_path}[/red]")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        # 샘플링 간격
        frame_interval = int(fps / sample_fps) if sample_fps > 0 else 1
        frame_interval = max(1, frame_interval)

        positions = []
        frame_idx = 0

        if show_progress:
            with Progress() as progress:
                task = progress.add_task(
                    "[cyan]피사체 추적 중...",
                    total=total_frames // frame_interval
                )

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if frame_idx % frame_interval == 0:
                        time = frame_idx / fps
                        position = self._detect_subject(frame, time)
                        positions.append(position)
                        progress.advance(task)

                    frame_idx += 1
        else:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_interval == 0:
                    time = frame_idx / fps
                    position = self._detect_subject(frame, time)
                    positions.append(position)

                frame_idx += 1

        cap.release()

        # 위치 보간 (부드럽게)
        positions = self._smooth_positions(positions)

        return positions

    def _detect_subject(self, frame: np.ndarray, time: float) -> SubjectPosition:
        """단일 프레임에서 피사체 위치 검출 (Tasks API 0.10.x)"""

        if not MEDIAPIPE_AVAILABLE or self.landmarker is None:
            return SubjectPosition(
                time=time, x=0.5, y=0.5,
                confidence=0.0, source="fallback"
            )

        # BGR → RGB → mp.Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.landmarker.detect(mp_img)
        except Exception:
            return SubjectPosition(
                time=time, x=0.5, y=0.5,
                confidence=0.0, source="fallback"
            )

        if not result.pose_landmarks:
            return SubjectPosition(
                time=time, x=0.5, y=0.5,
                confidence=0.0, source="fallback"
            )

        landmarks = result.pose_landmarks[0]

        # 1. 코(index 0)로 얼굴 위치 추정 — 별도 face_detection 모델 불필요
        nose = landmarks[0]
        if nose.visibility > 0.5:
            face_cx = nose.x
            face_cy = nose.y - 0.03  # 머리 위 공간 확보
            return SubjectPosition(
                time=time,
                x=float(np.clip(face_cx, 0, 1)),
                y=float(np.clip(face_cy, 0, 1)),
                confidence=float(nose.visibility),
                source="face"
            )

        # 2. 주요 랜드마크(어깨·엉덩이)로 몸통 중심 계산
        # 0: 코, 11: 왼쪽 어깨, 12: 오른쪽 어깨, 23: 왼쪽 엉덩이, 24: 오른쪽 엉덩이
        key_points = [0, 11, 12, 23, 24]
        valid_points = []
        for idx in key_points:
            lm = landmarks[idx]
            if lm.visibility > 0.5:
                valid_points.append((lm.x, lm.y))

        if valid_points:
            avg_x = np.mean([p[0] for p in valid_points])
            avg_y = np.mean([p[1] for p in valid_points])
            avg_y = avg_y - 0.1  # 머리 쪽으로 약간 오프셋
            return SubjectPosition(
                time=time,
                x=float(np.clip(avg_x, 0, 1)),
                y=float(np.clip(avg_y, 0, 1)),
                confidence=0.7,
                source="pose"
            )

        # 3. 아무것도 없으면 중앙
        return SubjectPosition(
            time=time, x=0.5, y=0.5,
            confidence=0.0, source="fallback"
        )

    def _smooth_positions(
        self,
        positions: List[SubjectPosition],
        window_size: int = 5
    ) -> List[SubjectPosition]:
        """이동 평균으로 위치 부드럽게"""
        if len(positions) < 3:
            return positions

        x_vals = [p.x for p in positions]
        y_vals = [p.y for p in positions]

        # 이동 평균
        def moving_average(vals, window):
            result = []
            for i in range(len(vals)):
                start = max(0, i - window // 2)
                end = min(len(vals), i + window // 2 + 1)
                result.append(np.mean(vals[start:end]))
            return result

        smooth_x = moving_average(x_vals, window_size)
        smooth_y = moving_average(y_vals, window_size)

        smoothed = []
        for i, pos in enumerate(positions):
            smoothed.append(SubjectPosition(
                time=pos.time,
                x=smooth_x[i],
                y=smooth_y[i],
                confidence=pos.confidence,
                source=pos.source
            ))

        return smoothed

    def close(self):
        """리소스 해제"""
        if self.landmarker is not None:
            self.landmarker.close()
            self.landmarker = None


class SmartReframer:
    """스마트 리프레임 처리기"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.tracker = SubjectTracker(console)

    def get_style_ratio(self, style: str) -> str:
        """스타일에 맞는 기본 비율 반환"""
        return STYLE_DEFAULT_RATIOS.get(style, "9:16")

    def calculate_crop_region(
        self,
        frame_width: int,
        frame_height: int,
        target_ratio: str,
        subject_x: float,
        subject_y: float,
        padding_top: float = 0.15,
        padding_sides: float = 0.1
    ) -> CropRegion:
        """
        피사체 위치 기반 크롭 영역 계산

        Args:
            frame_width: 원본 프레임 너비
            frame_height: 원본 프레임 높이
            target_ratio: 목표 비율 (예: "9:16")
            subject_x: 피사체 x 위치 (0-1)
            subject_y: 피사체 y 위치 (0-1)
            padding_top: 머리 위 여백 비율
            padding_sides: 좌우 여백 비율

        Returns:
            CropRegion
        """
        ratio = TARGET_RATIOS.get(target_ratio, (9, 16))
        target_ar = ratio[0] / ratio[1]  # 목표 종횡비
        source_ar = frame_width / frame_height  # 원본 종횡비

        # 크롭 크기 계산
        if target_ar < source_ar:
            # 목표가 더 세로로 긴 경우 (예: 16:9 → 9:16)
            # 세로 전체 사용, 가로 크롭
            crop_height = frame_height
            crop_width = int(frame_height * target_ar)
        else:
            # 목표가 더 가로로 긴 경우 (예: 9:16 → 16:9)
            # 가로 전체 사용, 세로 크롭
            crop_width = frame_width
            crop_height = int(frame_width / target_ar)

        # 크롭이 프레임보다 커지면 조정
        if crop_width > frame_width:
            crop_width = frame_width
            crop_height = int(crop_width / target_ar)
        if crop_height > frame_height:
            crop_height = frame_height
            crop_width = int(crop_height * target_ar)

        # 피사체 중심으로 크롭 위치 계산
        subject_px = int(subject_x * frame_width)
        subject_py = int(subject_y * frame_height)

        # 머리 위 공간을 위해 피사체를 크롭 영역의 약간 아래에 배치
        target_y_in_crop = int(crop_height * (0.35 + padding_top))  # 상단 35% + 패딩

        crop_x = subject_px - crop_width // 2
        crop_y = subject_py - target_y_in_crop

        # 경계 클램핑
        crop_x = max(0, min(crop_x, frame_width - crop_width))
        crop_y = max(0, min(crop_y, frame_height - crop_height))

        return CropRegion(
            x=int(crop_x),
            y=int(crop_y),
            width=int(crop_width),
            height=int(crop_height)
        )

    def reframe_clip(
        self,
        clip: VideoFileClip,
        target_ratio: str,
        positions: Optional[List[SubjectPosition]] = None,
        output_size: Optional[Tuple[int, int]] = None
    ) -> VideoFileClip:
        """
        클립을 목표 비율로 스마트 리프레임

        Args:
            clip: 입력 클립
            target_ratio: 목표 비율
            positions: 피사체 위치 리스트 (없으면 추적 실행)
            output_size: 출력 해상도 (None이면 자동)

        Returns:
            리프레임된 클립
        """
        w, h = clip.size
        duration = clip.duration
        fps = clip.fps or 30

        # 이미 목표 비율과 같으면 패스
        ratio = TARGET_RATIOS.get(target_ratio, (9, 16))
        target_ar = ratio[0] / ratio[1]
        source_ar = w / h
        if abs(target_ar - source_ar) < 0.01:
            self.console.print(f"[dim]이미 {target_ratio} 비율 - 리프레임 스킵[/dim]")
            return clip

        # 피사체 위치가 없으면 추출 (영상 파일이 필요)
        if positions is None or len(positions) == 0:
            # 중앙 크롭 폴백
            self.console.print("[dim]피사체 위치 없음 - 중앙 크롭[/dim]")
            positions = [SubjectPosition(
                time=t, x=0.5, y=0.4,
                confidence=0.0, source="fallback"
            ) for t in np.arange(0, duration, 0.2)]

        # 시간별 크롭 영역 계산
        def get_crop_at_time(t: float) -> CropRegion:
            # 가장 가까운 위치 찾기
            closest = min(positions, key=lambda p: abs(p.time - t))
            return self.calculate_crop_region(
                w, h, target_ratio,
                closest.x, closest.y
            )

        # 크롭 적용 함수
        def make_frame(get_frame, t):
            frame = get_frame(t)
            crop = get_crop_at_time(t)

            # 크롭
            cropped = frame[crop.y:crop.y+crop.height, crop.x:crop.x+crop.width]

            # 출력 크기로 리사이즈
            if output_size:
                cropped = cv2.resize(cropped, output_size, interpolation=cv2.INTER_LANCZOS4)

            return cropped

        # 새 클립 생성
        reframed = clip.transform(make_frame, apply_to=['video'])

        # 크기 업데이트 (첫 번째 크롭 기준)
        first_crop = get_crop_at_time(0)
        if output_size:
            new_size = output_size
        else:
            new_size = (first_crop.width, first_crop.height)

        return reframed

    def reframe_video(
        self,
        video_path: str,
        target_ratio: str,
        output_path: str,
        style: Optional[str] = None,
        output_size: Optional[Tuple[int, int]] = None,
        show_progress: bool = True
    ) -> str:
        """
        영상 파일을 리프레임해서 저장

        Args:
            video_path: 입력 영상 경로
            target_ratio: 목표 비율 (또는 None이면 스타일에서 결정)
            output_path: 출력 경로
            style: 스타일 이름 (비율 자동 결정용)
            output_size: 출력 해상도
            show_progress: 진행률 표시

        Returns:
            출력 파일 경로
        """
        # 스타일에서 비율 결정
        if target_ratio is None and style:
            target_ratio = self.get_style_ratio(style)
        if target_ratio is None:
            target_ratio = "9:16"

        self.console.print(f"[cyan]리프레임: {target_ratio}[/cyan]")

        # 피사체 추적
        self.console.print("[dim]피사체 추적 중...[/dim]")
        positions = self.tracker.extract_positions(
            video_path,
            sample_fps=5.0,
            show_progress=show_progress
        )

        # 영상 로드 및 리프레임
        clip = VideoFileClip(video_path)
        reframed = self.reframe_clip(clip, target_ratio, positions, output_size)

        # 저장
        reframed.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            logger=None
        )

        clip.close()
        reframed.close()

        return output_path

    def reframe_image(
        self,
        image: np.ndarray,
        target_ratio: str,
        subject_position: Optional[Tuple[float, float]] = None
    ) -> np.ndarray:
        """
        이미지를 목표 비율로 스마트 크롭

        Args:
            image: 입력 이미지 (BGR)
            target_ratio: 목표 비율
            subject_position: 피사체 위치 (x, y) 0-1, 없으면 중앙

        Returns:
            크롭된 이미지
        """
        h, w = image.shape[:2]

        if subject_position is None:
            subject_x, subject_y = 0.5, 0.4  # 기본: 약간 위쪽 중앙
        else:
            subject_x, subject_y = subject_position

        crop = self.calculate_crop_region(
            w, h, target_ratio,
            subject_x, subject_y
        )

        cropped = image[crop.y:crop.y+crop.height, crop.x:crop.x+crop.width]

        return cropped

    def detect_subject_in_image(self, image: np.ndarray) -> Tuple[float, float]:
        """
        이미지에서 피사체 위치 검출

        Args:
            image: 입력 이미지 (BGR)

        Returns:
            (x, y) 정규화된 좌표
        """
        position = self.tracker._detect_subject(image, 0.0)
        return (position.x, position.y)

    def close(self):
        """리소스 해제"""
        self.tracker.close()


# ============================================================
# 편의 함수
# ============================================================

def smart_reframe(
    clip: VideoFileClip,
    target_ratio: str,
    positions: Optional[List[SubjectPosition]] = None,
    console: Optional[Console] = None
) -> VideoFileClip:
    """
    클립을 스마트 리프레임 (간편 인터페이스)

    Args:
        clip: 입력 클립
        target_ratio: 목표 비율 (예: "9:16")
        positions: 피사체 위치 리스트 (선택)
        console: Rich 콘솔

    Returns:
        리프레임된 클립
    """
    reframer = SmartReframer(console)
    return reframer.reframe_clip(clip, target_ratio, positions)


def get_output_resolution(target_ratio: str, base_size: int = 1080) -> Tuple[int, int]:
    """
    비율에 맞는 출력 해상도 반환

    Args:
        target_ratio: 목표 비율
        base_size: 기준 크기 (짧은 변)

    Returns:
        (width, height)
    """
    ratio = TARGET_RATIOS.get(target_ratio, (9, 16))

    if ratio[0] < ratio[1]:
        # 세로가 더 긴 경우 (9:16)
        width = base_size
        height = int(base_size * ratio[1] / ratio[0])
    else:
        # 가로가 더 긴 경우 (16:9)
        height = base_size
        width = int(base_size * ratio[0] / ratio[1])

    return (width, height)
