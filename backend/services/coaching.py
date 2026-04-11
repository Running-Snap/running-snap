"""코칭 영상 생성 백그라운드 작업"""
import os
import shutil
from datetime import datetime

from core.database import SessionLocal
from core.models import CoachingJob
from core.config import (
    VIDEO_EDITOR_AVAILABLE, VIDEO_EDITOR_LOCK, VIDEO_EDITOR_PATH, OUTPUT_COACHING_FOLDER,
)
from services.opencv import create_coaching_video
from services.video import upload_to_s3, download_from_s3_if_needed


def run_coaching_task(job_id: int, video_path: str, coaching_text: str):
    db = SessionLocal()
    tmp_path = None
    try:
        job = db.query(CoachingJob).filter(CoachingJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # S3 URL이면 로컬로 다운로드
        local_path, is_tmp = download_from_s3_if_needed(video_path) if video_path else ("", False)
        if is_tmp:
            tmp_path = local_path
        video_path = local_path or video_path

        ts              = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"coaching_{job_id}_{ts}.mp4"
        output_path     = os.path.abspath(os.path.join(OUTPUT_COACHING_FOLDER, output_filename))
        success         = False

        # 1순위: CoachingAPI (video-editor)
        if VIDEO_EDITOR_AVAILABLE and os.path.exists(video_path):
            try:
                from src.api import CoachingAPI, CoachingConfig
                with VIDEO_EDITOR_LOCK:
                    orig = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        config = CoachingConfig(
                            tts_enabled=True,
                            subtitle_enabled=True,
                            use_llm_script=False,
                            output_dir=OUTPUT_COACHING_FOLDER,
                        )
                        result  = CoachingAPI(config).create(
                            video_path=video_path,
                            coaching_text=coaching_text,
                            output_path=output_path,
                        )
                        success = result.success and result.video_path and os.path.exists(result.video_path)
                        if success and result.video_path != output_path:
                            shutil.move(result.video_path, output_path)
                    finally:
                        os.chdir(orig)
            except Exception:
                success = False

        # 2순위: OpenCV 자막 오버레이
        if not success and os.path.exists(video_path):
            success = create_coaching_video(video_path, coaching_text, output_path)

        # 3순위: 원본 복사
        if not success and os.path.exists(video_path):
            shutil.copy2(video_path, output_path)
            success = True

        if success and os.path.exists(output_path):
            s3_url = upload_to_s3(output_path, "coaching")
            job.output_filename = s3_url if s3_url else output_filename
            job.status          = "done"
        else:
            job.status = "failed"
        db.commit()
    except Exception:
        job = db.query(CoachingJob).filter(CoachingJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
