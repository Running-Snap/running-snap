"""Video frame metadata and hybrid sampling for Qwen (uniform + MP-abnormal neighbors)."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from four_axis_metrics import (
    AXIS_ARM_SWING,
    AXIS_CADENCE,
    AXIS_FOOT_STRIKE,
    AXIS_STRIDE,
)
from normal_pose_reference import parse_float
from segment_running_cycles import read_track_csv

DEFAULT_UNIFORM_FRAMES = 8
DEFAULT_NEIGHBOR_FRAMES_PER_ABNORMAL = 2


def get_video_frame_meta(video_path: Path) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.release()
    return {
        "total_frames": total,
        "fps": round(fps, 2),
        "duration_sec": round(total / fps, 2) if fps > 0 else None,
    }


def compute_sample_frame_indices(total_frames: int, n_frames: int) -> list[int]:
    total = max(total_frames, 1)
    n = max(n_frames, 1)
    return [int(i * (total - 1) / max(n - 1, 1)) for i in range(n)]


def load_pose_track_rows(pose_dir: Path | None) -> list[dict[str, str]]:
    if pose_dir is None or not pose_dir.is_dir():
        return []
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    if not csv_path.exists():
        return []
    return read_track_csv(csv_path)


def _median_frame_step(rows: list[dict[str, str]]) -> int:
    frames = sorted(
        int(r["frame"]) for r in rows if r.get("pose_detected") == "yes" and str(r.get("frame", "")).isdigit()
    )
    if len(frames) < 2:
        return 1
    diffs = [frames[i + 1] - frames[i] for i in range(len(frames) - 1) if frames[i + 1] > frames[i]]
    return max(1, int(np.median(diffs))) if diffs else 1


def _frame_axis_score(row: dict[str, str], axis: str, rules_axes: dict[str, dict]) -> float:
    """Per-frame proxy for one axis (video-level axis should be abnormal)."""
    if axis == AXIS_ARM_SWING:
        sym = parse_float(row.get("elbow_symmetry_diff_deg", "nan"))
        th = rules_axes.get(AXIS_ARM_SWING, {}).get("symmetry_max_deg")
        if th is not None and not np.isnan(sym) and float(th) > 0:
            return sym / float(th)
        return 0.0
    if axis == AXIS_STRIDE:
        lf = parse_float(row.get("left_foot_forward", "nan"))
        rf = parse_float(row.get("right_foot_forward", "nan"))
        fwd = max(lf, rf) if not (np.isnan(lf) and np.isnan(rf)) else float("nan")
        th = rules_axes.get(AXIS_STRIDE, {}).get("overstride_forward_max")
        if th is not None and not np.isnan(fwd) and float(th) > 0:
            return fwd / float(th)
        return 0.0
    if axis == AXIS_FOOT_STRIKE:
        lh = parse_float(row.get("left_heel_drop", "nan"))
        rh = parse_float(row.get("right_heel_drop", "nan"))
        heel = max(lh, rh) if not (np.isnan(lh) and np.isnan(rh)) else float("nan")
        th = rules_axes.get(AXIS_FOOT_STRIKE, {}).get("heel_drop_max")
        if th is not None and not np.isnan(heel) and float(th) > 0:
            return heel / float(th)
        return 0.0
    return 0.0


def _frame_abnormality_score(
    row: dict[str, str],
    *,
    axis_results: dict[str, dict],
    rules_axes: dict[str, dict],
) -> float:
    """Per-frame proxy score when the video-level axis is abnormal."""
    score = 0.0
    for axis in (AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE):
        if axis_results.get(axis, {}).get("abnormal"):
            score = max(score, _frame_axis_score(row, axis, rules_axes))
    return score


def _pick_peak_frame_indices(
    scored: list[tuple[int, float]],
    rows: list[dict[str, str]],
    *,
    max_frames: int = 4,
) -> list[int]:
    if not scored:
        return []
    vals = [s for _, s in scored]
    thresh = float(max(np.percentile(vals, 75), 1.0))
    step = _median_frame_step(rows)
    picked: list[int] = []
    for frame_idx, s in sorted(scored, key=lambda x: (-x[1], x[0])):
        if s < thresh:
            continue
        if any(abs(frame_idx - c) <= step * 2 for c in picked):
            continue
        picked.append(frame_idx)
        if len(picked) >= max_frames:
            break
    return sorted(picked)


def detect_mp_abnormal_frames_per_axis(
    rows: list[dict[str, str]],
    evaluation: dict,
    rules_axes: dict[str, dict],
    *,
    max_per_axis: int = 4,
) -> dict[str, list[int]]:
    """Per-axis frame indices where row-level proxies peak."""
    axis_results = evaluation.get("axis_results", {}) or {}
    out: dict[str, list[int]] = {}
    detected = sorted(
        int(r["frame"]) for r in rows if r.get("pose_detected") == "yes" and str(r.get("frame", "")).isdigit()
    )

    for axis in (AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE, AXIS_CADENCE):
        if not axis_results.get(axis, {}).get("abnormal"):
            continue
        if axis == AXIS_CADENCE:
            if detected:
                picks = []
                for pos in (len(detected) // 3, (2 * len(detected)) // 3):
                    picks.append(detected[min(pos, len(detected) - 1)])
                out[axis] = sorted(set(picks))[:max_per_axis]
            continue
        scored: list[tuple[int, float]] = []
        for row in rows:
            if row.get("pose_detected") != "yes":
                continue
            s = _frame_axis_score(row, axis, rules_axes)
            if s >= 0.85:
                scored.append((int(row["frame"]), s))
        out[axis] = _pick_peak_frame_indices(scored, rows, max_frames=max_per_axis)
    return out


def detect_mp_abnormal_frame_centers(
    rows: list[dict[str, str]],
    evaluation: dict,
    rules_axes: dict[str, dict],
    *,
    max_centers: int = 6,
) -> list[int]:
    """
    Frame indices where per-row MP proxies peak (only for axes flagged abnormal).
    """
    axis_results = evaluation.get("axis_results", {}) or {}
    any_axis = any(axis_results.get(ax, {}).get("abnormal") for ax in (AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE))
    cadence_abnormal = bool(axis_results.get(AXIS_CADENCE, {}).get("abnormal"))

    scored: list[tuple[int, float]] = []
    for row in rows:
        if row.get("pose_detected") != "yes":
            continue
        s = _frame_abnormality_score(row, axis_results=axis_results, rules_axes=rules_axes)
        if s > 0:
            scored.append((int(row["frame"]), s))

    centers: list[int] = []
    if scored:
        vals = [s for _, s in scored]
        thresh = float(max(np.percentile(vals, 75), 1.0))
        step = _median_frame_step(rows)
        for frame_idx, s in sorted(scored, key=lambda x: (-x[1], x[0])):
            if s < thresh:
                continue
            if any(abs(frame_idx - c) <= step * 2 for c in centers):
                continue
            centers.append(frame_idx)
            if len(centers) >= max_centers:
                break

    if cadence_abnormal and len(centers) < max_centers:
        detected = sorted(
            int(r["frame"]) for r in rows if r.get("pose_detected") == "yes" and str(r.get("frame", "")).isdigit()
        )
        if detected:
            for pos in (len(detected) // 3, (2 * len(detected)) // 3):
                fi = detected[min(pos, len(detected) - 1)]
                if not any(abs(fi - c) <= _median_frame_step(rows) * 2 for c in centers):
                    centers.append(fi)
                    if len(centers) >= max_centers:
                        break

    return sorted(centers)


def expand_neighbor_frame_indices(
    centers: list[int],
    total_frames: int,
    *,
    neighbors_per_center: int = DEFAULT_NEIGHBOR_FRAMES_PER_ABNORMAL,
    frame_step: int | None = None,
) -> list[int]:
    """Around each abnormal center, sample `neighbors_per_center` frames (before/after)."""
    if not centers or neighbors_per_center <= 0:
        return []
    total = max(total_frames, 1)
    step = max(1, frame_step or 1)
    out: list[int] = []
    half = neighbors_per_center // 2
    remainder = neighbors_per_center - half
    for center in centers:
        for k in range(1, half + 1):
            out.append(max(0, min(total - 1, center - k * step)))
        for k in range(1, remainder + 1):
            out.append(max(0, min(total - 1, center + k * step)))
    return out


def merge_frame_indices(
    uniform: list[int],
    extra: list[int],
    total_frames: int,
    *,
    max_total: int | None = None,
) -> list[int]:
    total = max(total_frames, 1)
    merged: list[int] = []
    seen: set[int] = set()
    for idx in extra + uniform:
        clamped = max(0, min(total - 1, int(idx)))
        if clamped not in seen:
            seen.add(clamped)
            merged.append(clamped)
    if max_total is not None and len(merged) > max_total:
        extra_set = {max(0, min(total - 1, int(i))) for i in extra}
        kept = [i for i in merged if i in extra_set]
        for i in merged:
            if len(kept) >= max_total:
                break
            if i not in kept:
                kept.append(i)
        merged = kept[:max_total]
    return sorted(merged)


def compute_hybrid_sample_frame_indices(
    total_frames: int,
    rows: list[dict[str, str]],
    evaluation: dict,
    rules_axes: dict[str, dict],
    *,
    n_uniform: int = DEFAULT_UNIFORM_FRAMES,
    neighbors_per_abnormal: int = DEFAULT_NEIGHBOR_FRAMES_PER_ABNORMAL,
    max_centers: int = 6,
    max_total: int | None = None,
) -> tuple[list[int], dict[str, Any]]:
    uniform = compute_sample_frame_indices(total_frames, n_uniform)
    centers = detect_mp_abnormal_frame_centers(
        rows, evaluation, rules_axes, max_centers=max_centers
    )
    frames_by_axis = detect_mp_abnormal_frames_per_axis(
        rows, evaluation, rules_axes, max_per_axis=max(3, max_centers // 2)
    )
    step = _median_frame_step(rows) if rows else 1
    neighbors = expand_neighbor_frame_indices(
        centers,
        total_frames,
        neighbors_per_center=neighbors_per_abnormal,
        frame_step=step,
    )
    indices = merge_frame_indices(uniform, neighbors, total_frames, max_total=max_total)
    meta = {
        "qwen_sample_strategy": "hybrid_uniform8_mp_abnormal_neighbors2",
        "qwen_uniform_frame_count": n_uniform,
        "qwen_uniform_frame_indices": uniform,
        "qwen_neighbors_per_abnormal": neighbors_per_abnormal,
        "mp_abnormal_frame_centers": centers,
        "mp_abnormal_frames_by_axis": frames_by_axis,
        "mp_abnormal_neighbor_indices": sorted(set(neighbors)),
    }
    return indices, meta


def mp_pose_frame_meta(pose_dir: Path | None) -> dict:
    if pose_dir is None or not pose_dir.is_dir():
        return {}
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    if not csv_path.exists():
        return {}
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if not rows:
        return {}
    detected = sum(1 for r in rows if r.get("pose_detected") == "yes")
    frame_ids = sorted({int(r["frame"]) for r in rows if r.get("frame", "").isdigit()})
    return {
        "mp_csv_rows": len(rows),
        "mp_pose_detected_frames": detected,
        "mp_frame_index_min": frame_ids[0] if frame_ids else None,
        "mp_frame_index_max": frame_ids[-1] if frame_ids else None,
    }


def build_frame_context(
    video_path: Path,
    *,
    n_frames_sampled: int,
    sampled_indices: list[int],
    pose_dir: Path | None = None,
    sampling_meta: dict[str, Any] | None = None,
) -> dict:
    video_meta = get_video_frame_meta(video_path)
    ctx = {
        "video_file": video_path.name,
        **video_meta,
        "qwen_sampled_frame_count": len(sampled_indices),
        "qwen_sampled_frame_indices": sampled_indices,
        **mp_pose_frame_meta(pose_dir),
    }
    if sampling_meta:
        ctx.update(sampling_meta)
    return ctx


def attach_frame_context(axis_payload: dict, frame_context: dict) -> dict:
    out = dict(axis_payload)
    out["frame_context"] = frame_context
    return out


def sample_frames_with_meta(
    video_path: Path,
    n_frames: int = DEFAULT_UNIFORM_FRAMES,
    *,
    pose_dir: Path | None = None,
    evaluation: dict | None = None,
    rules_axes: dict[str, dict] | None = None,
    neighbors_per_abnormal: int = DEFAULT_NEIGHBOR_FRAMES_PER_ABNORMAL,
    max_abnormal_centers: int = 6,
    max_total_frames: int | None = None,
    use_hybrid: bool = True,
) -> tuple[list[Path], dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    rows = load_pose_track_rows(pose_dir)
    sampling_meta: dict[str, Any] = {}
    if (
        use_hybrid
        and evaluation is not None
        and rules_axes is not None
        and rows
    ):
        indices, sampling_meta = compute_hybrid_sample_frame_indices(
            total,
            rows,
            evaluation,
            rules_axes,
            n_uniform=n_frames,
            neighbors_per_abnormal=neighbors_per_abnormal,
            max_centers=max_abnormal_centers,
            max_total=max_total_frames,
        )
    else:
        indices = compute_sample_frame_indices(total, n_frames)
        sampling_meta = {
            "qwen_sample_strategy": "uniform_only",
            "qwen_uniform_frame_count": n_frames,
        }

    tmp_dir = Path(tempfile.mkdtemp(prefix="qwen_frames_"))
    paths: list[Path] = []
    for i, frame_idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        out = tmp_dir / f"frame_{i:02d}_idx{frame_idx}.jpg"
        cv2.imwrite(str(out), frame)
        paths.append(out)
    cap.release()
    meta = build_frame_context(
        video_path,
        n_frames_sampled=len(indices),
        sampled_indices=indices,
        pose_dir=pose_dir,
        sampling_meta=sampling_meta,
    )
    meta["qwen_saved_frame_count"] = len(paths)
    return paths, meta


def sample_frame_paths(
    video_path: Path,
    n_frames: int = DEFAULT_UNIFORM_FRAMES,
    **kwargs: Any,
) -> list[Path]:
    paths, _ = sample_frames_with_meta(video_path, n_frames, **kwargs)
    return paths
