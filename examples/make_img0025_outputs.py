"""
IMG_0025_black1.mov → 인증영상 + 포스터 생성
"""
import sys
import json
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor import TemplateExecutor

# ─── 설정 ────────────────────────────────────────────────────────
SRC_VIDEO  = "/Users/khy/Downloads/IMG_0025_black1.mov"
OUT_DIR    = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# ─── 러닝 기록 (실제 값으로 수정 가능) ──────────────────────────
RUN_DATE     = "2026.04.02"
DISTANCE_KM  = 5.2
PACE_STR     = "5'47\"/km"

# ─── 폰트 경로 ───────────────────────────────────────────────────
IMPACT   = "/System/Library/Fonts/Supplemental/Impact.ttf"
DIN_COND = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
DIN_ALT  = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
APPLEGOTHIC = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════
# 1. 인증영상 (certification video)
# ═══════════════════════════════════════════════════════════════════

CERT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "img0025_cert",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 7.0,
        "color_grade": "cool",
        "vibe_tags": ["record", "certification", "night", "track"],
    },
    "timeline": {
        "total_duration_seconds": 7.0,
        "narrative_flow": "intro → buildup → peak_slowmo → stats_reveal",
        "segments": [
            {
                "id": "seg_0",
                "type": "intro",
                "start_ratio": 0.0,
                "end_ratio": 0.25,
                "shot_type": "wide",
                "speed": 1.0,
                "description": "오프닝 와이드",
            },
            {
                "id": "seg_1",
                "type": "buildup",
                "start_ratio": 0.25,
                "end_ratio": 0.50,
                "shot_type": "medium",
                "speed": 1.0,
                "description": "빌드업",
            },
            {
                "id": "seg_2",
                "type": "peak",
                "start_ratio": 0.50,
                "end_ratio": 0.60,
                "shot_type": "close_up",
                "speed": 0.5,
                "description": "피크 슬로모션",
            },
            {
                "id": "seg_3",
                "type": "stats_reveal",
                "start_ratio": 0.60,
                "end_ratio": 1.0,
                "shot_type": "medium",
                "speed": 1.0,
                "description": "기록 공개",
            },
        ],
        "cuts": [
            {"position_ratio": 0.25, "type": "hard_cut"},
            {"position_ratio": 0.50, "type": "flash"},
            {"position_ratio": 0.60, "type": "hard_cut"},
        ],
    },
    "speed_changes": [
        {"start_ratio": 0.50, "end_ratio": 0.60, "speed": 0.5},
    ],
    "effects": [
        {"type": "zoom_in", "start_ratio": 0.0,  "end_ratio": 0.25, "intensity": 0.10},
        {"type": "zoom_in", "start_ratio": 0.50, "end_ratio": 0.60, "intensity": 0.08},
        {"type": "vignette","start_ratio": 0.0,  "end_ratio": 1.0,  "intensity": 0.40},
    ],
    "overlays": [
        # ── 인트로 타이틀 ────────────────────────────────
        {
            "id": "overlay_title",
            "type": "text",
            "content": "NIGHT\nRUN",
            "position_pct": {"x": 50, "y": 12},
            "start_ratio": 0.0,
            "end_ratio": 0.25,
            "animation_in": "fade_in",
            "animation_out": "fade_out",
            "style": {
                "font_weight": 700,
                "font_size_ratio": 0.082,
                "color": "#FFFFFF",
                "opacity": 0.95,
                "letter_spacing": 8,
            },
        },
        # ── 거리 카운터 ───────────────────────────────────
        {
            "id": "overlay_counter_km",
            "type": "counter",
            "content": f"{DISTANCE_KM} km",
            "position_pct": {"x": 50, "y": 40},
            "start_ratio": 0.60,
            "end_ratio": 1.0,
            "counter_config": {
                "start_value": 0.0,
                "end_value": DISTANCE_KM,
                "unit": "km",
                "decimal_places": 1,
                "count_up": True,
                "easing": "ease_out",
            },
            "style": {
                "font_weight": 900,
                "font_size_ratio": 0.15,
                "color": "#FFFFFF",
                "opacity": 1.0,
            },
        },
        # ── PACE 라벨 ─────────────────────────────────────
        {
            "id": "overlay_pace_label",
            "type": "text",
            "content": "PACE",
            "position_pct": {"x": 50, "y": 58},
            "start_ratio": 0.60,
            "end_ratio": 1.0,
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.032,
                "color": "#AADDFF",
                "opacity": 0.85,
            },
        },
        # ── 페이스 값 ─────────────────────────────────────
        {
            "id": "overlay_pace",
            "type": "text",
            "content": PACE_STR,
            "position_pct": {"x": 50, "y": 65},
            "start_ratio": 0.60,
            "end_ratio": 1.0,
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.055,
                "color": "#FFFFFF",
                "opacity": 0.90,
            },
        },
        # ── 날짜 ──────────────────────────────────────────
        {
            "id": "overlay_date",
            "type": "text",
            "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.60,
            "end_ratio": 1.0,
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.030,
                "color": "#99BBDD",
                "opacity": 0.75,
            },
        },
    ],
    "color_grade": {
        "overall_tone": "cool",
        "has_filter": True,
        "filter_style": "film",
        "adjustment_params": {
            "brightness": -8,
            "contrast": 18,
            "saturation": -12,
            "temperature": -20,
        },
    },
}


def make_cert_video():
    print("=" * 60)
    print("  [1/2] 인증영상 생성")
    print("=" * 60)
    import tempfile
    from moviepy import VideoFileClip, concatenate_videoclips

    # 소스가 2.9s로 짧아서 3x 루프로 먼저 늘림
    print("  [전처리] 소스 3x 루프 생성...")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        loop_path = tf.name

    clip = VideoFileClip(SRC_VIDEO)
    looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
    looped.write_videofile(
        loop_path, codec="libx264", audio_codec="aac",
        fps=30, preset="medium", threads=4, logger=None
    )
    looped.close()
    clip.close()
    print(f"  [전처리] 루프 영상 저장: {loop_path} ({looped.duration:.1f}s)")

    out_path = str(OUT_DIR / f"IMG0025_cert_{ts}.mp4")
    executor = TemplateExecutor(verbose=True)
    executor.execute(CERT_INSTRUCTION, loop_path, out_path)

    import os
    os.unlink(loop_path)

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"  → 완료: {out_path}  ({size_mb:.1f} MB)")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 2. 포스터 (poster image)
# ═══════════════════════════════════════════════════════════════════

def make_poster():
    print("\n" + "=" * 60)
    print("  [2/2] 포스터 생성")
    print("=" * 60)

    # ── 최적 프레임 추출 (t=1.0s — 러너 실루엣 선명) ────────────
    cap = cv2.VideoCapture(SRC_VIDEO)
    cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("  프레임 추출 실패")
        return None

    # BGR → RGB, PIL 변환
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    W, H = img.size   # 1080 × 1920

    # ── 색감 강화 (차갑고 드라마틱) ─────────────────────────────
    import PIL.ImageEnhance as Enhance
    img = Enhance.Brightness(img).enhance(0.75)
    img = Enhance.Contrast(img).enhance(1.25)
    img = Enhance.Color(img).enhance(0.6)      # 채도 감소 (무드)

    # 냉색 색조 (파란 틴트)
    r, g, b = img.split()
    b = b.point(lambda x: min(255, int(x * 1.18)))
    r = r.point(lambda x: int(x * 0.88))
    img = Image.merge("RGB", (r, g, b))

    draw = ImageDraw.Draw(img)

    # ── 그라디언트 오버레이 (상단 + 하단) ──────────────────────
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # 상단: 검정→투명 (위 40%)
    grad_h_top = int(H * 0.45)
    for y in range(grad_h_top):
        alpha = int(200 * (1 - y / grad_h_top) ** 1.5)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

    # 하단: 투명→검정 (아래 55%)
    grad_h_bot = int(H * 0.58)
    grad_start = H - grad_h_bot
    for y in range(grad_h_bot):
        alpha = int(210 * (y / grad_h_bot) ** 1.3)
        ov_draw.line([(0, grad_start + y), (W, grad_start + y)], fill=(0, 0, 0, alpha))

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── 텍스트 레이아웃 ──────────────────────────────────────────
    # 상단 영역: 브랜딩
    MARGIN = int(W * 0.08)

    # --- NIGHT RUN (메인 타이틀) ---
    fsize_title = int(W * 0.14)
    fnt_title = load_font(IMPACT, fsize_title)
    title = "NIGHT RUN"
    bbox = draw.textbbox((0, 0), title, font=fnt_title)
    tw = bbox[2] - bbox[0]
    tx = (W - tw) // 2
    ty = int(H * 0.07)
    # 글로우 효과
    for r in [6, 4, 2]:
        glow_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_img)
        gd.text((tx, ty), title, font=fnt_title, fill=(100, 180, 255, 60))
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=r))
        img = Image.alpha_composite(img.convert("RGBA"), glow_img).convert("RGB")
    draw = ImageDraw.Draw(img)
    # 그림자
    draw.text((tx + 3, ty + 3), title, font=fnt_title, fill=(0, 0, 0, 180))
    draw.text((tx, ty), title, font=fnt_title, fill="#FFFFFF")

    # --- 날짜 ---
    fsize_date = int(W * 0.038)
    fnt_date = load_font(DIN_ALT, fsize_date)
    date_txt = RUN_DATE
    bbox = draw.textbbox((0, 0), date_txt, font=fnt_date)
    dw = bbox[2] - bbox[0]
    draw.text(((W - dw) // 2, int(H * 0.07) + fsize_title + int(H * 0.012)),
              date_txt, font=fnt_date, fill=(170, 210, 255))

    # ── 하단 스탯 블록 ────────────────────────────────────────────
    # 수평 디바이더 라인
    line_y = int(H * 0.72)
    line_alpha = 100
    line_col = (150, 200, 255)
    draw.line([(MARGIN, line_y), (W - MARGIN, line_y)], fill=line_col, width=1)

    # 거리 (대형)
    fsize_dist = int(W * 0.22)
    fnt_dist = load_font(IMPACT, fsize_dist)
    dist_str = f"{DISTANCE_KM}"
    bbox = draw.textbbox((0, 0), dist_str, font=fnt_dist)
    dw = bbox[2] - bbox[0]
    dist_x = (W - dw) // 2
    dist_y = int(H * 0.73)
    draw.text((dist_x + 4, dist_y + 4), dist_str, font=fnt_dist, fill=(0, 0, 0, 160))
    draw.text((dist_x, dist_y), dist_str, font=fnt_dist, fill="#FFFFFF")

    # "km" 단위
    fsize_unit = int(W * 0.065)
    fnt_unit = load_font(DIN_ALT, fsize_unit)
    unit_x = dist_x + dw + int(W * 0.02)
    unit_y = dist_y + fsize_dist - fsize_unit - int(H * 0.01)
    draw.text((unit_x, unit_y), "km", font=fnt_unit, fill=(180, 220, 255))

    # 페이스 라벨
    fsize_label = int(W * 0.030)
    fnt_label = load_font(DIN_ALT, fsize_label)
    pace_label_y = dist_y + fsize_dist + int(H * 0.01)
    draw.text(((W - draw.textlength("PACE", font=fnt_label)) // 2,
               pace_label_y), "PACE", font=fnt_label, fill=(150, 200, 255))

    # 페이스 값
    fsize_pace = int(W * 0.055)
    fnt_pace = load_font(DIN_COND, fsize_pace)
    pace_y = pace_label_y + fsize_label + int(H * 0.008)
    pw = draw.textlength(PACE_STR, font=fnt_pace)
    draw.text(((W - pw) // 2, pace_y), PACE_STR, font=fnt_pace, fill="#FFFFFF")

    # ── 하단 로고/브랜딩 ─────────────────────────────────────────
    fsize_logo = int(W * 0.028)
    fnt_logo = load_font(DIN_ALT, fsize_logo)
    logo_txt = "TRACK NIGHT  /  04.02"
    lw = draw.textlength(logo_txt, font=fnt_logo)
    draw.text(((W - lw) // 2, int(H * 0.94)), logo_txt,
              font=fnt_logo, fill=(120, 160, 200))

    # ── 저장 ─────────────────────────────────────────────────────
    poster_path = str(OUT_DIR / f"IMG0025_poster_{ts}.jpg")
    img.save(poster_path, "JPEG", quality=95)
    size_kb = Path(poster_path).stat().st_size / 1024
    print(f"  → 포스터: {poster_path}  ({size_kb:.0f} KB)")
    return poster_path


if __name__ == "__main__":
    cert = make_cert_video()
    poster = make_poster()
    print("\n" + "=" * 60)
    print("  전체 완료!")
    print(f"  인증영상 : {cert}")
    print(f"  포스터   : {poster}")
    print("=" * 60)
