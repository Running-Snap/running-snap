"""Map 4-axis JSON metrics → per-axis coaching briefs for commentary prompts / SFT."""

from __future__ import annotations

from four_axis_metrics import AXIS_ARM_SWING, AXIS_CADENCE, AXIS_FOOT_STRIKE, AXIS_STRIDE, AXIS_LABELS_KO, FOUR_AXES


def _cadence_brief(entry: dict) -> str:
    spm = entry.get("cadence_spm")
    abnormal = entry.get("abnormal", False)
    if spm is None:
        return "케이던스 수치 없음 — 영상으로만 짧게 언급"
    spm_i = int(round(float(spm)))
    if abnormal:
        return (
            f"분당 약 {spm_i}보 (abnormal=true) → 이 숫자를 일상어로 넣고, "
            "보폭 줄이기·스텝 리듬 맞추기 해설"
        )
    return f"분당 약 {spm_i}보 (정상) → 리듬·페이스 유지 한 문장"


def _arm_swing_brief(entry: dict) -> str:
    bal = entry.get("arm_swing_balance")
    if bal and bal not in ("balanced", "unknown"):
        lr = entry.get("elbow_lr_median_gap_deg")
        left = entry.get("left_elbow_median_deg")
        right = entry.get("right_elbow_median_deg")
        parts = [f"좌우 팔꿈치 밸런스: {bal}"]
        if left is not None and right is not None:
            parts.append(f"(왼 {left:.0f}° / 오른 {right:.0f}°)")
        if lr is not None:
            parts.append(f"중앙값 차이 {lr:.0f}°")
        return " ".join(parts)
    abnormal = entry.get("abnormal", False)
    sev = entry.get("severity")
    sym = entry.get("elbow_symmetry_deg")
    parts = []
    if sev is not None:
        parts.append(f"severity {float(sev):.2f}")
    if sym is not None:
        parts.append(f"양팔 각도 차 {float(sym):.1f}°")
    metric = ", ".join(parts) if parts else "지표 참고"
    if abnormal:
        return (
            f"{metric} (abnormal=true) → 팔꿈치·스윙만 설명, "
            "몸 옆 앞뒤 작은 스윙·한쪽 과한 흔들림 교정"
        )
    return f"{metric} (정상) → 팔 스윙 양호 한 문장"


def _stride_brief(entry: dict) -> str:
    abnormal = entry.get("abnormal", False)
    mx = entry.get("overstride_forward_max")
    p90 = entry.get("overstride_forward_p90")
    sev = entry.get("severity")
    parts = []
    if mx is not None:
        parts.append(f"전방 과보폭 max {float(mx):.2f}")
    if p90 is not None:
        parts.append(f"p90 {float(p90):.2f}")
    if sev is not None:
        parts.append(f"severity {float(sev):.2f}")
    metric = ", ".join(parts) if parts else "지표 참고"
    if abnormal:
        return (
            f"{metric} (abnormal=true) → 보폭·전방 발만 설명, "
            "발이 몸보다 앞에 닿지 않게·보폭 줄이기"
        )
    return f"{metric} (정상) → 보폭 무난 한 문장"


def _foot_strike_brief(entry: dict) -> str:
    abnormal = entry.get("abnormal", False)
    p90 = entry.get("heel_drop_p90")
    med = entry.get("heel_drop_median")
    ct = entry.get("contact_time_sec")
    parts = []
    if p90 is not None:
        parts.append(f"뒤꿈치 하강 p90 {float(p90):.2f}")
    if med is not None:
        parts.append(f"median {float(med):.2f}")
    if ct is not None:
        parts.append(f"접촉 {float(ct):.2f}s")
    metric = ", ".join(parts) if parts else "지표 참고"
    if abnormal:
        return (
            f"{metric} (abnormal=true) → 착지만 설명, "
            "무거운 뒤꿈치 착지·가볍게 닿기·보폭·케이던스 연계"
        )
    return f"{metric} (정상) → 착지 양호 한 문장"


_BRIEF_FN = {
    AXIS_CADENCE: _cadence_brief,
    AXIS_ARM_SWING: _arm_swing_brief,
    AXIS_STRIDE: _stride_brief,
    AXIS_FOOT_STRIKE: _foot_strike_brief,
}


def build_axis_metric_briefs(axis_payload: dict) -> dict[str, str]:
    """One-line coaching hint per axis from JSON metrics."""
    axes = axis_payload.get("axes", {})
    out: dict[str, str] = {}
    for axis in FOUR_AXES:
        entry = axes.get(axis, {}) if isinstance(axes, dict) else {}
        fn = _BRIEF_FN.get(axis)
        out[axis] = fn(entry) if fn else ""
    return out


def format_metric_mapping_block(axis_payload: dict) -> str:
    """Text block for Qwen prompt: force commentary to follow each axis metric."""
    briefs = build_axis_metric_briefs(axis_payload)
    lines = [
        "[축별 지표 → 해설 매핑] (axes.{축}는 아래 해당 축 지표만 설명, 다른 축 금지)",
    ]
    triggers = axis_payload.get("triggers") or []
    if triggers:
        lines.append(f"- rule triggers: {triggers}")
    primary = axis_payload.get("primary_axis_ko", "")
    if primary:
        lines.append(f"- primary_axis_ko: {primary} (headline·commentary 우선 설명)")
    for axis in FOUR_AXES:
        label = AXIS_LABELS_KO[axis]
        lines.append(f"- {axis} ({label}): {briefs[axis]}")
    return "\n".join(lines)
