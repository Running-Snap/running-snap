"""베스트컷 추출 백그라운드 작업"""
import json
import os

from database import SessionLocal
from models import BestCutJob
from core.config import (
    VIDEO_EDITOR_AVAILABLE, VIDEO_EDITOR_LOCK, VIDEO_EDITOR_PATH,
    QWEN_API_KEY, ANTHROPIC_API_KEY, OUTPUT_FOLDER, OUTPUT_PHOTOS_FOLDER,
)
from services.opencv import extract_frames


def run_bestcut_task(job_id: int, video_paths: list, photo_count: int):
    db = SessionLocal()
    try:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        primary_path = video_paths[0] if video_paths else None
        photos       = []

        # 1순위: video-editor API (Qwen + Anthropic 둘 다 필요)
        if VIDEO_EDITOR_AVAILABLE and QWEN_API_KEY and ANTHROPIC_API_KEY and primary_path and os.path.exists(primary_path):
            try:
                from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode
                config = VideoEditorConfig(
                    mode=ProcessingMode.API,
                    qwen_api_key=QWEN_API_KEY,
                    claude_api_key=ANTHROPIC_API_KEY,
                    output_dir=OUTPUT_FOLDER,
                    cache_enabled=False,
                )
                with VIDEO_EDITOR_LOCK:
                    orig = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        result = VideoEditorAPI(config).process(
                            video_path=primary_path,
                            duration=10,
                            style="action",
                            photo_count=photo_count,
                            photo_preset="sports_action",
                        )
                    finally:
                        os.chdir(orig)
                if result.success and result.photos:
                    import shutil
                    for photo_path in result.photos:
                        base = os.path.basename(photo_path)
                        dest = os.path.join(OUTPUT_PHOTOS_FOLDER, base)
                        if photo_path != dest and os.path.exists(photo_path):
                            shutil.move(photo_path, dest)
                        photos.append({"photo_url": f"/outputs/photos/{base}", "timestamp": "0:00", "description": "AI 선정 베스트 컷"})
            except Exception:
                pass

        # 2순위: OpenCV
        if not photos and primary_path and os.path.exists(primary_path):
            photos = extract_frames(primary_path, photo_count, OUTPUT_PHOTOS_FOLDER)

        # 3순위: 추가 영상에서 보충
        if len(photos) < photo_count and len(video_paths) > 1:
            remaining = photo_count - len(photos)
            for vpath in video_paths[1:]:
                if len(photos) >= photo_count:
                    break
                if os.path.exists(vpath):
                    extra = extract_frames(vpath, remaining, OUTPUT_PHOTOS_FOLDER)
                    photos.extend(extra)
                    remaining -= len(extra)

        job.result_json = json.dumps(photos, ensure_ascii=False)
        job.status      = "done"
        db.commit()
    except Exception as e:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if job:
            job.status      = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()
