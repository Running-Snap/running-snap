"""4-axis MediaPipe context for Qwen prompts and axis-aligned hybrid rules."""

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

from four_axis_metrics import (
    AXIS_ARM_SWING,
    AXIS_CADENCE,
    AXIS_FOOT_STRIKE,
    AXIS_LABELS_KO,
    AXIS_STRIDE,
    FOUR_AXES,
)

GOOD_LABEL = "좋은 자세"
BAD_LABEL = "나쁜 자세"

AXIS_KEYWORDS: dict[str, list[str]] = {
    AXIS_CADENCE: ["케이던스", "스텝", "spm", "step", "cadence", "보폭 높", "스텝 수"],
    AXIS_ARM_SWING: ["팔꿈치", "팔 스윙", "팔꿈", "elbow", "arm swing", "arm_swing"],
    AXIS_STRIDE: ["보폭", "overstride", "오버스트라이드", "stride", "전방", "오버"],
    AXIS_FOOT_STRIKE: [
        "착지",
        "발목",
        "heel",
        "foot strike",
        "foot_strike",
        "뒤꿈치",
        "포어풋",
        "백스트라이크",
        "오버스트라이크",
    ],
}


def parse_triggers_field(raw: str) -> list[str]:
    if not raw or raw == "[]":
        return []
    try:
        return list(ast.literal_eval(raw))
    except (SyntaxError, ValueError):
        return [t.strip() for t in raw.split(";") if t.strip()]


def axes_from_triggers(triggers: list[str]) -> set[str]:
    axes: set[str] = set()
    for t in triggers:
        if ":" in t:
            axes.add(t.split(":", 1)[0])
    return axes


def axes_from_reason_text(text: str, *, qwen_label: str | None = None) -> set[str]:
    """Infer axes from Korean reason; skip generic praise lines on good labels."""
    if not text:
        return set()
    if qwen_label == "good":
        return set()
    if qwen_label != "bad" and any(
        p in text for p in ("적절합니다", "적절해", "올바르게", "올바른", "좋습니다", "좋은 자세")
    ):
        if not any(n in text for n in ("아닙니다", "아닌", "문제", "나쁨", "잘못")):
            return set()

    lower = text.lower()
    found: set[str] = set()
    for axis, keywords in AXIS_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lower or kw in text:
                found.add(axis)
                break
    return found


def evaluation_from_axis_payload(axis_payload: dict) -> dict:
    """Rebuild minimal evaluation dict for hybrid frame sampling."""
    axes = axis_payload.get("axes", {}) or {}
    axis_results = {
        ax: {"abnormal": bool((axes.get(ax) or {}).get("abnormal"))}
        for ax in FOUR_AXES
    }
    return {
        "predicted": axis_payload.get("overall_predicted", ""),
        "triggers": axis_payload.get("triggers", []),
        "axis_results": axis_results,
    }


def compact_axis_payload(metrics: dict[str, dict], evaluation: dict) -> dict:
    """JSON-safe summary for Qwen prompt."""
    axes_out: dict[str, dict] = {}
    axis_results = evaluation.get("axis_results", {})
    for axis in FOUR_AXES:
        m = metrics.get(axis, {})
        ar = axis_results.get(axis, {})
        entry: dict = {
            "label_ko": AXIS_LABELS_KO[axis],
            "abnormal": bool(ar.get("abnormal")),
        }
        if axis == AXIS_CADENCE:
            spm = m.get("cadence_spm")
            if spm is not None:
                entry["cadence_spm"] = spm
        else:
            if m.get("severity") is not None:
                entry["severity"] = m["severity"]
        if axis == AXIS_ARM_SWING:
            if m.get("elbow_symmetry_median_deg") is not None:
                entry["elbow_symmetry_deg"] = m["elbow_symmetry_median_deg"]
            if m.get("elbow_symmetry_p90_deg") is not None:
                entry["elbow_symmetry_p90_deg"] = m["elbow_symmetry_p90_deg"]
            if m.get("left_elbow_median_deg") is not None:
                entry["left_elbow_median_deg"] = round(float(m["left_elbow_median_deg"]), 1)
            if m.get("right_elbow_median_deg") is not None:
                entry["right_elbow_median_deg"] = round(float(m["right_elbow_median_deg"]), 1)
            if m.get("elbow_lr_median_gap_deg") is not None:
                entry["elbow_lr_median_gap_deg"] = round(float(m["elbow_lr_median_gap_deg"]), 1)
            if m.get("arm_swing_balance"):
                entry["arm_swing_balance"] = m["arm_swing_balance"]
        if axis == AXIS_STRIDE:
            for k in ("overstride_forward_max", "overstride_forward_p90"):
                if m.get(k) is not None:
                    entry[k] = m[k]
        if axis == AXIS_FOOT_STRIKE:
            for k in ("heel_drop_p90", "heel_drop_median", "contact_time_sec"):
                if m.get(k) is not None:
                    entry[k] = m[k]
        axes_out[axis] = entry

    return {
        "framework": "cadence | arm_swing | stride | foot_strike",
        "overall_predicted": evaluation.get("predicted", ""),
        "abnormal_axis_count": evaluation.get("abnormal_axis_count", 0),
        "triggers": evaluation.get("triggers", []),
        "primary_axis_ko": evaluation.get("primary_axis_ko", ""),
        "axes": axes_out,
    }


def build_minimal_prompt_with_axis_context(axis_payload: dict) -> str:
    """영상 + 4축 JSON만. good/bad 기준 문구·추가 힌트 없음 (출력 스키마만)."""
    ctx = json.dumps(axis_payload, ensure_ascii=False, indent=2)
    return f"""[4-axis JSON]
{ctx}

아래 JSON만 출력:
{{"label":"good"|"bad","axes_bad":[],"reason":""}}"""


def build_prompt_with_axis_context(axis_payload: dict) -> str:
    ctx = json.dumps(axis_payload, ensure_ascii=False, indent=2)
    vision_note = build_vision_context_note(axis_payload)
    return f"""이 영상은 러닝(달리기) 자세 영상입니다.
{vision_note}

아래는 MediaPipe 후처리 + 4축 rule 엔진이 계산한 참고 지표입니다 (케이던스·팔 스윙·보폭·착지).
영상 내용과 함께 참고하되, 지표와 다르면 영상을 우선하세요.

[4-axis 참고 JSON]
{ctx}

판단 기준:
- good: 마라톤/조깅에 적합한 전반적으로 올바른 러닝 자세
- bad: 명확한 자세 문제가 보임

반드시 아래 JSON만 출력하세요:
{{
  "label": "good" 또는 "bad",
  "axes_bad": ["cadence", "arm_swing", "stride", "foot_strike" 중 문제 있는 축만, 없으면 []],
  "reason": "한 문장 한국어"
}}"""


def build_vision_context_note(axis_payload: dict) -> str:
    """첨부 프레임과 MP JSON 매칭 안내."""
    fc = axis_payload.get("frame_context") or {}
    n = fc.get("qwen_saved_frame_count") or fc.get("qwen_sampled_frame_count")
    indices = fc.get("qwen_sampled_frame_indices") or []
    if not n:
        return "이 메시지 **앞쪽에 첨부된 러닝 영상 프레임**과 아래 JSON을 함께 보세요."
    idx_txt = ", ".join(str(i) for i in indices[:16])
    if len(indices) > 16:
        idx_txt += ", ..."
    return (
        f"이 메시지 **앞쪽에 첨부된 {n}장의 영상 프레임**(인덱스: {idx_txt})과 아래 JSON을 함께 보세요. "
        "JSON만 보지 말고 반드시 프레임에서 동작을 확인하세요."
    )


def build_user_feedback_prompt_with_full_axis(
    axis_payload: dict,
    *,
    qwen_label: str = "",
    qwen_axes_bad: list[str] | None = None,
    qwen_reason: str = "",
    style: str = "황영조",
    coaching_only: bool = False,
) -> str:
    """영상 + 풀 4축 JSON (+ 선택: 1단계 Qwen 분류) → user_feedback 코칭 프롬프트."""
    from user_feedback_schema import build_user_feedback_prompt_instruction
    from hwang_coaching_style import build_hwang_style_prompt_block

    ctx = json.dumps(axis_payload, ensure_ascii=False, indent=2)
    style_block = build_hwang_style_prompt_block(
        style=style,
        allow_video_observations=True,
    )
    vision_note = build_vision_context_note(axis_payload)
    classify_block = ""
    if qwen_label and not coaching_only:
        axes_txt = ", ".join(qwen_axes_bad or [])
        classify_block = f"""
[1단계 Qwen 4축 분류 — 참고]
- label: {qwen_label}
- axes_bad: [{axes_txt}]
- reason: {qwen_reason}
"""
    if coaching_only:
        level_rules = """- 축별로 영상·지표를 보고 checkpoint status를 good 또는 attention으로 제안하세요.
- summary.level은 good 또는 need_improvement 중 하나로 제안 (서버가 MP와 합의해 caution으로 조정할 수 있음).
- axes.*.abnormal 이 true 인 축은 보통 attention.
- **영상에서만** 보이고 MP JSON에는 없는 점(상체 기울기, 리듬감 등)은:
  1) 가능하면 해당하는 4축 checkpoint의 what_we_saw에 넣거나,
  2) 4축에 안 맞으면 video_only_notes 배열(한국어 문장 1~3개)에 추가하세요.
- MP JSON이 정상이어도 영상에서 분명한 문제가 있으면 그 축은 attention으로 표시하세요.
- MP overall_predicted·triggers·좌우 팔꿈치 수치를 반영하되, 지표와 영상이 다르면 **영상을 우선**하세요."""
    else:
        level_rules = """- label이 good이면 summary.level은 "good".
- label이 bad이면 summary.level은 "need_improvement", axes_bad 축은 attention 위주."""

    return f"""이 영상은 러닝(달리기) 자세입니다. {vision_note}
**초보 러너가 앱에서 읽을** 한국어 코칭 피드백 JSON을 작성하세요.
{classify_block}
[4-axis 참고 JSON — MediaPipe rule + 수치]
{ctx}

규칙:
- JSON·영문 키·severity는 사용자 문장에 넣지 마세요.
- checkpoints는 cadence, arm_swing, stride, foot_strike **4축 모두** area_key 포함.
{level_rules}
- style: {style}

{style_block}
{build_user_feedback_prompt_instruction()}
"""


def parse_qwen_axis_json(text: str) -> tuple[str, str, list[str]]:
    """Return (label, reason, axes_bad list)."""
    match = re.search(r"\{[\s\S]*\}", text)
    axes_bad: list[str] = []
    if match:
        try:
            data = json.loads(match.group())
            label = str(data.get("label", "")).lower()
            reason = str(data.get("reason", ""))
            raw_axes = data.get("axes_bad", [])
            if isinstance(raw_axes, list):
                for a in raw_axes:
                    s = str(a).strip()
                    if s in FOUR_AXES:
                        axes_bad.append(s)
            if label in ("good", "bad"):
                if not axes_bad and label == "bad":
                    axes_bad = sorted(axes_from_reason_text(reason, qwen_label=label))
                return label, reason, axes_bad
        except json.JSONDecodeError:
            pass
    if "bad" in text.lower() or "나쁨" in text or "문제" in text:
        reason = text[:200]
        return "bad", reason, sorted(axes_from_reason_text(reason, qwen_label="bad"))
    return "good", text[:200], []


def compute_axis_evaluation(
    out_name: str,
    *,
    pose_dir: Path,
    profiles_dir: Path,
    reference_dir: Path,
    cadence_spm: float | None = None,
) -> tuple[dict, dict]:
    """Rebuild four_axis metrics + evaluation from pose/profile dirs."""
    from normal_pose_reference import (
        build_marginal_reference,
        load_phase_reference,
        score_marginal_track,
        score_phase_profile,
    )
    from pose_rules import classify_four_axis, load_pose_rules

    rules = load_pose_rules(reference_dir / "pose_rules.json")
    ref = load_phase_reference(reference_dir / "normal_phase_reference.csv")
    marginal_ref = build_marginal_reference(ref)
    pdir = pose_dir / out_name

    prof_csv = profiles_dir / out_name / f"{out_name}_normal_phase_profile.csv"
    if prof_csv.exists():
        prof_rows = list(csv.DictReader(prof_csv.open(encoding="utf-8")))
        profile = [
            {"metric": x["metric"], "phase_pct": float(x["phase_pct"]), "mean": float(x["mean"])}
            for x in prof_rows
        ]
        report = score_phase_profile(profile, ref, video_name=out_name, person_id="1")
    else:
        report = score_marginal_track(pdir, marginal_ref, video_name=out_name, person_id="1")

    evaluation = classify_four_axis(report, rules, pose_dir=pdir, cadence_spm=cadence_spm)
    metrics = evaluation["four_axis_metrics"]
    return metrics, evaluation


def load_axis_evaluation_for_video(
    video: str,
    *,
    axis_csv: Path,
    pose_dir: Path,
    profiles_dir: Path,
    reference_dir: Path,
) -> tuple[dict, dict] | None:
    """Rebuild four_axis metrics + evaluation for one validation video."""
    from normal_pose_reference import parse_float

    rows = list(csv.DictReader(axis_csv.open(encoding="utf-8")))
    row = next((r for r in rows if r["video"] == video), None)
    if not row:
        return None

    out_name = row["output_name"]
    spm_raw = row.get("cadence_spm", "")
    cadence_spm = parse_float(spm_raw) if spm_raw not in ("", None) else None
    return compute_axis_evaluation(
        out_name,
        pose_dir=pose_dir,
        profiles_dir=profiles_dir,
        reference_dir=reference_dir,
        cadence_spm=cadence_spm,
    )


def mp_axes_from_evaluation(evaluation: dict) -> set[str]:
    triggers = evaluation.get("triggers", [])
    axes = axes_from_triggers(triggers)
    if axes:
        return axes
    # critical-only: infer from axis_results abnormal or high severity
    axis_results = evaluation.get("axis_results", {})
    for axis in FOUR_AXES:
        if axis_results.get(axis, {}).get("abnormal"):
            axes.add(axis)
    metrics = evaluation.get("four_axis_metrics", {})
    for axis in (AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE):
        sev = (metrics.get(axis) or {}).get("severity", 0) or 0
        if sev >= 3.0:
            axes.add(axis)
    if AXIS_CADENCE not in axes:
        m = metrics.get(AXIS_CADENCE, {})
        # cadence abnormal already in triggers; skip here
        _ = m
    return axes


def operational_hybrid_label(
    mp_bad: bool,
    qwen_bad: bool,
    mp_axes: set[str],
    qwen_axes: set[str],
) -> tuple[str, str, bool]:
    """
    합의 운영 규칙 (validation 30 기준).

    | MP | Qwen | 축 겹침 | 최종 | tier |
    | 좋음 | 좋음 | - | 좋음 | 확정_좋음 |
    | 나쁨 | 나쁨 | O | 나쁨 | 확정_나쁨 |
    | 나쁨 | 좋음 | - | 좋음 | 검토 |
    | 좋음 | 나쁨 | - | 나쁨 | Qwen_보완 |

    MP·Qwen 둘 다 나쁨인데 축 겹침 없음 → 나쁨 (둘다나쁨_축불일치).
    """
    overlap = bool(mp_axes & qwen_axes)
    if not mp_bad and not qwen_bad:
        return GOOD_LABEL, "확정_좋음", overlap
    if not mp_bad and qwen_bad:
        return BAD_LABEL, "Qwen_보완", overlap
    if mp_bad and not qwen_bad:
        return GOOD_LABEL, "검토", overlap
    if mp_bad and qwen_bad and overlap:
        return BAD_LABEL, "확정_나쁨", overlap
    if mp_bad and qwen_bad:
        return BAD_LABEL, "둘다나쁨_축불일치", overlap
    return GOOD_LABEL, "unknown", overlap


def disagreement_review_label(
    mp_bad: bool,
    qwen_bad: bool,
    mp_axes: set[str],
    qwen_axes: set[str],
) -> tuple[str, str, bool]:
    """
    MP ≠ Qwen 이면 무조건 검토 tier; 일치할 때만 확정.

    | MP | Qwen | 최종(일치 시) | tier |
    | 좋음 | 좋음 | 좋음 | 확정_좋음 |
    | 나쁨 | 나쁨 | 나쁨 | 확정_나쁨 |
    | 불일치 | - | (검토; CM용 별도 매핑) | 검토_불일치 |
    """
    overlap = bool(mp_axes & qwen_axes)
    if mp_bad != qwen_bad:
        return GOOD_LABEL, "검토_불일치", overlap
    if not mp_bad:
        return GOOD_LABEL, "확정_좋음", overlap
    return BAD_LABEL, "확정_나쁨", overlap


# Backward-compatible alias
def tiered_hybrid_label(
    mp_bad: bool,
    qwen_bad: bool,
    mp_axes: set[str],
    qwen_axes: set[str],
) -> tuple[str, str, bool]:
    return operational_hybrid_label(mp_bad, qwen_bad, mp_axes, qwen_axes)
