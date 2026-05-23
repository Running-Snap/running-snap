"""Korean running-form commentary prompts for base / fine-tuned Qwen2.5-VL."""

from __future__ import annotations

import json
import re
from typing import Any

from four_axis_metrics import AXIS_LABELS_KO, FOUR_AXES
from metric_commentary_hints import format_metric_mapping_block


def build_minimal_commentary_prompt(axis_payload: dict) -> str:
    """영상 + 4축 JSON + 축별 지표 매핑 + 출력 스키마."""
    return build_metric_linked_commentary_prompt(axis_payload)


def build_metric_linked_commentary_prompt(axis_payload: dict) -> str:
    """지표(JSON)와 1:1 대응하는 축별 해설을 강제하는 프롬프트."""
    ctx = json.dumps(axis_payload, ensure_ascii=False, indent=2)
    mapping = format_metric_mapping_block(axis_payload)
    axis_lines = "\n".join(
        f'    "{a}": "({AXIS_LABELS_KO[a]} — 위 매핑의 {a} 지표만)"' for a in FOUR_AXES
    )
    return f"""[4-axis JSON]
{ctx}

{mapping}

작성 규칙:
- axes.cadence / arm_swing / stride / foot_strike 각각 **해당 축 JSON만** 반영 (다른 축 지표 끌어오기 금지)
- abnormal=true: 위 매핑 숫자를 일상어로 1개 이상 + 고치는 동작 1개
- abnormal=false: 한 문장 양호·유지
- headline·commentary: primary_axis_ko·triggers 우선, 3~5문장
- severity·spm·overstride 등 영어 키 이름 나열 금지

반드시 JSON만 출력:
{{
  "overall": "good"|"bad",
  "headline": "",
  "commentary": "",
  "axes": {{
{axis_lines}
  }},
  "practice_tips": ["", "", ""]
}}"""


def build_commentary_prompt(
    axis_payload: dict,
    *,
    mp_predicted: str = "",
    qwen_label: str = "",
    qwen_axes_bad: list[str] | None = None,
) -> str:
    """Coaching commentary with optional classification hints + metric mapping."""
    base = build_metric_linked_commentary_prompt(axis_payload)
    if not mp_predicted and not qwen_label:
        return base
    extra: list[str] = []
    if mp_predicted:
        extra.append(f"MediaPipe rule 판정(참고): {mp_predicted}")
    if qwen_label:
        axes = ", ".join(qwen_axes_bad or []) or "(없음)"
        extra.append(f"Qwen 분류(참고): {qwen_label}, axes_bad={axes}")
    return base + "\n\n[참고만, 지표 매핑과 충돌 시 JSON·영상 우선]\n" + "\n".join(extra)


def parse_commentary_json(text: str) -> dict[str, Any]:
    """Best-effort parse of commentary JSON from model output."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {
            "overall": "",
            "headline": "",
            "commentary": text.strip()[:800],
            "axes": {},
            "practice_tips": [],
            "parse_ok": False,
        }
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {
            "overall": "",
            "headline": "",
            "commentary": text.strip()[:800],
            "axes": {},
            "practice_tips": [],
            "parse_ok": False,
        }

    overall = str(data.get("overall", "")).lower()
    if overall not in ("good", "bad"):
        overall = "bad" if "bad" in text.lower() or "나쁨" in text or "문제" in text else "good"

    tips = data.get("practice_tips", [])
    if not isinstance(tips, list):
        tips = [str(tips)] if tips else []

    axes_raw = data.get("axes", {})
    axes: dict[str, str] = {}
    if isinstance(axes_raw, dict):
        for axis in FOUR_AXES:
            if axis in axes_raw:
                axes[axis] = str(axes_raw[axis]).strip()

    return {
        "overall": overall,
        "headline": str(data.get("headline", "")).strip(),
        "commentary": str(data.get("commentary", "")).strip(),
        "axes": axes,
        "practice_tips": [str(t).strip() for t in tips if str(t).strip()],
        "parse_ok": True,
    }


def format_commentary_markdown(video_name: str, parsed: dict[str, Any], *, axis_payload: dict | None = None) -> str:
    """Human-readable report for quick review."""
    lines = [f"# 러닝 자세 해설 — {video_name}", ""]
    if parsed.get("headline"):
        lines.append(f"**{parsed['headline']}**")
        lines.append("")
    overall = parsed.get("overall", "")
    if overall:
        label = "양호" if overall == "good" else "개선 필요"
        lines.append(f"- 전체 판정: **{label}** (`{overall}`)")
        lines.append("")
    if parsed.get("commentary"):
        lines.append("## 전체 해설")
        lines.append(parsed["commentary"])
        lines.append("")
    axes = parsed.get("axes") or {}
    if axes:
        lines.append("## 축별 코멘트 (지표 대응)")
        for axis in FOUR_AXES:
            if axis in axes and axes[axis]:
                lines.append(f"- **{AXIS_LABELS_KO[axis]}**: {axes[axis]}")
        lines.append("")
    tips = parsed.get("practice_tips") or []
    if tips:
        lines.append("## 실천 팁")
        for i, tip in enumerate(tips, 1):
            lines.append(f"{i}. {tip}")
        lines.append("")
    if axis_payload:
        from metric_commentary_hints import format_metric_mapping_block

        lines.append("## 지표 → 해설 매핑 (입력)")
        lines.append("```")
        lines.append(format_metric_mapping_block(axis_payload))
        lines.append("```")
        lines.append("")
    fc = (axis_payload or {}).get("frame_context") if axis_payload else None
    if fc:
        lines.append("## 프레임 정보")
        lines.append(
            f"- 영상 전체: **{fc.get('total_frames', '?')}프레임** "
            f"({fc.get('fps', '?')} fps, 약 {fc.get('duration_sec', '?')}초)"
        )
        lines.append(
            f"- Qwen 입력: **{fc.get('qwen_saved_frame_count', fc.get('qwen_sampled_frame_count', '?'))}장** "
            f"(인덱스 {fc.get('qwen_sampled_frame_indices', [])})"
        )
        if fc.get("mp_csv_rows"):
            lines.append(
                f"- MP 분석: CSV **{fc['mp_csv_rows']}행**, 포즈 검출 **{fc.get('mp_pose_detected_frames', '?')}프레임**"
            )
        lines.append("")
    if axis_payload:
        lines.append("## 참고 지표 (4-axis JSON)")
        lines.append("```json")
        lines.append(json.dumps(axis_payload, ensure_ascii=False, indent=2))
        lines.append("```")
    return "\n".join(lines)
