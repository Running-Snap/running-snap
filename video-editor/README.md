# AI Video Editor

러닝/운동 영상을 자동으로 Nike 스타일 숏폼으로 편집하는 AI 시스템

## 특징

- **자동 영상 분석**: Qwen2.5-VL이 프레임별로 역동성, 감정, 구도 분석
- **AI 편집 감독**: Claude가 Walter Murch 원칙에 따라 편집 대본 생성
- **다양한 스타일**: Nike, TikTok, Cinematic, Humor 등 선택 가능
- **베스트컷 추출**: 가장 미학적인 순간을 자동 선별 및 프로 보정

## 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 API 키 입력
```

## 사용법

```bash
# 기본 사용 (10초 Nike 스타일)
python main.py my_run.mp4 -d 10 -s nike

# 30초 TikTok 스타일, 베스트컷 3장
python main.py marathon.mp4 -d 30 -s tiktok -p 3

# 테스트 모드 (API 키 없이)
python main.py test.mp4 -d 10 --mock

# 스타일 목록 확인
python main.py --list-styles
```

## 출력

```
outputs/
├── videos/
│   └── my_run_nike_10s_20240101_120000.mp4
└── photos/
    ├── best_1_2.5s.jpg
    ├── best_2_5.1s.jpg
    └── ...
```

## 편집 스타일

| 스타일 | 설명 |
|--------|------|
| nike | 에픽하고 영감을 주는 스포츠 광고 스타일 |
| tiktok | 빠르고 바이럴 친화적인 숏폼 스타일 |
| humor | 유머러스한 밈 스타일 |
| cinematic | 영화같은 서정적 스타일 |
| documentary | 진정성 있는 다큐 스타일 |

## 구조

```
video-editor/
├── configs/          # YAML 설정 파일 (수정 용이)
├── src/
│   ├── analyzers/    # Qwen 영상 분석
│   ├── directors/    # Claude 대본 생성
│   ├── renderers/    # MoviePy 렌더링
│   ├── photographers/# 베스트컷 선별/보정
│   ├── core/         # 공통 유틸리티
│   └── pipeline.py   # 메인 오케스트레이터
└── main.py           # CLI 진입점
```

## 라이선스

MIT
