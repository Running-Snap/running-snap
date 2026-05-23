"""Gait event detection from ankle trajectories."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

from .landmarks import LEFT_ANKLE, LEFT_HEEL, RIGHT_ANKLE, RIGHT_HEEL


@dataclass
class GaitEvent:
    side: str
    event_type: str  # foot_strike | toe_off
    frame: int
    time_sec: float


def _ankle_y_series(keypoints: np.ndarray, ankle_idx: int, heel_idx: int) -> np.ndarray:
    """Lower y = lower in image (often foot on ground in side view)."""
    ankle = keypoints[:, ankle_idx, 1]
    heel = keypoints[:, heel_idx, 1]
    combined = np.nanmean(np.stack([ankle, heel], axis=0), axis=0)
    return combined


def _detect_side_events(
    y: np.ndarray,
    fps: float,
    side: str,
    min_cycle_sec: float = 0.45,
    max_cycle_sec: float = 1.8,
) -> list[GaitEvent]:
    """Foot strike at y peaks (lowest position); toe-off between strikes at local y minima in derivative."""
    events: list[GaitEvent] = []
    filled = y.copy()
    valid = ~np.isnan(filled)
    if valid.sum() < 5:
        return events

    idx = np.arange(len(filled))
    filled[~valid] = np.interp(idx[~valid], idx[valid], filled[valid])

    # In image coords, larger y = lower on screen → foot strike ≈ peaks in y
    min_distance = int(min_cycle_sec * fps * 0.5)
    peaks, _ = find_peaks(filled, distance=max(3, min_distance), prominence=0.01)

    dy = np.gradient(filled) * fps
    for i, strike_frame in enumerate(peaks):
        events.append(
            GaitEvent(side=side, event_type="foot_strike", frame=int(strike_frame), time_sec=strike_frame / fps)
        )
        if i + 1 < len(peaks):
            seg = slice(peaks[i], peaks[i + 1])
            segment_dy = dy[seg]
            if len(segment_dy) < 2:
                continue
            # toe-off: fastest upward motion (dy most negative if y increases downward)
            local = np.argmin(segment_dy)
            toe_frame = peaks[i] + local
            events.append(
                GaitEvent(side=side, event_type="toe_off", frame=int(toe_frame), time_sec=toe_frame / fps)
            )

    return events


def detect_gait_events(
    keypoints: np.ndarray,
    fps: float,
) -> list[GaitEvent]:
    """
    Detect foot strike and toe-off for left and right legs.

    Uses ankle/heel vertical position and velocity.
    """
    all_events: list[GaitEvent] = []
    left_y = _ankle_y_series(keypoints, LEFT_ANKLE, LEFT_HEEL)
    right_y = _ankle_y_series(keypoints, RIGHT_ANKLE, RIGHT_HEEL)
    all_events.extend(_detect_side_events(left_y, fps, "left"))
    all_events.extend(_detect_side_events(right_y, fps, "right"))
    all_events.sort(key=lambda e: e.frame)
    return all_events
