import json
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, ShortformJob
from core.schemas import ShortformJobCreate, ShortformJobResponse
from core.security import get_current_user
from core.config import UPLOAD_FOLDER, AWS_BUCKET_NAME, AWS_REGION
from services.shortform import run_shortform_task

router = APIRouter(prefix="/shortform-jobs", tags=["shortform"])

VALID_STYLES = ["action", "instagram", "tiktok", "humor", "documentary"]


@router.post("/", response_model=ShortformJobResponse)
async def create_shortform_job(
    body: ShortformJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.style not in VALID_STYLES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 스타일. 가능: {VALID_STYLES}")
    if len(body.video_ids) < 1:
        raise HTTPException(status_code=400, detail="영상이 최소 1개 필요합니다")

    videos = []
    for vid_id in body.video_ids:
        v = db.query(Video).filter(Video.id == vid_id, Video.user_id == current_user.id).first()
        if not v:
            raise HTTPException(status_code=404, detail=f"영상 ID {vid_id}를 찾을 수 없습니다")
        videos.append(v)

    job = ShortformJob(
        user_id=current_user.id, video_id=videos[0].id,
        video_ids_json=json.dumps(body.video_ids),
        style=body.style, duration_sec=body.duration_sec, status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if AWS_BUCKET_NAME:
        video_paths = [f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{v.filename}" for v in videos]
    else:
        video_paths = [os.path.abspath(os.path.join(UPLOAD_FOLDER, v.filename)) for v in videos]
    run_shortform_task.delay(job.id, video_paths, body.style, body.duration_sec)
    return job


@router.get("/", response_model=List[ShortformJobResponse])
async def list_shortform_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(ShortformJob).filter(ShortformJob.user_id == current_user.id).order_by(ShortformJob.created_at.desc()).all()


@router.get("/{job_id}", response_model=ShortformJobResponse)
async def get_shortform_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(ShortformJob).filter(ShortformJob.id == job_id, ShortformJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="숏폼 작업을 찾을 수 없습니다")
    return job
