import os
import sys
import json
import shutil
import random
import threading
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

# ────────────────────────────────────────────────────────────
# 기본 디렉토리 (절대 경로)
# ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# running_pose 2 모듈 경로 추가
RUNNING_POSE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "running_pose 2")
)
sys.path.insert(0, RUNNING_POSE_PATH)

try:
    import pose_analyzer
    POSE_ANALYZER_AVAILABLE = True
except ImportError:
    POSE_ANALYZER_AVAILABLE = False

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
POSE_MODEL_PATH = os.getenv(
    "POSE_MODEL_PATH",
    os.path.join(BASE_DIR, "pose_landmarker_heavy.task")
)
POSE_OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs", "pose")
os.makedirs(POSE_OUTPUT_FOLDER, exist_ok=True)

# video-editor 모듈 경로 추가
VIDEO_EDITOR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "video-editor")
)
sys.path.insert(0, VIDEO_EDITOR_PATH)

try:
    from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode, CoachingAPI, CoachingConfig
    VIDEO_EDITOR_AVAILABLE = True
except ImportError:
    VIDEO_EDITOR_AVAILABLE = False

# video-editor API 키
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# video-editor os.chdir 보호용 락 (CWD 레이스 컨디션 방지)
VIDEO_EDITOR_LOCK = threading.Lock()

from pydantic import BaseModel
from fastapi import FastAPI, Depends, File, Form, UploadFile, HTTPException, status, BackgroundTasks, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from jose import JWTError, jwt
from passlib.context import CryptContext

from database import get_db, engine, SessionLocal
from models import Base, User, Video, AnalysisJob, ShortformJob, BestCutJob, CoachingJob, UserLocation, CameraClip, ClipMatch
from schemas import (
    UserCreate, UserResponse, Token,
    AnalysisJobCreate, AnalysisJobResponse,
    ShortformJobCreate, ShortformJobResponse,
    BestCutJobCreate, BestCutJobResponse,
    CoachingJobCreate, CoachingJobResponse,
)

# JWT 설정
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/")

# 디렉토리 설정 (절대 경로 사용 → CWD 변경에 영향 받지 않음)
UPLOAD_FOLDER        = os.path.join(BASE_DIR, "videos")
OUTPUT_FOLDER        = os.path.join(BASE_DIR, "outputs")
OUTPUT_VIDEOS_FOLDER = os.path.join(BASE_DIR, "outputs", "videos")
OUTPUT_PHOTOS_FOLDER = os.path.join(BASE_DIR, "outputs", "photos")
OUTPUT_COACHING_FOLDER = os.path.join(BASE_DIR, "outputs", "coaching")
CAMERA_CLIPS_FOLDER = os.path.join(BASE_DIR, "outputs", "camera_clips")
TRIMMED_CLIPS_FOLDER = os.path.join(BASE_DIR, "outputs", "trimmed_clips")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_VIDEOS_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_PHOTOS_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_COACHING_FOLDER, exist_ok=True)
os.makedirs(CAMERA_CLIPS_FOLDER, exist_ok=True)
os.makedirs(TRIMMED_CLIPS_FOLDER, exist_ok=True)

# FastAPI 앱 초기화
app = FastAPI(title="RunningDiary API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 출력 파일 정적 서빙
app.mount("/outputs", StaticFiles(directory=OUTPUT_FOLDER), name="outputs")
app.mount("/camera", StaticFiles(directory=os.path.join(BASE_DIR, "camera"), html=True), name="camera")


# ────────────────────────────────────────────────────────────
# JWT 유틸리티
# ────────────────────────────────────────────────────────────

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


# ────────────────────────────────────────────────────────────
# 헬퍼: 별도 스레드에서 동기 함수 실행
# ────────────────────────────────────────────────────────────

def _run_in_thread(func, *args):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        future.result()


# ────────────────────────────────────────────────────────────
# video-editor 설정 헬퍼
# ────────────────────────────────────────────────────────────

def _is_ollama_running() -> bool:
    """Ollama 서버가 실행 중인지 확인"""
    try:
        import requests as req
        r = req.get("http://localhost:11434/api/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def _get_video_editor_config(output_dir: str) -> "VideoEditorConfig":
    """환경에 맞는 video-editor 설정 반환 (API → LOCAL → MOCK 우선순위)"""
    # API 모드: QWEN + Anthropic 둘 다 있으면 최고, Anthropic만 있어도 됨
    if ANTHROPIC_API_KEY:
        return VideoEditorConfig(
            mode=ProcessingMode.API,
            qwen_api_key=QWEN_API_KEY if QWEN_API_KEY else None,
            claude_api_key=ANTHROPIC_API_KEY,
            output_dir=output_dir,
            cache_enabled=False,
        )
    # Ollama 서버가 돌아가고 있으면 LOCAL 모드 사용
    if _is_ollama_running():
        return VideoEditorConfig(
            mode=ProcessingMode.LOCAL,
            ollama_model="qwen2.5vl:7b",
            output_dir=output_dir,
            cache_enabled=False,
        )
    return VideoEditorConfig(
        mode=ProcessingMode.MOCK,
        output_dir=output_dir,
        cache_enabled=False,
    )


# ────────────────────────────────────────────────────────────
# OpenCV 기반 베스트 컷 프레임 추출
# ────────────────────────────────────────────────────────────

def _extract_frames_opencv(video_path: str, photo_count: int, output_dir: str) -> list:
    """
    OpenCV로 영상에서 균등 간격 프레임을 추출해 JPEG로 저장.
    실제 사진 URL이 포함된 결과 리스트 반환.
    """
    try:
        import cv2
    except ImportError:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    if total_frames <= 0:
        cap.release()
        return []

    descriptions = [
        "완벽한 착지 자세",
        "이상적인 팔 스윙",
        "균형 잡힌 상체 자세",
        "최적의 보폭 구간",
        "힘찬 킥 동작",
        "안정적인 코어 자세",
        "효율적인 호흡 구간",
        "강한 추진력 순간",
        "리듬감 있는 발걸음",
        "최고 속도 구간",
    ]

    # 영상 앞뒤 10% 제외하고 균등 분배
    start = int(total_frames * 0.1)
    end = int(total_frames * 0.9)
    usable = max(1, end - start)

    frame_indices = [
        start + int(i * usable / (photo_count + 1))
        for i in range(1, photo_count + 1)
    ]

    os.makedirs(output_dir, exist_ok=True)
    photos = []
    ts_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, frame_idx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        timestamp_sec = frame_idx / fps
        timestamp_str = f"{int(timestamp_sec // 60)}:{int(timestamp_sec % 60):02d}"

        filename = f"bestcut_{ts_prefix}_{i+1}.jpg"
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

        photos.append({
            "photo_url": f"/outputs/photos/{filename}",
            "timestamp": timestamp_str,
            "description": descriptions[i % len(descriptions)],
        })

    cap.release()
    return photos


# ────────────────────────────────────────────────────────────
# OpenCV 기반 코칭 영상 생성 (ffmpeg 없이)
# ────────────────────────────────────────────────────────────

def _create_coaching_video_opencv(
    video_path: str,
    coaching_text: str,
    output_path: str
) -> bool:
    """
    OpenCV만으로 코칭 텍스트 자막을 영상 하단에 오버레이하여 저장.
    한글은 ASCII로 렌더링되지 않으므로, 가능한 영문 fallback 텍스트를 사용.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 텍스트를 줄 단위로 분리 (최대 40자씩)
    sentences = [s.strip() for s in coaching_text.replace('\n', '. ').split('.') if s.strip()]
    if not sentences:
        sentences = [coaching_text[:40]]

    frames_per_sentence = max(1, total_frames // max(1, len(sentences)))

    # 임시 파일에 먼저 저장 (mp4v) 후 ffmpeg로 H.264 재인코딩
    import tempfile
    tmp_path = output_path + ".tmp.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(tmp_path, fourcc, fps, (width, height))

    if not out.isOpened():
        cap.release()
        return False

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        sentence_idx = min(frame_count // frames_per_sentence, len(sentences) - 1)
        text = sentences[sentence_idx]

        # 반투명 하단 바
        overlay = frame.copy()
        bar_h = max(60, height // 8)
        cv2.rectangle(overlay, (0, height - bar_h), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        # 텍스트 (한글은 ??? 로 표시되지만 구조는 유지)
        font_scale = max(0.5, width / 1280)
        cv2.putText(
            frame, text[:60], (20, height - bar_h // 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale,
            (255, 255, 255), 2, cv2.LINE_AA
        )

        out.write(frame)
        frame_count += 1

    cap.release()
    out.release()

    if frame_count == 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    # ffmpeg로 H.264 재인코딩 (브라우저/모바일 호환)
    # ffmpeg 경로 탐색 (Homebrew 우선)
    import subprocess, shutil as _shutil
    ffmpeg_bin = _shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg' or '/usr/local/bin/ffmpeg'
    try:
        result = subprocess.run([
            ffmpeg_bin, '-y', '-i', tmp_path,
            '-vcodec', 'libx264', '-an',
            '-movflags', '+faststart',
            output_path
        ], capture_output=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            os.remove(tmp_path)
            return True
        else:
            # ffmpeg 실패 로그 출력
            print(f"[COACHING ffmpeg 실패] returncode={result.returncode}")
            print(result.stderr.decode(errors='ignore')[-500:])
            if os.path.exists(tmp_path):
                shutil.move(tmp_path, output_path)
            return os.path.exists(output_path)
    except Exception as e:
        print(f"[COACHING ffmpeg 예외] {e}")
        # ffmpeg 실패 시 원본 그대로 사용
        if os.path.exists(tmp_path):
            shutil.move(tmp_path, output_path)
        return os.path.exists(output_path)


# ────────────────────────────────────────────────────────────
# 기본 엔드포인트
# ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "ok",
        "pose_analyzer_available": POSE_ANALYZER_AVAILABLE,
        "pose_model_exists": os.path.exists(POSE_MODEL_PATH),
        "video_editor_available": VIDEO_EDITOR_AVAILABLE,
        "video_editor_path": VIDEO_EDITOR_PATH,
        "video_editor_mode": "api" if ANTHROPIC_API_KEY else ("local" if _is_ollama_running() else "mock"),
    }


# ────────────────────────────────────────────────────────────
# 인증 엔드포인트
# ────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디 또는 이메일입니다")

    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/login-json", response_model=Token)
async def login_json(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == req.email) | (User.email == req.email)
    ).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 아이디 또는 비밀번호",
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == form_data.username) | (User.email == form_data.username)
    ).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 아이디 또는 비밀번호",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user



# ────────────────────────────────────────────────────────────
# 영상 업로드 / 조회
# ────────────────────────────────────────────────────────────

@app.post("/upload-video/")
async def upload_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # content_type 체크 (video/* 또는 application/octet-stream 허용, 확장자로도 검증)
    allowed_extensions = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".webm"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    is_video_mime = file.content_type and file.content_type.startswith("video/")
    is_video_ext = file_ext in allowed_extensions
    is_octet_stream = file.content_type == "application/octet-stream"

    if not (is_video_mime or (is_octet_stream and is_video_ext) or is_video_ext):
        raise HTTPException(status_code=400, detail="비디오 파일만 업로드 가능합니다 (.mp4, .mov 등)")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{current_user.id}_{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_video = Video(user_id=current_user.id, filename=filename)
    db.add(db_video)
    db.commit()
    db.refresh(db_video)

    return {
        "success": True,
        "video_id": db_video.id,
        "filename": filename,
        "user_id": current_user.id,
        "size_bytes": os.path.getsize(filepath),
        "video_url": f"/videos/{filename}",
    }


@app.get("/videos/{filename}")
async def get_video(
    filename: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    raw_token = token
    if not raw_token and authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:]

    if not raw_token:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    try:
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    current_user = db.query(User).filter(User.username == username).first()
    if not current_user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    if not filename.startswith(f"{current_user.id}_"):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    return FileResponse(filepath, media_type="video/mp4")


@app.get("/my-videos/")
async def get_my_videos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """업로드한 영상 목록 조회"""
    videos = db.query(Video).filter(Video.user_id == current_user.id).order_by(Video.id.asc()).all()
    result = []
    for v in videos:
        filepath = os.path.join(UPLOAD_FOLDER, v.filename)
        size_bytes = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        result.append({
            "video_id":   v.id,
            "filename":   v.filename,
            "size_bytes": size_bytes,
            "video_url":  f"/videos/{v.filename}",
        })
    return result


# ────────────────────────────────────────────────────────────
# 영상 분석 (running_pose 2 연동)
# ────────────────────────────────────────────────────────────

def _build_mock_analysis_result() -> dict:
    """running_pose 2를 사용할 수 없을 때 또는 테스트용 분석 결과"""
    score = random.randint(65, 92)
    feedbacks = [
        {
            "title": "무릎 각도",
            "status": "good" if score >= 75 else "warning",
            "message": "무릎 각도가 적절합니다" if score >= 75 else "무릎을 조금 더 구부려 충격을 흡수하세요",
        },
        {
            "title": "보폭",
            "status": "warning" if score < 80 else "good",
            "message": "보폭을 조금 더 넓히는 것을 권장합니다" if score < 80 else "보폭이 안정적입니다",
        },
        {
            "title": "상체 각도",
            "status": "good",
            "message": "상체 자세가 안정적입니다",
        },
        {
            "title": "착지",
            "status": "bad" if score < 70 else "good",
            "message": "중족부 착지를 연습하세요. 발 앞쪽 충격을 줄여보세요" if score < 70 else "착지 자세가 좋습니다",
        },
    ]
    return {
        "score": score,
        "feedbacks": feedbacks,
        "pose_stats": {
            "cadence": round(random.uniform(155, 175), 1),
            "v_oscillation": round(random.uniform(6.0, 10.0), 1),
            "avg_impact_z": round(random.uniform(0.18, 0.38), 2),
            "asymmetry": round(random.uniform(0.5, 3.5), 1),
            "elbow_angle": round(random.uniform(75, 105), 1),
        },
        "coaching_report": "분석 모듈을 사용할 수 없어 기본 피드백을 제공합니다. 정확한 분석을 위해 영상을 다시 업로드해주세요.",
    }


def _run_analysis_task(job_id: int, video_path: str):
    """백그라운드 분석 작업 (별도 스레드)"""
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        result = None

        if (
            POSE_ANALYZER_AVAILABLE
            and os.path.exists(video_path)
            and os.path.exists(POSE_MODEL_PATH)
        ):
            try:
                work_dir = os.path.join(POSE_OUTPUT_FOLDER, str(job_id))
                result = pose_analyzer.analyze_video(
                    video_path=video_path,
                    work_dir=work_dir,
                    model_path=POSE_MODEL_PATH,
                    gemini_api_key=GEMINI_API_KEY,
                )
            except Exception as e:
                result = None

        if result is None:
            result = _build_mock_analysis_result()

        job.result_json = json.dumps(result, ensure_ascii=False)
        job.status = "done"
        db.commit()

    except Exception as e:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()


@app.post("/analysis-jobs/", response_model=AnalysisJobResponse)
async def create_analysis_job(
    body: AnalysisJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(
        Video.id == body.video_id, Video.user_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    job = AnalysisJob(user_id=current_user.id, video_id=body.video_id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    video_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))
    background_tasks.add_task(
        _run_in_thread, _run_analysis_task, job.id, video_path
    )
    return job


@app.get("/analysis-jobs/", response_model=List[AnalysisJobResponse])
async def list_analysis_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(AnalysisJob)
        .filter(AnalysisJob.user_id == current_user.id)
        .order_by(AnalysisJob.created_at.desc())
        .all()
    )


@app.get("/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
async def get_analysis_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(AnalysisJob).filter(
        AnalysisJob.id == job_id, AnalysisJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다")
    return job


# ────────────────────────────────────────────────────────────
# 숏폼 생성 (video-editor 연동)
# ────────────────────────────────────────────────────────────

def _run_shortform_task(job_id: int, video_paths: list, style: str, duration_sec: float):
    """백그라운드 숏폼 생성 작업"""
    db = SessionLocal()
    try:
        job = db.query(ShortformJob).filter(ShortformJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        output_filename = None
        primary_path = video_paths[0] if video_paths else None

        if VIDEO_EDITOR_AVAILABLE and primary_path and os.path.exists(primary_path):
            try:
                with VIDEO_EDITOR_LOCK:
                    orig_dir = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        config = _get_video_editor_config(OUTPUT_FOLDER)
                        api = VideoEditorAPI(config)
                        result = api.process(
                            video_path=primary_path,
                            duration=duration_sec,
                            style=style,
                            photo_count=0,
                        )
                    finally:
                        os.chdir(orig_dir)

                if result.success and result.video_path and os.path.exists(result.video_path):
                    base_name = os.path.basename(result.video_path)
                    dest = os.path.join(OUTPUT_VIDEOS_FOLDER, base_name)
                    if result.video_path != dest:
                        shutil.move(result.video_path, dest)
                    output_filename = base_name
                else:
                    print(f"[SHORTFORM] video-editor 실패: success={result.success}, "
                          f"video_path={result.video_path}, error={result.error}")
            except Exception as e:
                import traceback
                print(f"[SHORTFORM ERROR] {type(e).__name__}: {e}")
                print(traceback.format_exc())

        # video-editor 결과 없으면 원본 첫 번째 영상 복사
        if not output_filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"shortform_{job_id}_{ts}.mp4"
            dest = os.path.join(OUTPUT_VIDEOS_FOLDER, output_filename)
            if primary_path and os.path.exists(primary_path):
                shutil.copy2(primary_path, dest)

        job.output_filename = output_filename
        job.status = "done"
        db.commit()

    except Exception as e:
        job = db.query(ShortformJob).filter(ShortformJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()


@app.post("/shortform-jobs/", response_model=ShortformJobResponse)
async def create_shortform_job(
    body: ShortformJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid_styles = ["action", "instagram", "tiktok", "humor", "documentary"]

    if body.style not in valid_styles:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 스타일. 가능: {valid_styles}")

    if len(body.video_ids) < 1:
        raise HTTPException(status_code=400, detail="숏폼 생성에는 영상이 최소 1개 필요합니다")

    videos = []
    for vid_id in body.video_ids:
        video = db.query(Video).filter(
            Video.id == vid_id, Video.user_id == current_user.id
        ).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"영상 ID {vid_id}를 찾을 수 없습니다")
        videos.append(video)

    job = ShortformJob(
        user_id=current_user.id,
        video_id=videos[0].id,
        video_ids_json=json.dumps(body.video_ids),
        style=body.style,
        duration_sec=body.duration_sec,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    video_paths = [os.path.abspath(os.path.join(UPLOAD_FOLDER, v.filename)) for v in videos]
    background_tasks.add_task(
        _run_in_thread, _run_shortform_task, job.id, video_paths, body.style, body.duration_sec
    )
    return job


@app.get("/shortform-jobs/", response_model=List[ShortformJobResponse])
async def list_shortform_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ShortformJob)
        .filter(ShortformJob.user_id == current_user.id)
        .order_by(ShortformJob.created_at.desc())
        .all()
    )


@app.get("/shortform-jobs/{job_id}", response_model=ShortformJobResponse)
async def get_shortform_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(ShortformJob).filter(
        ShortformJob.id == job_id, ShortformJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="숏폼 작업을 찾을 수 없습니다")
    return job


# ────────────────────────────────────────────────────────────
# 베스트 컷 추출 (OpenCV + video-editor 연동)
# ────────────────────────────────────────────────────────────

def _run_bestcut_task(job_id: int, video_paths: list, photo_count: int):
    """백그라운드 베스트 컷 추출 작업"""
    db = SessionLocal()
    try:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        photos = []
        primary_path = video_paths[0] if video_paths else None

        # 1순위: video-editor API 모드 (API 키가 있을 때)
        if VIDEO_EDITOR_AVAILABLE and QWEN_API_KEY and ANTHROPIC_API_KEY and primary_path and os.path.exists(primary_path):
            try:
                with VIDEO_EDITOR_LOCK:
                    orig_dir = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        config = _get_video_editor_config(OUTPUT_FOLDER)
                        api = VideoEditorAPI(config)
                        result = api.process(
                            video_path=primary_path,
                            duration=10,
                            style="action",
                            photo_count=photo_count,
                            photo_preset="sports_action",
                        )
                    finally:
                        os.chdir(orig_dir)

                if result.success and result.photos:
                    for photo_path in result.photos:
                        base_name = os.path.basename(photo_path)
                        dest = os.path.join(OUTPUT_PHOTOS_FOLDER, base_name)
                        if photo_path != dest and os.path.exists(photo_path):
                            shutil.move(photo_path, dest)
                        photos.append({
                            "photo_url": f"/outputs/photos/{base_name}",
                            "timestamp": "0:00",
                            "description": "AI 선정 베스트 컷",
                        })
            except Exception:
                pass

        # 2순위: OpenCV 직접 프레임 추출 (모든 환경에서 작동)
        if not photos and primary_path and os.path.exists(primary_path):
            photos = _extract_frames_opencv(primary_path, photo_count, OUTPUT_PHOTOS_FOLDER)

        # 3순위: 다중 영상에서 추가 프레임 추출
        if len(photos) < photo_count and len(video_paths) > 1:
            remaining = photo_count - len(photos)
            for vpath in video_paths[1:]:
                if len(photos) >= photo_count:
                    break
                if os.path.exists(vpath):
                    extra = _extract_frames_opencv(vpath, remaining, OUTPUT_PHOTOS_FOLDER)
                    photos.extend(extra)
                    remaining -= len(extra)

        job.result_json = json.dumps(photos, ensure_ascii=False)
        job.status = "done"
        db.commit()

    except Exception as e:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()


@app.post("/bestcut-jobs/", response_model=BestCutJobResponse)
async def create_bestcut_job(
    body: BestCutJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not 1 <= body.photo_count <= 10:
        raise HTTPException(status_code=400, detail="photo_count는 1~10 사이여야 합니다")

    if len(body.video_ids) < 1:
        raise HTTPException(status_code=400, detail="영상을 최소 1개 이상 선택해주세요")

    videos = []
    for vid_id in body.video_ids:
        video = db.query(Video).filter(
            Video.id == vid_id, Video.user_id == current_user.id
        ).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"영상 ID {vid_id}를 찾을 수 없습니다")
        videos.append(video)

    job = BestCutJob(
        user_id=current_user.id,
        video_id=videos[0].id,
        video_ids_json=json.dumps(body.video_ids),
        photo_count=body.photo_count,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    video_paths = [os.path.abspath(os.path.join(UPLOAD_FOLDER, v.filename)) for v in videos]
    background_tasks.add_task(
        _run_in_thread, _run_bestcut_task, job.id, video_paths, body.photo_count
    )
    return job


@app.get("/bestcut-jobs/", response_model=List[BestCutJobResponse])
async def list_bestcut_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(BestCutJob)
        .filter(BestCutJob.user_id == current_user.id)
        .order_by(BestCutJob.created_at.desc())
        .all()
    )


@app.get("/bestcut-jobs/{job_id}", response_model=BestCutJobResponse)
async def get_bestcut_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(BestCutJob).filter(
        BestCutJob.id == job_id, BestCutJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="베스트 컷 작업을 찾을 수 없습니다")
    return job


# ────────────────────────────────────────────────────────────
# 코칭 영상 생성 (video-editor CoachingAPI + OpenCV fallback)
# ────────────────────────────────────────────────────────────

def _run_coaching_task(job_id: int, video_path: str, coaching_text: str):
    """백그라운드 코칭 영상 생성 작업"""
    db = SessionLocal()
    try:
        job = db.query(CoachingJob).filter(CoachingJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"coaching_{job_id}_{ts}.mp4"
        output_path = os.path.abspath(os.path.join(OUTPUT_COACHING_FOLDER, output_filename))
        success = False

        # 1순위: CoachingAPI (video-editor)
        if VIDEO_EDITOR_AVAILABLE and os.path.exists(video_path):
            try:
                with VIDEO_EDITOR_LOCK:
                    orig_dir = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        config = CoachingConfig(
                            tts_enabled=True,
                            subtitle_enabled=True,
                            use_llm_script=False,
                            output_dir=OUTPUT_COACHING_FOLDER,
                        )
                        api = CoachingAPI(config)
                        result = api.create(
                            video_path=video_path,
                            coaching_text=coaching_text,
                            output_path=output_path,
                        )
                        success = result.success and result.video_path and os.path.exists(result.video_path)
                        if success and result.video_path != output_path:
                            shutil.move(result.video_path, output_path)
                    finally:
                        os.chdir(orig_dir)
            except Exception:
                success = False

        # 2순위: OpenCV 텍스트 오버레이
        if not success and os.path.exists(video_path):
            success = _create_coaching_video_opencv(video_path, coaching_text, output_path)

        # 3순위: 원본 영상 복사 (영상만 제공)
        if not success and os.path.exists(video_path):
            shutil.copy2(video_path, output_path)
            success = True

        if success and os.path.exists(output_path):
            job.output_filename = output_filename
            job.status = "done"
        else:
            job.status = "failed"

        db.commit()

    except Exception as e:
        job = db.query(CoachingJob).filter(CoachingJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()


@app.post("/coaching-jobs/", response_model=CoachingJobResponse)
async def create_coaching_job(
    body: CoachingJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """코칭 영상 생성 작업 시작"""
    video = db.query(Video).filter(
        Video.id == body.video_id, Video.user_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    # coaching_text가 비어있으면 analysis_job에서 coaching_report 자동 추출
    coaching_text = body.coaching_text.strip() if body.coaching_text else ""

    if not coaching_text and body.analysis_job_id:
        analysis_job = db.query(AnalysisJob).filter(
            AnalysisJob.id == body.analysis_job_id,
            AnalysisJob.user_id == current_user.id
        ).first()
        if analysis_job and analysis_job.result_json:
            try:
                result_data = json.loads(analysis_job.result_json)
                coaching_text = result_data.get("coaching_report", "")
                if not coaching_text:
                    # feedbacks에서 메시지 조합
                    feedbacks = result_data.get("feedbacks", [])
                    coaching_text = " ".join([fb.get("message", "") for fb in feedbacks])
            except Exception:
                pass

    if not coaching_text:
        coaching_text = "좋은 자세를 유지하며 달리세요. 케이던스와 착지 자세에 집중해보세요."

    job = CoachingJob(
        user_id=current_user.id,
        video_id=body.video_id,
        coaching_text=coaching_text,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    video_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))
    background_tasks.add_task(
        _run_in_thread, _run_coaching_task, job.id, video_path, coaching_text
    )
    return job


@app.get("/coaching-jobs/", response_model=List[CoachingJobResponse])
async def list_coaching_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """내 코칭 영상 목록 조회"""
    return (
        db.query(CoachingJob)
        .filter(CoachingJob.user_id == current_user.id)
        .order_by(CoachingJob.created_at.desc())
        .all()
    )


@app.get("/coaching-jobs/{job_id}", response_model=CoachingJobResponse)
async def get_coaching_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """코칭 영상 작업 상태 조회"""
    job = db.query(CoachingJob).filter(
        CoachingJob.id == job_id, CoachingJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="코칭 영상 작업을 찾을 수 없습니다")
    return job


# ────────────────────────────────────────────────────────────
# GPS / 카메라 클립 / 매칭
# ────────────────────────────────────────────────────────────

import math

def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    """두 GPS 좌표 사이 거리(미터) 계산"""
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) *
         math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _convert_to_mp4(input_path: str, output_path: str) -> bool:
    """webm 등 영상을 mp4로 변환"""
    import subprocess, shutil as _shutil
    ffmpeg_bin = _shutil.which('ffmpeg')
    if not ffmpeg_bin:
        shutil.copy2(input_path, output_path)
        return True
    try:
        result = subprocess.run([
            ffmpeg_bin, '-y',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-c:a', 'aac',
            output_path
        ], capture_output=True, timeout=120)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def _concat_clips(clip_paths: list, output_path: str) -> bool:
    """ffmpeg filter_complex concat으로 여러 클립을 하나로 합치기 (타임스탬프 리셋으로 멈춤 방지)"""
    import subprocess, shutil as _shutil
    ffmpeg_bin = _shutil.which('ffmpeg')
    if not ffmpeg_bin:
        return False
    try:
        n = len(clip_paths)
        cmd = [ffmpeg_bin, '-y']
        for p in clip_paths:
            cmd += ['-i', p]
        filter_str = ''.join(f'[{i}:v]' for i in range(n)) + f'concat=n={n}:v=1[v]'
        cmd += [
            '-filter_complex', filter_str,
            '-map', '[v]',
            '-c:v', 'libx264', '-preset', 'fast',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=180)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def _trim_clip(input_path: str, output_path: str, start_sec: float, end_sec: float) -> bool:
    """ffmpeg로 영상 구간 잘라내기 + mp4 변환 (webm 포함 모든 포맷 지원)"""
    import subprocess, shutil as _shutil
    ffmpeg_bin = _shutil.which('ffmpeg')
    if not ffmpeg_bin:
        shutil.copy2(input_path, output_path)
        return True
    try:
        duration = max(1.0, end_sec - start_sec)
        result = subprocess.run([
            ffmpeg_bin, '-y',
            '-ss', str(start_sec),
            '-i', input_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-c:a', 'aac',
            output_path
        ], capture_output=True, timeout=120)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def _auto_process_trimmed_clip(user_id: int, trimmed_path: str):
    """트림된 클립으로 분석/베스트컷/숏폼 자동 실행"""
    print(f"[AUTO] 유저 {user_id} 자동 처리 시작: {os.path.basename(trimmed_path)}")
    db = SessionLocal()
    try:
        analysis_job = AnalysisJob(user_id=user_id, status="pending")
        bestcut_job = BestCutJob(user_id=user_id, video_ids_json="[]", photo_count=5, status="pending")
        shortform_job = ShortformJob(user_id=user_id, video_ids_json="[]", style="action", duration_sec=30.0, status="pending")
        db.add_all([analysis_job, bestcut_job, shortform_job])
        db.commit()
        db.refresh(analysis_job)
        db.refresh(bestcut_job)
        db.refresh(shortform_job)
        analysis_id = analysis_job.id
        bestcut_id = bestcut_job.id
        shortform_id = shortform_job.id
    except Exception as e:
        print(f"[AUTO] 유저 {user_id} 잡 생성 실패: {e}")
        return
    finally:
        db.close()

    _run_analysis_task(analysis_id, trimmed_path)
    _run_bestcut_task(bestcut_id, [trimmed_path], 5)
    _run_shortform_task(shortform_id, [trimmed_path], "action", 30.0)
    print(f"[AUTO] 유저 {user_id} 자동 처리 완료")


def _process_clip_matching(clip_id: int):
    """클립 업로드 후 50m 이내 유저와 매칭 → 구간 잘라내기"""
    db = SessionLocal()
    try:
        clip = db.query(CameraClip).filter(CameraClip.id == clip_id).first()
        if not clip:
            return

        PROXIMITY_M = 50.0

        print(f"[MATCH] 클립 {clip_id} | 카메라 위치: ({clip.camera_lat}, {clip.camera_lng}) | 시간: {clip.clip_start} ~ {clip.clip_end}")

        # 클립 시간대에 위치 기록이 있는 유저 조회
        locations = db.query(UserLocation).filter(
            UserLocation.recorded_at >= clip.clip_start,
            UserLocation.recorded_at <= clip.clip_end,
        ).all()

        print(f"[MATCH] 클립 {clip_id} | 시간대 내 GPS 기록 {len(locations)}개")
        for loc in locations:
            dist = _haversine_m(loc.lat, loc.lng, clip.camera_lat, clip.camera_lng)
            print(f"[MATCH]   유저 {loc.user_id} | 거리: {dist:.1f}m | 위치: ({loc.lat}, {loc.lng})")

        matched_users: dict[int, dict] = {}
        for loc in locations:
            dist = _haversine_m(loc.lat, loc.lng, clip.camera_lat, clip.camera_lng)
            if dist <= PROXIMITY_M:
                uid = loc.user_id
                if uid not in matched_users:
                    matched_users[uid] = {"enter": loc.recorded_at, "exit": loc.recorded_at}
                    print(f"[MATCH] 유저 {uid} 범위 진입 - {loc.recorded_at} (거리: {dist:.1f}m)")
                else:
                    if loc.recorded_at < matched_users[uid]["enter"]:
                        matched_users[uid]["enter"] = loc.recorded_at
                    if loc.recorded_at > matched_users[uid]["exit"]:
                        matched_users[uid]["exit"] = loc.recorded_at

        for uid, times in matched_users.items():
            print(f"[MATCH] 유저 {uid} 범위 이탈 - {times['exit']} / 진입:{times['enter']} ~ 이탈:{times['exit']}")

        clip_path = os.path.join(CAMERA_CLIPS_FOLDER, clip.filename)

        for user_id, times in matched_users.items():
            # 이미 매칭된 경우 스킵
            existing = db.query(ClipMatch).filter(
                ClipMatch.user_id == user_id,
                ClipMatch.clip_id == clip_id,
            ).first()
            if existing:
                continue

            match = ClipMatch(
                user_id=user_id,
                clip_id=clip_id,
                enter_time=times["enter"],
                exit_time=times["exit"],
                status="processing",
            )
            db.add(match)
            db.commit()
            db.refresh(match)

            # 클립 내 상대 시간 계산 (초)
            clip_duration = (clip.clip_end - clip.clip_start).total_seconds()
            start_sec = max(0.0, (times["enter"] - clip.clip_start).total_seconds() - 2)
            end_sec = min(clip_duration, (times["exit"] - clip.clip_start).total_seconds() + 2)
            # exit 시점이 클립 종료 10초 이내면 끝까지 포함 (GPS 끊김 대응)
            if clip_duration - end_sec <= 10:
                end_sec = clip_duration

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            trimmed_filename = f"trimmed_{user_id}_{clip_id}_{ts}.mp4"
            trimmed_path = os.path.join(TRIMMED_CLIPS_FOLDER, trimmed_filename)

            success = _trim_clip(clip_path, trimmed_path, start_sec, end_sec)

            if not success:
                match.status = "failed"
                db.commit()
                print(f"[MATCH] 유저 {user_id} 트림 실패")
                continue

            match.trimmed_filename = trimmed_filename
            match.status = "done"
            db.commit()

            # 이전 연속 클립과 합치기
            # clip_start 기준 25초 이내에 끝난 이전 매칭이 있으면 merge
            prev_match = (
                db.query(ClipMatch)
                .filter(
                    ClipMatch.user_id == user_id,
                    ClipMatch.id != match.id,
                    ClipMatch.status == "done",
                    ClipMatch.exit_time >= clip.clip_start - timedelta(seconds=25),
                    ClipMatch.exit_time <= clip.clip_start + timedelta(seconds=5),
                )
                .order_by(ClipMatch.created_at.desc())
                .first()
            )

            if prev_match and prev_match.trimmed_filename:
                prev_path = os.path.join(TRIMMED_CLIPS_FOLDER, prev_match.trimmed_filename)
                if os.path.exists(prev_path):
                    ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                    merged_filename = f"merged_{user_id}_{ts2}.mp4"
                    merged_path = os.path.join(TRIMMED_CLIPS_FOLDER, merged_filename)
                    ok = _concat_clips([prev_path, trimmed_path], merged_path)
                    if ok:
                        # 이전 매칭을 merged 영상으로 업데이트
                        prev_match.trimmed_filename = merged_filename
                        prev_match.exit_time = match.exit_time
                        db.commit()
                        # 현재 매칭은 merged 처리 (앱에서 노출 안 함)
                        match.status = "merged"
                        db.commit()
                        # 임시 파일 정리
                        try:
                            os.remove(trimmed_path)
                        except Exception:
                            pass
                        print(f"[MATCH] 유저 {user_id} 클립 합치기 완료 → {merged_filename}")
                        _auto_process_trimmed_clip(user_id, merged_path)
                        continue

            print(f"[MATCH] 유저 {user_id} 영상 전송 완료 → {trimmed_filename}")
            _auto_process_trimmed_clip(user_id, trimmed_path)

    except Exception as e:
        print(f"[CLIP MATCHING ERROR] {e}")
    finally:
        db.close()


class LocationIn(BaseModel):
    lat: float
    lng: float
    recorded_at: str  # ISO8601 문자열


@app.post("/location")
async def post_location(
    body: LocationIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """아이폰에서 5초마다 GPS 위치 전송"""
    try:
        recorded_at = datetime.fromisoformat(body.recorded_at.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        recorded_at = datetime.utcnow()

    loc = UserLocation(
        user_id=current_user.id,
        lat=body.lat,
        lng=body.lng,
        recorded_at=recorded_at,
    )
    db.add(loc)
    db.commit()
    return {"ok": True}


@app.post("/camera-clip")
async def upload_camera_clip(
    file: UploadFile = File(...),
    camera_lat: float = Form(0.0),
    camera_lng: float = Form(0.0),
    clip_start: str = Form(""),
    clip_end: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """갤럭시에서 30초 클립 업로드 (인증 불필요 - 카메라 전용)"""
    try:
        start_dt = datetime.fromisoformat(clip_start.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(clip_end.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        now = datetime.utcnow()
        start_dt = now
        end_dt = now

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # 업로드된 파일 그대로 저장 (변환 없이)
    content_type = file.content_type or ""
    raw_ext = ".mp4" if "mp4" in content_type else ".webm"
    filename = f"clip_{ts}{raw_ext}"
    filepath = os.path.join(CAMERA_CLIPS_FOLDER, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    clip = CameraClip(
        filename=filename,
        camera_lat=camera_lat,
        camera_lng=camera_lng,
        clip_start=start_dt,
        clip_end=end_dt,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)

    background_tasks.add_task(_run_in_thread, _process_clip_matching, clip.id)

    return {"ok": True, "clip_id": clip.id}


@app.get("/my-clips")
async def get_my_clips(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """아이폰에서 본인에게 매칭된 영상 목록 조회"""
    matches = (
        db.query(ClipMatch)
        .filter(ClipMatch.user_id == current_user.id, ClipMatch.status == "done")
        .order_by(ClipMatch.created_at.desc())
        .all()
    )
    result = []
    for m in matches:
        result.append({
            "match_id": m.id,
            "clip_id": m.clip_id,
            "trimmed_url": f"/outputs/trimmed_clips/{m.trimmed_filename}" if m.trimmed_filename else None,
            "enter_time": m.enter_time.isoformat() if m.enter_time else None,
            "exit_time": m.exit_time.isoformat() if m.exit_time else None,
            "created_at": m.created_at.isoformat(),
        })
    return result


# ────────────────────────────────────────────────────────────
# DB 테이블 생성
# ────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)
