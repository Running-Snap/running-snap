# RunningDiary - 백엔드 API 서버

러닝 영상 분석, 숏폼 생성, 베스트 컷 추출, AI 코칭 영상 생성을 제공하는 FastAPI 백엔드 서버입니다.

---

## 프로젝트 구조

```
run/
├── backend/                  ← 백엔드 (이 폴더)
│   ├── main.py               ← FastAPI 앱 + 전체 엔드포인트
│   ├── models.py             ← SQLAlchemy DB 모델
│   ├── schemas.py            ← Pydantic 요청/응답 스키마
│   ├── database.py           ← DB 연결 설정
│   ├── .env                  ← API 키 설정 (Git 비공개)
│   ├── .env.example          ← 환경변수 형식 예시
│   ├── requirements.txt      ← Python 패키지 목록
│   ├── venv/                 ← Python 가상환경
│   ├── videos/               ← 업로드된 원본 영상
│   ├── outputs/
│   │   ├── videos/           ← 숏폼 생성 결과 영상
│   │   ├── photos/           ← 베스트 컷 사진
│   │   ├── coaching/         ← 코칭 영상
│   │   └── pose/             ← 포즈 분석 중간 결과
│   └── pose_landmarker_heavy.task  ← MediaPipe 모델 파일 (별도 다운로드)
│
├── running_pose/             ← 포즈 분석 모듈 (MediaPipe + Gemini)
│   └── pose_analyzer.py
│
└── video-editor/             ← 영상 편집 모듈 (AI 기반)
    └── src/
```
