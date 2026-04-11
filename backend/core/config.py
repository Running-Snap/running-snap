import os
import sys
import threading

from dotenv import load_dotenv
load_dotenv()

# 프로젝트 루트
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── OCR 분류 모듈 ───────────────────────────────────────────
OCR_CLASSIFICATION_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "OCR_Classification"))
sys.path.insert(0, OCR_CLASSIFICATION_PATH)

try:
    from person_appearance_report.analyzer import run_report
    from person_appearance_report.config import ReportConfig
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── 자세 분석 모듈 ──────────────────────────────────────────
RUNNING_POSE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "running_pose"))
sys.path.insert(0, RUNNING_POSE_PATH)

try:
    import pose_analyzer
    POSE_ANALYZER_AVAILABLE = True
except ImportError:
    POSE_ANALYZER_AVAILABLE = False

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
POSE_MODEL_PATH = os.getenv("POSE_MODEL_PATH", os.path.join(BASE_DIR, "pose_landmarker_heavy.task"))

# ── video-editor 모듈 ────────────────────────────────────────
VIDEO_EDITOR_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "video-editor"))
sys.path.insert(0, VIDEO_EDITOR_PATH)

try:
    from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode, CoachingAPI, CoachingConfig
    VIDEO_EDITOR_AVAILABLE = True
except ImportError:
    VIDEO_EDITOR_AVAILABLE = False

QWEN_API_KEY      = os.getenv("QWEN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VIDEO_EDITOR_LOCK = threading.Lock()

# ── AWS S3 ───────────────────────────────────────────────────
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_BUCKET_NAME       = os.getenv("AWS_BUCKET_NAME", "")
AWS_REGION            = os.getenv("AWS_REGION", "ap-northeast-2")

# ── JWT ──────────────────────────────────────────────────────
SECRET_KEY                  = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간

# ── 디렉토리 ─────────────────────────────────────────────────
UPLOAD_FOLDER         = os.path.join(BASE_DIR, "videos")
OUTPUT_FOLDER         = os.path.join(BASE_DIR, "outputs")
OUTPUT_VIDEOS_FOLDER  = os.path.join(BASE_DIR, "outputs", "videos")
OUTPUT_PHOTOS_FOLDER        = os.path.join(BASE_DIR, "outputs", "photos")
OUTPUT_PHOTOS_BESTCUT_FOLDER= os.path.join(BASE_DIR, "outputs", "photos", "bestcut")
OUTPUT_PHOTOS_POSTER_FOLDER = os.path.join(BASE_DIR, "outputs", "photos", "poster")
OUTPUT_COACHING_FOLDER      = os.path.join(BASE_DIR, "outputs", "coaching")
OUTPUT_CERT_FOLDER          = os.path.join(BASE_DIR, "outputs", "cert")
CAMERA_CLIPS_FOLDER   = os.path.join(BASE_DIR, "outputs", "camera_clips")
TRIMMED_CLIPS_FOLDER  = os.path.join(BASE_DIR, "outputs", "trimmed_clips")
POSE_OUTPUT_FOLDER    = os.path.join(BASE_DIR, "outputs", "pose")

for _d in [
    UPLOAD_FOLDER, OUTPUT_VIDEOS_FOLDER, OUTPUT_PHOTOS_FOLDER,
    OUTPUT_PHOTOS_BESTCUT_FOLDER, OUTPUT_PHOTOS_POSTER_FOLDER,
    OUTPUT_COACHING_FOLDER, OUTPUT_CERT_FOLDER,
    CAMERA_CLIPS_FOLDER, TRIMMED_CLIPS_FOLDER, POSE_OUTPUT_FOLDER,
]:
    os.makedirs(_d, exist_ok=True)
