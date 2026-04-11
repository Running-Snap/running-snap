import json
import os
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, CertJob
from core.schemas import CertJobCreate, CertJobResponse
from core.security import get_current_user
from core.utils import run_in_thread
from core.config import UPLOAD_FOLDER, AWS_BUCKET_NAME, AWS_REGION
from services.cert import run_cert_task

router = APIRouter(prefix="/cert-jobs", tags=["cert"])


@router.post("/", response_model=CertJobResponse)
async def create_cert_job(
    body: CertJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.mode not in ("simple", "full"):
        raise HTTPException(status_code=400, detail="mode는 'simple' 또는 'full' 이어야 합니다")

    video = db.query(Video).filter(
        Video.id == body.video_id, Video.user_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(status_code=404, detail=f"영상 ID {body.video_id}를 찾을 수 없습니다")

    event_config = {
        "title":          body.title,
        "location":       body.location,
        "distance_km":    body.distance_km,
        "run_time":       body.run_time,
        "pace":           body.pace,
        "calories":       body.calories,
        "elevation_gain": body.elevation_gain,
        "avg_heart_rate": body.avg_heart_rate,
        "cadence":        body.cadence,
        "color_scheme":   body.color_scheme,
    }

    job = CertJob(
        user_id=current_user.id,
        video_id=video.id,
        mode=body.mode,
        event_config_json=json.dumps(event_config, ensure_ascii=False),
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if AWS_BUCKET_NAME:
        video_path = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video.filename}"
    else:
        video_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, video.filename))

    background_tasks.add_task(
        run_in_thread, run_cert_task,
        job.id, video_path, body.mode, event_config,
    )
    return job


@router.get("/", response_model=List[CertJobResponse])
async def list_cert_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(CertJob)
        .filter(CertJob.user_id == current_user.id)
        .order_by(CertJob.created_at.desc())
        .all()
    )


@router.get("/{job_id}", response_model=CertJobResponse)
async def get_cert_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(CertJob).filter(
        CertJob.id == job_id, CertJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="인증영상 작업을 찾을 수 없습니다")
    return job
