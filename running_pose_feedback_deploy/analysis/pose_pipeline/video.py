"""Video loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class VideoData:
    frames: list[np.ndarray]
    fps: float
    width: int
    height: int
    frame_count: int


def load_video(
    video_path: str | Path,
    *,
    max_frames: int | None = None,
    target_width: int | None = 960,
    keep_aspect: bool = True,
) -> VideoData:
    """
    Read video with OpenCV.

    Returns RGB frames (H, W, 3), consistent FPS metadata, optional resize.
    """
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames: list[np.ndarray] = []
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if target_width and width > target_width:
            if keep_aspect:
                scale = target_width / width
                new_h = int(height * scale)
                frame_rgb = cv2.resize(frame_rgb, (target_width, new_h), interpolation=cv2.INTER_AREA)
            else:
                frame_rgb = cv2.resize(frame_rgb, (target_width, target_width), interpolation=cv2.INTER_AREA)
        frames.append(frame_rgb)
        if max_frames and len(frames) >= max_frames:
            break

    cap.release()
    if not frames:
        raise ValueError(f"No frames read from {path}")

    h, w = frames[0].shape[:2]
    return VideoData(frames=frames, fps=fps, width=w, height=h, frame_count=len(frames))
