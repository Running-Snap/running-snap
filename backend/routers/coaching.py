import json
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, AnalysisJob, CoachingJob
from core.schemas import CoachingJobCreate, CoachingJobResponse
from core.security import get_current_user
from core.config import UPLOAD_FOLDER, AWS_BUCKET_NAME
from services.coaching import run_coaching_task

router = APIRouter(prefix="/coaching-jobs", tags=["coaching"])

DEFAULT_COACHING = "좋은 자세를 유지하며 달리세요. 케이던스와 착지 자세에 집중해보세요."


@router.post("/", response_model=CoachingJobResponse)
async def create_coaching_job(
    body: CoachingJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == body.video_id, Video.user_id == current_user.id).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    coaching_text = body.coaching_text.strip() if body.coaching_text else ""

    # 분석 결과에서 coaching_report 자동 추출
    if not coaching_text and body.analysis_job_id:
        aj = db.query(AnalysisJob).filter(
            AnalysisJob.id == body.analysis_job_id, AnalysisJob.user_id == current_user.id
        ).first()
        if aj and aj.result_json:
            try:
                data          = json.loads(aj.result_json)
                coaching_text = data.get("coaching_report", "") or " ".join(
                    fb.get("message", "") for fb in data.get("feedbacks", [])
                )
            except Exception:
                pass

    if not coaching_text:
        coaching_text = DEFAULT_COACHING

    job = CoachingJob(user_id=current_user.id, video_id=body.video_id, coaching_text=coaching_text, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    video_path = video.s3_url if (AWS_BUCKET_NAME and video.s3_url) else os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))
    run_coaching_task.delay(job.id, video_path, coaching_text)
    return job


@router.get("/", response_model=List[CoachingJobResponse])
async def list_coaching_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(CoachingJob).filter(CoachingJob.user_id == current_user.id).order_by(CoachingJob.created_at.desc()).all()


@router.get("/{job_id}", response_model=CoachingJobResponse)
async def get_coaching_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(CoachingJob).filter(CoachingJob.id == job_id, CoachingJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="코칭 영상 작업을 찾을 수 없습니다")
    return job
