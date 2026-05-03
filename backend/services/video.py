"""ffmpeg 기반 영상 처리 유틸리티"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile

import boto3
from core.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME, AWS_REGION


def get_s3_client():
    """공유 S3 클라이언트 반환."""
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def download_from_s3_if_needed(video_path: str) -> tuple[str, bool]:
    """
    S3 URL이면 임시 파일로 다운로드 후 (로컬경로, True) 반환.
    로컬 경로면 (원래경로, False) 반환.
    is_tmp=True면 사용 후 직접 삭제 필요.
    """
    if not (video_path and video_path.startswith("http") and "amazonaws.com" in video_path):
        return video_path, False
    try:
        s3 = get_s3_client()
        s3_key = video_path.split("amazonaws.com/")[-1].split("?")[0]
        ext = ".mp4"
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.close()
        s3.download_file(AWS_BUCKET_NAME, s3_key, tmp.name)
        print(f"[S3 DOWNLOAD] {s3_key} → {tmp.name}")
        return tmp.name, True
    except Exception as e:
        print(f"[S3 DOWNLOAD ERROR] {e}")
        return "", False


def upload_to_s3(local_path: str, s3_folder: str) -> str | None:
    """로컬 파일을 S3에 업로드하고 S3 URL 반환. 실패 시 None 반환. 항상 로컬 파일 삭제."""
    if not AWS_BUCKET_NAME:
        return None
    try:
        s3 = get_s3_client()
        filename = os.path.basename(local_path)
        s3_key = f"{s3_folder}/{filename}"
        s3.upload_file(local_path, AWS_BUCKET_NAME, s3_key)
        url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        return url
    except Exception as e:
        print(f"[S3 UPLOAD ERROR] {e}")
        return None
    finally:
        # S3 업로드 성공/실패 무관하게 로컬 파일 항상 삭제
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _run_ffmpeg_with_fallback(cmd_nvenc: list, cmd_cpu: list, timeout: int = 120) -> subprocess.CompletedProcess:
    """h264_nvenc 시도 후 실패 시 libx264로 fallback."""
    result = subprocess.run(cmd_nvenc, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        print("[FFMPEG] nvenc 실패 → libx264 fallback")
        result = subprocess.run(cmd_cpu, capture_output=True, timeout=timeout)
    return result


def trim_clip(input_path: str, output_path: str, start_sec: float, end_sec: float) -> bool:
    """영상 구간 자르기 + mp4 변환 (webm 포함 모든 포맷 지원)"""
    ffmpeg_bin = _ffmpeg()
    if not ffmpeg_bin:
        shutil.copy2(input_path, output_path)
        return True
    try:
        duration = max(1.0, end_sec - start_sec)
        base_args = [ffmpeg_bin, "-y", "-ss", str(start_sec), "-i", input_path, "-t", str(duration)]
        result = _run_ffmpeg_with_fallback(
            cmd_nvenc=base_args + ["-c:v", "h264_nvenc", "-preset", "fast", "-c:a", "aac", output_path],
            cmd_cpu=base_args + ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac", output_path],
            timeout=120,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def concat_clips(clip_paths: list, output_path: str) -> bool:
    """여러 클립을 하나로 합치기 (타임스탬프 리셋으로 멈춤 방지)"""
    ffmpeg_bin = _ffmpeg()
    if not ffmpeg_bin:
        return False
    try:
        n = len(clip_paths)
        base_cmd = [ffmpeg_bin, "-y"]
        for p in clip_paths:
            base_cmd += ["-i", p]
        filter_str = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1[v]"
        result = _run_ffmpeg_with_fallback(
            cmd_nvenc=base_cmd + ["-filter_complex", filter_str, "-map", "[v]", "-c:v", "h264_nvenc", "-preset", "fast", output_path],
            cmd_cpu=base_cmd + ["-filter_complex", filter_str, "-map", "[v]", "-c:v", "libx264", "-preset", "fast", output_path],
            timeout=180,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False
