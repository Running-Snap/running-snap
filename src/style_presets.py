"""
style_presets.py
================
style 이름 → 편집 파라미터 묶음 정의.

지원 스타일:
  action       빠른 컷, 강한 대비, 슬로우 모션
  instagram    따뜻하고 밝은 봄/라이프스타일 감성
  tiktok       강렬한 색감, 빠른 리듬, 세로 최적화
  humor        밝고 가벼운 분위기, 과장된 연출
  documentary  차분하고 묵직한 색감, 느린 호흡
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class StylePreset:
    # ── 컬러 그레이딩 ───────────────────────────────────────────────
    color_tone: str        # "warm" / "cool" / "dark" / "vibrant" / "natural"
    brightness: int        # -30 ~ +30
    contrast: int          # 0 ~ 40
    saturation: int        # -30 ~ +30
    temperature: int       # -30 (쿨) ~ +30 (웜)

    # ── 레이아웃 ────────────────────────────────────────────────────
    crop_zoom: float       # 1.0 = no crop, 1.3 = 30% zoom-in

    # ── 편집 리듬 ────────────────────────────────────────────────────
    slowmo_speed: float    # 0.25 = 4x slow, 0.5 = 2x slow
    freeze_dur: float      # 피드백 freeze 초
    score_freeze_dur: float
    stats_freeze_dur: float

    # ── 컷 스타일 ────────────────────────────────────────────────────
    # "fast" = 0.8s avg, "medium" = 1.5s, "slow" = 2.5s
    cut_rhythm: str
    cut_types: List[str]   # ["hard_cut", "flash", "dissolve"] 중 선택

    # ── 오버레이 스타일 ───────────────────────────────────────────────
    badge_style: str       # "solid" / "outline" / "minimal"
    score_color_map: dict  # score 범위 → hex 색상

    # ── 비네팅 ──────────────────────────────────────────────────────
    vignette: float        # 0.0 ~ 1.0


STYLE_PRESETS: dict[str, StylePreset] = {

    "action": StylePreset(
        color_tone="dark",
        brightness=-8, contrast=28, saturation=12, temperature=-8,
        crop_zoom=1.25,
        slowmo_speed=0.25,
        freeze_dur=2.5,
        score_freeze_dur=2.0,
        stats_freeze_dur=3.5,
        cut_rhythm="fast",
        cut_types=["hard_cut", "flash"],
        badge_style="solid",
        score_color_map={"high": "#44EE88", "mid": "#FFCC44", "low": "#FF5533"},
        vignette=0.50,
    ),

    "instagram": StylePreset(
        color_tone="warm",
        brightness=10, contrast=14, saturation=14, temperature=14,
        crop_zoom=1.15,
        slowmo_speed=0.40,
        freeze_dur=3.0,
        score_freeze_dur=2.5,
        stats_freeze_dur=4.0,
        cut_rhythm="medium",
        cut_types=["hard_cut", "dissolve"],
        badge_style="outline",
        score_color_map={"high": "#44EE88", "mid": "#FFDD55", "low": "#FF6644"},
        vignette=0.30,
    ),

    "tiktok": StylePreset(
        color_tone="vibrant",
        brightness=6, contrast=22, saturation=22, temperature=6,
        crop_zoom=1.30,
        slowmo_speed=0.30,
        freeze_dur=2.0,
        score_freeze_dur=1.8,
        stats_freeze_dur=3.0,
        cut_rhythm="fast",
        cut_types=["hard_cut", "flash", "hard_cut"],
        badge_style="solid",
        score_color_map={"high": "#00FFAA", "mid": "#FFEE00", "low": "#FF3355"},
        vignette=0.25,
    ),

    "humor": StylePreset(
        color_tone="warm",
        brightness=14, contrast=10, saturation=20, temperature=18,
        crop_zoom=1.10,
        slowmo_speed=0.50,
        freeze_dur=3.5,
        score_freeze_dur=3.0,
        stats_freeze_dur=4.5,
        cut_rhythm="medium",
        cut_types=["hard_cut", "dissolve"],
        badge_style="outline",
        score_color_map={"high": "#FFDD00", "mid": "#FFAA33", "low": "#FF6622"},
        vignette=0.15,
    ),

    "documentary": StylePreset(
        color_tone="cool",
        brightness=-5, contrast=18, saturation=-10, temperature=-14,
        crop_zoom=1.05,
        slowmo_speed=0.50,
        freeze_dur=4.0,
        score_freeze_dur=3.0,
        stats_freeze_dur=5.0,
        cut_rhythm="slow",
        cut_types=["dissolve", "hard_cut"],
        badge_style="minimal",
        score_color_map={"high": "#88CCFF", "mid": "#AABBCC", "low": "#FF7755"},
        vignette=0.40,
    ),
}


def get_preset(style: str) -> StylePreset:
    style = style.lower().strip()
    if style not in STYLE_PRESETS:
        raise ValueError(
            f"지원하지 않는 스타일: '{style}'. "
            f"가능한 스타일: {list(STYLE_PRESETS.keys())}"
        )
    return STYLE_PRESETS[style]


def score_to_color(score: int, preset: StylePreset) -> str:
    cm = preset.score_color_map
    if score >= 80:
        return cm["high"]
    if score >= 55:
        return cm["mid"]
    return cm["low"]
