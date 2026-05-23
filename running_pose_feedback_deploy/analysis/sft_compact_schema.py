"""
Compact SFT schema for commentary fine-tuning.

  {
    "input": {
      "cadence": 154,              // SPM (int, 분당 스텝)
      "stride": "long" | "ok",
      "foot_strike": "over_front" | "heavy_heel" | "ok",
      "arm_swing_balance": "imbalanced" | "ok"
    },
    "style": "황영조",
    "output": "2~4문장 코칭 해설 (plain text)"
  }

Maps from MediaPipe 4-axis JSON (compact_axis_payload).
"""

from __future__ import annotations

import json
from typing import Any

from four_axis_metrics import AXIS_ARM_SWING, AXIS_CADENCE, AXIS_FOOT_STRIKE, AXIS_STRIDE

STRIDE_LONG = "long"
STRIDE_OK = "ok"

FOOT_OVER_FRONT = "over_front"
FOOT_HEAVY_HEEL = "heavy_heel"
FOOT_OK = "ok"

ARM_IMBALANCED = "imbalanced"
ARM_OK = "ok"

from hwang_coaching_style import STYLE_HWANG, build_hwang_style_prompt_block  # noqa: E402


def _stride_label(entry: dict) -> str:
    if entry.get("abnormal"):
        return STRIDE_LONG
    mx = entry.get("overstride_forward_max")
    if mx is not None and float(mx) > 0.17:
        return STRIDE_LONG
    return STRIDE_OK


def _foot_strike_label(entry: dict) -> str:
    if not entry.get("abnormal"):
        return FOOT_OK
    p90 = entry.get("heel_drop_p90")
    mx = entry.get("overstride_forward_max")
    if mx is not None and float(mx) > 0.15:
        return FOOT_OVER_FRONT
    if p90 is not None and float(p90) > 0.03:
        return FOOT_HEAVY_HEEL
    return FOOT_OVER_FRONT


def _arm_balance_label(entry: dict) -> str:
    if entry.get("abnormal"):
        return ARM_IMBALANCED
    bal = entry.get("arm_swing_balance")
    if bal and bal not in ("balanced", "unknown"):
        return ARM_IMBALANCED
    sym = entry.get("elbow_symmetry_deg")
    if sym is not None and float(sym) > 85.0:
        return ARM_IMBALANCED
    sym_p90 = entry.get("elbow_symmetry_p90_deg")
    if sym_p90 is not None and float(sym_p90) > 100.0:
        return ARM_IMBALANCED
    lr_gap = entry.get("elbow_lr_median_gap_deg")
    if lr_gap is not None and float(lr_gap) > 51.0:
        return ARM_IMBALANCED
    sev = entry.get("severity")
    if sev is not None and float(sev) >= 3.0:
        return ARM_IMBALANCED
    return ARM_OK


def axis_payload_to_compact_input(axis_payload: dict) -> dict[str, Any]:
    """MP 4-axis JSON → 사용자 예시 형식 input."""
    axes = axis_payload.get("axes", {}) or {}
    cadence_e = axes.get(AXIS_CADENCE, {})
    spm = cadence_e.get("cadence_spm")
    out: dict[str, Any] = {
        "cadence": int(round(float(spm))) if spm is not None else None,
        "stride": _stride_label(axes.get(AXIS_STRIDE, {})),
        "foot_strike": _foot_strike_label(axes.get(AXIS_FOOT_STRIKE, {})),
        "arm_swing_balance": _arm_balance_label(axes.get(AXIS_ARM_SWING, {})),
    }
    triggers = axis_payload.get("triggers") or []
    if triggers:
        out["triggers"] = triggers
    primary = axis_payload.get("primary_axis_ko")
    if primary:
        out["primary_issue_ko"] = primary
    return out


def target_to_plain_output(target: dict[str, Any]) -> str:
    """Structured target → 연속 한국어 해설 (SFT assistant)."""
    parts: list[str] = []
    headline = target.get("headline", "").strip()
    commentary = target.get("commentary", "").strip()
    if headline:
        parts.append(headline)
    if commentary:
        parts.append(commentary)
    axes = target.get("axes") or {}
    for key in ("cadence", "arm_swing", "stride", "foot_strike"):
        line = axes.get(key, "").strip()
        if line and line not in commentary:
            parts.append(line)
    tips = target.get("practice_tips") or []
    if tips:
        parts.append(" ".join(f"· {t}" for t in tips[:3]))
    return "\n".join(parts).strip()


def load_label_output(label_doc: dict) -> tuple[dict[str, Any] | None, str, str, dict[str, Any] | None]:
    """
    Parse finetune_data/labels/{stem}.json.

    Returns (input_override|None, output_text, style, user_feedback_dict|None).
    """
    from commentary_sft_target import normalize_target
    import json as _json

    style = str(label_doc.get("style", STYLE_HWANG))
    uf = label_doc.get("user_feedback")
    if isinstance(uf, dict) and uf.get("summary"):
        inp = label_doc.get("input")
        return (
            inp if isinstance(inp, dict) else None,
            _json.dumps(uf, ensure_ascii=False, indent=2),
            style,
            uf,
        )
    if isinstance(label_doc.get("output"), str) and label_doc["output"].strip():
        inp = label_doc.get("input")
        return (inp if isinstance(inp, dict) else None, label_doc["output"].strip(), style, None)
    target = label_doc.get("target")
    if isinstance(target, dict):
        return (
            label_doc.get("input") if isinstance(label_doc.get("input"), dict) else None,
            target_to_plain_output(normalize_target(target)),
            style,
            None,
        )
    return None, "", style, None


def build_compact_user_text(
    compact_input: dict[str, Any],
    *,
    style: str = STYLE_HWANG,
    include_frame_context: dict | None = None,
    user_feedback_schema: bool = False,
    allow_video_observations: bool = False,
) -> str:
    body = {"input": compact_input, "style": style}
    if include_frame_context:
        body["frame_context"] = include_frame_context
    style_block = build_hwang_style_prompt_block(
        style=style,
        allow_video_observations=allow_video_observations,
    )
    if user_feedback_schema:
        from user_feedback_schema import build_user_feedback_prompt_instruction

        return (
            "아래 input 지표와 style을 보고, **사용자가 앱에서 읽을** 쉬운 한국어 피드백 JSON을 작성하세요.\n"
            "input에 없는 문제는 만들지 마세요. checkpoints는 4축 모두 포함.\n\n"
            + (style_block + "\n" if style_block else "")
            + json.dumps(body, ensure_ascii=False, indent=2)
            + "\n\n"
            + build_user_feedback_prompt_instruction()
        )
    return (
        "아래 input 지표만 보고 style 톤으로 러닝 코칭 해설을 작성하세요.\n"
        "input에 없는 문제는 만들지 마세요. 2~4문장, 쉬운 한국어.\n\n"
        + (style_block + "\n" if style_block else "")
        + json.dumps(body, ensure_ascii=False, indent=2)
    )


def build_inference_user_feedback_sft_record(
    *,
    record_id: str,
    video_name: str,
    axis_payload: dict,
    output_text: str,
    frame_paths: list,
    style: str = STYLE_HWANG,
) -> dict:
    """추론(generate_commentary, coaching_only)과 동일한 user 프롬프트 + hybrid 프레임."""
    from qwen_four_axis_context import build_user_feedback_prompt_with_full_axis

    user_text = build_user_feedback_prompt_with_full_axis(
        axis_payload,
        coaching_only=True,
        style=style,
    )
    user_content: list[dict] = []
    for p in frame_paths:
        user_content.append({"type": "image", "image": str(p)})
    user_content.append({"type": "text", "text": user_text})
    return {
        "id": record_id,
        "video": video_name,
        "schema": "user_feedback",
        "style": style,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": output_text},
        ],
    }


def build_compact_sft_record(
    *,
    record_id: str,
    video_name: str,
    compact_input: dict[str, Any],
    output_text: str,
    style: str = STYLE_HWANG,
    frame_paths: list | None = None,
    frame_context: dict | None = None,
    with_images: bool = True,
    user_feedback_schema: bool = False,
) -> dict:
    user_text = build_compact_user_text(
        compact_input,
        style=style,
        include_frame_context=frame_context,
        user_feedback_schema=user_feedback_schema,
        allow_video_observations=with_images and bool(frame_paths),
    )
    user_content: list[dict] = []
    if with_images and frame_paths:
        for p in frame_paths:
            user_content.append({"type": "image", "image": str(p)})
    user_content.append({"type": "text", "text": user_text})
    return {
        "id": record_id,
        "video": video_name,
        "schema": "user_feedback" if user_feedback_schema else "compact",
        "compact_input": compact_input,
        "style": style,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": output_text},
        ],
    }
