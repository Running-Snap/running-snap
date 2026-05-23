"""황영조식 코칭 — 4축별 철학 (SFT user 프롬프트·Qwen 코칭 공통)."""

from __future__ import annotations

from four_axis_metrics import AXIS_ARM_SWING, AXIS_CADENCE, AXIS_FOOT_STRIKE, AXIS_STRIDE

STYLE_HWANG = "황영조"

# Feature(4축) → 황영조 철학 (한 줄)
AXIS_PHILOSOPHY_KO: dict[str, str] = {
    AXIS_CADENCE: "리듬 유지",
    AXIS_ARM_SWING: "밸런스",
    AXIS_STRIDE: "자연스러운 보폭",
    AXIS_FOOT_STRIKE: "충격 감소 · 몸 아래 착지",
}

AXIS_AVOID_KO: dict[str, str] = {
    AXIS_CADENCE: "힘으로 밀어내기, 숨 차는 페이스",
    AXIS_ARM_SWING: "팔 과하게 흔들기, 한쪽만 크게",
    AXIS_STRIDE: "과도한 보폭, 발이 몸보다 앞에 먼저 닿기, 과한 상체 숙임",
    AXIS_FOOT_STRIKE: "무거운 착지, 억지 미드풋 강요",
}


def build_hwang_style_prompt_block(
    *,
    style: str = STYLE_HWANG,
    allow_video_observations: bool = False,
) -> str:
    """SFT·추론 user 메시지에 붙이는 짧은 스타일 블록.

    allow_video_observations=True: 영상+풀 JSON 추론 (MP에 없는 관찰 가능).
    False: compact input만 (합성 텍스트 SFT) — input과 모순되는 축 문제 금지.
    """
    if style != STYLE_HWANG:
        return ""
    rows = [
        f"| {k} | {AXIS_PHILOSOPHY_KO[k]} | 피하기: {AXIS_AVOID_KO[k]} |"
        for k in (AXIS_CADENCE, AXIS_ARM_SWING, AXIS_STRIDE, AXIS_FOOT_STRIKE)
    ]
    table = "\n".join(["| Feature | 황영조 철학 |", "|---------|-------------|"] + rows)
    if allow_video_observations:
        observe_rule = (
            "- **영상·4-axis JSON**을 함께 볼 때: MP/input에 없는 수치는 지어내지 말고, "
            "영상에서 분명한 점은 해당 축 checkpoint의 what_we_saw에 넣거나 "
            "`video_only_notes`에 쓰세요. 지표와 다르면 영상 우선·caution 가능.\n"
        )
    else:
        observe_rule = (
            "- **input만** 있을 때: input에 없는 축 문제를 새로 만들지 마세요 "
            "(없는 severity·트리거 금지).\n"
        )
    return f"""[style: {style} — 4축별 코칭 관점]
{table}

{observe_rule}- 각 checkpoint는 해당 축 철학에 맞게 what_we_saw / how_to_fix 작성.
- summary.level: good(전반 유지·격려) | need_improvement(고칠 점 분명) | caution(전반 좋음+일부만 가볍게 점검, disagreement_note).
- checkpoint status caution: "가볍게 점검", 영상·측정 차이 언급 가능 (attention보다 부드럽게).
- 전체 톤: 자연스러운 러닝, 오래 갈 수 있는 자세, 격려·습관 교정 (진단·속도 경쟁 X).
"""
