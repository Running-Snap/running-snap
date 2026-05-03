"""인증영상 생성 백그라운드 작업 (Nike 스타일)"""
import json
import os
import shutil
from datetime import datetime

from core.database import SessionLocal
from core.utils import KST
from core.celery_app import celery_app
from core.models import CertJob
from core.config import (
    VIDEO_EDITOR_AVAILABLE, VIDEO_EDITOR_LOCK, VIDEO_EDITOR_PATH,
    OUTPUT_CERT_FOLDER, OUTPUT_FOLDER,
)
from services.video import upload_to_s3, download_from_s3_if_needed


@celery_app.task(name="cert.run", bind=True, max_retries=2)
def run_cert_task(self, job_id: int, video_path: str, mode: str, event_config: dict, bib: str = ""):
    db = SessionLocal()
    tmp_path = None
    try:
        job = db.query(CertJob).filter(CertJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # S3 URL이면 로컬로 다운로드
        local_path, is_tmp = download_from_s3_if_needed(video_path) if video_path else ("", False)
        if is_tmp and local_path:
            tmp_path = local_path

        if not local_path or not os.path.exists(local_path):
            raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}")

        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        bib_part = bib if bib else str(job_id)
        output_name = f"cert_{bib_part}_{ts}.mp4"
        output_path = os.path.join(OUTPUT_CERT_FOLDER, output_name)

        success = False

        # RunningPipeline 사용 (VIDEO_EDITOR_AVAILABLE)
        if VIDEO_EDITOR_AVAILABLE:
            try:
                import sys
                sys.path.insert(0, VIDEO_EDITOR_PATH)
                from src.running_pipeline import RunningPipeline

                # date 자동 설정 (KST 기준)
                ec = dict(event_config)
                if not ec.get("date"):
                    ec["date"] = datetime.now(KST).strftime("%Y.%m.%d")

                orig = os.getcwd()
                os.chdir(VIDEO_EDITOR_PATH)
                try:
                    with VIDEO_EDITOR_LOCK:
                        pipeline = RunningPipeline(
                            qwen_api_key=None,   # Ollama 로컬 사용
                        )
                        result = pipeline.run(
                            video_path=local_path,
                            event_config=ec,
                            feedback_data=None,   # 자세분석 생략
                            output_dir=OUTPUT_FOLDER,
                            cert_mode=mode,       # "simple" or "full"
                        )
                    print(f"[CERT] RunningPipeline 결과: success={result.success}, cert={result.cert_path}")
                    if result.success and result.cert_path and os.path.exists(result.cert_path):
                        shutil.move(result.cert_path, output_path)
                        success = True
                    elif not result.success:
                        print(f"[CERT] RunningPipeline 실패: {result.error}")
                finally:
                    os.chdir(orig)
            except Exception as e:
                print(f"[CERT] RunningPipeline 예외: {e}, fallback으로 전환")

        # Fallback: 원본 영상 복사
        if not success:
            print(f"[CERT] Fallback: 원본 영상 복사 → {output_path}")
            shutil.copy2(local_path, output_path)
            success = True

        # S3 업로드
        s3_url = upload_to_s3(output_path, "cert")
        final_url = s3_url if s3_url else f"/outputs/cert/{output_name}"

        job.output_filename = final_url
        job.status = "done"
        db.commit()
        print(f"[CERT] 완료: {final_url}")

    except Exception as e:
        print(f"[CERT] 작업 실패 (job_id={job_id}): {e}")
        job = db.query(CertJob).filter(CertJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.event_config_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
