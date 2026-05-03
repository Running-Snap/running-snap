import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, AnalysisJob
from core.schemas import AnalysisJobCreate, AnalysisJobResponse
from core.security import get_current_user
from core.config import UPLOAD_FOLDER, AWS_BUCKET_NAME, AWS_REGION
from services.analysis import run_analysis_task

router = APIRouter(prefix="/analysis-jobs", tags=["analysis"])


@router.post("/", response_model=AnalysisJobResponse)
async def create_analysis_job(
    body: AnalysisJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == body.video_id, Video.user_id == current_user.id).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    job = AnalysisJob(user_id=current_user.id, video_id=body.video_id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    # S3에 저장된 경우 S3 URL, 로컬에 있으면 로컬 경로 사용
    s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video.filename}"
    local_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))
    video_path = s3_url if AWS_BUCKET_NAME else local_path
    run_analysis_task.delay(job.id, video_path)
    return job


@router.get("/", response_model=List[AnalysisJobResponse])
async def list_analysis_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AnalysisJob).filter(AnalysisJob.user_id == current_user.id).order_by(AnalysisJob.created_at.desc()).all()


@router.get("/{job_id}", response_model=AnalysisJobResponse)
async def get_analysis_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id, AnalysisJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다")
    return job
