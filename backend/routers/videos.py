import os
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import User, Video
from core.config import (
    SECRET_KEY, ALGORITHM,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME, AWS_REGION,
)
from core.security import get_current_user

router = APIRouter(tags=["videos"])

def _s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


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
    s3_key   = f"videos/{filename}"

    try:
        s3 = _s3_client()
        s3.upload_fileobj(file.file, AWS_BUCKET_NAME, s3_key)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 업로드 실패: {str(e)}")

    db_video = Video(user_id=current_user.id, filename=filename)
    db.add(db_video)
    db.commit()
    db.refresh(db_video)

    video_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

    return {
        "success":   True,
        "video_id":  db_video.id,
        "filename":  filename,
        "user_id":   current_user.id,
        "video_url": video_url,
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

    s3_key = f"videos/{filename}"
    try:
        s3  = _s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=3600,
        )
    except ClientError as e:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")

    return {"video_url": url}


@router.get("/my-videos/")
async def get_my_videos(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    videos = db.query(Video).filter(Video.user_id == current_user.id).order_by(Video.id.asc()).all()
    s3 = _s3_client()
    result = []
    for v in videos:
        s3_key = f"videos/{v.filename}"
        try:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": AWS_BUCKET_NAME, "Key": s3_key},
                ExpiresIn=3600,
            )
        except ClientError:
            url = ""
        result.append({
            "video_id":  v.id,
            "filename":  v.filename,
            "video_url": url,
        })
    return result
