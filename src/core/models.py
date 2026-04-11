"""데이터 모델 정의"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum


# ============================================================
# 출력 비율 설정
# ============================================================

class OutputRatio(Enum):
    """출력 영상/사진 비율"""
    VERTICAL = "9:16"      # 1080x1920 - 틱톡, 릴스, 스토리
    PORTRAIT = "4:5"       # 1080x1350 - 인스타 피드
    SQUARE = "1:1"         # 1080x1080 - 인스타 피드, 카루셀
    LANDSCAPE = "16:9"     # 1920x1080 - 유튜브, 웹
    CINEMATIC = "21:9"     # 2560x1080 - 시네마틱

    @property
    def dimensions(self) -> Tuple[int, int]:
        """비율에 맞는 기본 해상도 반환 (width, height)"""
        ratio_map = {
            "9:16": (1080, 1920),
            "4:5": (1080, 1350),
            "1:1": (1080, 1080),
            "16:9": (1920, 1080),
            "21:9": (2560, 1080),
        }
        return ratio_map.get(self.value, (1080, 1920))

    @property
    def aspect_ratio(self) -> float:
        """width / height 비율 반환"""
        w, h = self.dimensions
        return w / h

    @classmethod
    def from_string(cls, ratio_str: str) -> "OutputRatio":
        """문자열에서 OutputRatio 반환"""
        for ratio in cls:
            if ratio.value == ratio_str:
                return ratio
        return cls.VERTICAL  # 기본값


class OutputConfig(BaseModel):
    """출력 설정"""
    ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    bitrate: str = "10M"

    @classmethod
    def from_ratio(cls, ratio_str: str, base_size: int = None) -> "OutputConfig":
        """비율에서 OutputConfig 생성

        Args:
            ratio_str: 비율 문자열 (예: "9:16", "16:9")
            base_size: 기준 크기 (None이면 기본 해상도 사용)
        """
        output_ratio = OutputRatio.from_string(ratio_str)
        w, h = output_ratio.dimensions

        # base_size로 스케일링 (옵션)
        if base_size is not None:
            # 짧은 쪽을 base_size에 맞춤
            if w <= h:  # 세로형 (9:16 등)
                scale = base_size / w
            else:  # 가로형 (16:9 등)
                scale = base_size / h
            w = int(w * scale)
            h = int(h * scale)

        return cls(ratio=ratio_str, width=w, height=h)

    @classmethod
    def from_style(cls, style_name: str, config_loader=None) -> "OutputConfig":
        """스타일에서 OutputConfig 생성"""
        # 스타일별 기본 비율
        default_ratios = {
            "action": "9:16",
            "instagram": "9:16",
            "tiktok": "9:16",
            "humor": "9:16",
            "documentary": "16:9",
            "coaching": "9:16",
        }

        # config_loader가 있으면 설정에서 읽기
        if config_loader:
            try:
                style = config_loader.get_style(style_name)
                ratio = style.get("defaults", {}).get("output_ratio", default_ratios.get(style_name, "9:16"))
            except Exception:
                ratio = default_ratios.get(style_name, "9:16")
        else:
            ratio = default_ratios.get(style_name, "9:16")

        return cls.from_ratio(ratio)


class DurationType(Enum):
    """영상 길이 분류"""
    SHORT = "short"    # 0-10초
    MEDIUM = "medium"  # 10-30초
    LONG = "long"      # 30-60초

    @classmethod
    def from_duration(cls, seconds: float) -> "DurationType":
        if seconds <= 10:
            return cls.SHORT
        elif seconds <= 30:
            return cls.MEDIUM
        else:
            return cls.LONG

class FrameAnalysis(BaseModel):
    """단일 프레임 분석 결과"""
    timestamp: float
    # ── 기존 필드 (하위 호환) ────────────────────────────────────
    faces_detected: int = 0
    face_expressions: List[str] = Field(default_factory=list)
    motion_level: float = Field(default=0.5, ge=0, le=1)
    composition_score: float = Field(default=0.5, ge=0, le=1)
    lighting: str = "moderate"
    background_type: str = ""
    is_action_peak: bool = False
    aesthetic_score: float = Field(default=0.5, ge=0, le=1)
    emotional_tone: str = ""
    description: str = ""
    # ── 포스터 프레임 선별용 신규 필드 ───────────────────────────
    runner_detected: bool = False
    runner_center_x: float = 0.5    # 0=왼쪽, 1=오른쪽
    runner_center_y: float = 0.5    # 0=위, 1=아래
    runner_size: float = 0.0        # 러너 높이/프레임 높이 비율
    limb_spread: float = 0.0        # 팔다리 펼침 정도 (0=모임, 1=역동적)
    face_expression_quality: str = "neutral"   # positive / neutral / negative
    poster_score: float = 0.0       # 포스터 적합도 종합점수 (0~1)

class VideoAnalysis(BaseModel):
    """전체 영상 분석 결과"""
    source_path: str
    duration: float
    fps: float
    resolution: Tuple[int, int]
    duration_type: DurationType
    frames: List[FrameAnalysis]
    highlights: List[float] = Field(default_factory=list, description="하이라이트 타임스탬프")
    story_beats: Optional[Dict[str, Any]] = None
    overall_motion: str = ""  # "low", "medium", "high"
    dominant_lighting: str = ""
    summary: str = ""

class EditSegment(BaseModel):
    """편집 세그먼트 하나"""
    start_time: float = Field(description="출력 영상에서의 시작 시간")
    end_time: float = Field(description="출력 영상에서의 끝 시간")
    source_start: float = Field(description="원본 영상에서 가져올 시작 시간")
    source_end: float = Field(description="원본 영상에서 가져올 끝 시간")
    speed: float = Field(default=1.0, description="재생 속도 (0.5=슬로모, 2.0=2배속)")
    effects: List[str] = Field(default_factory=list)
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None
    purpose: str = Field(description="hook, build, climax, resolution 등")

class EditScript(BaseModel):
    """LLM이 생성한 편집 대본"""
    segments: List[EditSegment]
    color_grade: str = "default"
    audio_config: Dict[str, Any] = Field(default_factory=dict)
    total_duration: float
    style_applied: str

class PhotoCandidate(BaseModel):
    """베스트컷 후보"""
    timestamp: float
    aesthetic_score: float
    composition_score: float
    emotional_impact: float
    technical_quality: float
    overall_score: float = 0.0
    frame_path: Optional[str] = None

class ProcessingResult(BaseModel):
    """최종 처리 결과"""
    video_path: str
    video_duration: float
    photos: List[str]
    style_used: str
    processing_time: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
