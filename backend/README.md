# RunningDiary - 백엔드 API 서버

러닝 영상 분석, 숏폼 생성, 베스트 컷 추출, AI 코칭 영상 생성을 제공하는 FastAPI 백엔드 서버입니다.

---

## 프로젝트 구조

```
run/
├── testrun/                  ← 백엔드 (이 폴더)
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
├── running_pose 2/           ← 포즈 분석 모듈 (MediaPipe + Gemini)
│   └── pose_analyzer.py
│
└── video-editor/             ← 영상 편집 모듈 (AI 기반)
    └── src/
```

---

## 사전 요구사항

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) (코칭 영상 H.264 인코딩에 사용)
- [Ollama](https://ollama.com/) + `qwen2.5vl:7b` 모델 (로컬 영상 분석 사용 시)
- MediaPipe 포즈 모델 파일: `pose_landmarker_heavy.task`

### ffmpeg 설치 (macOS)
```bash
brew install ffmpeg
```

### Ollama 설치 및 모델 다운로드
```bash
brew install ollama
ollama pull qwen2.5vl:7b
ollama serve  # 백그라운드 실행
```

---

## 설치 및 실행

### 1. 가상환경 생성 및 패키지 설치
```bash
cd testrun
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 2. 환경변수 설정
```bash
cp .env.example .env
# .env 파일을 열어서 API 키 입력
```

`.env` 파일 내용:
```
GEMINI_API_KEY=여기에_Gemini_API_키_입력
ANTHROPIC_API_KEY=여기에_Anthropic_API_키_입력
POSE_MODEL_PATH=./pose_landmarker_heavy.task
SECRET_KEY=랜덤_시크릿_키_입력
```

> **시크릿 키 생성 방법**: `python -c "import secrets; print(secrets.token_hex(32))"`

### 3. 서버 실행
```bash
cd testrun
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. API 문서 확인
```
http://localhost:8000/docs      ← Swagger UI
http://localhost:8000/redoc     ← ReDoc
```

---

## 환경변수 상세

| 변수명 | 설명 | 필수 여부 |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API 키 (포즈 분석 리포트 생성) | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API 키 (숏폼 스크립트 생성) | 선택 |
| `POSE_MODEL_PATH` | MediaPipe 포즈 모델 파일 경로 | 권장 |
| `SECRET_KEY` | JWT 토큰 서명 시크릿 키 | **필수** |

> API 키 미설정 시 자동 폴백:
> - `ANTHROPIC_API_KEY` 없음 → Ollama 로컬 모드 → Mock 모드 순으로 전환
> - `GEMINI_API_KEY` 없음 → 기본 피드백 텍스트 사용

---

## 영상 편집 모드

서버 시작 시 아래 우선순위로 모드를 자동 선택합니다:

| 우선순위 | 모드 | 조건 | 동작 |
|---|---|---|---|
| 1 | **API** | `ANTHROPIC_API_KEY` 설정됨 | Claude AI로 편집 스크립트 생성 |
| 2 | **LOCAL** | Ollama 실행 중 (`qwen2.5vl:7b`) | 로컬 AI로 프레임 분석 |
| 3 | **MOCK** | 위 조건 모두 해당 없음 | 원본 영상 복사 (테스트용) |

현재 모드 확인:
```bash
curl http://localhost:8000/
# "video_editor_mode": "api" | "local" | "mock"
```

---

## API 엔드포인트

### 인증
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/auth/register` | 회원가입 |
| `POST` | `/auth/login-json` | 로그인 (JSON) → JWT 토큰 반환 |
| `POST` | `/auth/login` | 로그인 (Form) |
| `GET` | `/auth/me` | 내 정보 조회 |

### 영상 업로드
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/upload-video/` | 영상 업로드 |
| `GET` | `/my-videos/` | 내 업로드 영상 목록 |
| `GET` | `/videos/{filename}` | 영상 파일 직접 접근 |

### 포즈 분석
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/analysis-jobs/` | 분석 작업 생성 (백그라운드 실행) |
| `GET` | `/analysis-jobs/` | 내 분석 기록 목록 |
| `GET` | `/analysis-jobs/{job_id}` | 특정 분석 결과 조회 |

### 숏폼 생성
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/shortform-jobs/` | 숏폼 생성 작업 (백그라운드 실행) |
| `GET` | `/shortform-jobs/` | 내 숏폼 목록 |
| `GET` | `/shortform-jobs/{job_id}` | 특정 숏폼 결과 조회 |

숏폼 스타일: `action` / `instagram` / `tiktok` / `humor` / `documentary`

### 베스트 컷
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/bestcut-jobs/` | 베스트 컷 추출 작업 |
| `GET` | `/bestcut-jobs/` | 내 베스트 컷 목록 |
| `GET` | `/bestcut-jobs/{job_id}` | 특정 베스트 컷 결과 조회 |

### 코칭 영상
| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/coaching-jobs/` | 코칭 영상 생성 작업 |
| `GET` | `/coaching-jobs/` | 내 코칭 영상 목록 |
| `GET` | `/coaching-jobs/{job_id}` | 특정 코칭 영상 결과 조회 |

### 정적 파일
| 경로 | 설명 |
|---|---|
| `/outputs/videos/{filename}` | 숏폼 영상 |
| `/outputs/photos/{filename}` | 베스트 컷 사진 |
| `/outputs/coaching/{filename}` | 코칭 영상 |

---

## 작업 흐름 (폴링 방식)

모든 영상 처리 작업은 백그라운드에서 실행됩니다. 완료 여부는 폴링으로 확인합니다.

```
POST /analysis-jobs/  →  { id: 1, status: "pending" }
          ↓
GET  /analysis-jobs/1  →  { status: "processing" }  (처리 중)
          ↓
GET  /analysis-jobs/1  →  { status: "done", result_json: {...} }  (완료)
```

작업 상태: `pending` → `processing` → `done` / `failed`

---

## 데이터 초기화

### DB + 파일 전체 삭제
```bash
rm -f running_app.db
rm -f videos/* outputs/videos/* outputs/coaching/* outputs/photos/* outputs/pose/*
```

### DB 테이블만 초기화 (파일 유지)
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('running_app.db')
cur = conn.cursor()
tables = ['coaching_jobs', 'shortform_jobs', 'bestcut_jobs', 'analysis_jobs', 'videos', 'users']
for t in tables:
    cur.execute(f'DELETE FROM {t}')
    cur.execute(f'DELETE FROM sqlite_sequence WHERE name=\"{t}\"')
conn.commit()
conn.close()
print('DB 초기화 완료')
"
```

---

## 외부 모듈 연동 방식

이 백엔드는 두 개의 외부 모듈을 `sys.path`로 직접 임포트합니다 (모듈 내 별도 서버 없음):

| 모듈 | 경로 | 역할 |
|---|---|---|
| `running_pose 2` | `../running_pose 2/pose_analyzer.py` | MediaPipe + Gemini 포즈 분석 |
| `video-editor` | `../video-editor/src/` | AI 기반 영상 편집 |

> 각 모듈이 없거나 import 실패 시 자동으로 폴백 동작합니다.

---

## 주의사항

- `.env` 파일은 절대 Git에 커밋하지 않습니다
- `pose_landmarker_heavy.task` 파일은 용량이 크므로 별도 공유합니다 ([다운로드](https://developers.google.com/mediapipe/solutions/vision/pose_landmarker))
- `venv/` 폴더는 `.gitignore`에 포함해야 합니다
- 코칭 영상 생성 시 ffmpeg가 반드시 설치되어 있어야 H.264 인코딩이 가능합니다
