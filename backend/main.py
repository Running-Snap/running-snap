import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine
from models import Base
from core.config import OUTPUT_FOLDER, BASE_DIR

from routers import auth, videos, analysis, shortform, bestcut, coaching, camera

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RunningDiary API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙
app.mount("/outputs", StaticFiles(directory=OUTPUT_FOLDER), name="outputs")
app.mount("/camera",  StaticFiles(directory=os.path.join(BASE_DIR, "camera"), html=True), name="camera")

# 라우터 등록
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(analysis.router)
app.include_router(shortform.router)
app.include_router(bestcut.router)
app.include_router(coaching.router)
app.include_router(camera.router)


@app.get("/")
async def root():
    from core.config import POSE_ANALYZER_AVAILABLE, VIDEO_EDITOR_AVAILABLE, ANTHROPIC_API_KEY, POSE_MODEL_PATH
    return {
        "status":                   "ok",
        "pose_analyzer_available":  POSE_ANALYZER_AVAILABLE,
        "pose_model_exists":        os.path.exists(POSE_MODEL_PATH),
        "video_editor_available":   VIDEO_EDITOR_AVAILABLE,
        "video_editor_mode":        "api" if ANTHROPIC_API_KEY else "mock",
    }
