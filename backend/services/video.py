"""ffmpeg 기반 영상 처리 유틸리티"""
from __future__ import annotations
import math
import os
import shutil
import subprocess


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 GPS 좌표 간 거리(미터) 계산"""
    R = 6371000
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def trim_clip(input_path: str, output_path: str, start_sec: float, end_sec: float) -> bool:
    """영상 구간 자르기 + mp4 변환 (webm 포함 모든 포맷 지원)"""
    ffmpeg_bin = _ffmpeg()
    if not ffmpeg_bin:
        shutil.copy2(input_path, output_path)
        return True
    try:
        duration = max(1.0, end_sec - start_sec)
        result = subprocess.run(
            [
                ffmpeg_bin, "-y",
                "-ss", str(start_sec),
                "-i", input_path,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                output_path,
            ],
            capture_output=True,
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
        n   = len(clip_paths)
        cmd = [ffmpeg_bin, "-y"]
        for p in clip_paths:
            cmd += ["-i", p]
        filter_str = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1[v]"
        cmd += ["-filter_complex", filter_str, "-map", "[v]", "-c:v", "libx264", "-preset", "fast", output_path]
        result = subprocess.run(cmd, capture_output=True, timeout=180)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False
