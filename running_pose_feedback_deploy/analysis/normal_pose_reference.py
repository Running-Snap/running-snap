from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Marathon good-pose reference: 4 limb angle metrics (cycle phase-normalized)
REFERENCE_METRICS = [
    "left_elbow_deg",
    "right_elbow_deg",
    "left_knee_deg",
    "right_knee_deg",
]

PHASE_METRICS = REFERENCE_METRICS + [
    "torso_lean_deg",
]

METRIC_LABELS_KO = {
    "left_elbow_deg": "왼팔 팔꿈치",
    "right_elbow_deg": "오른팔 팔꿈치",
    "left_knee_deg": "왼쪽 무릎",
    "right_knee_deg": "오른쪽 무릎",
    "torso_lean_deg": "상체 기울기",
}

ISSUE_RULES = {
    "low_knee_flexion": {
        "metrics": ["left_knee_deg", "right_knee_deg"],
        "direction": "below",
        "phase_ranges": [(15, 35), (65, 85)],
        "label_ko": "무릎 굽힘이 정상보다 부족함 (다리가 과도하게 펴짐)",
    },
    "high_knee_flexion": {
        "metrics": ["left_knee_deg", "right_knee_deg"],
        "direction": "above",
        "phase_ranges": [(15, 35), (65, 85)],
        "label_ko": "무릎 굽힘이 정상보다 과함",
    },
    "excessive_torso_lean": {
        "metrics": ["torso_lean_deg"],
        "direction": "above",
        "phase_ranges": [(25, 65)],
        "label_ko": "상체 전방 기울기가 정상보다 큼",
    },
    "low_torso_lean": {
        "metrics": ["torso_lean_deg"],
        "direction": "below",
        "phase_ranges": [(25, 65)],
        "label_ko": "상체 전방 기울기가 정상보다 작음 (뒤로 젖힘)",
    },
    "elbow_too_extended": {
        "metrics": ["left_elbow_deg", "right_elbow_deg"],
        "direction": "above",
        "phase_ranges": [(0, 100)],
        "label_ko": "팔꿈치 각도가 정상보다 큼 (팔이 과도하게 펴짐)",
    },
    "elbow_too_bent": {
        "metrics": ["left_elbow_deg", "right_elbow_deg"],
        "direction": "below",
        "phase_ranges": [(0, 100)],
        "label_ko": "팔꿈치 각도가 정상보다 작음 (팔이 과도하게 굽음)",
    },
}


@dataclass
class ReferenceRow:
    metric: str
    phase_pct: float
    mean: float
    std: float
    p10: float
    p25: float
    p75: float
    p90: float
    n_videos: int


def parse_float(value: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return math.nan


def load_phase_profiles(profiles_root: Path) -> list[dict[str, str | int | float]]:
    """Load per-video phase profile rows from all *_normal_phase_profile.csv files."""
    rows: list[dict] = []
    for csv_path in sorted(profiles_root.glob("*/*_normal_phase_profile.csv")):
        video_dir = csv_path.parent.name
        for row in csv.DictReader(csv_path.open(encoding="utf-8")):
            rows.append(
                {
                    "video_dir": video_dir,
                    "person_id": row.get("person_id", ""),
                    "metric": row["metric"],
                    "phase_pct": parse_float(row["phase_pct"]),
                    "mean": parse_float(row["mean"]),
                    "p10": parse_float(row["p10"]),
                    "p25": parse_float(row["p25"]),
                    "p75": parse_float(row["p75"]),
                    "p90": parse_float(row["p90"]),
                    "n_cycles": int(float(row.get("n_cycles", 0) or 0)),
                }
            )
    return rows


def build_phase_reference(
    profile_rows: list[dict],
    metrics: list[str] | None = None,
) -> list[ReferenceRow]:
    """Pool per-video phase means into a global reference distribution."""
    metrics = metrics or REFERENCE_METRICS
    reference: list[ReferenceRow] = []
    for metric in metrics:
        metric_rows = [r for r in profile_rows if r["metric"] == metric and not math.isnan(r["mean"])]
        phases = sorted({r["phase_pct"] for r in metric_rows})
        for phase in phases:
            values = [r["mean"] for r in metric_rows if r["phase_pct"] == phase]
            if len(values) < 2:
                continue
            arr = np.array(values, dtype=float)
            reference.append(
                ReferenceRow(
                    metric=metric,
                    phase_pct=phase,
                    mean=float(np.mean(arr)),
                    std=float(np.std(arr)),
                    p10=float(np.percentile(arr, 10)),
                    p25=float(np.percentile(arr, 25)),
                    p75=float(np.percentile(arr, 75)),
                    p90=float(np.percentile(arr, 90)),
                    n_videos=len(values),
                )
            )
    return reference


def write_phase_reference_csv(path: Path, reference: list[ReferenceRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "metric",
                "phase_pct",
                "mean",
                "std",
                "p10",
                "p25",
                "p75",
                "p90",
                "n_videos",
            ],
        )
        writer.writeheader()
        for row in reference:
            writer.writerow(
                {
                    "metric": row.metric,
                    "phase_pct": f"{row.phase_pct:.1f}",
                    "mean": f"{row.mean:.2f}",
                    "std": f"{row.std:.2f}",
                    "p10": f"{row.p10:.2f}",
                    "p25": f"{row.p25:.2f}",
                    "p75": f"{row.p75:.2f}",
                    "p90": f"{row.p90:.2f}",
                    "n_videos": row.n_videos,
                }
            )


def load_phase_reference(path: Path) -> dict[tuple[str, float], ReferenceRow]:
    lookup: dict[tuple[str, float], ReferenceRow] = {}
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            phase = parse_float(row["phase_pct"])
            lookup[(row["metric"], phase)] = ReferenceRow(
                metric=row["metric"],
                phase_pct=phase,
                mean=parse_float(row["mean"]),
                std=parse_float(row["std"]),
                p10=parse_float(row["p10"]),
                p25=parse_float(row["p25"]),
                p75=parse_float(row["p75"]),
                p90=parse_float(row["p90"]),
                n_videos=int(row["n_videos"]),
            )
    return lookup


def build_cadence_reference(cycles_summary_path: Path) -> dict[str, float | int]:
    cadences: list[float] = []
    durations: list[float] = []
    with cycles_summary_path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if int(row.get("cycles", 0) or 0) < 2:
                continue
            cadence = parse_float(row.get("median_cadence_spm", ""))
            duration = parse_float(row.get("median_duration_sec", ""))
            if not math.isnan(cadence):
                cadences.append(cadence)
            if not math.isnan(duration):
                durations.append(duration)
    if not cadences:
        return {}
    c = np.array(cadences)
    d = np.array(durations) if durations else np.array([])
    return {
        "n_tracks": len(cadences),
        "cadence_median": float(np.median(c)),
        "cadence_p10": float(np.percentile(c, 10)),
        "cadence_p90": float(np.percentile(c, 90)),
        "duration_median": float(np.median(d)) if len(d) else 0.0,
        "duration_p10": float(np.percentile(d, 10)) if len(d) else 0.0,
        "duration_p90": float(np.percentile(d, 90)) if len(d) else 0.0,
    }


def nearest_reference(
    lookup: dict[tuple[str, float], ReferenceRow], metric: str, phase_pct: float
) -> ReferenceRow | None:
    keys = [k for k in lookup if k[0] == metric]
    if not keys:
        return None
    best_key = min(keys, key=lambda k: abs(k[1] - phase_pct))
    return lookup[best_key]


def deviation_from_band(value: float, ref: ReferenceRow) -> tuple[str, float]:
    """Return ('ok'|'below'|'above'|'missing', severity 0–5 capped)."""
    if math.isnan(value):
        return "missing", 0.0
    spread = max(ref.std, 5.0)
    if value < ref.p10:
        band = max(ref.p10 - ref.p25, spread * 0.5)
        severity = min((ref.p10 - value) / band, 5.0)
        return "below", float(severity)
    if value > ref.p90:
        band = max(ref.p90 - ref.p75, spread * 0.5)
        severity = min((value - ref.p90) / band, 5.0)
        return "above", float(severity)
    return "ok", 0.0


def phase_in_ranges(phase: float, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= phase <= end for start, end in ranges)


def score_phase_profile(
    profile_rows: list[dict],
    reference_lookup: dict[tuple[str, float], ReferenceRow],
    *,
    video_name: str,
    person_id: str,
    severity_threshold: float = 0.5,
) -> dict:
    deviations: list[dict] = []
    for row in profile_rows:
        metric = row["metric"]
        if metric not in PHASE_METRICS:
            continue
        phase = float(row["phase_pct"])
        value = float(row["mean"])
        ref = nearest_reference(reference_lookup, metric, phase)
        if ref is None:
            continue
        direction, severity = deviation_from_band(value, ref)
        if direction in {"below", "above"} and severity >= severity_threshold:
            deviations.append(
                {
                    "metric": metric,
                    "metric_label_ko": METRIC_LABELS_KO.get(metric, metric),
                    "phase_pct": phase,
                    "value": round(value, 2),
                    "ref_p10": round(ref.p10, 2),
                    "ref_p90": round(ref.p90, 2),
                    "ref_mean": round(ref.mean, 2),
                    "direction": direction,
                    "severity": round(severity, 3),
                }
            )

    deviations.sort(key=lambda d: d["severity"], reverse=True)

    issues: list[dict] = []
    for rule_id, rule in ISSUE_RULES.items():
        hits = [
            d
            for d in deviations
            if d["metric"] in rule["metrics"]
            and d["direction"] == ("below" if rule["direction"] == "below" else "above")
            and phase_in_ranges(d["phase_pct"], rule["phase_ranges"])
        ]
        if not hits:
            continue
        max_severity = max(h["severity"] for h in hits)
        issues.append(
            {
                "issue_id": rule_id,
                "label_ko": rule["label_ko"],
                "severity": round(max_severity, 3),
                "hit_count": len(hits),
                "example_phases": sorted({h["phase_pct"] for h in hits})[:5],
            }
        )
    issues.sort(key=lambda i: i["severity"], reverse=True)

    outside_count = len(deviations)
    total_checked = sum(1 for r in profile_rows if r["metric"] in PHASE_METRICS)
    overall_score = (
        float(np.median([d["severity"] for d in deviations[:20]])) if deviations else 0.0
    )

    return {
        "video": video_name,
        "person_id": person_id,
        "overall_deviation_score": round(overall_score, 3),
        "outside_band_count": outside_count,
        "phases_checked": total_checked,
        "top_deviations": deviations[:15],
        "detected_issues": issues,
    }


def build_marginal_reference(
    reference_lookup: dict[tuple[str, float], ReferenceRow],
) -> dict[str, dict[str, float]]:
    """Per-metric marginal stats from phase reference (for videos without clear cycles)."""
    marginal: dict[str, dict[str, float]] = {}
    for metric in REFERENCE_METRICS:
        rows = [ref for key, ref in reference_lookup.items() if key[0] == metric]
        if not rows:
            continue
        means = np.array([r.mean for r in rows], dtype=float)
        marginal[metric] = {
            "mean": float(np.mean(means)),
            "p10": float(np.percentile(means, 10)),
            "p90": float(np.percentile(means, 90)),
        }
    return marginal


def score_marginal_track(
    pose_video_dir: Path,
    marginal_ref: dict[str, dict[str, float]],
    *,
    video_name: str,
    person_id: str,
) -> dict:
    """Score using median angles when gait cycles cannot be segmented."""
    csvs = sorted(pose_video_dir.glob("person_*_elbow_angles.csv"))
    if not csvs:
        fallback = pose_video_dir / "initial_box_tracks_elbow_angles.csv"
        if fallback.exists():
            csvs = [fallback]
        else:
            return {"status": "no_track", "video": video_name}

    best_csv = csvs[0]
    best_count = 0
    for csv_path in csvs:
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        count = sum(1 for row in rows if row.get("pose_detected") == "yes")
        if count > best_count:
            best_count = count
            best_csv = csv_path

    rows = list(csv.DictReader(best_csv.open(encoding="utf-8")))
    if best_csv.name == "initial_box_tracks_elbow_angles.csv":
        person_id = rows[0].get("person_id", "1") if rows else "1"
    else:
        person_id = best_csv.stem.replace("person_", "").replace("_elbow_angles", "")
    deviations: list[dict] = []

    for metric in REFERENCE_METRICS:
        ref = marginal_ref.get(metric)
        if not ref:
            continue
        values = [parse_float(row.get(metric, "nan")) for row in rows if row.get("pose_detected") == "yes"]
        values = [v for v in values if not math.isnan(v)]
        if len(values) < 5:
            continue
        median_val = float(np.median(values))
        fake_ref = ReferenceRow(
            metric=metric,
            phase_pct=50.0,
            mean=ref["mean"],
            std=max(ref["p90"] - ref["p10"], 5.0) / 2,
            p10=ref["p10"],
            p25=ref["p10"],
            p75=ref["p90"],
            p90=ref["p90"],
            n_videos=0,
        )
        direction, severity = deviation_from_band(median_val, fake_ref)
        if direction in {"below", "above"}:
            deviations.append(
                {
                    "metric": metric,
                    "metric_label_ko": METRIC_LABELS_KO.get(metric, metric),
                    "phase_pct": 50.0,
                    "value": round(median_val, 2),
                    "ref_mean": round(ref["mean"], 2),
                    "ref_p10": round(ref["p10"], 2),
                    "ref_p90": round(ref["p90"], 2),
                    "direction": direction,
                    "severity": round(severity, 3),
                    "mode": "marginal",
                }
            )

    deviations.sort(key=lambda d: d["severity"], reverse=True)
    issues: list[dict] = []
    for rule_id, rule in ISSUE_RULES.items():
        hits = [
            d
            for d in deviations
            if d["metric"] in rule["metrics"]
            and d["direction"] == ("below" if rule["direction"] == "below" else "above")
        ]
        if hits:
            issues.append(
                {
                    "issue_id": rule_id,
                    "label_ko": rule["label_ko"],
                    "severity": max(h["severity"] for h in hits),
                    "hit_count": len(hits),
                    "example_phases": [],
                }
            )
    issues.sort(key=lambda i: i["severity"], reverse=True)

    return {
        "video": video_name,
        "person_id": person_id,
        "scoring_mode": "marginal_median",
        "overall_deviation_score": round(float(np.median([d["severity"] for d in deviations[:10]])) if deviations else 0.0, 3),
        "outside_band_count": len(deviations),
        "top_deviations": deviations[:15],
        "detected_issues": issues,
        "status": "ok",
    }


def load_user_phase_profile_csv(path: Path) -> tuple[str, str, list[dict]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise ValueError(f"Empty profile: {path}")
    video = rows[0].get("video_dir", path.parent.name)
    person = rows[0].get("person_id", "")
    profile = [
        {
            "metric": r["metric"],
            "phase_pct": parse_float(r["phase_pct"]),
            "mean": parse_float(r["mean"]),
        }
        for r in rows
        if r["metric"] in PHASE_METRICS
    ]
    return video, person, profile


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
