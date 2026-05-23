"""Export post-processed pose keypoints to cycle-segmentation CSV format."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from .angles import calculate_angle
from .landmarks import (
    LEFT_ANKLE,
    LEFT_ELBOW,
    LEFT_FOOT_INDEX,
    LEFT_HEEL,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_ANKLE,
    RIGHT_ELBOW,
    RIGHT_FOOT_INDEX,
    RIGHT_HEEL,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
)

TRACK_FIELDS = [
    "frame",
    "time_sec",
    "person_id",
    "left_elbow_deg",
    "right_elbow_deg",
    "left_knee_deg",
    "right_knee_deg",
    "torso_lean_deg",
    "elbow_symmetry_diff_deg",
    "knee_symmetry_diff_deg",
    "left_foot_forward",
    "right_foot_forward",
    "left_heel_drop",
    "right_heel_drop",
    "left_ankle_deg",
    "right_ankle_deg",
    "pose_detected",
]


def _vis(kps: np.ndarray, idx: int, min_vis: float) -> bool:
    return not np.any(np.isnan(kps[idx, :2])) and kps[idx, 2] >= min_vis


def _torso_lean_deg(kps: np.ndarray, min_vis: float) -> float:
    idxs = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)
    if not all(_vis(kps, i, min_vis) for i in idxs):
        return math.nan
    shoulder_x = (kps[LEFT_SHOULDER, 0] + kps[RIGHT_SHOULDER, 0]) / 2
    shoulder_y = (kps[LEFT_SHOULDER, 1] + kps[RIGHT_SHOULDER, 1]) / 2
    hip_x = (kps[LEFT_HIP, 0] + kps[RIGHT_HIP, 0]) / 2
    hip_y = (kps[LEFT_HIP, 1] + kps[RIGHT_HIP, 1]) / 2
    dx = shoulder_x - hip_x
    dy = shoulder_y - hip_y
    return float(np.degrees(np.arctan2(abs(dx), abs(dy))))


def frame_metrics(kps: np.ndarray, min_visibility: float = 0.5) -> dict[str, float | str]:
    """Per-frame limb metrics from (33, 3) keypoints."""
    out: dict[str, float | str] = {k: math.nan for k in TRACK_FIELDS if k.endswith("_deg")}
    out["pose_detected"] = "no"

    if np.all(np.isnan(kps[:, :2])):
        return out

    if _vis(kps, LEFT_SHOULDER, min_visibility) and _vis(kps, LEFT_ELBOW, min_visibility) and _vis(
        kps, LEFT_WRIST, min_visibility
    ):
        out["left_elbow_deg"] = calculate_angle(kps[LEFT_SHOULDER], kps[LEFT_ELBOW], kps[LEFT_WRIST])
    if _vis(kps, RIGHT_SHOULDER, min_visibility) and _vis(kps, RIGHT_ELBOW, min_visibility) and _vis(
        kps, RIGHT_WRIST, min_visibility
    ):
        out["right_elbow_deg"] = calculate_angle(
            kps[RIGHT_SHOULDER], kps[RIGHT_ELBOW], kps[RIGHT_WRIST]
        )
    if _vis(kps, LEFT_HIP, min_visibility) and _vis(kps, LEFT_KNEE, min_visibility) and _vis(
        kps, LEFT_ANKLE, min_visibility
    ):
        out["left_knee_deg"] = calculate_angle(kps[LEFT_HIP], kps[LEFT_KNEE], kps[LEFT_ANKLE])
    if _vis(kps, RIGHT_HIP, min_visibility) and _vis(kps, RIGHT_KNEE, min_visibility) and _vis(
        kps, RIGHT_ANKLE, min_visibility
    ):
        out["right_knee_deg"] = calculate_angle(kps[RIGHT_HIP], kps[RIGHT_KNEE], kps[RIGHT_ANKLE])

    out["torso_lean_deg"] = _torso_lean_deg(kps, min_visibility)

    le, re = out["left_elbow_deg"], out["right_elbow_deg"]
    lk, rk = out["left_knee_deg"], out["right_knee_deg"]
    if isinstance(le, float) and isinstance(re, float) and not (math.isnan(le) or math.isnan(re)):
        out["elbow_symmetry_diff_deg"] = abs(le - re)
    if isinstance(lk, float) and isinstance(rk, float) and not (math.isnan(lk) or math.isnan(rk)):
        out["knee_symmetry_diff_deg"] = abs(lk - rk)

    hip_x = (kps[LEFT_HIP, 0] + kps[RIGHT_HIP, 0]) / 2 if _vis(kps, LEFT_HIP, min_visibility) and _vis(kps, RIGHT_HIP, min_visibility) else math.nan
    for side, ankle_i, heel_i, foot_i, fwd_key, drop_key, ang_key in (
        ("left", LEFT_ANKLE, LEFT_HEEL, LEFT_FOOT_INDEX, "left_foot_forward", "left_heel_drop", "left_ankle_deg"),
        ("right", RIGHT_ANKLE, RIGHT_HEEL, RIGHT_FOOT_INDEX, "right_foot_forward", "right_heel_drop", "right_ankle_deg"),
    ):
        if _vis(kps, ankle_i, min_visibility) and not math.isnan(hip_x):
            out[fwd_key] = float(kps[ankle_i, 0] - hip_x)
        if _vis(kps, ankle_i, min_visibility) and _vis(kps, heel_i, min_visibility):
            out[drop_key] = float(kps[heel_i, 1] - kps[ankle_i, 1])
        if _vis(kps, LEFT_KNEE if side == "left" else RIGHT_KNEE, min_visibility) and _vis(kps, ankle_i, min_visibility) and _vis(
            kps, foot_i, min_visibility
        ):
            knee_i = LEFT_KNEE if side == "left" else RIGHT_KNEE
            out[ang_key] = calculate_angle(kps[knee_i], kps[ankle_i], kps[foot_i])

    if any(
        not (isinstance(out[k], float) and math.isnan(out[k]))
        for k in TRACK_FIELDS
        if k.endswith("_deg")
    ):
        out["pose_detected"] = "yes"
    return out


def keypoints_to_track_rows(
    keypoints: np.ndarray,
    fps: float,
    *,
    frame_stride: int = 1,
    start_frame: int = 0,
    person_id: str = "1",
) -> list[dict[str, str | int | float]]:
    rows: list[dict[str, str | int | float]] = []
    for t in range(keypoints.shape[0]):
        frame = start_frame + t * frame_stride
        metrics = frame_metrics(keypoints[t])
        row: dict[str, str | int | float] = {
            "frame": frame,
            "time_sec": round(frame / fps, 4),
            "person_id": person_id,
        }
        for key in TRACK_FIELDS:
            if key in ("frame", "time_sec", "person_id"):
                continue
            val = metrics.get(key, math.nan)
            if key == "pose_detected":
                row[key] = val
            elif isinstance(val, float) and math.isnan(val):
                row[key] = ""
            else:
                row[key] = f"{val:.2f}" if isinstance(val, float) else val
        rows.append(row)
    return rows


def write_track_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TRACK_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
