"""
나이키 스타일 인증 영상 생성기
  - 속도 자막 없음
  - 끝에 km 카운터 + 시간 + 페이스 나이키 스타일로
  - 굵은 폰트
"""
import sys, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.preprocessor    import preprocess
from src.template_executor import TemplateExecutor

SRC      = "/Users/khy/Downloads/KakaoTalk_Video_2026-04-03-21-23-30.mp4"
OUT_DIR  = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_PATH = str(OUT_DIR / f"cert_nike_{ts}.mp4")

# ── 러닝 기록 ─────────────────────────────────────────────────────
DISTANCE_KM = 3.8
RUN_TIME    = "25'34\""
PACE        = "6'42\"/km"
RUN_DATE    = "2026.04.03"

# ── 인증 영상 instruction ──────────────────────────────────────────
# 흐름: 와이드 → 러너 접근 (1x) → 슬로우 클로즈업 → 스탯 카드
CERT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "cert_nike_v1",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 12.0,
        "color_grade": "warm",
        "crop_zoom": 1.20,
    },
    "timeline": {
        "total_duration_seconds": 12.0,
        "segments": [
            # 오프닝: 와이드샷 벚꽃 도로
            {
                "id": "s0_wide",
                "type": "intro",
                "source_start_sec": 0.0,
                "source_end_sec":   2.0,
                "speed": 1.0,
                "start_ratio": 0.00,
                "end_ratio":   0.17,
            },
            # 러너 접근 (원속도)
            {
                "id": "s1_approach",
                "type": "buildup",
                "source_start_sec": 2.0,
                "source_end_sec":   4.5,
                "speed": 1.0,
                "start_ratio": 0.17,
                "end_ratio":   0.38,
            },
            # 슬로우 클로즈업 — 라벨 없음
            {
                "id": "s2_slowmo",
                "type": "peak",
                "source_start_sec": 4.5,
                "source_end_sec":   5.8,
                "speed": 0.35,
                "start_ratio": 0.38,
                "end_ratio":   0.62,
            },
            # 스탯 카드 freeze (나이키 스타일 카운터)
            {
                "id": "s3_stats",
                "type": "freeze",
                "source_start_sec": 5.0,
                "source_end_sec":   5.0,
                "freeze_duration": 4.5,
                "start_ratio": 0.62,
                "end_ratio":   1.00,
            },
        ],
        "cuts": [
            {"position_ratio": 0.17, "type": "hard_cut"},
            {"position_ratio": 0.38, "type": "flash"},
            {"position_ratio": 0.62, "type": "hard_cut"},
        ],
    },
    "speed_changes": [
        {"start_ratio": 0.38, "end_ratio": 0.62, "speed": 0.35},
    ],
    "effects": [
        {"type": "zoom_in",  "start_ratio": 0.00, "end_ratio": 0.17, "intensity": 0.06},
        {"type": "zoom_in",  "start_ratio": 0.17, "end_ratio": 0.38, "intensity": 0.10},
        {"type": "zoom_in",  "start_ratio": 0.38, "end_ratio": 0.62, "intensity": 0.16},
        {"type": "vignette", "start_ratio": 0.00, "end_ratio": 1.00, "intensity": 0.38},
    ],
    "overlays": [
        # ── 스탯 카드 (freeze 구간만) ──────────────────────────────
        # 거리 카운터 — 가장 크게
        {
            "id": "ov_km_counter",
            "type": "counter",
            "content": f"{DISTANCE_KM}",
            "position_pct": {"x": 50, "y": 44},
            "start_ratio": 0.62,
            "end_ratio":   1.00,
            "counter_config": {
                "start_value":    0.0,
                "end_value":      DISTANCE_KM,
                "unit":           "",
                "decimal_places": 1,
                "count_up":       True,
                "easing":         "ease_out",
            },
            "animation_in": "fade_in",
            "style": {
                "font_weight":      900,
                "font_size_ratio":  0.22,   # 화면의 22% — 크고 임팩트있게
                "color":            "#FFFFFF",
                "opacity":          1.0,
            },
        },
        # "km" 단위 레이블
        {
            "id": "ov_km_label",
            "type": "text",
            "content": "km",
            "position_pct": {"x": 50, "y": 58},
            "start_ratio": 0.62,
            "end_ratio":   1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight":     700,
                "font_size_ratio": 0.045,
                "color":           "#FFFFFF",
                "opacity":         0.75,
            },
        },
        # 구분선 역할: 시간
        {
            "id": "ov_time",
            "type": "text",
            "content": RUN_TIME,
            "position_pct": {"x": 30, "y": 72},
            "start_ratio": 0.68,   # km보다 약간 늦게 등장
            "end_ratio":   1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight":     900,
                "font_size_ratio": 0.068,
                "color":           "#FFFFFF",
                "opacity":         1.0,
            },
        },
        # 페이스
        {
            "id": "ov_pace",
            "type": "text",
            "content": PACE,
            "position_pct": {"x": 72, "y": 72},
            "start_ratio": 0.68,
            "end_ratio":   1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight":     700,
                "font_size_ratio": 0.040,
                "color":           "#FFEECC",
                "opacity":         0.90,
            },
        },
        # 날짜 — 맨 아래 작게
        {
            "id": "ov_date",
            "type": "text",
            "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.70,
            "end_ratio":   1.00,
            "animation_in": "fade_in",
            "style": {
                "font_weight":     300,
                "font_size_ratio": 0.028,
                "color":           "#CCBBAA",
                "opacity":         0.65,
            },
        },
    ],
    "color_grade": {
        "overall_tone": "warm",
        "adjustment_params": {
            "brightness":  8,
            "contrast":    18,
            "saturation":  10,
            "temperature": 12,
        },
    },
}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        print("[전처리] rotation fix + 루프...")
        info = preprocess(SRC, target_duration=12.0, tmpdir=tmpdir)
        print(f"  소스: {info.width}x{info.height}  {info.duration:.1f}s  (루프 {info.loop_count}x)\n")

        print("[렌더링] 나이키 스타일 인증 영상...")
        executor = TemplateExecutor(verbose=True)
        executor.execute(CERT_INSTRUCTION, info.path, OUT_PATH)

    if Path(OUT_PATH).exists():
        mb = Path(OUT_PATH).stat().st_size / 1024 / 1024
        print(f"\n완료: {OUT_PATH}  ({mb:.1f} MB)")
    else:
        print("실패: 출력 파일 없음")
