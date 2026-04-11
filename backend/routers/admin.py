"""관리자 API - 영상 배정, OCR 결과 조회/수정"""
import tempfile

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, Video, CameraClip, DetectedBib, ClipMatch
from core.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME, AWS_REGION
from core.utils import run_in_thread
from services.matching import auto_process

router = APIRouter(prefix="/admin", tags=["admin"])


# ── 기존: 수동 영상 배정 ─────────────────────────────────────

class AssignRequest(BaseModel):
    user_id: int
    video_id: int


@router.post("/assign")
def assign_video(req: AssignRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저 없음")

    video = db.query(Video).filter(Video.id == req.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="영상 없음")

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    try:
        s3.download_file(AWS_BUCKET_NAME, f"videos/{video.filename}", tmp.name)
    except ClientError as e:
        raise HTTPException(status_code=404, detail=f"S3 다운로드 실패: {str(e)}")
    finally:
        tmp.close()

    video.user_id = req.user_id
    db.commit()

    run_in_thread(auto_process, req.user_id, tmp.name)
    return {"ok": True, "message": "자세분석/베스트컷/숏폼 자동 실행 시작"}


# ── OCR 결과 조회 ─────────────────────────────────────────────

@router.get("/ocr-results")
def get_ocr_results(
    clip_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """
    OCR 인식 결과 전체 조회.
    - clip_id: 특정 클립만 조회
    - status: pending / matched / failed / corrected
    """
    query = db.query(DetectedBib)
    if clip_id:
        query = query.filter(DetectedBib.clip_id == clip_id)
    if status:
        query = query.filter(DetectedBib.status == status)

    results = query.order_by(DetectedBib.created_at.desc()).all()

    return [
        {
            "id":           r.id,
            "clip_id":      r.clip_id,
            "raw_bib":      r.raw_bib,        # OCR 원본 인식값
            "assigned_bib": r.assigned_bib,   # 실제 배정값 (수정 가능)
            "confidence":   round(r.confidence, 3) if r.confidence else None,
            "start_sec":    r.start_sec,
            "end_sec":      r.end_sec,
            "status":       r.status,
            "created_at":   r.created_at.isoformat(),
        }
        for r in results
    ]


# ── OCR 결과 수정 (배번 오인식 수정) ──────────────────────────

class CorrectBibRequest(BaseModel):
    new_bib: str   # 올바른 배번


@router.patch("/ocr-results/{detected_bib_id}/correct")
def correct_bib(
    detected_bib_id: int,
    req: CorrectBibRequest,
    db: Session = Depends(get_db),
):
    """
    OCR 오인식 수정 + 클립 재배정.
    예: "1Z34" → "1234" 로 수정하면
    → 기존 매칭 삭제 → "1234" 유저 찾기/생성 → 재매칭 → auto_process
    """
    from services.ocr_classifier import reassign_clip

    record = db.query(DetectedBib).filter(DetectedBib.id == detected_bib_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="DetectedBib 없음")

    result = reassign_clip(
        clip_id=record.clip_id,
        new_bib=req.new_bib,
        detected_bib_id=detected_bib_id,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "ok": True,
        "clip_id": record.clip_id,
        "old_bib": record.raw_bib,
        "new_bib": req.new_bib,
        "user_id": result["user_id"],
        "username": result["username"],
    }


# ── 클립 수동 재배정 ──────────────────────────────────────────

class ReassignClipRequest(BaseModel):
    bib_number: str   # 재배정할 배번


@router.patch("/clips/{clip_id}/reassign")
def reassign_clip_endpoint(
    clip_id: int,
    req: ReassignClipRequest,
    db: Session = Depends(get_db),
):
    """
    특정 클립을 다른 배번(유저)으로 강제 재배정.
    DetectedBib 레코드 없이도 사용 가능.
    """
    from services.ocr_classifier import reassign_clip

    result = reassign_clip(clip_id=clip_id, new_bib=req.bib_number)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "ok": True,
        "clip_id": clip_id,
        "bib_number": req.bib_number,
        "user_id": result["user_id"],
        "username": result["username"],
    }


# ── 유저 배번 수정 ────────────────────────────────────────────

class UpdateBibRequest(BaseModel):
    bib_number: str


@router.patch("/users/{user_id}/bib")
def update_user_bib(
    user_id: int,
    req: UpdateBibRequest,
    db: Session = Depends(get_db),
):
    """유저 배번 직접 수정."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저 없음")

    user.bib_number = req.bib_number
    db.commit()

    return {"ok": True, "user_id": user_id, "bib_number": req.bib_number}


# ── 유저 목록 조회 ────────────────────────────────────────────

@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    """전체 유저 목록 + 배번 조회."""
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id":         u.id,
            "username":   u.username,
            "email":      u.email,
            "bib_number": u.bib_number,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


# ── 클립 목록 조회 ────────────────────────────────────────────

@router.get("/clips")
def get_clips(db: Session = Depends(get_db)):
    """전체 카메라 클립 + OCR 인식 결과 요약."""
    clips = db.query(CameraClip).order_by(CameraClip.created_at.desc()).limit(100).all()
    result = []
    for c in clips:
        bibs = db.query(DetectedBib).filter(DetectedBib.clip_id == c.id).all()
        matches = db.query(ClipMatch).filter(ClipMatch.clip_id == c.id).all()
        result.append({
            "clip_id":    c.id,
            "filename":   c.filename,
            "s3_url":     c.s3_url,
            "clip_start": c.clip_start.isoformat() if c.clip_start else None,
            "clip_end":   c.clip_end.isoformat() if c.clip_end else None,
            "detected_bibs": [
                {"id": b.id, "raw_bib": b.raw_bib, "assigned_bib": b.assigned_bib, "status": b.status}
                for b in bibs
            ],
            "matched_users": [
                {"user_id": m.user_id, "status": m.status}
                for m in matches
            ],
            "created_at": c.created_at.isoformat(),
        })
    return result
