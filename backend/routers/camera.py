import os
import shutil
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserLocation, CameraClip, ClipMatch
from core.security import get_current_user
from core.utils import run_in_thread
from core.config import CAMERA_CLIPS_FOLDER
from services.matching import process_clip_matching

router = APIRouter(tags=["camera"])


class LocationIn(BaseModel):
    lat: float
    lng: float
    recorded_at: str  # ISO8601


# GPS 기능 보류 중
# @router.post("/location")
# async def post_location(...)


@router.post("/camera-clip")
async def upload_camera_clip(
    file: UploadFile = File(...),
    camera_lat: float = Form(0.0),
    camera_lng: float = Form(0.0),
    clip_start: str = Form(""),
    clip_end: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    try:
        start_dt = datetime.fromisoformat(clip_start.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt   = datetime.fromisoformat(clip_end.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        now      = datetime.utcnow()
        start_dt = end_dt = now

    content_type = file.content_type or ""
    ext          = ".mp4" if "mp4" in content_type else ".webm"
    filename     = f"clip_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    filepath     = os.path.join(CAMERA_CLIPS_FOLDER, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    clip = CameraClip(
        filename=filename, camera_lat=camera_lat, camera_lng=camera_lng,
        clip_start=start_dt, clip_end=end_dt,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)

    background_tasks.add_task(run_in_thread, process_clip_matching, clip.id)
    return {"ok": True, "clip_id": clip.id}


@router.get("/my-clips")
async def get_my_clips(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    matches = (
        db.query(ClipMatch)
        .filter(ClipMatch.user_id == current_user.id, ClipMatch.status == "done")
        .order_by(ClipMatch.created_at.desc())
        .all()
    )
    return [
        {
            "match_id":    m.id,
            "clip_id":     m.clip_id,
            "trimmed_url": f"/outputs/trimmed_clips/{m.trimmed_filename}" if m.trimmed_filename else None,
            "enter_time":  m.enter_time.isoformat() if m.enter_time else None,
            "exit_time":   m.exit_time.isoformat() if m.exit_time else None,
            "created_at":  m.created_at.isoformat(),
        }
        for m in matches
    ]
