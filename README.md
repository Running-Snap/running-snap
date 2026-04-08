# Running Video Editor

러닝 영상 한 편으로 **포스터 · 인증영상 · 자세분석 영상** 3종을 자동 생성하는 파이프라인.

---

## 주요 기능

| 출력물 | 형식 | 설명 |
|--------|------|------|
| 베스트컷 포스터 | JPG | MediaPipe로 러너가 중앙에 있는 최적 프레임 선택 + 이벤트 정보 합성 |
| 인증영상 (full) | MP4 9:16 | intro → buildup → slowmo 0.35x → 기록 그래픽 |
| 인증영상 (simple) | MP4 9:16 | 슬로우모 없이 원본 1x 재생 + 후반부 기록 그래픽 |
| 자세분석 영상 | MP4 9:16 | skeleton overlay + 피드백 카드 (feedback_data 제공 시) |

기록 그래픽은 **Nike Run Club** 스타일 3×2 그리드:
```
[ AVG PACE ]  [   TIME   ]  [ CALORIES ]
[ ELEVATION]  [  AVG HR  ]  [  CADENCE ]
```

---

## 프로젝트 구조

```
video-editor/
├── make_blossom_outputs.py      # ★ 메인 실행 스크립트 (포스터 + full 인증 + 자세분석)
├── make_blossom_simple.py       # ★ 단순 인증영상 (슬로우모 없음, 단편 버전)
├── make_blossom_photo_poster.py # 사진 1장으로 포스터만 생성
│
├── src/
│   ├── cert_builder.py          # ★ 인증영상 Instruction 빌더 (CertBuilder)
│   ├── running_pipeline.py      # ★ 통합 파이프라인 (RunningPipeline)
│   ├── template_executor.py     # ★ Instruction → 실제 영상 렌더러
│   ├── preprocessor.py          # 입력 영상 정규화 (rotation fix + loop)
│   ├── poster_maker.py          # 포스터 이미지 생성 (PIL)
│   ├── instruction_builder.py   # 자세분석 영상 Instruction 빌더
│   ├── pose_skeleton_renderer.py# 스켈레톤 오버레이 렌더러
│   └── style_presets.py         # 색조 / 속도 / 효과 프리셋
│
├── examples/        # 이벤트별 실행 예시 스크립트 (참고용)
├── configs/         # YAML 설정 파일 (LLM 프롬프트, 분석 프로파일)
├── templates/       # JSON 편집 템플릿
├── models/          # ML 모델 파일 (.gitignore — 별도 다운로드)
└── outputs/         # 생성 결과물 (.gitignore)
```

---

## 빠른 시작

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 메인 실행 (포스터 + 인증영상 + 자세분석)

`make_blossom_outputs.py` 상단의 `SRC`와 `EVENT_CONFIG`를 수정하고 실행:
```bash
python make_blossom_outputs.py
```

### 3. 슬로우모 없는 단편 인증영상 (3초 버전)
```bash
python make_blossom_simple.py
# 또는 경로 직접 지정
python make_blossom_simple.py /path/to/video.mp4
```

### 4. 사진으로 포스터만 생성
```bash
python make_blossom_photo_poster.py /path/to/photo.jpg
```

---

## 설정 가이드

### 이벤트 설정 (`EVENT_CONFIG`)

> **수정 위치**: `make_blossom_outputs.py` 또는 `make_blossom_simple.py` 상단

```python
EVENT_CONFIG = {
    # 포스터 + 인증영상 상단 타이틀
    "title":          "BLOSSOM\nRUNNING",   # \n 줄바꿈 지원

    # 포스터 전용
    "location":       "Chungnam National Univ.",
    "sublocation":    "N9-2",
    "time":           "P.M. 03:00",
    "branding":       "BLOSSOM RUN  /  CNU N9-2  /  2026.04.03",

    # 인증영상 기록 그래픽 (6개 항목)
    "date":           "2026.04.03",
    "distance_km":    5.2,           # float
    "pace":           "6'35\"/km",
    "run_time":       "34'18\"",
    "calories":       "312 kcal",
    "elevation_gain": "48 m",
    "avg_heart_rate": "152 bpm",
    "cadence":        "163 spm",

    # 색조 테마
    "color_scheme":   "warm",        # warm / cool / neutral
}
```

### 자세분석 피드백 설정 (`FEEDBACK_DATA`)

> **수정 위치**: `make_blossom_outputs.py` 상단
> `FEEDBACK_DATA = None` 으로 설정하면 자세분석 영상 건너뜀

```python
FEEDBACK_DATA = {
    "score": 60,                    # 종합 점수 (0~100)
    "feedbacks": [
        {
            "title":   "팔꿈치 각도",
            "message": "팔꿈치를 약 90도로 유지하세요.",
            "status":  "warning",   # good / warning / bad
        },
    ],
    "pose_stats": {
        "cadence":       158,
        "elbow_angle":   110,
        "avg_impact_z":  "보통",
        "asymmetry":     12,
        "v_oscillation": 68,
    },
}
```

---

## API 키 설정 (선택)

Qwen VLM으로 영상에서 러너가 잘 보이는 구간을 자동 탐지.
키 없이도 동작하지만, 있으면 더 정확한 하이라이트 선택.

```bash
export DASHSCOPE_API_KEY="sk-..."
python make_blossom_outputs.py
```

---

## 핵심 모듈 API

### `CertBuilder` — 인증영상 Instruction 생성
```python
from src.cert_builder import CertBuilder

# 슬로우모 포함 일반 버전
instruction = CertBuilder.build_full(info, event_config, highlights)

# 슬로우모 없는 단편 버전
instruction = CertBuilder.build_simple(orig_duration_sec, event_config)
```

### `RunningPipeline` — 통합 파이프라인
```python
from src.running_pipeline import RunningPipeline

result = RunningPipeline(qwen_api_key="sk-...").run(
    video_path   = "/path/to/video.mp4",
    event_config = EVENT_CONFIG,
    feedback_data= FEEDBACK_DATA,   # None이면 자세분석 생략
    output_dir   = "outputs/blossom",
    name_prefix  = "blossom",
)
print(result.poster_path)   # → JPG 경로
print(result.cert_path)     # → MP4 인증영상 경로
print(result.pose_path)     # → MP4 자세분석 경로 (없으면 "")
```

### `TemplateExecutor` — 단독 렌더링
```python
from src.template_executor import TemplateExecutor
from src.cert_builder import CertBuilder

instruction = CertBuilder.build_simple(3.33, event_config)
TemplateExecutor(verbose=True).execute(instruction, "input.mp4", "output.mp4")
```

---

## 의존성

| 패키지 | 용도 | 필수 |
|--------|------|------|
| moviepy | 영상 편집 / 속도 조절 | ✅ |
| opencv-python | 프레임 추출 / 색상 처리 | ✅ |
| pillow | 포스터 · 텍스트 오버레이 | ✅ |
| numpy | 배열 처리 | ✅ |
| mediapipe | 베스트컷 프레임 선택 | 선택 |
| aiohttp | Qwen VLM API 통신 | 선택 |

```bash
pip install -r requirements.txt
```

---

## 라이선스

MIT
