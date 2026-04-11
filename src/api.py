"""
========================================================================
비디오 AI 파이프라인 - 통합 API
========================================================================

백엔드 통합을 위한 단일 진입점.
이 파일 하나만 import하면 모든 기능 사용 가능.

사용 예시:
    from src.api import VideoEditorAPI, CoachingAPI, VideoEditorConfig

    # 일반 영상 편집
    api = VideoEditorAPI()
    result = api.process("video.mp4", duration=10, style="action")

    # 코칭 영상
    coaching = CoachingAPI()
    result = coaching.create("video.mp4", "어깨 힘 빼세요. 팔은 옆으로.")
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from enum import Enum
import asyncio


# ============================================================
# 설정 (Configuration)
# ============================================================

class EditStyle(Enum):
    """편집 스타일"""
    ACTION = "action"           # 스포츠 액션샷
    INSTAGRAM = "instagram"     # 인스타그램 스타일
    TIKTOK = "tiktok"          # 틱톡 바이럴
    HUMOR = "humor"            # 밈/유머
    DOCUMENTARY = "documentary" # 다큐멘터리


class PhotoPreset(Enum):
    """사진 보정 프리셋"""
    SPORTS_ACTION = "sports_action"   # 스포츠 액션 (고대비, 선명)
    GOLDEN_HOUR = "golden_hour"       # 황금빛 따뜻한 톤
    DRAMATIC = "dramatic"             # 드라마틱 (강한 대비)
    CLEAN_BRIGHT = "clean_bright"     # 깨끗하고 밝은


class ProcessingMode(Enum):
    """처리 모드"""
    LOCAL = "local"     # 로컬 AI (Ollama) - 무료, 느림
    API = "api"         # 클라우드 API - 유료, 빠름
    MOCK = "mock"       # 테스트용 더미


@dataclass
class VideoEditorConfig:
    """
    비디오 에디터 설정

    Attributes:
        mode: 처리 모드 (local/api/mock)
        ollama_model: 로컬 AI 모델명
        cache_enabled: 캐시 사용 여부
        output_dir: 출력 디렉토리
        temp_dir: 임시 파일 디렉토리
    """
    mode: ProcessingMode = ProcessingMode.LOCAL
    ollama_model: str = "qwen2.5vl:7b"
    cache_enabled: bool = True
    output_dir: str = "outputs"
    temp_dir: str = "temp"

    # API 키 (mode=API일 때만 필요)
    qwen_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None


@dataclass
class CoachingConfig:
    """
    코칭 영상 설정

    Attributes:
        tts_enabled: TTS 음성 사용 여부
        subtitle_enabled: 자막 사용 여부
        use_llm_script: LLM으로 대본 최적화 여부
        llm_model: LLM 모델명
    """
    tts_enabled: bool = True
    subtitle_enabled: bool = True
    use_llm_script: bool = True
    llm_model: str = "qwen2.5vl:7b"
    output_dir: str = "outputs/videos"


# ============================================================
# 결과 타입 (Result Types)
# ============================================================

@dataclass
class EditResult:
    """
    영상 편집 결과

    Attributes:
        success: 성공 여부
        video_path: 출력 영상 경로
        video_duration: 영상 길이 (초)
        photos: 베스트컷 사진 경로 리스트
        processing_time: 처리 시간 (초)
        error: 에러 메시지 (실패 시)
        metadata: 추가 메타데이터
    """
    success: bool
    video_path: Optional[str] = None
    video_duration: float = 0.0
    photos: List[str] = field(default_factory=list)
    processing_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (JSON 직렬화용)"""
        return {
            "success": self.success,
            "video_path": self.video_path,
            "video_duration": self.video_duration,
            "photos": self.photos,
            "processing_time": self.processing_time,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class CoachingResult:
    """
    코칭 영상 결과

    Attributes:
        success: 성공 여부
        video_path: 출력 영상 경로
        video_duration: 영상 길이 (초)
        tts_duration: TTS 음성 길이 (초)
        subtitle_count: 자막 개수
        error: 에러 메시지 (실패 시)
    """
    success: bool
    video_path: Optional[str] = None
    video_duration: float = 0.0
    tts_duration: float = 0.0
    subtitle_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "success": self.success,
            "video_path": self.video_path,
            "video_duration": self.video_duration,
            "tts_duration": self.tts_duration,
            "subtitle_count": self.subtitle_count,
            "error": self.error
        }


# ============================================================
# 콜백 타입 (Progress Callbacks)
# ============================================================

# 진행률 콜백 타입: (step: str, progress: float, message: str) -> None
ProgressCallback = Callable[[str, float, str], None]


# ============================================================
# 메인 API 클래스
# ============================================================

class VideoEditorAPI:
    """
    비디오 에디터 통합 API

    백엔드에서 이 클래스만 import하면 됨.

    Example:
        ```python
        from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode

        # 1. 설정 생성
        config = VideoEditorConfig(
            mode=ProcessingMode.LOCAL,
            cache_enabled=True
        )

        # 2. API 초기화
        api = VideoEditorAPI(config)

        # 3. 영상 처리
        result = api.process(
            video_path="input.mp4",
            duration=10,
            style="action",
            photo_count=5
        )

        # 4. 결과 확인
        if result.success:
            print(f"영상: {result.video_path}")
            print(f"사진: {result.photos}")
        else:
            print(f"실패: {result.error}")
        ```
    """

    def __init__(self, config: Optional[VideoEditorConfig] = None):
        """
        API 초기화

        Args:
            config: 설정 객체 (None이면 기본값 사용)
        """
        self.config = config or VideoEditorConfig()
        self._pipeline = None
        self._initialized = False

    def _ensure_initialized(self):
        """파이프라인 지연 초기화"""
        if self._initialized:
            return

        from .pipeline import VideoPipeline

        self._pipeline = VideoPipeline(
            qwen_api_key=self.config.qwen_api_key,
            claude_api_key=self.config.claude_api_key,
            use_mock=(self.config.mode == ProcessingMode.MOCK),
            use_local=(self.config.mode == ProcessingMode.LOCAL),
            ollama_model=self.config.ollama_model,
            use_cache=self.config.cache_enabled
        )
        self._initialized = True

    def process(
        self,
        video_path: str,
        duration: float,
        style: str = "action",
        photo_count: int = 5,
        photo_preset: str = "sports_action",
        progress_callback: Optional[ProgressCallback] = None
    ) -> EditResult:
        """
        영상 처리 (동기)

        Args:
            video_path: 입력 영상 경로
            duration: 목표 영상 길이 (초)
            style: 편집 스타일 (action/instagram/tiktok/humor/documentary)
            photo_count: 베스트컷 사진 개수 (1-10)
            photo_preset: 사진 보정 프리셋
            progress_callback: 진행률 콜백 함수

        Returns:
            EditResult: 처리 결과
        """
        return asyncio.run(self.process_async(
            video_path=video_path,
            duration=duration,
            style=style,
            photo_count=photo_count,
            photo_preset=photo_preset,
            progress_callback=progress_callback
        ))

    async def process_async(
        self,
        video_path: str,
        duration: float,
        style: str = "action",
        photo_count: int = 5,
        photo_preset: str = "sports_action",
        progress_callback: Optional[ProgressCallback] = None
    ) -> EditResult:
        """
        영상 처리 (비동기)

        Args:
            video_path: 입력 영상 경로
            duration: 목표 영상 길이 (초)
            style: 편집 스타일
            photo_count: 베스트컷 사진 개수
            photo_preset: 사진 보정 프리셋
            progress_callback: 진행률 콜백 함수

        Returns:
            EditResult: 처리 결과
        """
        try:
            # 입력 검증
            if not Path(video_path).exists():
                return EditResult(
                    success=False,
                    error=f"입력 파일이 없습니다: {video_path}"
                )

            if duration <= 0:
                return EditResult(
                    success=False,
                    error="duration은 0보다 커야 합니다"
                )

            valid_styles = ["action", "instagram", "tiktok", "humor", "documentary"]
            if style not in valid_styles:
                return EditResult(
                    success=False,
                    error=f"지원하지 않는 스타일: {style}. 가능: {valid_styles}"
                )

            # 초기화
            self._ensure_initialized()

            # 처리 실행
            result = await self._pipeline.process(
                input_video=video_path,
                target_duration=duration,
                style=style,
                output_dir=self.config.output_dir,
                photo_count=photo_count,
                photo_preset=photo_preset
            )

            return EditResult(
                success=True,
                video_path=result.video_path,
                video_duration=result.video_duration,
                photos=result.photos,
                processing_time=result.processing_time,
                metadata=result.metadata
            )

        except Exception as e:
            return EditResult(
                success=False,
                error=str(e)
            )

    def get_available_styles(self) -> List[Dict[str, str]]:
        """
        사용 가능한 스타일 목록 반환

        Returns:
            스타일 정보 리스트
        """
        return [
            {
                "id": "action",
                "name": "Action Sports",
                "description": "스포츠 사진작가 스타일 - 결정적 순간 포착, 슬로모션"
            },
            {
                "id": "instagram",
                "name": "Instagram",
                "description": "인플루언서 콘텐츠 - 멋있어 보이게, 따뜻한 색감"
            },
            {
                "id": "tiktok",
                "name": "TikTok Viral",
                "description": "틱톡 바이럴 - 빠른 컷, 높은 채도, 트렌디"
            },
            {
                "id": "humor",
                "name": "Humor/Meme",
                "description": "밈 편집 - 코미디 타이밍, 웃긴 순간 강조"
            },
            {
                "id": "documentary",
                "name": "Documentary",
                "description": "다큐멘터리 - 자연스러운 흐름, 최소 편집"
            }
        ]

    def clear_cache(self, video_path: Optional[str] = None):
        """
        캐시 삭제

        Args:
            video_path: 특정 영상의 캐시만 삭제 (None이면 전체)
        """
        from .core.analysis_cache import AnalysisCache
        cache = AnalysisCache()

        if video_path:
            cache.clear_cache(video_path)
        else:
            cache.clear_all()


class CoachingAPI:
    """
    코칭 영상 API

    자세 분석 텍스트를 받아 TTS + 자막이 들어간 코칭 영상 생성.

    Example:
        ```python
        from src.api import CoachingAPI, CoachingConfig

        # 1. 설정 (선택)
        config = CoachingConfig(
            tts_enabled=True,
            subtitle_enabled=True
        )

        # 2. API 초기화
        api = CoachingAPI(config)

        # 3. 코칭 영상 생성
        result = api.create(
            video_path="running.mp4",
            coaching_text="어깨 힘 빼세요. 팔은 옆으로 리듬만 주세요."
        )

        # 4. 결과 확인
        if result.success:
            print(f"코칭 영상: {result.video_path}")
        ```
    """

    def __init__(self, config: Optional[CoachingConfig] = None):
        """
        API 초기화

        Args:
            config: 설정 객체
        """
        self.config = config or CoachingConfig()
        self._composer = None
        self._initialized = False

    def _ensure_initialized(self):
        """컴포저 지연 초기화"""
        if self._initialized:
            return

        from .coaching import CoachingComposer

        self._composer = CoachingComposer(
            tts_enabled=self.config.tts_enabled,
            subtitle_enabled=self.config.subtitle_enabled,
            use_llm_script=self.config.use_llm_script,
            llm_model=self.config.llm_model
        )
        self._initialized = True

    def create(
        self,
        video_path: str,
        coaching_text: str,
        output_path: Optional[str] = None
    ) -> CoachingResult:
        """
        코칭 영상 생성

        Args:
            video_path: 입력 영상 경로
            coaching_text: 코칭 텍스트 (자세 분석 결과 등)
            output_path: 출력 경로 (None이면 자동 생성)

        Returns:
            CoachingResult: 생성 결과
        """
        try:
            # 입력 검증
            if not Path(video_path).exists():
                return CoachingResult(
                    success=False,
                    error=f"입력 파일이 없습니다: {video_path}"
                )

            if not coaching_text or not coaching_text.strip():
                return CoachingResult(
                    success=False,
                    error="코칭 텍스트가 비어있습니다"
                )

            # 초기화
            self._ensure_initialized()

            # 출력 경로 설정
            if output_path is None:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                stem = Path(video_path).stem
                output_dir = Path(self.config.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = str(output_dir / f"{stem}_coaching_{timestamp}.mp4")

            # 처리 실행
            result_path = self._composer.compose(
                input_video=video_path,
                coaching_text=coaching_text,
                output_video=output_path
            )

            # 결과 정보 수집
            import subprocess
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                     result_path],
                    capture_output=True, text=True
                )
                duration = float(probe.stdout.strip())
            except:
                duration = 0.0

            return CoachingResult(
                success=True,
                video_path=result_path,
                video_duration=duration
            )

        except Exception as e:
            return CoachingResult(
                success=False,
                error=str(e)
            )


# ============================================================
# 편의 함수 (Convenience Functions)
# ============================================================

def quick_edit(
    video_path: str,
    duration: float = 10,
    style: str = "action"
) -> EditResult:
    """
    빠른 영상 편집 (기본 설정 사용)

    Args:
        video_path: 입력 영상
        duration: 목표 길이 (초)
        style: 편집 스타일

    Returns:
        EditResult
    """
    api = VideoEditorAPI()
    return api.process(video_path, duration, style)


def quick_coaching(
    video_path: str,
    coaching_text: str
) -> CoachingResult:
    """
    빠른 코칭 영상 생성 (기본 설정 사용)

    Args:
        video_path: 입력 영상
        coaching_text: 코칭 텍스트

    Returns:
        CoachingResult
    """
    api = CoachingAPI()
    return api.create(video_path, coaching_text)


# ============================================================
# 모듈 내보내기
# ============================================================

__all__ = [
    # 설정
    "VideoEditorConfig",
    "CoachingConfig",
    "EditStyle",
    "PhotoPreset",
    "ProcessingMode",

    # 결과
    "EditResult",
    "CoachingResult",

    # API 클래스
    "VideoEditorAPI",
    "CoachingAPI",

    # 편의 함수
    "quick_edit",
    "quick_coaching",
]
