import os
import shutil
from datetime import datetime

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, CameraClip, ClipMatch
from core.security import get_current_user
from core.config import (
    CAMERA_CLIPS_FOLDER,
    AWS_BUCKET_NAME, AWS_REGION,
)
from services.video import get_s3_client
from services.ocr_classifier import run_ocr_matching

router = APIRouter(tags=["camera"])


@router.post("/camera-clip")
async def upload_camera_clip(
    file: UploadFile = File(...),
    clip_start: str = Form(""),
    clip_end: str = Form(""),
    camera_id: str = Form("cam1"),
    db: Session = Depends(get_db),
):
    # 클립 시간 파싱
    try:
        start_dt = datetime.fromisoformat(clip_start.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt   = datetime.fromisoformat(clip_end.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        now      = datetime.utcnow()
        start_dt = end_dt = now

    # 파일 확장자 결정
    content_type = file.content_type or ""
    ext      = ".mp4" if "mp4" in content_type or not content_type else ".webm"
    filename = f"clip_{camera_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    s3_key   = f"camera_clips/{filename}"
    s3_url   = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

    # S3 업로드 (실패 시 로컬 폴백)
    try:
        get_s3_client().upload_fileobj(file.file, AWS_BUCKET_NAME, s3_key)
    except ClientError:
        file.file.seek(0)
        filepath = os.path.join(CAMERA_CLIPS_FOLDER, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        s3_url = None

    # DB에 클립 저장
    clip = CameraClip(
        filename=filename,
        s3_url=s3_url,
        camera_id=camera_id,
        clip_start=start_dt,
        clip_end=end_dt,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)

    # OCR 배번 인식 → 유저 매칭 (백그라운드)
    if s3_url:
        run_ocr_matching.delay(s3_url, clip.id)
        print(f"[CLIP] 클립 {clip.id} 업로드 완료 → OCR Celery 큐 등록")
    else:
        print(f"[CLIP] 클립 {clip.id} 로컬 저장 (S3 실패) → OCR 건너뜀")

    return {"ok": True, "clip_id": clip.id}


@router.get("/my-clips")
async def get_my_clips(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matches = (
        db.query(ClipMatch)
        .filter(ClipMatch.user_id == current_user.id, ClipMatch.status == "done")
        .order_by(ClipMatch.created_at.desc())
        .all()
    )
    result = []
    for m in matches:
        clip = db.query(CameraClip).filter(CameraClip.id == m.clip_id).first()
        result.append({
            "match_id":    m.id,
            "clip_id":     m.clip_id,
            "camera_id":   clip.camera_id if clip else None,
            "trimmed_url": m.trimmed_filename,
            "enter_time":  m.enter_time.isoformat() if m.enter_time else None,
            "exit_time":   m.exit_time.isoformat() if m.exit_time else None,
            "created_at":  m.created_at.isoformat(),
        })
    return result
