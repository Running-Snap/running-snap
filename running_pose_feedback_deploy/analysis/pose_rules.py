"""4-axis pose rules: cadence, arm_swing, stride, foot_strike."""

from __future__ import annotations

import json
from pathlib import Path

from four_axis_metrics import (
    FourAxisRules,
    calibrate_four_axis_rules,
    evaluate_four_axes,
    load_track_and_metrics,
)

# Backward-compatible alias
PoseRules = FourAxisRules


def load_pose_rules(path: Path) -> FourAxisRules:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version", "1") == "1" and "bad_score_threshold" in data:
        raise ValueError(
            f"Legacy pose_rules v1 at {path}. Re-run build_marathon_postprocess_rules.py for v2."
        )
    return FourAxisRules.from_dict(data)


def save_pose_rules(path: Path, rules: FourAxisRules) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def classify_four_axis(
    phase_report: dict,
    rules: FourAxisRules,
    *,
    pose_dir: Path | None = None,
    cadence_spm: float | None = None,
) -> dict:
    """Classify using 4-axis framework."""
    if pose_dir is not None:
        metrics = load_track_and_metrics(pose_dir, phase_report, cadence_spm)
    else:
        from four_axis_metrics import compute_four_axis_metrics

        metrics = compute_four_axis_metrics(
            phase_report=phase_report,
            cadence_spm=cadence_spm,
        )
    return evaluate_four_axes(metrics, rules)


# Legacy name
def classify_from_phase_report(
    phase_report: dict,
    rules: FourAxisRules,
    *,
    cadence_spm: float | None = None,
    elbow_symmetry_median: float | None = None,
    knee_symmetry_median: float | None = None,
    pose_dir: Path | None = None,
) -> dict:
    return classify_four_axis(phase_report, rules, pose_dir=pose_dir, cadence_spm=cadence_spm)


def calibrate_rules_from_scores(
    samples: list[dict],
    *,
    cadence_ref: dict,
    percentile: float = 90.0,
    method: str,
    n_videos: int,
    **_,
) -> FourAxisRules:
    return calibrate_four_axis_rules(
        samples,
        cadence_ref=cadence_ref,
        percentile=percentile,
        method=method,
    )
