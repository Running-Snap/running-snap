"""자동 처리 서비스 - 영상 분석/베스트컷/숏폼 자동 실행"""
import os
import json
from datetime import datetime

from core.database import SessionLocal
from core.models import Video, AnalysisJob, BestCutJob, PoseVideoJob
from core.celery_app import celery_app
from services.analysis import run_analysis_task
from services.bestcut import run_bestcut_task
from services.pose_video import run_pose_video_task
from services.cert import run_cert_task


@celery_app.task(name="matching.upload_pipeline", bind=True, max_retries=1)
def run_upload_pipeline(self, user_id: int, video_id: int, video_path: str, analysis_job_id: int, bestcut_job_id: int, bib: str = "upload"):
    """수동 업로드 파이프라인 - 자세분석 → 자세분석영상 → 베스트컷 순차 실행"""
    print(f"[UPLOAD] 유저 {user_id} 파이프라인 시작 (video_id={video_id}, bib={bib})")
    try:
        # Step 1: 자세분석
        print(f"[UPLOAD] Step 1: 자세분석 시작 (analysis_job_id={analysis_job_id})")
        run_analysis_task(analysis_job_id, video_path)

        # 자세분석 결과 가져오기
        db = SessionLocal()
        try:
            analysis_job = db.query(AnalysisJob).filter(AnalysisJob.id == analysis_job_id).first()
            feedback_data = None
            if analysis_job and analysis_job.result_json:
                try:
                    feedback_data = json.loads(analysis_job.result_json)
                except Exception:
                    feedback_data = None

            # Step 2: 자세분석 영상 job 생성
            pose_video_job = PoseVideoJob(
                user_id=user_id,
                video_id=video_id,
                analysis_job_id=analysis_job_id,
                status="pending",
            )
            db.add(pose_video_job)
            db.commit()
            db.refresh(pose_video_job)
            pv_id = pose_video_job.id
        except Exception as e:
            print(f"[UPLOAD] 자세분석 영상 job 생성 실패: {e}")
            pv_id = None
            feedback_data = None
        finally:
            db.close()

        # Step 2: 자세분석 영상
        if pv_id:
            print(f"[UPLOAD] Step 2: 자세분석 영상 시작 (pose_video_job_id={pv_id})")
            run_pose_video_task(pv_id, video_path, feedback_data or {}, user_id=user_id, bib=bib)

        # Step 3: 베스트컷
        print(f"[UPLOAD] Step 3: 베스트컷 시작 (bestcut_job_id={bestcut_job_id})")
        run_bestcut_task(bestcut_job_id, [video_path], 5, user_id=user_id, bib=bib)

        print(f"[UPLOAD] 유저 {user_id} 파이프라인 완료 (video_id={video_id})")

    except Exception as e:
        print(f"[UPLOAD] 파이프라인 실패 (video_id={video_id}): {e}")


# camera_id → distance_km 매핑
CAMERA_DISTANCE_MAP = {
    "cam1": 5.0,
    "cam2": 10.0,
}


@celery_app.task(name="matching.auto_process", bind=True, max_retries=1)
def auto_process(self, user_id: int, trimmed_path: str, camera_id: str = "cam1", bib: str = ""):
    """트림된 영상으로 자세분석 → 자세분석영상 → 베스트컷 자동 실행"""
    print(f"[AUTO] 유저 {user_id} 자동 처리 시작: {os.path.basename(trimmed_path)}")
    _auto_process_impl(user_id, trimmed_path, camera_id, bib)


def _auto_process_impl(user_id: int, trimmed_path: str, camera_id: str = "cam1", bib: str = ""):
    db = SessionLocal()
    try:
        # 1) Video 레코드 생성 → 내 영상에 표시됨
        filename = os.path.basename(trimmed_path)
        video = Video(user_id=user_id, filename=filename)
        db.add(video)
        db.commit()
        db.refresh(video)
        video_id = video.id
        print(f"[AUTO] Video 레코드 생성: video_id={video_id}")

        # 2) 자세분석 job 생성
        analysis_job = AnalysisJob(user_id=user_id, video_id=video_id, status="pending")
        db.add(analysis_job)
        db.commit()
        db.refresh(analysis_job)
        a_id = analysis_job.id

    except Exception as e:
        print(f"[AUTO] 잡 생성 실패: {e}")
        return
    finally:
        db.close()

    # ── Step 1: 자세분석 (동기 - 완료까지 대기) ──────────────────────
    print(f"[AUTO] Step 1: 자세분석 시작 (analysis_job_id={a_id})")
    run_analysis_task(a_id, trimmed_path)

    # 자세분석 결과 가져오기
    db = SessionLocal()
    try:
        analysis_job = db.query(AnalysisJob).filter(AnalysisJob.id == a_id).first()
        feedback_data = None
        if analysis_job and analysis_job.result_json:
            try:
                feedback_data = json.loads(analysis_job.result_json)
            except Exception:
                feedback_data = None

        # ── Step 2: 자세분석 영상 job 생성 ──────────────────────────
        pose_video_job = PoseVideoJob(
            user_id=user_id,
            video_id=video_id,
            analysis_job_id=a_id,
            status="pending",
        )
        db.add(pose_video_job)
        db.commit()
        db.refresh(pose_video_job)
        pv_id = pose_video_job.id

        # ── Step 3: 베스트컷 job 생성 ───────────────────────────────
        bestcut_job = BestCutJob(
            user_id=user_id,
            video_id=video_id,
            video_ids_json=json.dumps([video_id]),
            photo_count=5,
            status="pending",
        )
        db.add(bestcut_job)
        db.commit()
        db.refresh(bestcut_job)
        b_id = bestcut_job.id

    except Exception as e:
        print(f"[AUTO] 잡 생성 실패: {e}")
        return
    finally:
        db.close()

    # ── Step 2: 자세분석 영상 (동기 - 완료까지 대기) ─────────────────
    print(f"[AUTO] Step 2: 자세분석 영상 시작 (pose_video_job_id={pv_id})")
    run_pose_video_task(pv_id, trimmed_path, feedback_data or {}, user_id=user_id, bib=bib)

    # ── Step 3: 베스트컷 ─────────────────────────────────────────
    distance_km = CAMERA_DISTANCE_MAP.get(camera_id, 10.0)
    poster_config = {"distance_km": distance_km}
    print(f"[AUTO] Step 3: 베스트컷 시작 (bestcut_job_id={b_id}, distance={distance_km}km)")
    run_bestcut_task(b_id, [trimmed_path], 5, poster_config, user_id=user_id, bib=bib)

    print(f"[AUTO] 유저 {user_id} 자동 처리 완료 (video_id={video_id})")
