# 비디오 AI 파이프라인 - API 명세서

> **버전**: 1.0.0
> **최종 수정**: 2026-02-17
> **대상**: 백엔드 개발자

---

## 목차

1. [빠른 시작](#1-빠른-시작)
2. [통합 API 상세](#2-통합-api-상세)
3. [모듈별 상세 명세](#3-모듈별-상세-명세)
4. [데이터 타입 정의](#4-데이터-타입-정의)
5. [에러 처리](#5-에러-처리)
6. [실행 예시](#6-실행-예시)

---

## 1. 빠른 시작

### 1.1 가장 간단한 사용법

```python
from src.api import VideoEditorAPI, CoachingAPI

# 영상 편집 (10초 액션 스타일)
api = VideoEditorAPI()
result = api.process("input.mp4", duration=10, style="action")
print(result.video_path)  # outputs/videos/input_action_10s_xxx.mp4

# 코칭 영상 (TTS + 자막)
coaching = CoachingAPI()
result = coaching.create("input.mp4", "어깨 힘 빼세요. 팔은 옆으로.")
print(result.video_path)  # outputs/videos/input_coaching_xxx.mp4
```

### 1.2 설치 및 의존성

```bash
# Python 패키지
pip install -r requirements.txt

# 시스템 의존성
brew install ffmpeg  # macOS
# apt install ffmpeg  # Ubuntu

# 로컬 AI (선택, 권장)
# https://ollama.ai 에서 설치 후:
ollama pull qwen2.5vl:7b
```

---

## 2. 통합 API 상세

### 2.1 VideoEditorAPI

일반 영상 편집을 위한 메인 API.

#### 클래스 정의

```python
class VideoEditorAPI:
    def __init__(self, config: Optional[VideoEditorConfig] = None)
    def process(video_path, duration, style, photo_count, photo_preset, progress_callback) -> EditResult
    async def process_async(...) -> EditResult
    def get_available_styles() -> List[Dict]
    def clear_cache(video_path: Optional[str] = None)
```

#### process() 메서드

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `video_path` | `str` | ✅ | - | 입력 영상 파일 경로 |
| `duration` | `float` | ✅ | - | 목표 영상 길이 (초) |
| `style` | `str` | ❌ | `"action"` | 편집 스타일 |
| `photo_count` | `int` | ❌ | `5` | 베스트컷 사진 개수 (1-10) |
| `photo_preset` | `str` | ❌ | `"sports_action"` | 사진 보정 프리셋 |
| `progress_callback` | `Callable` | ❌ | `None` | 진행률 콜백 |

**반환값**: `EditResult`

```python
@dataclass
class EditResult:
    success: bool              # 성공 여부
    video_path: str           # 출력 영상 경로
    video_duration: float     # 영상 길이 (초)
    photos: List[str]         # 베스트컷 사진 경로들
    processing_time: float    # 처리 시간 (초)
    error: Optional[str]      # 에러 메시지 (실패 시)
    metadata: Dict            # 추가 정보
```

#### 스타일 옵션

| 스타일 | 설명 | 특징 |
|--------|------|------|
| `action` | 스포츠 액션샷 | 슬로우모션, 고대비, 결정적 순간 |
| `instagram` | 인스타그램 스타일 | 따뜻한 색감, 멋있어 보이게 |
| `tiktok` | 틱톡 바이럴 | 빠른 컷, 높은 채도, 트렌디 |
| `humor` | 밈/유머 | 코미디 타이밍, 웃긴 순간 |
| `documentary` | 다큐멘터리 | 자연스러운 흐름, 최소 편집 |

#### 사진 프리셋 옵션

| 프리셋 | 설명 |
|--------|------|
| `sports_action` | 고대비, 선명, 생동감 있는 |
| `golden_hour` | 황금빛 따뜻한 톤 |
| `dramatic` | 강한 대비, 드라마틱 |
| `clean_bright` | 깨끗하고 밝은 |

---

### 2.2 CoachingAPI

코칭 영상 생성 API (TTS + 자막).

#### 클래스 정의

```python
class CoachingAPI:
    def __init__(self, config: Optional[CoachingConfig] = None)
    def create(video_path, coaching_text, output_path) -> CoachingResult
```

#### create() 메서드

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `video_path` | `str` | ✅ | - | 입력 영상 파일 경로 |
| `coaching_text` | `str` | ✅ | - | 코칭 텍스트 (자세 분석 등) |
| `output_path` | `str` | ❌ | 자동 생성 | 출력 경로 |

**반환값**: `CoachingResult`

```python
@dataclass
class CoachingResult:
    success: bool              # 성공 여부
    video_path: str           # 출력 영상 경로
    video_duration: float     # 영상 길이 (초)
    tts_duration: float       # TTS 음성 길이 (초)
    subtitle_count: int       # 자막 개수
    error: Optional[str]      # 에러 메시지
```

---

### 2.3 설정 클래스

#### VideoEditorConfig

```python
@dataclass
class VideoEditorConfig:
    mode: ProcessingMode = ProcessingMode.LOCAL  # LOCAL, API, MOCK
    ollama_model: str = "qwen2.5vl:7b"
    cache_enabled: bool = True
    output_dir: str = "outputs"
    temp_dir: str = "temp"

    # API 모드에서만 필요
    qwen_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
```

#### CoachingConfig

```python
@dataclass
class CoachingConfig:
    tts_enabled: bool = True        # TTS 음성 사용
    subtitle_enabled: bool = True   # 자막 사용
    use_llm_script: bool = True     # LLM으로 대본 최적화
    llm_model: str = "qwen2.5vl:7b"
    output_dir: str = "outputs/videos"
```

---

## 3. 모듈별 상세 명세

### 3.1 pipeline.py - 메인 파이프라인

```
경로: src/pipeline.py
역할: 전체 처리 흐름 조율 (Step 1-5)
```

#### VideoPipeline 클래스

```python
class VideoPipeline:
    """
    메인 비디오 편집 파이프라인

    처리 흐름:
    Step 1: 영상 분석 (VideoAnalyzer)
    Step 2: 편집 대본 생성 (ScriptGenerator)
    Step 3: 영상 렌더링 (VideoRenderer)
    Step 4: 베스트컷 선별 (FrameSelector)
    Step 5: 사진 보정 (PhotoEnhancer)
    """

    def __init__(
        self,
        qwen_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
        config_dir: str = "configs",
        use_mock: bool = False,
        use_local: bool = False,
        ollama_model: str = "qwen2.5vl:7b",
        use_cache: bool = True
    ):
        """
        Args:
            qwen_api_key: Qwen API 키 (분석용, 로컬 모드에선 불필요)
            claude_api_key: Claude API 키 (대본용, 로컬 모드에선 불필요)
            config_dir: 설정 YAML 파일 디렉토리
            use_mock: 테스트 모드 (더미 데이터)
            use_local: 로컬 AI 사용 (Ollama + Claude CLI)
            ollama_model: Ollama 비전 모델명
            use_cache: 분석 결과/대본 캐시 사용
        """

    async def process(
        self,
        input_video: str,
        target_duration: float,
        style: str = "action",
        output_dir: str = "outputs",
        photo_count: int = 5,
        photo_preset: str = "sports_action"
    ) -> ProcessingResult:
        """
        비동기 처리 파이프라인

        Returns:
            ProcessingResult: 처리 결과 (영상 경로, 사진 경로 등)
        """

    def process_sync(...) -> ProcessingResult:
        """동기 버전 (내부적으로 asyncio.run 호출)"""
```

**내부 처리 흐름:**

```
process() 호출
    │
    ├─► Step 1: self.video_analyzer.analyze()
    │   └─► VideoAnalysis 반환 (캐시 저장)
    │
    ├─► Step 2: self.script_generator.generate()
    │   └─► EditScript 반환 (캐시 저장)
    │
    ├─► Step 3: self.renderer.render()
    │   └─► 영상 파일 생성
    │
    ├─► Step 4: self.frame_selector.select_best_frames()
    │   └─► 베스트컷 프레임 추출
    │
    └─► Step 5: self.photo_enhancer.enhance_and_save()
        └─► 보정된 사진 저장

    → ProcessingResult 반환
```

---

### 3.2 analyzers/ - 영상 분석 모듈

```
경로: src/analyzers/
역할: 영상 프레임을 AI로 분석하여 내용 파악
```

#### VideoAnalyzer

```python
class VideoAnalyzer:
    """
    영상 분석 오케스트레이터

    역할:
    - 영상 메타데이터 추출 (길이, FPS, 해상도)
    - 프레임 샘플링 (2초마다 1장)
    - FrameAnalyzer로 각 프레임 분석
    - 하이라이트 구간 식별
    """

    async def analyze(
        self,
        video_path: str,
        target_duration: float,
        max_concurrent: int = 5,
        show_progress: bool = True,
        max_frames: int = 0
    ) -> VideoAnalysis:
        """
        Args:
            video_path: 입력 영상 경로
            target_duration: 목표 출력 길이
            max_concurrent: 동시 분석 프레임 수
            show_progress: 진행률 표시
            max_frames: 최대 분석 프레임 (0=무제한)

        Returns:
            VideoAnalysis: 분석 결과
        """
```

#### FrameAnalyzer (3가지 구현)

| 클래스 | 용도 | 특징 |
|--------|------|------|
| `OllamaFrameAnalyzer` | 로컬 AI | 무료, GPU 권장, 느림 |
| `FrameAnalyzer` | Qwen API | 유료, 빠름 |
| `MockFrameAnalyzer` | 테스트 | 더미 데이터 |

```python
class OllamaFrameAnalyzer:
    """
    Ollama 로컬 AI로 프레임 분석

    사용 모델: qwen2.5vl:7b (비전 모델)
    """

    async def analyze_frame(
        self,
        frame_path: str,
        timestamp: float
    ) -> FrameAnalysis:
        """
        단일 프레임 분석

        Args:
            frame_path: 프레임 이미지 경로
            timestamp: 영상에서의 시간 (초)

        Returns:
            FrameAnalysis: 프레임 분석 결과
        """
```

---

### 3.3 directors/ - 편집 대본 생성 모듈

```
경로: src/directors/
역할: 분석 결과를 바탕으로 편집 계획 생성
```

#### ScriptGenerator (3가지 구현)

| 클래스 | 용도 | 특징 |
|--------|------|------|
| `ClaudeCodeScriptGenerator` | 로컬 | Claude CLI 사용, 무료 |
| `ScriptGenerator` | Claude API | 유료, 빠름 |
| `MockScriptGenerator` | 테스트 | 더미 데이터 |

```python
class ClaudeCodeScriptGenerator:
    """
    Claude Code CLI로 편집 대본 생성

    스타일별 프롬프트가 configs/script_prompts.yaml에 정의됨
    """

    async def generate(
        self,
        video_analysis: VideoAnalysis,
        target_duration: float,
        style: str = "action"
    ) -> EditScript:
        """
        편집 대본 생성

        Args:
            video_analysis: 영상 분석 결과
            target_duration: 목표 영상 길이 (초)
            style: 편집 스타일

        Returns:
            EditScript: 편집 대본 (세그먼트 리스트 포함)
        """
```

---

### 3.4 renderers/ - 영상 렌더링 모듈

```
경로: src/renderers/
역할: 편집 대본에 따라 실제 영상 렌더링
```

#### VideoRenderer

```python
class VideoRenderer:
    """
    비디오 렌더러

    기능:
    - 원본에서 세그먼트 추출
    - 속도 조절 (슬로우모션/타임랩스)
    - 색상 그레이딩
    - 스마트 리프레임 (피사체 추적)
    - 전환 효과
    """

    def render(
        self,
        video_path: str,
        script: EditScript,
        output_path: str,
        show_progress: bool = True
    ) -> str:
        """
        영상 렌더링

        Args:
            video_path: 원본 영상 경로
            script: 편집 대본
            output_path: 출력 경로
            show_progress: 진행률 표시

        Returns:
            str: 출력 영상 경로
        """
```

#### 이펙트 모듈 (effects/)

| 파일 | 클래스 | 기능 |
|------|--------|------|
| `color_grade.py` | `ColorGrader` | 색상 조정 (밝기, 대비, 채도) |
| `speed_ramp.py` | `SpeedRamper` | 속도 변경 |
| `reframe.py` | `SmartReframer` | 피사체 추적 + 자동 줌/팬 |
| `transitions.py` | `TransitionApplier` | 전환 효과 |

```python
class SmartReframer:
    """
    스마트 리프레임

    MediaPipe로 피사체(사람) 추적하여
    세로형(9:16) 영상에서 항상 피사체가 중심에 오도록 자동 크롭
    """

    def process_clip(
        self,
        clip: VideoClip,
        output_config: OutputConfig
    ) -> VideoClip:
        """
        클립 리프레임

        Args:
            clip: 원본 클립 (MoviePy VideoClip)
            output_config: 출력 설정 (비율, 해상도)

        Returns:
            리프레임된 클립
        """
```

---

### 3.5 photographers/ - 베스트컷 선별/보정 모듈

```
경로: src/photographers/
역할: 가장 잘 나온 프레임 선별 + 사진 보정
```

#### FrameSelector

```python
class FrameSelector:
    """
    베스트컷 프레임 선별기

    점수 계산:
    - aesthetic_score * 0.30 (미적 점수)
    - composition_score * 0.25 (구도)
    - emotional_impact * 0.25 (감정)
    - technical_quality * 0.20 (기술적 품질)
    """

    def select_best_frames(
        self,
        video_path: str,
        analysis: VideoAnalysis,
        count: int = 5,
        output_dir: str = "temp/frames",
        style: str = "action",
        apply_composition: bool = True
    ) -> List[PhotoCandidate]:
        """
        베스트컷 선별

        Args:
            video_path: 원본 영상 경로
            analysis: 영상 분석 결과
            count: 선별할 사진 개수
            output_dir: 프레임 저장 디렉토리
            style: 적용할 구도 스타일
            apply_composition: 구도 자동 조정

        Returns:
            PhotoCandidate 리스트
        """
```

#### PhotoEnhancer

```python
class PhotoEnhancer:
    """
    사진 보정기

    보정 항목:
    - 노이즈 제거
    - 색온도 조정
    - 대비/채도 조정
    - 샤프닝
    - 비네팅
    """

    def enhance_and_save(
        self,
        input_path: str,
        output_path: str,
        preset: str = "sports_action"
    ) -> str:
        """
        보정 후 저장

        Args:
            input_path: 입력 이미지 경로
            output_path: 출력 경로
            preset: 보정 프리셋

        Returns:
            저장된 파일 경로
        """
```

---

### 3.6 coaching/ - 코칭 영상 모듈

```
경로: src/coaching/
역할: 자세 분석 텍스트 → TTS + 자막 코칭 영상
```

#### CoachingComposer (메인)

```python
class CoachingComposer:
    """
    코칭 영상 합성기

    파이프라인:
    1. LLM으로 영상 길이에 맞는 대본 생성
    2. 대본을 TTS로 변환
    3. TTS 길이에 맞춰 영상 편집 (필요시 슬로우모션)
    4. 자막 렌더링
    5. 오디오 합성
    """

    def __init__(
        self,
        tts_enabled: bool = True,
        subtitle_enabled: bool = True,
        use_llm_script: bool = True,
        llm_model: str = "qwen2.5vl:7b",
        console: Optional[Console] = None
    ):
        """
        Args:
            tts_enabled: TTS 음성 사용
            subtitle_enabled: 자막 사용
            use_llm_script: LLM으로 대본 최적화
            llm_model: LLM 모델명
        """

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
        코칭 영상 생성

        Args:
            input_video: 원본 영상 경로
            coaching_text: 코칭 텍스트
            output_video: 출력 경로 (None이면 자동)
            video_start_time: 자막 시작 시간
            subtitle_gap: 자막 간 간격 (초)
            duration_tolerance: TTS-영상 길이 허용 오차

        Returns:
            출력 영상 경로
        """
```

#### CoachingScriptWriter

```python
class CoachingScriptWriter:
    """
    LLM 코칭 대본 생성기

    역할:
    - 자세 분석 텍스트를 TTS용 대본으로 변환
    - 영상 길이에 맞게 문장 수 조절
    - 중요도(priority) 기반 문장 선택
    """

    def generate_script(
        self,
        analysis_text: str,
        video_duration: float,
        tolerance: float = 2.0
    ) -> CoachingScript:
        """
        대본 생성

        Args:
            analysis_text: 자세 분석 텍스트
            video_duration: 영상 길이 (초)
            tolerance: 허용 오차 (초)

        Returns:
            CoachingScript: 생성된 대본
        """
```

#### TTSEngine

```python
class TTSEngine:
    """
    TTS 음성 생성 엔진

    지원 엔진:
    - gTTS (Google TTS) - 기본, 온라인
    - pyttsx3 - 오프라인 폴백
    """

    def generate(self, text: str) -> TTSResult:
        """
        단일 문장 TTS 생성

        Returns:
            TTSResult: 음성 파일 경로 + 길이
        """

    def generate_batch(self, texts: List[str]) -> List[TTSResult]:
        """여러 문장 일괄 생성"""
```

#### SubtitleGenerator & SubtitleRenderer

```python
class SubtitleGenerator:
    """자막 세그먼트 생성 (타이밍 계산)"""

    def create_segments(
        self,
        texts: List[str],
        tts_durations: List[float],
        gap: float = 0.5
    ) -> List[SubtitleSegment]:
        """TTS 길이에 맞춘 자막 세그먼트 생성"""


class SubtitleRenderer:
    """자막을 영상에 렌더링 (PIL 사용, 한글 지원)"""

    def render_video_with_subtitles(
        self,
        input_video: str,
        output_video: str,
        segments: List[SubtitleSegment]
    ) -> str:
        """자막이 입혀진 영상 생성"""
```

#### CoachingVideoEditor

```python
class CoachingVideoEditor:
    """
    코칭용 영상 편집기

    역할:
    - TTS 총 길이에 맞춰 영상 길이 조절
    - 슬로우모션 적용 (영상 < TTS일 때)
    - 배속은 하지 않음 (영상 >= TTS)
    """

    def edit_video_for_tts(
        self,
        input_video: str,
        output_video: str,
        tts_total_duration: float,
        subtitle_segments: List[SubtitleSegment]
    ) -> str:
        """TTS 길이에 맞춰 영상 편집"""
```

---

### 3.7 core/ - 공통 유틸리티

```
경로: src/core/
역할: 설정 로드, 데이터 모델, 캐시 등
```

#### ConfigLoader

```python
class ConfigLoader:
    """YAML 설정 파일 로더"""

    def get_style(self, style_name: str) -> Dict
    def get_analysis_profile(self, duration_type: str) -> Dict
    def get_output_spec(self, platform: str) -> Dict
    def get_available_styles(self) -> List[str]
```

#### AnalysisCache

```python
class AnalysisCache:
    """분석 결과 및 대본 캐시"""

    def save_analysis(self, video_path: str, analysis: VideoAnalysis)
    def load_analysis(self, video_path: str) -> Optional[VideoAnalysis]
    def save_script(self, video_path: str, style: str, duration: float, script: EditScript, prompt: str)
    def load_script(self, video_path: str, style: str, duration: float) -> Optional[EditScript]
    def clear_cache(self, video_path: str)
    def clear_all(self)
```

---

## 4. 데이터 타입 정의

### 4.1 입력 타입

```python
# 영상 편집 요청
class EditRequest:
    video_path: str          # 필수: 입력 영상 경로
    duration: float          # 필수: 목표 길이 (초)
    style: str = "action"    # 선택: 편집 스타일
    photo_count: int = 5     # 선택: 베스트컷 개수
    photo_preset: str = "sports_action"

# 코칭 요청
class CoachingRequest:
    video_path: str          # 필수: 입력 영상 경로
    coaching_text: str       # 필수: 코칭 텍스트
    output_path: str = None  # 선택: 출력 경로
```

### 4.2 출력 타입

```python
# 영상 분석 결과
class VideoAnalysis:
    source_path: str
    duration: float
    fps: float
    resolution: Tuple[int, int]
    duration_type: DurationType  # SHORT/MEDIUM/LONG
    frames: List[FrameAnalysis]  # 프레임별 분석
    highlights: List[float]      # 하이라이트 타임스탬프
    overall_motion: str          # "low"/"medium"/"high"
    summary: str

# 프레임 분석 결과
class FrameAnalysis:
    timestamp: float
    faces_detected: int
    face_expressions: List[str]
    motion_level: float          # 0.0 ~ 1.0
    composition_score: float     # 0.0 ~ 1.0
    lighting: str                # "good"/"moderate"/"poor"
    is_action_peak: bool
    aesthetic_score: float       # 0.0 ~ 1.0
    emotional_tone: str
    description: str

# 편집 대본
class EditScript:
    segments: List[EditSegment]
    color_grade: str
    audio_config: Dict
    total_duration: float
    style_applied: str

# 편집 세그먼트
class EditSegment:
    start_time: float        # 출력에서의 시작
    end_time: float          # 출력에서의 끝
    source_start: float      # 원본에서 가져올 시작
    source_end: float        # 원본에서 가져올 끝
    speed: float             # 1.0 = 원본, 0.5 = 슬로모
    effects: List[str]
    transition_in: str
    transition_out: str
    purpose: str             # "hook"/"build"/"climax" 등

# 최종 결과
class ProcessingResult:
    video_path: str
    video_duration: float
    photos: List[str]
    style_used: str
    processing_time: float
    metadata: Dict
```

---

## 5. 에러 처리

### 5.1 예외 클래스

```python
from src.core.exceptions import (
    VideoEditorError,      # 기본 예외
    ConfigurationError,    # 설정 오류
    AnalysisError,         # 분석 실패
    RenderingError,        # 렌더링 실패
    FileNotFoundError,     # 파일 없음
)
```

### 5.2 에러 핸들링 패턴

```python
from src.api import VideoEditorAPI, EditResult

api = VideoEditorAPI()
result: EditResult = api.process("video.mp4", duration=10)

if result.success:
    print(f"성공: {result.video_path}")
else:
    print(f"실패: {result.error}")
    # 에러 타입에 따른 처리
    if "파일" in result.error:
        # 파일 관련 에러
        pass
    elif "API" in result.error:
        # API 관련 에러
        pass
```

### 5.3 공통 에러 메시지

| 에러 | 원인 | 해결 |
|------|------|------|
| `입력 파일이 없습니다` | 경로 오류 | 파일 경로 확인 |
| `지원하지 않는 스타일` | 잘못된 스타일명 | `get_available_styles()` 확인 |
| `Ollama 연결 실패` | Ollama 미실행 | `ollama serve` 실행 |
| `ffmpeg 없음` | ffmpeg 미설치 | ffmpeg 설치 |
| `메모리 부족` | 영상이 너무 큼 | 해상도 낮추기 |

---

## 6. 실행 예시

### 6.1 백엔드 통합 예시 (FastAPI)

```python
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from src.api import VideoEditorAPI, CoachingAPI, VideoEditorConfig, ProcessingMode

app = FastAPI()

# API 초기화 (앱 시작 시 1번)
config = VideoEditorConfig(mode=ProcessingMode.LOCAL)
video_api = VideoEditorAPI(config)
coaching_api = CoachingAPI()


class EditRequest(BaseModel):
    video_path: str
    duration: float
    style: str = "action"
    photo_count: int = 5


class CoachingRequest(BaseModel):
    video_path: str
    coaching_text: str


@app.post("/api/edit")
async def edit_video(request: EditRequest, background_tasks: BackgroundTasks):
    """영상 편집 (비동기)"""
    result = await video_api.process_async(
        video_path=request.video_path,
        duration=request.duration,
        style=request.style,
        photo_count=request.photo_count
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result.to_dict()


@app.post("/api/coaching")
def create_coaching(request: CoachingRequest):
    """코칭 영상 생성"""
    result = coaching_api.create(
        video_path=request.video_path,
        coaching_text=request.coaching_text
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result.to_dict()


@app.get("/api/styles")
def get_styles():
    """사용 가능한 스타일 목록"""
    return video_api.get_available_styles()
```

### 6.2 CLI 사용 예시

```bash
# 기본 편집
python main.py video.mp4 -d 10 -s action --local

# 코칭 영상
python main.py video.mp4 -s coaching --coaching-text "어깨 힘 빼세요."

# 테스트 모드
python main.py video.mp4 -d 10 -s tiktok --mock
```

### 6.3 Python 스크립트 사용

```python
# 간단한 사용
from src.api import quick_edit, quick_coaching

# 영상 편집
result = quick_edit("video.mp4", duration=10, style="action")
print(result.video_path)

# 코칭 영상
result = quick_coaching("video.mp4", "어깨 힘 빼세요.")
print(result.video_path)
```

---

## 부록: 파일 구조

```
video-editor/
├── main.py                    # CLI 진입점
├── requirements.txt           # Python 의존성
├── API_SPEC.md               # 이 문서
├── HANDOVER.md               # 인수인계 문서
│
├── src/
│   ├── api.py                # ⭐ 통합 API (이것만 import)
│   ├── pipeline.py           # 메인 파이프라인
│   │
│   ├── core/                 # 공통 유틸리티
│   │   ├── config_loader.py
│   │   ├── models.py        # 데이터 모델
│   │   ├── exceptions.py    # 예외 클래스
│   │   └── analysis_cache.py
│   │
│   ├── analyzers/            # 영상 분석
│   │   ├── video_analyzer.py
│   │   └── frame_analyzer.py
│   │
│   ├── directors/            # 대본 생성
│   │   ├── prompt_builder.py
│   │   └── script_generator.py
│   │
│   ├── renderers/            # 영상 렌더링
│   │   ├── video_renderer.py
│   │   └── effects/
│   │       ├── color_grade.py
│   │       ├── speed_ramp.py
│   │       ├── reframe.py
│   │       └── transitions.py
│   │
│   ├── photographers/        # 베스트컷
│   │   ├── frame_selector.py
│   │   ├── composition_analyzer.py
│   │   └── photo_enhancer.py
│   │
│   └── coaching/             # 코칭 영상
│       ├── coaching_composer.py
│       ├── script_writer.py
│       ├── tts_engine.py
│       ├── subtitle_generator.py
│       └── video_editor.py
│
├── configs/                  # YAML 설정
│   ├── script_prompts.yaml
│   ├── analysis_profiles.yaml
│   ├── output_specs.yaml
│   └── photo_grading.yaml
│
└── outputs/                  # 출력
    ├── videos/
    ├── photos/
    └── cache/
```

---

**끝.**
