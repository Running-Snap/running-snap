"""
4-axis running form metrics: cadence, arm_swing, stride, foot_strike.

Used for rule definition, calibration, and Qwen JSON summaries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from normal_pose_reference import parse_float
from segment_running_cycles import read_track_csv

AXIS_CADENCE = "cadence"
AXIS_ARM_SWING = "arm_swing"
AXIS_STRIDE = "stride"
AXIS_FOOT_STRIKE = "foot_strike"

FOUR_AXES = (AXIS_CADENCE, AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE)

AXIS_LABELS_KO = {
    AXIS_CADENCE: "케이던스",
    AXIS_ARM_SWING: "팔 스윙",
    AXIS_STRIDE: "보폭",
    AXIS_FOOT_STRIKE: "착지 패턴",
}

# Map legacy phase issue ids → axis
ISSUE_TO_AXIS = {
    "elbow_too_bent": AXIS_ARM_SWING,
    "elbow_too_extended": AXIS_ARM_SWING,
    "low_knee_flexion": AXIS_STRIDE,
    "high_knee_flexion": AXIS_STRIDE,
    "excessive_torso_lean": AXIS_STRIDE,
    "low_torso_lean": AXIS_STRIDE,
}


@dataclass
class AxisThresholds:
    """Calibrated band / limit for one axis."""

    spm_min: float | None = None
    spm_max: float | None = None
    symmetry_max_deg: float | None = None
    symmetry_p90_max_deg: float | None = None
    lr_median_gap_deg_min: float | None = None
    phase_severity_min: float = 0.5
    overstride_forward_max: float | None = None
    knee_extension_phase_severity_min: float = 0.5
    contact_time_min_sec: float | None = None
    contact_time_max_sec: float | None = None
    heel_drop_max: float | None = None
    ankle_angle_min_deg: float | None = None
    ankle_angle_max_deg: float | None = None
    critical_severity: float = 3.0


@dataclass
class FourAxisRules:
    version: str = "2"
    method: str = ""
    axes: dict[str, dict] = field(default_factory=dict)
    min_axes_abnormal: int = 2
    severity_threshold: float = 0.5
    calibration_n_videos: int = 0

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "method": self.method,
            "framework": "cadence | arm_swing | stride | foot_strike",
            "min_axes_abnormal": self.min_axes_abnormal,
            "severity_threshold": self.severity_threshold,
            "calibration_n_videos": self.calibration_n_videos,
            "axes": self.axes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FourAxisRules:
        return cls(
            version=str(data.get("version", "2")),
            method=data.get("method", ""),
            axes=data.get("axes", {}),
            min_axes_abnormal=int(data.get("min_axes_abnormal", 2)),
            severity_threshold=float(data.get("severity_threshold", 0.5)),
            calibration_n_videos=int(data.get("calibration_n_videos", 0)),
        )


def _series(rows: list[dict], key: str) -> np.ndarray:
    vals = []
    for row in rows:
        if row.get("pose_detected") != "yes":
            continue
        v = parse_float(row.get(key, ""))
        if not math.isnan(v):
            vals.append(v)
    return np.array(vals, dtype=float)


def _strike_frames(rows: list[dict], ankle_y_key: str = "left_ankle_deg") -> list[int]:
    """Proxy: use lowest foot_forward frames at high ankle y — use heel_drop + forward."""
    ys = []
    for i, row in enumerate(rows):
        if row.get("pose_detected") != "yes":
            continue
        for ak in ("left_heel_drop", "right_heel_drop"):
            v = parse_float(row.get(ak, ""))
            if not math.isnan(v):
                ys.append((i, v))
    if not ys:
        return []
    arr = np.array([y[1] for y in ys])
    thresh = np.percentile(arr, 75)
    return [ys[j][0] for j in range(len(ys)) if arr[j] >= thresh]


def compute_track_proxies(rows: list[dict]) -> dict[str, float]:
    """Stride / foot-strike scalars from per-frame track CSV."""
    lf = _series(rows, "left_foot_forward")
    rf = _series(rows, "right_foot_forward")
    forward = np.concatenate([lf, rf]) if len(lf) and len(rf) else (lf if len(lf) else rf)

    lh = _series(rows, "left_heel_drop")
    rh = _series(rows, "right_heel_drop")
    heel = np.concatenate([lh, rh]) if len(lh) and len(rh) else (lh if len(lh) else rh)

    la = _series(rows, "left_ankle_deg")
    ra = _series(rows, "right_ankle_deg")
    ankle_ang = np.concatenate([la, ra]) if len(la) and len(ra) else (la if len(la) else ra)

    le = _series(rows, "left_elbow_deg")
    re = _series(rows, "right_elbow_deg")
    elbow_sym = _series(rows, "elbow_symmetry_diff_deg")
    knee_sym = _series(rows, "knee_symmetry_diff_deg")

    out: dict[str, float] = {}
    if len(forward):
        out["overstride_forward_max"] = float(np.max(forward))
        out["overstride_forward_p90"] = float(np.percentile(forward, 90))
    if len(heel):
        out["heel_drop_median"] = float(np.median(heel))
        out["heel_drop_p90"] = float(np.percentile(heel, 90))
    if len(ankle_ang):
        out["ankle_angle_median"] = float(np.median(ankle_ang))
    if len(elbow_sym):
        out["elbow_symmetry_median"] = float(np.median(elbow_sym))
        out["elbow_symmetry_p90"] = float(np.percentile(elbow_sym, 90))
    if len(le) and len(re):
        out["left_elbow_median_deg"] = float(np.median(le))
        out["right_elbow_median_deg"] = float(np.median(re))
        out["elbow_lr_median_gap_deg"] = abs(out["left_elbow_median_deg"] - out["right_elbow_median_deg"])
    if len(knee_sym):
        out["knee_symmetry_median"] = float(np.median(knee_sym))

    # Contact time proxy: ankle y velocity peaks spacing — simplified via cycle duration fraction
    times = np.array([parse_float(r["time_sec"]) for r in rows if r.get("pose_detected") == "yes"])
    if len(times) >= 10:
        out["track_duration_sec"] = float(times[-1] - times[0])
    return out


def infer_arm_swing_balance_label(left_median: float | None, right_median: float | None) -> str:
    """좌우 팔꿈치 중앙값 → 해석용 라벨 (rule/Qwen JSON)."""
    if left_median is None or right_median is None:
        return "unknown"
    gap = abs(left_median - right_median)
    if gap < 15.0:
        return "balanced"
    if left_median < right_median - 10.0:
        return "left_arm_more_bent"
    if right_median < left_median - 10.0:
        return "right_arm_more_bent"
    return "asymmetric"


def arm_swing_severity_from_report(phase_report: dict) -> tuple[float, list[str]]:
    """Aggregate elbow-related phase deviations into arm_swing severity."""
    labels: list[str] = []
    severities: list[float] = []
    for issue in phase_report.get("detected_issues", []):
        iid = issue.get("issue_id", "")
        if ISSUE_TO_AXIS.get(iid) == AXIS_ARM_SWING:
            severities.append(float(issue.get("severity", 0)))
            labels.append(issue.get("label_ko", iid))
    for dev in phase_report.get("top_deviations", []):
        if dev.get("metric", "") in ("left_elbow_deg", "right_elbow_deg"):
            severities.append(float(dev.get("severity", 0)))
    severity = float(max(severities)) if severities else 0.0
    return severity, labels


def stride_severity_from_report(phase_report: dict, proxies: dict) -> tuple[float, list[str]]:
    labels: list[str] = []
    severities: list[float] = []
    for issue in phase_report.get("detected_issues", []):
        iid = issue.get("issue_id", "")
        if ISSUE_TO_AXIS.get(iid) == AXIS_STRIDE:
            severities.append(float(issue.get("severity", 0)))
            labels.append(issue.get("label_ko", iid))
    for dev in phase_report.get("top_deviations", []):
        if dev.get("metric", "") in ("left_knee_deg", "right_knee_deg", "torso_lean_deg"):
            severities.append(float(dev.get("severity", 0)) * 0.8)
    return float(max(severities)) if severities else 0.0, labels


def compute_four_axis_metrics(
    *,
    phase_report: dict,
    track_rows: list[dict] | None = None,
    cadence_spm: float | None = None,
    contact_time_sec: float | None = None,
) -> dict[str, dict]:
    """Build per-axis measurement dict for one video."""
    proxies = compute_track_proxies(track_rows) if track_rows else {}
    arm_sev, arm_labels = arm_swing_severity_from_report(phase_report)
    stride_sev, stride_labels = stride_severity_from_report(phase_report, proxies)

    metrics: dict[str, dict] = {
        AXIS_CADENCE: {
            "cadence_spm": cadence_spm,
            "status": "unknown" if cadence_spm is None else "measured",
        },
        AXIS_ARM_SWING: {
            "severity": round(arm_sev, 3),
            "elbow_symmetry_median_deg": proxies.get("elbow_symmetry_median"),
            "elbow_symmetry_p90_deg": proxies.get("elbow_symmetry_p90"),
            "left_elbow_median_deg": proxies.get("left_elbow_median_deg"),
            "right_elbow_median_deg": proxies.get("right_elbow_median_deg"),
            "elbow_lr_median_gap_deg": proxies.get("elbow_lr_median_gap_deg"),
            "arm_swing_balance": infer_arm_swing_balance_label(
                proxies.get("left_elbow_median_deg"),
                proxies.get("right_elbow_median_deg"),
            ),
            "labels": arm_labels,
        },
        AXIS_STRIDE: {
            "severity": round(stride_sev, 3),
            "overstride_forward_max": proxies.get("overstride_forward_max"),
            "overstride_forward_p90": proxies.get("overstride_forward_p90"),
            "labels": stride_labels,
        },
        AXIS_FOOT_STRIKE: {
            "contact_time_sec": contact_time_sec,
            "heel_drop_median": proxies.get("heel_drop_median"),
            "heel_drop_p90": proxies.get("heel_drop_p90"),
            "ankle_angle_median_deg": proxies.get("ankle_angle_median"),
            "severity": 0.0,
            "labels": [],
        },
    }

    # Foot strike severity: extreme heel drop or ankle angle vs neutral ~100-130
    fs_sev = 0.0
    fs_labels: list[str] = []
    if proxies.get("heel_drop_p90") is not None and proxies["heel_drop_p90"] > 0.08:
        fs_sev = max(fs_sev, min((proxies["heel_drop_p90"] - 0.05) / 0.03, 5.0))
        fs_labels.append("heel drop 큼 (뒤꿈치 착지 경향)")
    ang = proxies.get("ankle_angle_median")
    if ang is not None and (ang < 95 or ang > 140):
        fs_sev = max(fs_sev, min(abs(ang - 115) / 15.0, 5.0))
        fs_labels.append("발목 각도 비정상 (착지 패턴)")
    if contact_time_sec is not None:
        metrics[AXIS_FOOT_STRIKE]["contact_time_sec"] = round(contact_time_sec, 4)
    for k in ("heel_drop_median", "heel_drop_p90", "ankle_angle_median"):
        if proxies.get(k) is not None:
            key = "ankle_angle_median_deg" if k == "ankle_angle_median" else k
            metrics[AXIS_FOOT_STRIKE][key] = proxies[k]
    metrics[AXIS_FOOT_STRIKE]["severity"] = round(fs_sev, 3)
    metrics[AXIS_FOOT_STRIKE]["labels"] = fs_labels

    return metrics


def evaluate_four_axes(metrics: dict[str, dict], rules: FourAxisRules) -> dict:
    """Return per-axis abnormal flags and overall classification."""
    axis_results: dict[str, dict] = {}
    abnormal_count = 0
    triggers: list[str] = []
    th = rules.severity_threshold

    cadence_rules = rules.axes.get(AXIS_CADENCE, {})
    spm = metrics[AXIS_CADENCE].get("cadence_spm")
    cadence_abnormal = False
    if spm is not None:
        lo, hi = cadence_rules.get("spm_min"), cadence_rules.get("spm_max")
        if lo is not None and spm < lo:
            cadence_abnormal = True
            triggers.append(f"{AXIS_CADENCE}:spm<{lo}")
        if hi is not None and spm > hi:
            cadence_abnormal = True
            triggers.append(f"{AXIS_CADENCE}:spm>{hi}")
    if cadence_abnormal:
        abnormal_count += 1
    axis_results[AXIS_CADENCE] = {"abnormal": cadence_abnormal, "metrics": metrics[AXIS_CADENCE]}

    arm_rules = rules.axes.get(AXIS_ARM_SWING, {})
    arm = metrics[AXIS_ARM_SWING]
    arm_abnormal = False
    if arm.get("severity", 0) >= arm_rules.get("phase_severity_min", th):
        arm_abnormal = True
        triggers.append(f"{AXIS_ARM_SWING}:severity>={arm_rules.get('phase_severity_min', th)}")
    sym_max = arm_rules.get("symmetry_max_deg")
    sym = arm.get("elbow_symmetry_median_deg")
    if sym_max is not None and sym is not None and sym > sym_max:
        arm_abnormal = True
        triggers.append(f"{AXIS_ARM_SWING}:symmetry>{sym_max}")
    sym_p90_max = arm_rules.get("symmetry_p90_max_deg")
    sym_p90 = arm.get("elbow_symmetry_p90_deg")
    lr_gap_min = arm_rules.get("lr_median_gap_deg_min")
    lr_gap = arm.get("elbow_lr_median_gap_deg")
    if lr_gap_min is not None and lr_gap is not None and lr_gap > lr_gap_min:
        arm_abnormal = True
        triggers.append(f"{AXIS_ARM_SWING}:lr_median_gap>{lr_gap_min}")
    elif (
        sym_p90_max is not None
        and sym_p90 is not None
        and lr_gap_min is not None
        and lr_gap is not None
        and sym_p90 > sym_p90_max
        and lr_gap > lr_gap_min * 0.85
    ):
        arm_abnormal = True
        triggers.append(f"{AXIS_ARM_SWING}:symmetry_p90>{sym_p90_max}")
    if arm_abnormal:
        abnormal_count += 1
    axis_results[AXIS_ARM_SWING] = {"abnormal": arm_abnormal, "metrics": arm}

    stride_rules = rules.axes.get(AXIS_STRIDE, {})
    stride = metrics[AXIS_STRIDE]
    stride_abnormal = False
    if stride.get("severity", 0) >= stride_rules.get("phase_severity_min", th):
        stride_abnormal = True
        triggers.append(f"{AXIS_STRIDE}:phase_severity")
    fwd_max = stride_rules.get("overstride_forward_max")
    fwd = stride.get("overstride_forward_max") or stride.get("overstride_forward_p90")
    if fwd_max is not None and fwd is not None and fwd > fwd_max:
        stride_abnormal = True
        triggers.append(f"{AXIS_STRIDE}:overstride>{fwd_max}")
    if stride_abnormal:
        abnormal_count += 1
    axis_results[AXIS_STRIDE] = {"abnormal": stride_abnormal, "metrics": stride}

    fs_rules = rules.axes.get(AXIS_FOOT_STRIKE, {})
    fs = metrics[AXIS_FOOT_STRIKE]
    fs_abnormal = False
    if fs.get("severity", 0) >= fs_rules.get("severity_min", th):
        fs_abnormal = True
        triggers.append(f"{AXIS_FOOT_STRIKE}:severity")
    ct = fs.get("contact_time_sec")
    if ct is not None:
        if fs_rules.get("contact_time_min_sec") is not None and ct < fs_rules["contact_time_min_sec"]:
            fs_abnormal = True
            triggers.append(f"{AXIS_FOOT_STRIKE}:contact_short")
        if fs_rules.get("contact_time_max_sec") is not None and ct > fs_rules["contact_time_max_sec"]:
            fs_abnormal = True
            triggers.append(f"{AXIS_FOOT_STRIKE}:contact_long")
    hd_max = fs_rules.get("heel_drop_max")
    hd = fs.get("heel_drop_p90")
    if hd is None:
        hd = fs.get("heel_drop_median")
    if hd_max is not None and hd is not None and hd > hd_max:
        fs_abnormal = True
        triggers.append(f"{AXIS_FOOT_STRIKE}:heel_drop")
    if fs_abnormal:
        abnormal_count += 1
    axis_results[AXIS_FOOT_STRIKE] = {"abnormal": fs_abnormal, "metrics": fs}

    critical = any(
        metrics[ax].get("severity", 0) >= rules.axes.get(ax, {}).get("critical_severity", 3.0)
        for ax in (AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE)
    )
    is_bad = abnormal_count >= rules.min_axes_abnormal or critical

    primary = ""
    for ax in FOUR_AXES:
        if axis_results[ax]["abnormal"]:
            primary = AXIS_LABELS_KO[ax]
            break

    return {
        "predicted": "나쁜 자세" if is_bad else "좋은 자세",
        "is_bad_candidate": is_bad,
        "abnormal_axis_count": abnormal_count,
        "triggers": triggers,
        "primary_axis_ko": primary,
        "axis_results": axis_results,
        "four_axis_metrics": metrics,
    }


def calibrate_four_axis_rules(
    samples: list[dict[str, dict]],
    *,
    cadence_ref: dict,
    percentile: float = 90.0,
    method: str,
) -> FourAxisRules:
    """Calibrate axis bands from Marathon good-pose samples (list of compute_four_axis_metrics outputs)."""
    spms = [s[AXIS_CADENCE]["cadence_spm"] for s in samples if s[AXIS_CADENCE].get("cadence_spm") is not None]
    sym = [s[AXIS_ARM_SWING]["elbow_symmetry_median_deg"] for s in samples if s[AXIS_ARM_SWING].get("elbow_symmetry_median_deg")]
    sym_p90 = [s[AXIS_ARM_SWING]["elbow_symmetry_p90_deg"] for s in samples if s[AXIS_ARM_SWING].get("elbow_symmetry_p90_deg")]
    lr_gap = [s[AXIS_ARM_SWING]["elbow_lr_median_gap_deg"] for s in samples if s[AXIS_ARM_SWING].get("elbow_lr_median_gap_deg")]
    fwd = [s[AXIS_STRIDE].get("overstride_forward_max") or s[AXIS_STRIDE].get("overstride_forward_p90") for s in samples]
    fwd = [f for f in fwd if f is not None]
    heel = [s[AXIS_FOOT_STRIKE].get("heel_drop_p90") or s[AXIS_FOOT_STRIKE].get("heel_drop_median") for s in samples]
    heel = [h for h in heel if h is not None]
    ct = [s[AXIS_FOOT_STRIKE]["contact_time_sec"] for s in samples if s[AXIS_FOOT_STRIKE].get("contact_time_sec")]
    arm_sev = [s[AXIS_ARM_SWING]["severity"] for s in samples]
    stride_sev = [s[AXIS_STRIDE]["severity"] for s in samples]
    fs_sev = [s[AXIS_FOOT_STRIKE]["severity"] for s in samples]

    def pct(arr, p, default=0.0):
        return float(np.percentile(arr, p)) if arr else default

    c_min = cadence_ref.get("cadence_p10") or (pct(spms, 10) if spms else None)
    c_max = cadence_ref.get("cadence_p90") or (pct(spms, 90) if spms else None)
    if c_min is not None:
        c_min = float(c_min) * 0.85
    if c_max is not None:
        c_max = float(c_max) * 1.15

    axes = {
        AXIS_CADENCE: {
            "label_ko": AXIS_LABELS_KO[AXIS_CADENCE],
            "spm_min": round(c_min, 2) if c_min is not None else None,
            "spm_max": round(c_max, 2) if c_max is not None else None,
            "description": "주기 기반 분당 스텝 수 (SPM)",
        },
        AXIS_ARM_SWING: {
            "label_ko": AXIS_LABELS_KO[AXIS_ARM_SWING],
            "symmetry_max_deg": round(pct(sym, percentile) * 1.05, 2) if sym else None,
            "symmetry_p90_max_deg": round(pct(sym_p90, 98) * 1.02, 2) if sym_p90 else None,
            "lr_median_gap_deg_min": round(pct(lr_gap, 95) * 1.02, 2) if lr_gap else None,
            "phase_severity_min": round(max(pct(arm_sev, 95), 1.2), 2),
            "critical_severity": 3.0,
            "description": "팔꿈치 phase 편차 + 좌우 대칭(median/p90/L-R gap)",
        },
        AXIS_STRIDE: {
            "label_ko": AXIS_LABELS_KO[AXIS_STRIDE],
            "overstride_forward_max": round(pct(fwd, percentile) * 1.08, 4) if fwd else None,
            "phase_severity_min": round(max(pct(stride_sev, 95), 1.2), 2),
            "critical_severity": 3.0,
            "description": "발 전방 위치(overstride 프록시) + 무릎/상체 phase",
        },
        AXIS_FOOT_STRIKE: {
            "label_ko": AXIS_LABELS_KO[AXIS_FOOT_STRIKE],
            "heel_drop_max": round(pct(heel, percentile) * 1.1, 4) if heel else None,
            "contact_time_min_sec": round(pct(ct, 5) * 0.85, 3) if ct else None,
            "contact_time_max_sec": round(pct(ct, 95) * 1.15, 3) if ct else None,
            "severity_min": round(max(pct(fs_sev, 95), 1.0), 2),
            "critical_severity": 3.0,
            "description": "heel drop, 접지 시간, 발목 각도 프록시",
        },
    }

    return FourAxisRules(
        version="2",
        method=method,
        axes=axes,
        min_axes_abnormal=2,
        severity_threshold=0.5,
        calibration_n_videos=len(samples),
    )


def load_track_and_metrics(
    pose_dir: Path,
    phase_report: dict,
    cadence_spm: float | None,
) -> dict[str, dict]:
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    rows = read_track_csv(csv_path) if csv_path.exists() else None
    contact = None
    # rough contact: 40% of step period if cadence known
    if cadence_spm and cadence_spm > 0:
        period = 60.0 / cadence_spm
        contact = period * 0.4
    return compute_four_axis_metrics(
        phase_report=phase_report,
        track_rows=rows,
        cadence_spm=cadence_spm,
        contact_time_sec=contact,
    )
