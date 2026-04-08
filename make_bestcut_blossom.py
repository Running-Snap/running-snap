"""
BLOSSOM RUNNING 베스트컷 영상
  - 타이틀: BLOSSOM RUNNING
  - 위치: Chungnam National University N9-2
  - 시간: P.M. 03:00
  - 멀티컷 + 슬로우모션 + 타이틀 카드
"""
import sys, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.preprocessor      import preprocess
from src.template_executor import TemplateExecutor

SRC      = "/Users/khy/Downloads/KakaoTalk_Video_2026-04-03-21-23-30.mp4"
OUT_DIR  = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_PATH = str(OUT_DIR / f"bestcut_blossom_{ts}.mp4")

# ── 러닝 기록 ─────────────────────────────────────────────────────
DISTANCE_KM = 5.2
RUN_TIME    = "34'18\""
PACE        = "6'35\"/km"
LOCATION    = "Chungnam National Univ."
SUBLOC      = "N9-2"
RUN_CLOCK   = "P.M. 03:00"
RUN_DATE    = "2026.04.03"

INSTRUCTION = {
    "version": "1.0",
    "template_id": "bestcut_blossom_v1",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 14.0,
        "color_grade": "warm",
        "crop_zoom": 1.15,
    },
    "timeline": {
        "total_duration_seconds": 14.0,
        "segments": [
            # ① 와이드 오프닝 — 벚꽃 도로 전경
            {
                "id": "c0_wide",
                "type": "intro",
                "source_start_sec": 0.0,
                "source_end_sec":   1.8,
                "speed": 1.0,
                "start_ratio": 0.00, "end_ratio": 0.13,
            },
            # ② 러너 접근 — 원속도
            {
                "id": "c1_approach",
                "type": "buildup",
                "source_start_sec": 1.8,
                "source_end_sec":   3.6,
                "speed": 1.0,
                "start_ratio": 0.13, "end_ratio": 0.28,
            },
            # ③ 슬로우 클로즈업 — 피크
            {
                "id": "c2_slow",
                "type": "peak",
                "source_start_sec": 3.6,
                "source_end_sec":   5.2,
                "speed": 0.30,
                "start_ratio": 0.28, "end_ratio": 0.52,
            },
            # ④ 컷백 — 2루프 다른 구간 (속도감)
            {
                "id": "c3_cutback",
                "type": "action",
                "source_start_sec": 6.6,
                "source_end_sec":   8.0,
                "speed": 1.0,
                "start_ratio": 0.52, "end_ratio": 0.62,
            },
            # ⑤ 울트라 슬로우 — 3루프 (얼굴 클로즈업 구간)
            {
                "id": "c4_ultra",
                "type": "peak",
                "source_start_sec": 10.8,
                "source_end_sec":   11.8,
                "speed": 0.25,
                "start_ratio": 0.62, "end_ratio": 0.73,
            },
            # ⑥ 타이틀 카드 freeze
            {
                "id": "c5_title",
                "type": "freeze",
                "source_start_sec": 4.8,
                "source_end_sec":   4.8,
                "freeze_duration":  3.8,
                "start_ratio": 0.73, "end_ratio": 1.00,
            },
        ],
        "cuts": [
            {"position_ratio": 0.13, "type": "hard_cut"},
            {"position_ratio": 0.28, "type": "flash"},
            {"position_ratio": 0.52, "type": "hard_cut"},
            {"position_ratio": 0.62, "type": "flash"},
            {"position_ratio": 0.73, "type": "dissolve"},
        ],
    },
    "speed_changes": [
        {"start_ratio": 0.28, "end_ratio": 0.52, "speed": 0.30},
        {"start_ratio": 0.62, "end_ratio": 0.73, "speed": 0.25},
    ],
    "effects": [
        {"type": "zoom_in",  "start_ratio": 0.00, "end_ratio": 0.13, "intensity": 0.05},
        {"type": "zoom_in",  "start_ratio": 0.13, "end_ratio": 0.28, "intensity": 0.10},
        {"type": "zoom_in",  "start_ratio": 0.28, "end_ratio": 0.52, "intensity": 0.18},
        {"type": "zoom_in",  "start_ratio": 0.62, "end_ratio": 0.73, "intensity": 0.14},
        {"type": "vignette", "start_ratio": 0.00, "end_ratio": 1.00, "intensity": 0.42},
    ],
    "overlays": [
        # ── 오프닝: 위치 정보 ─────────────────────────────────────
        {
            "id": "ov_location",
            "type": "text",
            "content": LOCATION,
            "position_pct": {"x": 50, "y": 10},
            "start_ratio": 0.00, "end_ratio": 0.13,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {
                "font_weight": 700, "font_size_ratio": 0.034,
                "color": "#FFFFFF", "opacity": 0.90,
            },
        },
        {
            "id": "ov_subloc",
            "type": "text",
            "content": f"{SUBLOC}  ·  {RUN_CLOCK}",
            "position_pct": {"x": 50, "y": 17},
            "start_ratio": 0.00, "end_ratio": 0.13,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.026,
                "color": "#FFEECC", "opacity": 0.75,
            },
        },

        # ── 타이틀 카드 ───────────────────────────────────────────
        # BLOSSOM RUNNING — 메인 타이틀
        {
            "id": "ov_title",
            "type": "text",
            "content": "BLOSSOM\nRUNNING",
            "position_pct": {"x": 50, "y": 24},
            "start_ratio": 0.73, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 900, "font_size_ratio": 0.115,
                "color": "#FFFFFF", "opacity": 1.0,
            },
        },
        # 구분선 대신 날짜
        {
            "id": "ov_date_card",
            "type": "text",
            "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 50},
            "start_ratio": 0.75, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.028,
                "color": "#FFDDAA", "opacity": 0.70,
            },
        },
        # 거리 카운터
        {
            "id": "ov_km",
            "type": "counter",
            "content": f"{DISTANCE_KM}",
            "position_pct": {"x": 28, "y": 66},
            "start_ratio": 0.73, "end_ratio": 1.00,
            "counter_config": {
                "start_value": 0.0, "end_value": DISTANCE_KM,
                "unit": "", "decimal_places": 1,
                "count_up": True, "easing": "ease_out",
            },
            "animation_in": "fade_in",
            "style": {
                "font_weight": 900, "font_size_ratio": 0.095,
                "color": "#FFFFFF", "opacity": 1.0,
            },
        },
        {
            "id": "ov_km_unit",
            "type": "text",
            "content": "km",
            "position_pct": {"x": 28, "y": 76},
            "start_ratio": 0.73, "end_ratio": 1.00,
            "style": {
                "font_weight": 300, "font_size_ratio": 0.026,
                "color": "#FFFFFF", "opacity": 0.65,
            },
        },
        # 시간
        {
            "id": "ov_time",
            "type": "text",
            "content": RUN_TIME,
            "position_pct": {"x": 72, "y": 66},
            "start_ratio": 0.75, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 900, "font_size_ratio": 0.072,
                "color": "#FFFFFF", "opacity": 1.0,
            },
        },
        {
            "id": "ov_pace",
            "type": "text",
            "content": PACE,
            "position_pct": {"x": 72, "y": 76},
            "start_ratio": 0.75, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.026,
                "color": "#FFEECC", "opacity": 0.70,
            },
        },
        # 위치 — 맨 아래
        {
            "id": "ov_loc_bot",
            "type": "text",
            "content": f"{LOCATION}  {SUBLOC}",
            "position_pct": {"x": 50, "y": 90},
            "start_ratio": 0.77, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.024,
                "color": "#CCBBAA", "opacity": 0.60,
            },
        },
    ],
    "color_grade": {
        "overall_tone": "warm",
        "adjustment_params": {
            "brightness":  6,
            "contrast":    20,
            "saturation":  12,
            "temperature": 10,
        },
    },
}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        print("[전처리]...")
        info = preprocess(SRC, target_duration=14.0, tmpdir=tmpdir)
        print(f"  {info.width}x{info.height}  {info.duration:.1f}s  ({info.loop_count}x 루프)\n")

        print("[렌더링] BLOSSOM RUNNING 베스트컷...")
        executor = TemplateExecutor(verbose=True)
        executor.execute(INSTRUCTION, info.path, OUT_PATH)

    if Path(OUT_PATH).exists():
        mb = Path(OUT_PATH).stat().st_size / 1024 / 1024
        print(f"\n완료: {OUT_PATH}  ({mb:.1f} MB)")
