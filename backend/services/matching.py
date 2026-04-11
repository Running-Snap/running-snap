"""자동 처리 서비스 - 영상 분석/베스트컷/숏폼 자동 실행"""
import os
import json

from core.database import SessionLocal
from core.models import Video, AnalysisJob, BestCutJob, ShortformJob
from services.analysis import run_analysis_task
from services.bestcut import run_bestcut_task
from services.shortform import run_shortform_task


def auto_process(user_id: int, trimmed_path: str):
    """트림된 영상으로 분석/베스트컷/숏폼 자동 실행"""
    print(f"[AUTO] 유저 {user_id} 자동 처리 시작: {os.path.basename(trimmed_path)}")
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

        # 2) 3가지 job 생성 (video_id 연결)
        analysis_job  = AnalysisJob(user_id=user_id, video_id=video_id, status="pending")
        bestcut_job   = BestCutJob(user_id=user_id, video_id=video_id, video_ids_json=json.dumps([video_id]), photo_count=5, status="pending")
        shortform_job = ShortformJob(user_id=user_id, video_id=video_id, video_ids_json=json.dumps([video_id]), style="action", duration_sec=30.0, status="pending")
        db.add_all([analysis_job, bestcut_job, shortform_job])
        db.commit()
        db.refresh(analysis_job)
        db.refresh(bestcut_job)
        db.refresh(shortform_job)
        a_id, b_id, s_id = analysis_job.id, bestcut_job.id, shortform_job.id
    except Exception as e:
        print(f"[AUTO] 잡 생성 실패: {e}")
        return
    finally:
        db.close()

    run_analysis_task(a_id, trimmed_path)
    run_bestcut_task(b_id, [trimmed_path], 5)
    run_shortform_task(s_id, [trimmed_path], "action", 30.0)
    print(f"[AUTO] 유저 {user_id} 자동 처리 완료 (video_id={video_id})")
