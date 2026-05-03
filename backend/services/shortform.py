"""숏폼 생성 백그라운드 작업"""
import os
import shutil
from datetime import datetime

from core.database import SessionLocal
from core.models import ShortformJob
from core.config import (
    VIDEO_EDITOR_AVAILABLE, VIDEO_EDITOR_LOCK, VIDEO_EDITOR_PATH,
    ANTHROPIC_API_KEY, OUTPUT_FOLDER, OUTPUT_VIDEOS_FOLDER,
)


def _get_editor_config():
    from src.api import VideoEditorConfig, ProcessingMode

    # 1순위: Ollama 로컬 (qwen2.5vl:7b) - 설치되면 자동으로 사용
    try:
        import requests as req
        if req.get("http://localhost:11434/api/version", timeout=2).status_code == 200:
            print("[SHORTFORM] Ollama 감지 → LOCAL 모드 (qwen2.5vl:7b)")
            return VideoEditorConfig(
                mode=ProcessingMode.LOCAL,
                ollama_model="qwen2.5vl:7b",
                output_dir=OUTPUT_FOLDER,
                cache_enabled=False,
            )
    except Exception:
        pass

    # 2순위: MOCK 모드 (API 키 없이 동작)
    print("[SHORTFORM] Ollama 미설치 → MOCK 모드")
    return VideoEditorConfig(mode=ProcessingMode.MOCK, output_dir=OUTPUT_FOLDER, cache_enabled=False)


from core.celery_app import celery_app
from services.video import upload_to_s3, download_from_s3_if_needed


@celery_app.task(name="shortform.run", bind=True, max_retries=2)
def run_shortform_task(self, job_id: int, video_paths: list, style: str, duration_sec: float):
    db = SessionLocal()
    tmp_path = None
    try:
        job = db.query(ShortformJob).filter(ShortformJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        raw_path = video_paths[0] if video_paths else None
        primary_path, is_tmp = download_from_s3_if_needed(raw_path) if raw_path else ("", False)
        if is_tmp:
            tmp_path = primary_path
        output_filename = None

        if VIDEO_EDITOR_AVAILABLE and primary_path and os.path.exists(primary_path):
            from core.config import QWEN_API_KEY
            print(f"[SHORTFORM] AI 처리 시작 - job_id={job_id}, style={style}, duration={duration_sec}s")
            try:
                from src.api import VideoEditorAPI
                with VIDEO_EDITOR_LOCK:
                    orig = os.getcwd()
                    os.chdir(VIDEO_EDITOR_PATH)
                    try:
                        result = VideoEditorAPI(_get_editor_config()).process(
                            video_path=primary_path,
                            duration=duration_sec,
                            style=style,
                            photo_count=0,
                        )
                    finally:
                        os.chdir(orig)
                print(f"[SHORTFORM] result.success={result.success}, video_path={result.video_path}, error={getattr(result, 'error', None)}")
                if result.success and result.video_path and os.path.exists(result.video_path):
                    base = os.path.basename(result.video_path)
                    dest = os.path.join(OUTPUT_VIDEOS_FOLDER, base)
                    if result.video_path != dest:
                        shutil.move(result.video_path, dest)
                    output_filename = base
                    print(f"[SHORTFORM] AI 처리 완료 - {output_filename}")
                else:
                    print(f"[SHORTFORM] AI 처리 실패 - 원본 복사로 대체")
            except Exception as e:
                import traceback
                print(f"[SHORTFORM ERROR] {e}\n{traceback.format_exc()}")
        else:
            print(f"[SHORTFORM] VIDEO_EDITOR 미사용 - VIDEO_EDITOR_AVAILABLE={VIDEO_EDITOR_AVAILABLE}")

        if not output_filename:
            ts              = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"shortform_{job_id}_{ts}.mp4"
            dest            = os.path.join(OUTPUT_VIDEOS_FOLDER, output_filename)
            if primary_path and os.path.exists(primary_path):
                shutil.copy2(primary_path, dest)

        output_path = os.path.join(OUTPUT_VIDEOS_FOLDER, output_filename)
        if os.path.exists(output_path):
            s3_url = upload_to_s3(output_path, "shortform")
            job.output_filename = s3_url if s3_url else output_filename
        else:
            job.output_filename = output_filename
        job.status = "done"
        db.commit()
    except Exception:
        job = db.query(ShortformJob).filter(ShortformJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
