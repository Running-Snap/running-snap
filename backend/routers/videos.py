import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import User, Video
from core.config import SECRET_KEY, ALGORITHM, UPLOAD_FOLDER
from core.security import get_current_user

router = APIRouter(tags=["videos"])


@router.post("/upload-video/")
async def upload_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_ext = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".webm"}
    ext         = os.path.splitext(file.filename or "")[1].lower()
    is_video    = (file.content_type and file.content_type.startswith("video/")) or ext in allowed_ext
    if not is_video:
        raise HTTPException(status_code=400, detail="비디오 파일만 업로드 가능합니다")

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{current_user.id}_{ts}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    db_video = Video(user_id=current_user.id, filename=filename)
    db.add(db_video)
    db.commit()
    db.refresh(db_video)

    return {
        "success":    True,
        "video_id":   db_video.id,
        "filename":   filename,
        "user_id":    current_user.id,
        "size_bytes": os.path.getsize(filepath),
        "video_url":  f"/videos/{filename}",
    }


@router.get("/videos/{filename}")
async def get_video(
    filename: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    raw_token = token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if not raw_token:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    try:
        payload  = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")
    if not filename.startswith(f"{user.id}_"):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")
    return FileResponse(filepath, media_type="video/mp4")


@router.get("/my-videos/")
async def get_my_videos(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    videos = db.query(Video).filter(Video.user_id == current_user.id).order_by(Video.id.asc()).all()
    return [
        {
            "video_id":   v.id,
            "filename":   v.filename,
            "size_bytes": os.path.getsize(os.path.join(UPLOAD_FOLDER, v.filename)) if os.path.exists(os.path.join(UPLOAD_FOLDER, v.filename)) else 0,
            "video_url":  f"/videos/{v.filename}",
        }
        for v in videos
    ]
