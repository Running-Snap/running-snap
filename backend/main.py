import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer

from core.database import engine
from core.models import Base
from core.config import OUTPUT_FOLDER, BASE_DIR

from routers import auth, videos, analysis, shortform, bestcut, coaching, camera, admin, pose_video, cert

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RunningDiary API",
    version="2.0.0",
)

# Swagger UI에서 Bearer 토큰 직접 입력 가능하도록
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    # OAuth2 Token URL 슬래시 제거 (307 리다이렉트 방지)
    for scheme in schema.get("components", {}).get("securitySchemes", {}).values():
        if scheme.get("type") == "oauth2":
            flows = scheme.get("flows", {})
            for flow in flows.values():
                if "tokenUrl" in flow:
                    flow["tokenUrl"] = flow["tokenUrl"].rstrip("/")
    # BearerAuth 추가
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    for path in schema.get("paths", {}).values():
        for op in path.values():
            op.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

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
app.include_router(admin.router)
app.include_router(pose_video.router)
app.include_router(cert.router)


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
