import json
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, AnalysisJob, PoseVideoJob
from core.schemas import PoseVideoJobCreate, PoseVideoJobResponse
from core.security import get_current_user
from core.utils import run_in_thread
from core.config import UPLOAD_FOLDER, AWS_BUCKET_NAME, AWS_REGION
from services.pose_video import run_pose_video_task

router = APIRouter(prefix="/pose-video-jobs", tags=["pose-video"])


@router.post("/", response_model=PoseVideoJobResponse)
async def create_pose_video_job(
    body: PoseVideoJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 영상 확인
    video = db.query(Video).filter(Video.id == body.video_id, Video.user_id == current_user.id).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    # 분석 결과 확인
    aj = db.query(AnalysisJob).filter(
        AnalysisJob.id == body.analysis_job_id,
        AnalysisJob.user_id == current_user.id
    ).first()
    if not aj or not aj.result_json:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")

    try:
        feedback_data = json.loads(aj.result_json)
    except Exception:
        raise HTTPException(status_code=400, detail="분석 결과 파싱 실패")

    # 영상 경로
    import os
    if AWS_BUCKET_NAME:
        video_path = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video.filename}"
    else:
        video_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))

    job = PoseVideoJob(
        user_id=current_user.id,
        video_id=body.video_id,
        analysis_job_id=body.analysis_job_id,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_in_thread, run_pose_video_task, job.id, video_path, feedback_data)
    return job


@router.get("/", response_model=List[PoseVideoJobResponse])
async def list_pose_video_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(PoseVideoJob).filter(
        PoseVideoJob.user_id == current_user.id
    ).order_by(PoseVideoJob.created_at.desc()).all()


@router.get("/{job_id}", response_model=PoseVideoJobResponse)
async def get_pose_video_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(PoseVideoJob).filter(
        PoseVideoJob.id == job_id,
        PoseVideoJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    return job
