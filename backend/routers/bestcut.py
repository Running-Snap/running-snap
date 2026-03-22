import json
import os
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User, Video, BestCutJob
from schemas import BestCutJobCreate, BestCutJobResponse
from core.security import get_current_user
from core.utils import run_in_thread
from core.config import UPLOAD_FOLDER
from services.bestcut import run_bestcut_task

router = APIRouter(prefix="/bestcut-jobs", tags=["bestcut"])


@router.post("/", response_model=BestCutJobResponse)
async def create_bestcut_job(
    body: BestCutJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not 1 <= body.photo_count <= 10:
        raise HTTPException(status_code=400, detail="photo_count는 1~10 사이여야 합니다")
    if len(body.video_ids) < 1:
        raise HTTPException(status_code=400, detail="영상을 최소 1개 이상 선택해주세요")

    videos = []
    for vid_id in body.video_ids:
        v = db.query(Video).filter(Video.id == vid_id, Video.user_id == current_user.id).first()
        if not v:
            raise HTTPException(status_code=404, detail=f"영상 ID {vid_id}를 찾을 수 없습니다")
        videos.append(v)

    job = BestCutJob(
        user_id=current_user.id, video_id=videos[0].id,
        video_ids_json=json.dumps(body.video_ids),
        photo_count=body.photo_count, status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    video_paths = [os.path.abspath(os.path.join(UPLOAD_FOLDER, v.filename)) for v in videos]
    background_tasks.add_task(run_in_thread, run_bestcut_task, job.id, video_paths, body.photo_count)
    return job


@router.get("/", response_model=List[BestCutJobResponse])
async def list_bestcut_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(BestCutJob).filter(BestCutJob.user_id == current_user.id).order_by(BestCutJob.created_at.desc()).all()


@router.get("/{job_id}", response_model=BestCutJobResponse)
async def get_bestcut_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(BestCutJob).filter(BestCutJob.id == job_id, BestCutJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="베스트 컷 작업을 찾을 수 없습니다")
    return job
