"""
사용자용 러닝 피드백 JSON (앱/화면 표시용).

SFT assistant 정답·API 응답 모두 이 형식을 권장합니다.
숫자·severity·영문 키는 넣지 않고, 초보자가 읽는 한국어만 사용합니다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from four_axis_metrics import AXIS_ARM_SWING, AXIS_CADENCE, AXIS_FOOT_STRIKE, AXIS_STRIDE, AXIS_LABELS_KO, FOUR_AXES
from sft_compact_schema import (
    ARM_IMBALANCED,
    ARM_OK,
    FOOT_HEAVY_HEEL,
    FOOT_OK,
    FOOT_OVER_FRONT,
    STRIDE_LONG,
    STRIDE_OK,
    axis_payload_to_compact_input,
)

STATUS_GOOD = "good"
STATUS_ATTENTION = "attention"
STATUS_CAUTION = "caution"

LEVEL_GOOD = "good"
LEVEL_CAUTION = "caution"
LEVEL_NEED_IMPROVEMENT = "need_improvement"

AREA_KEYS = {
    AXIS_CADENCE: AXIS_CADENCE,
    AXIS_ARM_SWING: AXIS_ARM_SWING,
    AXIS_STRIDE: AXIS_STRIDE,
    AXIS_FOOT_STRIKE: AXIS_FOOT_STRIKE,
}

USER_FEEDBACK_JSON_SCHEMA_DOC = """
{
  "summary": {
    "title": "한 줄 제목 (예: 팔 밸런스부터 맞춰 보세요)",
    "level": "good | caution | need_improvement",
    "message": "2~3문장 전체 요약. 쉬운 한국어.",
    "disagreement_note": "선택 — caution일 때 영상·측정 의견 차이 한 줄"
  },
  "checkpoints": [
    {
      "area": "케이던스 | 팔 스윙 | 보폭 | 착지",
      "area_key": "cadence | arm_swing | stride | foot_strike",
      "status": "good | caution | attention",
      "what_we_saw": "영상·지표에서 본 점 (한두 문장)",
      "how_to_fix": "고치는 방법 (한두 문장, good이면 유지 팁)",
      "at_moment": "선택 — 프레임/초 (없으면 null; 서버가 MP 이상 프레임으로 채울 수 있음)",
      "problem_frame_indices": [0, 129]
    }
  ],
  "today_tips": [
    "오늘 바로 할 수 있는 행동 1",
    "행동 2",
    "행동 3"
  ],
  "video_only_notes": [
    "선택 — MP JSON에는 없지만 영상에서 본 점 (한국어 1문장씩)"
  ]
}
""".strip()


def _cadence_user_lines(compact: dict, axis_entry: dict) -> tuple[str, str, str]:
    spm = compact.get("cadence")
    if compact.get("cadence") is None and axis_entry:
        spm = axis_entry.get("cadence_spm")
    spm_i = int(round(float(spm))) if spm is not None else None
    status = STATUS_ATTENTION if axis_entry.get("abnormal") else STATUS_GOOD
    if status == STATUS_GOOD:
        return (
            STATUS_GOOD,
            f"분당 {spm_i}보 전후로 스텝 리듬이 안정적이에요." if spm_i else "케이던스가 무난해 보여요.",
            "지금 페이스를 유지하면서 가볍게 뛰어 보세요.",
        )
    return (
        STATUS_ATTENTION,
        f"분당 {spm_i}보로 보폭에 비해 스텝이 맞지 않을 수 있어요." if spm_i else "케이던스 리듬을 점검해 볼게요.",
        "보폭을 조금 줄이고 같은 속도에서 스텝만 살짝 빠르게 맞춰 보세요.",
    )


def _arm_user_lines(compact: dict, axis_entry: dict) -> tuple[str, str, str]:
    bal = compact.get("arm_swing_balance", ARM_OK)
    status = STATUS_ATTENTION if bal == ARM_IMBALANCED or axis_entry.get("abnormal") else STATUS_GOOD
    if status == STATUS_GOOD:
        return STATUS_GOOD, "양팔 스윙이 고르고 팔꿈치 각도도 안정적이에요.", "몸 옆에서 짧게만 스윙하는 지금 동작을 유지하세요."
    return (
        STATUS_ATTENTION,
        "한쪽 팔만 크게 흔들거나 팔꿈치가 과하게 펴진 구간이 있어요.",
        "팔꿈치를 살짝 구부리고, 손이 허리 옆을 지나가게만 앞뒤로 스윙해 보세요.",
    )


def _stride_user_lines(compact: dict, axis_entry: dict) -> tuple[str, str, str]:
    st = compact.get("stride", STRIDE_OK)
    status = STATUS_ATTENTION if st == STRIDE_LONG or axis_entry.get("abnormal") else STATUS_GOOD
    if status == STATUS_GOOD:
        return STATUS_GOOD, "발이 몸보다 너무 앞에 나가지 않아 보폭이 안정적이에요.", "지금 보폭을 유지하며 리듬에 맞게 뛰세요."
    return (
        STATUS_ATTENTION,
        "발이 몸보다 앞에서 먼저 닿아 브레이크가 걸리는 느낌이 있어요.",
        "보폭을 5~10% 줄이고, 발이 엉덩이 바로 아래로 떨어지게 맞춰 보세요.",
    )


def _foot_user_lines(compact: dict, axis_entry: dict) -> tuple[str, str, str]:
    fs = compact.get("foot_strike", FOOT_OK)
    status = STATUS_ATTENTION if fs in (FOOT_OVER_FRONT, FOOT_HEAVY_HEEL) or axis_entry.get("abnormal") else STATUS_GOOD
    if fs == FOOT_HEAVY_HEEL:
        saw = "뒤꿈치에 힘이 많이 실려 착지가 무거워 보여요."
        fix = "보폭을 줄이고 발 전체를 가볍게 닿게, 착지 소리를 작게 만들어 보세요."
    elif fs == FOOT_OVER_FRONT:
        saw = "발이 앞쪽으로 먼저 닿으면서 착지가 딱딱할 수 있어요."
        fix = "발을 몸 아래로 모아 닿이고, 무릎을 살짝 굽혀 충격을 흡수하세요."
    elif status == STATUS_GOOD:
        return STATUS_GOOD, "착지가 비교적 가볍고 리듬에 맞게 이어져요.", "지금처럼 가볍게 닿는 연습을 이어 가세요."
    else:
        saw = "착지 패턴에 조정이 필요해 보여요."
        fix = "짧은 보폭으로 가볍게 닿는 연습을 1분 해 보세요."
    return status, saw, fix


_AXIS_BUILDERS = {
    AXIS_CADENCE: _cadence_user_lines,
    AXIS_ARM_SWING: _arm_user_lines,
    AXIS_STRIDE: _stride_user_lines,
    AXIS_FOOT_STRIKE: _foot_user_lines,
}


def build_user_feedback(
    axis_payload: dict,
    *,
    title: str = "",
    message: str = "",
    today_tips: list[str] | None = None,
) -> dict[str, Any]:
    """MP 4-axis JSON → 사용자용 피드백 JSON."""
    compact = axis_payload_to_compact_input(axis_payload)
    axes = axis_payload.get("axes", {}) or {}
    checkpoints: list[dict[str, Any]] = []

    for axis in FOUR_AXES:
        entry = axes.get(axis, {}) if isinstance(axes, dict) else {}
        fn = _AXIS_BUILDERS[axis]
        status, saw, fix = fn(compact, entry)
        checkpoints.append(
            {
                "area": AXIS_LABELS_KO[axis],
                "area_key": axis,
                "status": status,
                "what_we_saw": saw,
                "how_to_fix": fix,
                "at_moment": None,
            }
        )

    attention = [c for c in checkpoints if c["status"] == STATUS_ATTENTION]
    level = LEVEL_NEED_IMPROVEMENT if attention else LEVEL_GOOD

    if not title:
        primary = axis_payload.get("primary_axis_ko", "")
        if attention and primary:
            title = f"{primary}부터 가볍게 맞춰 보세요"
        elif attention:
            title = "몇 가지 습관만 고치면 더 편하게 뛸 수 있어요"
        else:
            title = "전반적으로 안정적인 러닝 리듬이에요"

    if not message:
        if attention:
            names = ", ".join(c["area"] for c in attention[:2])
            message = (
                f"{names} 쪽에 손볼 점이 보여요. "
                "러닝은 밸런스 운동이라, 아래 항목 순서대로 하나씩만 맞춰도 체감이 달라질 수 있어요."
            )
        else:
            message = "케이던스·팔·보폭·착지가 고르게 맞아 있어요. 지금 페이스를 유지하며 편하게 뛰세요."

    if not today_tips:
        today_tips = []
        for c in attention[:3]:
            today_tips.append(c["how_to_fix"])
        if not today_tips:
            today_tips = ["오늘은 편한 페이스로 10분만 뛰며 리듬을 느껴 보세요."]

    return {
        "summary": {
            "title": title,
            "level": level,
            "message": message,
        },
        "checkpoints": checkpoints,
        "today_tips": today_tips[:3],
    }


def mp_bad_axis_keys(axis_payload: dict) -> set[str]:
    """4축 중 MP rule이 abnormal=true 로 본 축."""
    axes = axis_payload.get("axes", {}) or {}
    if not isinstance(axes, dict):
        return set()
    return {ax for ax in FOUR_AXES if (axes.get(ax) or {}).get("abnormal")}


def qwen_attention_axis_keys(user_fb: dict[str, Any]) -> set[str]:
    """Qwen 코칭 JSON에서 attention 으로 표시한 축 (복합 area_key 포함)."""
    keys: set[str] = set()
    for cp in user_fb.get("checkpoints") or []:
        if cp.get("status") != STATUS_ATTENTION:
            continue
        raw = (cp.get("area_key") or "").strip()
        if raw in FOUR_AXES:
            keys.add(raw)
            continue
        for part in re.split(r"[|,/\s]+", raw):
            part = part.strip()
            if part in FOUR_AXES:
                keys.add(part)
    return keys


def qwen_signals_bad(user_fb: dict[str, Any]) -> bool:
    """Qwen이 나쁨/주의 쪽으로 본 신호 (attention 또는 level)."""
    if qwen_attention_axis_keys(user_fb):
        return True
    level = (user_fb.get("summary") or {}).get("level", "")
    return level == LEVEL_NEED_IMPROVEMENT


def reconcile_summary_level(*, mp_bad: bool, qwen_bad: bool) -> str:
    """MP·Qwen 합의 → summary.level (good | caution | need_improvement)."""
    if not mp_bad and not qwen_bad:
        return LEVEL_GOOD
    if mp_bad and qwen_bad:
        return LEVEL_NEED_IMPROVEMENT
    return LEVEL_CAUTION


def _join_axis_ko(keys: set[str]) -> str:
    ordered = [AXIS_LABELS_KO[ax] for ax in FOUR_AXES if ax in keys]
    if not ordered:
        return "특정 부분"
    if len(ordered) == 1:
        return ordered[0]
    return ", ".join(ordered[:-1]) + f", {ordered[-1]}"


def build_caution_summary_copy(
    *,
    mp_bad_axes: set[str],
    qwen_attn: set[str],
) -> tuple[str, str, str]:
    """
    MP·Qwen 불일치(caution)용 요약 문구.
    Returns (title, message, disagreement_note).
    """
    disputed = mp_bad_axes | qwen_attn
    areas = _join_axis_ko(disputed)
    only_mp = mp_bad_axes - qwen_attn
    only_qwen = qwen_attn - mp_bad_axes
    both = mp_bad_axes & qwen_attn

    title = "전반적으로 좋은 편이에요"
    parts = [
        "전반적인 달리기 자세는 괜찮아 보여요.",
    ]
    if only_qwen:
        parts.append(
            f"다만 **영상**에서는 {_join_axis_ko(only_qwen)} 쪽에 조정 여지가 보였고, "
            "자동 포즈 측정과는 조금 다르게 보였어요."
        )
    if only_mp:
        parts.append(
            f"**자동 측정**에서는 {_join_axis_ko(only_mp)} 수치가 기준을 살짝 넘었지만, "
            "영상만 보면 크게 나쁘다고 보기 어려울 수 있어요."
        )
    if both:
        parts.append(
            f"{_join_axis_ko(both)}는 영상과 측정 모두에서 한번 더 보면 좋아요."
        )
    parts.append(f"아래 🟡 표시된 {areas}만 가볍게 확인해 보시면 됩니다.")
    message = " ".join(parts)
    note = "영상(Qwen)과 자동 측정(MediaPipe) 의견이 일부 달랐습니다. 전반 자세는 유지하고 표시된 부분만 점검하세요."
    return title, message, note


def _normalize_video_only_notes(user_fb: dict[str, Any]) -> list[str]:
    raw = user_fb.get("video_only_notes")
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()][:5]
    return []


def _qwen_only_attention_axes(mp_bad_axes: set[str], qwen_attn: set[str]) -> set[str]:
    return qwen_attn - mp_bad_axes


def format_problem_frames_at_moment(frame_indices: list[int], fps: float | None) -> str:
    """프레임 번호 + 초(가능 시) 한국어 한 줄."""
    if not frame_indices:
        return ""
    parts: list[str] = []
    for fi in sorted(set(int(x) for x in frame_indices))[:6]:
        if fps and fps > 0:
            parts.append(f"프레임 {fi} (약 {fi / fps:.1f}초)")
        else:
            parts.append(f"프레임 {fi}")
    tail = ""
    if len(frame_indices) > 6:
        tail = f" 외 {len(set(frame_indices)) - 6}곳"
    return " · ".join(parts) + tail


def problem_frames_for_checkpoint(
    axis_key: str,
    frame_context: dict,
    *,
    mp_bad_axes: set[str],
) -> list[int]:
    """축별 MP 이상 프레임; 없으면 전체 center 목록으로 fallback."""
    by_axis = frame_context.get("mp_abnormal_frames_by_axis") or {}
    if isinstance(by_axis, dict) and by_axis.get(axis_key):
        raw = by_axis[axis_key]
        return sorted({int(x) for x in raw})
    if axis_key in mp_bad_axes:
        centers = frame_context.get("mp_abnormal_frame_centers") or []
        return sorted({int(x) for x in centers})
    return []


def attach_problem_frames_to_checkpoints(
    checkpoints: list[dict[str, Any]],
    axis_payload: dict,
    *,
    mp_bad_axes: set[str],
    qwen_attn: set[str],
) -> None:
    """attention/caution 축에 problem_frame_indices·at_moment(프레임 번호) 부여."""
    fc = axis_payload.get("frame_context") or {}
    fps = fc.get("fps")
    try:
        fps_f = float(fps) if fps is not None else None
    except (TypeError, ValueError):
        fps_f = None

    for c in checkpoints:
        key = c.get("area_key")
        if key not in FOUR_AXES:
            continue
        if c.get("status") not in (STATUS_ATTENTION, STATUS_CAUTION):
            c.pop("problem_frame_indices", None)
            continue
        frames = problem_frames_for_checkpoint(key, fc, mp_bad_axes=mp_bad_axes)
        if key in qwen_attn and not frames:
            centers = fc.get("mp_abnormal_frame_centers") or []
            frames = sorted({int(x) for x in centers})
        if not frames:
            continue
        c["problem_frame_indices"] = frames
        auto_moment = format_problem_frames_at_moment(frames, fps_f)
        prev = (c.get("at_moment") or "").strip()
        if prev and prev.lower() not in ("null", "none") and "프레임" not in prev:
            c["at_moment"] = f"{prev} — {auto_moment}"
        else:
            c["at_moment"] = auto_moment


def apply_caution_checkpoint_copy(
    c: dict[str, Any],
    *,
    from_mp: bool,
    from_qwen: bool,
) -> None:
    """caution 축: 전반 좋음 + 해당 부분만 점검 톤."""
    saw = (c.get("what_we_saw") or "").strip()
    if saw:
        if from_mp and from_qwen:
            lead = "영상·측정 모두에서 이 부분이 눈에 띄어요. "
        elif from_qwen:
            lead = "영상에서는 이 부분이 신경 쓰이지만, 측정값은 크게 나쁘지 않을 수 있어요. "
        elif from_mp:
            lead = "자동 측정에서는 수치가 기준을 살짝 넘었지만, 영상만 보면 괜찮아 보일 수 있어요. "
        else:
            lead = ""
        if lead and lead not in saw:
            c["what_we_saw"] = f"{lead}{saw.rstrip('.')}. 전반 자세는 좋은 편이니 이 항목만 가볍게 확인해 보세요."
    fix = (c.get("how_to_fix") or "").strip()
    if fix and not fix.startswith("가볍게"):
        c["how_to_fix"] = f"가볍게 점검: {fix}"


def _checkpoints_by_area_key(checkpoints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in checkpoints:
        key = c.get("area_key")
        if key in FOUR_AXES:
            out[key] = c
    return out


def finalize_user_feedback(
    user_fb: dict[str, Any],
    axis_payload: dict,
    *,
    qwen_label: str = "",
    qwen_axes_bad: list[str] | None = None,
) -> dict[str, Any]:
    """MP·Qwen 합의로 level 정합: 둘 다 good→good, 둘 다 bad→need_improvement, 불일치→caution."""
    template = build_user_feedback(axis_payload)
    by_key = _checkpoints_by_area_key(user_fb.get("checkpoints", []))
    merged: list[dict[str, Any]] = []
    for tc in template["checkpoints"]:
        key = tc["area_key"]
        if key in by_key:
            src = by_key[key]
            merged.append(
                {
                    **tc,
                    "area": src.get("area") or tc["area"],
                    "status": src.get("status") or tc["status"],
                    "what_we_saw": (src.get("what_we_saw") or "").strip() or tc["what_we_saw"],
                    "how_to_fix": (src.get("how_to_fix") or "").strip() or tc["how_to_fix"],
                    "at_moment": src.get("at_moment"),
                }
            )
        else:
            merged.append(tc)

    mp_bad_axes = mp_bad_axis_keys(axis_payload)
    qwen_attn = set(qwen_attention_axis_keys(user_fb))
    if qwen_axes_bad:
        qwen_attn |= {a for a in qwen_axes_bad if a in FOUR_AXES}

    qwen_bad = qwen_signals_bad(user_fb) or bool(qwen_attn)
    if qwen_label == "good":
        qwen_bad = False
        qwen_attn = set()
    elif qwen_label == "bad":
        qwen_bad = True
        if qwen_axes_bad:
            qwen_attn |= set(qwen_axes_bad)

    mp_bad = bool(mp_bad_axes)
    target_level = reconcile_summary_level(mp_bad=mp_bad, qwen_bad=qwen_bad)

    for c in merged:
        key = c["area_key"]
        if target_level == LEVEL_GOOD:
            c["status"] = STATUS_GOOD
        elif target_level == LEVEL_NEED_IMPROVEMENT:
            if key in mp_bad_axes or key in qwen_attn:
                c["status"] = STATUS_ATTENTION
            else:
                c["status"] = STATUS_GOOD
        else:
            if key in mp_bad_axes or key in qwen_attn:
                c["status"] = STATUS_CAUTION
                apply_caution_checkpoint_copy(
                    c,
                    from_mp=key in mp_bad_axes,
                    from_qwen=key in qwen_attn,
                )
            else:
                c["status"] = STATUS_GOOD

    summary = dict(user_fb.get("summary") or template["summary"])
    summary["level"] = target_level
    if target_level == LEVEL_CAUTION:
        title, message, note = build_caution_summary_copy(
            mp_bad_axes=mp_bad_axes,
            qwen_attn=qwen_attn,
        )
        summary["title"] = title
        summary["message"] = message
        summary["disagreement_note"] = note
        caution_tips = [
            c["how_to_fix"]
            for c in merged
            if c.get("status") == STATUS_CAUTION and (c.get("how_to_fix") or "").strip()
        ]
        if caution_tips:
            tips = caution_tips[:3]
        else:
            tips = user_fb.get("today_tips") or template.get("today_tips", [])
    else:
        summary.pop("disagreement_note", None)
        tips = user_fb.get("today_tips") or template.get("today_tips", [])

    if not tips:
        tips = template.get("today_tips", [])

    attach_problem_frames_to_checkpoints(
        merged,
        axis_payload,
        mp_bad_axes=mp_bad_axes,
        qwen_attn=qwen_attn,
    )

    video_only_notes = _normalize_video_only_notes(user_fb)
    qwen_only = _qwen_only_attention_axes(mp_bad_axes, qwen_attn)
    if qwen_only and not video_only_notes:
        video_only_notes = [
            f"{AXIS_LABELS_KO[ax]}: {(by_key.get(ax) or {}).get('what_we_saw', '').strip()}"
            for ax in FOUR_AXES
            if ax in qwen_only and (by_key.get(ax) or {}).get("what_we_saw")
        ][:3]

    fc_out = axis_payload.get("frame_context")
    out: dict[str, Any] = {
        "summary": summary,
        "checkpoints": merged,
        "today_tips": list(tips)[:3],
        "video_only_notes": video_only_notes,
    }
    if fc_out:
        out["frame_context"] = fc_out
    return out


def format_pose_feedback_markdown(
    video_name: str,
    user_fb: dict[str, Any],
    *,
    four_axis: dict | None = None,
    mp_predicted: str = "",
) -> str:
    """4축 분류 + 사용자 코칭을 한 문서로."""
    parts: list[str] = [f"# 러닝 피드백 — {video_name}", ""]
    if four_axis:
        label = four_axis.get("qwen_label", "")
        axes = four_axis.get("axes_bad") or []
        parts.extend(
            [
                "## 4축 분류 (Qwen + 영상)",
                "",
                f"- **판정:** {label} ({'양호' if label == 'good' else '개선 필요' if label == 'bad' else label})",
                f"- **문제 축:** {', '.join(axes) if axes else '없음'}",
                f"- **이유:** {four_axis.get('reason', '')}",
            ]
        )
        if mp_predicted:
            parts.append(f"- **MP rule 참고:** {mp_predicted}")
        parts.append("")
    parts.append(format_user_feedback_markdown(video_name, user_fb).split("\n", 1)[1])
    return "\n".join(parts)


def parse_user_feedback_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if "summary" not in data or "checkpoints" not in data:
        return None
    return data


def format_user_feedback_markdown(video_name: str, fb: dict[str, Any]) -> str:
    """앱 미리보기용 마크다운."""
    level = fb.get("summary", {}).get("level", "")
    if level == LEVEL_GOOD:
        level_ko = "양호"
    elif level == LEVEL_CAUTION:
        level_ko = "약간 주의"
    elif level == LEVEL_NEED_IMPROVEMENT:
        level_ko = "개선하면 더 편해져요"
    else:
        level_ko = level
    lines = [
        f"# 러닝 피드백 — {video_name}",
        "",
        f"## {fb.get('summary', {}).get('title', '')}",
        "",
        f"**{level_ko}**",
        "",
    ]
    if level == LEVEL_CAUTION and fb.get("summary", {}).get("disagreement_note"):
        lines.append(f"_{fb['summary']['disagreement_note']}_")
        lines.append("")
    lines.extend(
        [
            fb.get("summary", {}).get("message", ""),
            "",
        ]
    )
    all_problem: list[int] = []
    for c in fb.get("checkpoints", []):
        pf = c.get("problem_frame_indices") or []
        all_problem.extend(int(x) for x in pf)
    fc = fb.get("frame_context") or {}
    if all_problem:
        fps = fc.get("fps")
        try:
            fps_f = float(fps) if fps is not None else None
        except (TypeError, ValueError):
            fps_f = None
        lines.append("## 문제가 보인 프레임 (MP)")
        lines.append("")
        lines.append(f"- {format_problem_frames_at_moment(sorted(set(all_problem)), fps_f)}")
        lines.append("")
    lines.extend(["## 항목별 안내", ""])
    for c in fb.get("checkpoints", []):
        st = c.get("status")
        icon = "✅" if st == STATUS_GOOD else "🟡" if st == STATUS_CAUTION else "⚠️"
        lines.append(f"### {icon} {c.get('area', '')}")
        lines.append(f"- **보면:** {c.get('what_we_saw', '')}")
        lines.append(f"- **해보기:** {c.get('how_to_fix', '')}")
        if c.get("problem_frame_indices"):
            pf = c["problem_frame_indices"]
            lines.append(f"- **문제 프레임:** {', '.join(str(int(x)) for x in pf)}")
        if c.get("at_moment"):
            lines.append(f"- **참고:** {c['at_moment']}")
        lines.append("")
    vnotes = fb.get("video_only_notes") or []
    if vnotes:
        lines.append("## 영상에서 추가로 본 점 (MP 수치 외)")
        lines.append("")
        for note in vnotes:
            lines.append(f"- {note}")
        lines.append("")
    tips = fb.get("today_tips", [])
    if tips:
        lines.append("## 오늘 할 일")
        for i, t in enumerate(tips, 1):
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


def user_feedback_to_plain_text(fb: dict[str, Any]) -> str:
    """사용자 JSON → 읽기용 텍스트 (미리보기)."""
    lines = [fb["summary"]["title"], "", fb["summary"]["message"], ""]
    for c in fb.get("checkpoints", []):
        st = c.get("status")
        mark = "✓" if st == STATUS_GOOD else "~" if st == STATUS_CAUTION else "!"
        lines.append(f"[{mark}] {c['area']}: {c['what_we_saw']} → {c['how_to_fix']}")
    lines.append("")
    for i, tip in enumerate(fb.get("today_tips", []), 1):
        lines.append(f"{i}. {tip}")
    return "\n".join(lines)


def build_user_feedback_prompt_instruction() -> str:
    return (
        "반드시 아래 사용자용 JSON만 출력 (마크다운·설명 없음). "
        "severity·영문 지표명·raw JSON 키 노출 금지. 초보자가 읽는 쉬운 한국어만. "
        "영상 전용 관찰은 video_only_notes 또는 해당 축 checkpoint에 넣으세요.\n\n"
        f"형식:\n{USER_FEEDBACK_JSON_SCHEMA_DOC}"
    )
