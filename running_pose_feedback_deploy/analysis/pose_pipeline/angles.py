"""Joint angle computation."""

from __future__ import annotations

import math

import numpy as np

from .landmarks import ANGLE_TRIPLETS


def calculate_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Return interior angle at point b (degrees). a, b, c are (x, y) or (x, y, z)."""
    ba = np.asarray(a, dtype=float)[:2] - np.asarray(b, dtype=float)[:2]
    bc = np.asarray(c, dtype=float)[:2] - np.asarray(b, dtype=float)[:2]
    denom = np.linalg.norm(ba) * np.linalg.norm(bc)
    if denom < 1e-8:
        return math.nan
    cosine = np.clip(np.dot(ba, bc) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def extract_joint_angles(keypoints: np.ndarray, min_visibility: float = 0.5) -> dict[str, np.ndarray]:
    """
    Compute hip, knee, ankle angles per frame.

    Returns dict[name] -> (T,) array in degrees.
    """
    t_len = keypoints.shape[0]
    angles: dict[str, np.ndarray] = {}
    for name, (i, j, k) in ANGLE_TRIPLETS.items():
        series = np.full(t_len, np.nan, dtype=np.float32)
        for t in range(t_len):
            vis = keypoints[t, [i, j, k], 2]
            if np.any(vis < min_visibility) or np.any(np.isnan(keypoints[t, [i, j, k], :2])):
                continue
            series[t] = calculate_angle(keypoints[t, i], keypoints[t, j], keypoints[t, k])
        angles[name] = series
    return angles
