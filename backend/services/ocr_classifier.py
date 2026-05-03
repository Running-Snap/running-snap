"""
OCR 배번 인식 → 트림 → 연속 클립 합치기 → 유저 매칭 서비스

흐름:
1. 클립 S3 다운로드
2. YOLO + EasyOCR로 배번 인식 (start_sec, end_sec 포함)
3. detected_bibs 테이블에 결과 저장
4. 배번 등장 구간만 트림 (ffmpeg)
5. 이전 클립에 같은 배번이 있으면 합치기 (연속 클립 병합)
6. 최종 영상 S3 업로드
7. 유저 찾기/자동 생성 → ClipMatch 생성 → auto_process 실행
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from core.celery_app import celery_app
from datetime import timedelta

import boto3
from botocore.exceptions import ClientError

from core.config import (
    OCR_AVAILABLE,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME,
    AWS_REGION,
)

log = logging.getLogger(__name__)

# OCR 동시 실행 제한은 Celery worker concurrency로 대체

# 연속 클립 병합 허용 간격 (초) - 이전 클립 종료 후 이 시간 안에 다음 클립 시작이면 같은 러너로 판단
MERGE_GAP_SEC = 30


def _s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _download_from_s3(s3_url: str, dest_dir: str | None = None) -> str | None:
    """S3 URL을 임시 파일로 다운로드. 실패 시 None 반환."""
    try:
        s3_key = s3_url.split(".amazonaws.com/", 1)[-1]
        if dest_dir is None:
            dest_dir = tempfile.mkdtemp(prefix="ocr_clip_")
        filename = os.path.basename(s3_key)
        local_path = os.path.join(dest_dir, filename)

        print(f"[OCR] S3 다운로드: {s3_key} → {local_path}")
        _s3_client().download_file(AWS_BUCKET_NAME, s3_key, local_path)
        return local_path
    except Exception as e:
        print(f"[OCR] S3 다운로드 실패: {e}")
        return None


def _upload_to_s3(local_path: str, s3_folder: str) -> str | None:
    """로컬 파일을 S3에 업로드하고 URL 반환."""
    try:
        filename = os.path.basename(local_path)
        s3_key = f"{s3_folder}/{filename}"
        _s3_client().upload_file(local_path, AWS_BUCKET_NAME, s3_key)
        url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        print(f"[OCR] S3 업로드 완료: {url}")
        return url
    except Exception as e:
        print(f"[OCR] S3 업로드 실패: {e}")
        return None


def _run_ffmpeg_with_fallback(cmd_nvenc: list, cmd_cpu: list, timeout: int = 120) -> subprocess.CompletedProcess:
    """h264_nvenc 시도 후 실패 시 libx264로 fallback."""
    result = subprocess.run(cmd_nvenc, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        print("[OCR][FFMPEG] nvenc 실패 → libx264 fallback")
        result = subprocess.run(cmd_cpu, capture_output=True, timeout=timeout)
    return result


def _trim_video(input_path: str, output_path: str, start_sec: float, end_sec: float) -> bool:
    """ffmpeg으로 영상 구간 트림."""
    duration = max(1.0, end_sec - start_sec)
    try:
        base_args = ["ffmpeg", "-y", "-ss", str(start_sec), "-i", input_path, "-t", str(duration)]
        result = _run_ffmpeg_with_fallback(
            cmd_nvenc=base_args + ["-c:v", "h264_nvenc", "-preset", "fast", "-c:a", "aac", output_path],
            cmd_cpu=base_args + ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac", output_path],
            timeout=120,
        )
        ok = result.returncode == 0 and os.path.exists(output_path)
        if ok:
            print(f"[OCR] 트림 완료: {start_sec:.1f}s~{end_sec:.1f}s → {os.path.basename(output_path)}")
        else:
            print(f"[OCR] 트림 실패: {result.stderr.decode()[-200:]}")
        return ok
    except Exception as e:
        print(f"[OCR] 트림 오류: {e}")
        return False


def _concat_videos(clip_paths: list[str], output_path: str) -> bool:
    """ffmpeg으로 여러 클립 순서대로 합치기."""
    try:
        n = len(clip_paths)
        base_cmd = ["ffmpeg", "-y"]
        for p in clip_paths:
            base_cmd += ["-i", p]
        filter_str = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1[v]"
        result = _run_ffmpeg_with_fallback(
            cmd_nvenc=base_cmd + ["-filter_complex", filter_str, "-map", "[v]", "-c:v", "h264_nvenc", "-preset", "fast", output_path],
            cmd_cpu=base_cmd + ["-filter_complex", filter_str, "-map", "[v]", "-c:v", "libx264", "-preset", "fast", output_path],
            timeout=180,
        )
        ok = result.returncode == 0 and os.path.exists(output_path)
        if ok:
            print(f"[OCR] 합치기 완료: {len(clip_paths)}개 → {os.path.basename(output_path)}")
        else:
            print(f"[OCR] 합치기 실패: {result.stderr.decode()[-200:]}")
        return ok
    except Exception as e:
        print(f"[OCR] 합치기 오류: {e}")
        return False


def _run_ocr_on_file(local_path: str, clip_id: int) -> list[dict]:
    """OCR 실행 후 전체 트랙 이벤트 반환."""
    from person_appearance_report.analyzer import run_report
    from person_appearance_report.config import ReportConfig

    out_dir = tempfile.mkdtemp(prefix="ocr_out_")
    try:
        cfg = ReportConfig(
            video_source=local_path,
            mode="file",
            output_dir=out_dir,
            use_gpu_yolo=True,
            use_gpu_ocr=True,
            ocr_backend="easyocr",
            ocr_interval_frames=5,
            ocr_min_confidence=0.25,
            log_recognition=True,
            progress_log_interval_frames=120,
        )
        print(f"[OCR] 클립 {clip_id}: EasyOCR 분석 시작...")
        result = run_report(cfg)
        print(f"[OCR] 클립 {clip_id}: 완료 | "
              f"프레임={result.get('total_frames')} | "
              f"트랙={result.get('events_count')} | "
              f"배번인식={result.get('label_clips_count')}")

        events_json_path = result.get("outputs", {}).get("events_json", "")
        if not events_json_path or not os.path.exists(events_json_path):
            return []
        with open(events_json_path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _save_detected_bibs(db, clip_id: int, events: list[dict]) -> list:
    """OCR 결과를 detected_bibs 테이블에 저장. 배번 인식된 것만."""
    from core.models import DetectedBib

    saved = []
    labeled = [e for e in events if not str(e.get("label", "")).startswith("unknown_")]
    for e in labeled:
        bib = str(e.get("label", "")).strip()
        if not bib:
            continue
        conf_scores = e.get("confidence_scores", {})
        confidence = sum(conf_scores.values()) / len(conf_scores) if conf_scores else None

        record = DetectedBib(
            clip_id=clip_id,
            raw_bib=bib,
            assigned_bib=bib,
            confidence=confidence,
            start_sec=e.get("start_sec"),
            end_sec=e.get("end_sec"),
            status="pending",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        saved.append(record)
        print(f"[OCR] DetectedBib 저장: clip={clip_id} bib={bib} "
              f"{e.get('start_sec'):.1f}s~{e.get('end_sec'):.1f}s "
              f"conf={round(confidence, 3) if confidence else 'N/A'}")
    return saved


def _get_or_create_user(db, bib: str):
    """배번(username)으로 유저 찾기. 없으면 자동 생성."""
    from core.models import User
    from core.security import get_password_hash

    user = db.query(User).filter(User.username == bib).first()
    if user:
        print(f"[OCR] 배번 {bib} → 기존 계정 (id={user.id})")
        return user

    new_user = User(
        username=bib,
        email=None,
        hashed_password=get_password_hash(bib),
        bib_number=bib,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    print(f"[OCR] 배번 {bib} → 새 계정 생성 (id={new_user.id})")
    return new_user


def _find_prev_match(db, user_id: int, clip_start_time) -> object | None:
    """
    같은 유저의 이전 ClipMatch 중 실제 촬영 시간 기준으로
    현재 클립 시작 시간과 가장 가까운 것을 찾기.
    업로드 순서와 무관하게 clip_start/clip_end 실제 시간 기준으로 병합.
    """
    from core.models import ClipMatch, CameraClip

    # 현재 클립 시작 시간보다 이전에 종료된 클립 중 MERGE_GAP_SEC 이내인 것
    cutoff = clip_start_time - timedelta(seconds=MERGE_GAP_SEC)
    prev = (
        db.query(ClipMatch)
        .join(CameraClip, ClipMatch.clip_id == CameraClip.id)
        .filter(
            ClipMatch.user_id == user_id,
            ClipMatch.status == "done",
            CameraClip.clip_end >= cutoff,
            CameraClip.clip_end <= clip_start_time,  # 현재 클립 시작 전에 끝난 것
        )
        .order_by(CameraClip.clip_end.desc())  # 가장 최근에 끝난 것
        .first()
    )
    return prev


def _process_bib(db, detected, clip, local_clip_path: str, work_dir: str) -> str | None:
    """
    배번 1개에 대해:
    1. 등장 구간 트림
    2. 이전 클립과 연속이면 합치기
    3. S3 업로드
    최종 S3 URL 반환. 실패 시 None.
    """
    from core.models import ClipMatch, CameraClip
    import datetime

    bib = detected.assigned_bib
    start_sec = detected.start_sec or 0.0
    end_sec = detected.end_sec or 60.0

    # 1. 현재 클립에서 배번 등장 구간 트림
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    trimmed_path = os.path.join(work_dir, f"trim_{bib}_{ts}.mp4")
    if not _trim_video(local_clip_path, trimmed_path, start_sec, end_sec):
        print(f"[OCR] 배번 {bib} 트림 실패 → 전체 클립 사용")
        trimmed_path = local_clip_path

    user = _get_or_create_user(db, bib)

    # 2. 이전 연속 클립 확인
    prev_match = _find_prev_match(db, user.id, clip.clip_start)

    if prev_match and prev_match.trimmed_filename and prev_match.trimmed_filename.startswith("http"):
        print(f"[OCR] 배번 {bib}: 이전 클립 발견 → 합치기 시도")

        # 이전 트림 클립 다운로드
        prev_local = _download_from_s3(prev_match.trimmed_filename, work_dir)
        if prev_local:
            merged_path = os.path.join(work_dir, f"merged_{bib}_{ts}.mp4")
            if _concat_videos([prev_local, trimmed_path], merged_path):
                # 이전 ClipMatch를 merged 상태로 변경
                prev_match.status = "merged"
                db.commit()
                trimmed_path = merged_path
                print(f"[OCR] 배번 {bib}: 합치기 완료")
            else:
                print(f"[OCR] 배번 {bib}: 합치기 실패 → 현재 클립만 사용")
        else:
            print(f"[OCR] 배번 {bib}: 이전 클립 다운로드 실패 → 현재 클립만 사용")

    # 3. S3 업로드
    final_url = _upload_to_s3(trimmed_path, "trimmed_clips")
    return final_url


def _create_clip_match(db, user_id: int, clip_id: int, s3_url: str,
                       enter_time=None, exit_time=None) -> bool:
    """ClipMatch 생성. 중복이면 False 반환."""
    from core.models import ClipMatch

    if db.query(ClipMatch).filter(
        ClipMatch.user_id == user_id,
        ClipMatch.clip_id == clip_id,
    ).first():
        print(f"[OCR] 유저 {user_id} 클립 {clip_id}: 이미 매칭됨 - 스킵")
        return False

    match = ClipMatch(
        user_id=user_id,
        clip_id=clip_id,
        trimmed_filename=s3_url,
        enter_time=enter_time,
        exit_time=exit_time,
        status="done",
    )
    db.add(match)
    db.commit()
    return True


@celery_app.task(name="ocr.run_matching", bind=True, max_retries=2)
def run_ocr_matching(self, video_url: str, clip_id: int):
    """
    OCR 배번 인식 → 트림 → 연속 클립 병합 → 유저 매칭 메인 함수.
    """
    print(f"[OCR] 클립 {clip_id} 처리 시작")

    if not OCR_AVAILABLE:
        print(f"[OCR] 경고: OCR 모듈 없음 (ultralytics/easyocr 미설치)")
        return

    print(f"[OCR] 클립 {clip_id}: 처리 시작")

    work_dir = tempfile.mkdtemp(prefix="ocr_work_")
    auto_process_tasks = []  # (user_id, final_url, camera_id, bib) 목록
    try:
        # 1. S3 다운로드
        local_path = _download_from_s3(video_url, work_dir)
        if not local_path:
            return

        # 2. OCR 실행
        events = _run_ocr_on_file(local_path, clip_id)

        from core.database import SessionLocal
        from core.models import CameraClip

        db = SessionLocal()
        try:
            # 3. DetectedBib 저장
            saved_bibs = _save_detected_bibs(db, clip_id, events)
            if not saved_bibs:
                print(f"[OCR] 클립 {clip_id}: 인식된 배번 없음")
                return

            clip = db.query(CameraClip).filter(CameraClip.id == clip_id).first()

            for detected in saved_bibs:
                bib = detected.assigned_bib
                print(f"[OCR] 배번 {bib} 처리 중...")

                # 4. 트림 + 연속 클립 병합 + S3 업로드
                final_url = _process_bib(db, detected, clip, local_path, work_dir)
                if not final_url:
                    print(f"[OCR] 배번 {bib}: S3 업로드 실패 → 원본 URL 사용")
                    final_url = video_url

                # 5. 유저 찾기/생성
                user = _get_or_create_user(db, bib)

                # 6. ClipMatch 생성
                matched = _create_clip_match(
                    db, user.id, clip_id, final_url,
                    enter_time=clip.clip_start if clip else None,
                    exit_time=clip.clip_end if clip else None,
                )
                if matched:
                    detected.status = "matched"
                    db.commit()
                    print(f"[OCR] 배번 {bib} → 유저 {user.username} 매칭 완료")
                    # auto_process Celery 큐 등록
                    camera_id = clip.camera_id if clip else "cam1"
                    auto_process_tasks.append((user.id, final_url, camera_id, bib))

        finally:
            db.close()

    except Exception as e:
        print(f"[OCR] 클립 {clip_id} 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"[OCR] 클립 {clip_id}: OCR 완료, auto_process {len(auto_process_tasks)}개 큐 등록")

    # auto_process를 Celery 큐로 등록
    from services.matching import auto_process
    for user_id, final_url, camera_id, bib in auto_process_tasks:
        auto_process.delay(user_id, final_url, camera_id, bib)
        print(f"[OCR] 클립 {clip_id}: auto_process 큐 등록 (user_id={user_id}, camera_id={camera_id}, bib={bib})")


def reassign_clip(clip_id: int, new_bib: str, detected_bib_id: int | None = None):
    """관리자용: 클립을 다른 배번(유저)으로 재배정."""
    from core.database import SessionLocal
    from core.models import ClipMatch, DetectedBib, CameraClip
    from services.matching import auto_process

    db = SessionLocal()
    try:
        clip = db.query(CameraClip).filter(CameraClip.id == clip_id).first()
        if not clip:
            return {"error": "클립 없음"}
        s3_url = clip.s3_url
        if not s3_url:
            return {"error": "S3 URL 없음"}

        # 기존 ClipMatch 제거
        db.query(ClipMatch).filter(ClipMatch.clip_id == clip_id).delete()
        db.commit()

        # DetectedBib 수정
        if detected_bib_id:
            record = db.query(DetectedBib).filter(DetectedBib.id == detected_bib_id).first()
            if record:
                record.assigned_bib = new_bib
                record.status = "corrected"
                db.commit()

        user = _get_or_create_user(db, new_bib)
        _create_clip_match(db, user.id, clip_id, s3_url,
                           enter_time=clip.clip_start, exit_time=clip.clip_end)

        camera_id = clip.camera_id if clip else "cam1"
        print(f"[ADMIN] 클립 {clip_id} → 배번 {new_bib}(유저 {user.username}) 재배정 완료")
        auto_process(user.id, s3_url, camera_id=camera_id, bib=new_bib)
        return {"ok": True, "user_id": user.id, "username": user.username}

    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()
