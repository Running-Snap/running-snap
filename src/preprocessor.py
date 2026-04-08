"""
preprocessor.py
===============
입력 영상을 편집 파이프라인에 맞게 정규화.

담당:
  1. rotation 메타데이터 적용 (아이폰 세로 영상 등)
  2. 소스가 target_duration 보다 짧으면 루프 반복
  3. 정규화된 임시 mp4 경로 + 실제 소스 길이 반환

사용:
  info = preprocess(video_path, target_duration, tmpdir)
  info.path          # 처리된 mp4 경로
  info.duration      # 초
  info.width
  info.height
  info.fps
  info.loop_count    # 루프 적용 횟수 (1 = 루프 없음)
"""
from __future__ import annotations

import os
import math
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path


FFMPEG  = "/opt/homebrew/bin/ffmpeg"  if os.path.exists("/opt/homebrew/bin/ffmpeg")  else "ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe"

MIN_LOOP_FACTOR = 1.5  # source < target * 이 비율이면 루프


@dataclass
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    loop_count: int = 1
    original_duration: float = 0.0  # 루프 전 단일 클립 길이


def preprocess(
    video_path: str,
    target_duration: float,
    tmpdir: str,
) -> VideoInfo:
    """
    영상을 편집 파이프라인용으로 정규화.

    Args:
        video_path: 원본 파일 경로
        target_duration: 목표 출력 길이 (초)
        tmpdir: 임시 파일 저장 디렉터리

    Returns:
        VideoInfo — 처리 완료된 영상 정보
    """
    # ── Step 1: 원본 메타데이터 확인 ────────────────────────────────
    meta = _probe(video_path)
    print(f"[Preprocess] 원본: {Path(video_path).name}")
    print(f"  {meta['width']}x{meta['height']}  {meta['fps']:.1f}fps  "
          f"{meta['duration']:.2f}s  rotation={meta.get('rotation', 0)}")

    # ── Step 2: rotation fix → 정규화된 mp4 ─────────────────────────
    fixed_path = os.path.join(tmpdir, "fixed.mp4")
    _fix_rotation(video_path, fixed_path, meta)

    fixed_meta = _probe(fixed_path)
    print(f"  → fixed: {fixed_meta['width']}x{fixed_meta['height']}  "
          f"{fixed_meta['duration']:.2f}s")

    original_dur = fixed_meta["duration"]

    # ── Step 3: 루프 (필요 시) ──────────────────────────────────────
    need_loop = original_dur < target_duration * MIN_LOOP_FACTOR
    loop_count = 1

    if need_loop:
        loop_count = math.ceil(target_duration * MIN_LOOP_FACTOR / original_dur)
        loop_count = max(loop_count, 2)
        looped_path = os.path.join(tmpdir, "loop.mp4")
        _make_loop(fixed_path, looped_path, loop_count)
        loop_meta = _probe(looped_path)
        print(f"  → {loop_count}x 루프: {loop_meta['duration']:.2f}s")
        return VideoInfo(
            path=looped_path,
            duration=loop_meta["duration"],
            width=loop_meta["width"],
            height=loop_meta["height"],
            fps=loop_meta["fps"],
            loop_count=loop_count,
            original_duration=original_dur,
        )

    return VideoInfo(
        path=fixed_path,
        duration=fixed_meta["duration"],
        width=fixed_meta["width"],
        height=fixed_meta["height"],
        fps=fixed_meta["fps"],
        loop_count=1,
        original_duration=original_dur,
    )


# ── 내부 함수 ────────────────────────────────────────────────────────

def _probe(video_path: str) -> dict:
    """ffprobe로 영상 메타데이터 추출"""
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    data = json.loads(out)

    video_stream = next(
        (s for s in data["streams"] if s["codec_type"] == "video"), {}
    )

    # fps 파싱 (분수 형태 처리: "30/1", "24000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # duration: stream 또는 format에서
    duration = float(
        video_stream.get("duration")
        or data.get("format", {}).get("duration", 0)
    )

    # rotation
    rotation = 0
    for sd in video_stream.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"])
            break

    return {
        "width":    int(video_stream.get("width", 0)),
        "height":   int(video_stream.get("height", 0)),
        "fps":      fps,
        "duration": duration,
        "rotation": rotation,
    }


def _fix_rotation(src: str, dst: str, meta: dict) -> None:
    """rotation 메타데이터를 실제 픽셀 회전으로 베이크"""
    rotation = meta.get("rotation", 0)

    # ffmpeg가 디코딩 시 display matrix(rotation)를 자동 적용하므로
    # 그냥 재인코딩하면 결과물엔 rotation=0이 됨
    cmd = [
        FFMPEG, "-y",
        "-i", src,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an",            # 루프 편의 + 오디오는 마지막 단계에서 머지
        dst,
        "-loglevel", "error",
    ]
    subprocess.run(cmd, check=True)


def _make_loop(src: str, dst: str, loop_count: int) -> None:
    """moviepy로 N회 루프 생성"""
    try:
        from moviepy import VideoFileClip, concatenate_videoclips
        clip = VideoFileClip(src)
        clips = [clip] + [clip.copy() for _ in range(loop_count - 1)]
        looped = concatenate_videoclips(clips)
        looped.write_videofile(
            dst,
            codec="libx264", audio_codec="aac",
            fps=30, preset="fast", threads=4, logger=None,
            ffmpeg_params=["-crf", "16", "-pix_fmt", "yuv420p"],
        )
        looped.close()
        clip.close()
    except Exception as e:
        raise RuntimeError(f"루프 생성 실패: {e}") from e
