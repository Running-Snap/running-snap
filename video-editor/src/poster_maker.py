"""
poster_maker.py
===============
러닝 베스트컷 포스터 생성기 (PIL 기반 정적 JPG 출력).

event_config 딕셔너리로 매 대회마다 다른 컨셉 적용.

사용:
    from src.poster_maker import PosterMaker

    path = PosterMaker().make(
        video_path   = "/path/to/video.mp4",
        frame_time   = 2.5,                # 추출할 프레임 시각 (초)
        event_config = {
            "title":        "BLOSSOM\\nRUNNING",
            "location":     "Chungnam National Univ.",
            "sublocation":  "N9-2",
            "time":         "P.M. 03:00",
            "date":         "2026.04.03",
            "distance_km":  5.2,
            "run_time":     "34'18\\"",
            "pace":         "6'35\\"/km",
            "color_scheme": "warm",          # warm / cool / neutral
            "branding":     "BLOSSOM RUN  /  04.03",   # optional
        },
        output_path  = "outputs/posters/blossom.jpg",
    )
"""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import PIL.ImageEnhance as Enhance


# ── 폰트 경로 ─────────────────────────────────────────────────────
def _find_font(candidates: list) -> str:
    """후보 경로 중 존재하는 첫 번째 폰트 반환"""
    import os
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]  # 없으면 첫 번째 반환 (load_default 폴백)

_FONTS: Dict[str, str] = {
    "impact": _find_font([
        "/System/Library/Fonts/Supplemental/Impact.ttf",           # macOS
        "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf",       # Ubuntu (굵은 스퀘어)
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "din_bold": _find_font([
        "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquare_acEB.ttf",    # Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "din_alt": _find_font([
        "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",        # Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "gothic": _find_font([
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",     # Ubuntu
    ]),
    "futura": _find_font([
        "/System/Library/Fonts/Supplemental/Futura.ttc",
        "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf",       # Ubuntu (굵고 깔끔)
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "gill": _find_font([
        "/System/Library/Fonts/Supplemental/GillSans.ttc",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "avenir_condensed": _find_font([
        "/System/Library/Fonts/Avenir Next Condensed.ttc",
        "/usr/share/fonts/truetype/nanum/NanumSquare_acB.ttf",     # Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
    ]),
    "avenir": _find_font([
        "/System/Library/Fonts/Avenir Next.ttc",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf", # Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "helvetica": _find_font([
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf", # Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "inter_black": _find_font([
        "/usr/share/fonts/truetype/inter/Inter-Black.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "inter_semibold": _find_font([
        "/usr/share/fonts/truetype/inter/Inter-SemiBold.ttf",
        "/System/Library/Fonts/Avenir Next.ttc",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]),
    "inter_regular": _find_font([
        "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
        "/System/Library/Fonts/Avenir Next.ttc",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]),
}


def _load_font(key: str, size: int) -> ImageFont.FreeTypeFont:
    path = _FONTS.get(key, _FONTS["impact"])
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ── 색 조합 정의 ──────────────────────────────────────────────────
_SCHEMES: Dict[str, Dict] = {
    "warm": {
        "brightness": 0.85, "contrast": 1.25, "saturation": 1.10,
        "r_mult": 1.08, "g_mult": 1.02, "b_mult": 0.88,
        "title":    "#FFFFFF",
        "accent":   "#FFDDAA",
        "stat":     "#FFEECC",
        "branding": "#CCBBAA",
        "glow_rgb": (255, 200, 120),
    },
    "cool": {
        "brightness": 0.75, "contrast": 1.25, "saturation": 0.60,
        "r_mult": 0.88, "g_mult": 0.96, "b_mult": 1.18,
        "title":    "#FFFFFF",
        "accent":   "#AADDFF",
        "stat":     "#99BBDD",
        "branding": "#7799BB",
        "glow_rgb": (100, 180, 255),
    },
    "neutral": {
        "brightness": 0.85, "contrast": 1.20, "saturation": 0.90,
        "r_mult": 1.00, "g_mult": 1.00, "b_mult": 1.00,
        "title":    "#FFFFFF",
        "accent":   "#CCCCCC",
        "stat":     "#DDDDDD",
        "branding": "#AAAAAA",
        "glow_rgb": (200, 200, 200),
    },
}


class PosterMaker:
    """러닝 베스트컷 포스터 생성기."""

    # ── 9:16 포스터 기본 크기 ─────────────────────────────────────
    POSTER_W = 1080
    POSTER_H = 1920

    def make(
        self,
        event_config: Dict[str, Any],
        output_path:  str,
        # ── 배경 소스: 둘 중 하나만 지정 ──
        video_path:   Optional[str] = None,
        frame_time:   float = 0.0,
        image_path:   Optional[str] = None,
        # ── 포스터 버전 ──
        poster_mode:  str = "photo",   # "photo" | "feed"
        # ── 색보정 ──
        color_grade:  bool = False,    # True = 밝기/대비/채도 보정 적용, False = 원본 그대로
    ) -> Optional[str]:
        """
        포스터 생성 후 저장.

        poster_mode:
          "photo" (기본) — 원본 비율 유지, no-stats 시 하단 그라디언트 확장
          "feed"         — 4:5 인스타그램 피드 (1080×1350), 커버 크롭, 스탯 레이아웃

        Returns:
            저장된 파일 경로 (실패 시 None)
        """
        if image_path:
            frame = self._load_image(image_path)
            if frame is None:
                print(f"[PosterMaker] 이미지 로드 실패: {image_path}")
                return None
        elif video_path:
            frame = self._extract_frame(video_path, frame_time)
            if frame is None:
                print(f"[PosterMaker] 프레임 추출 실패: {video_path} @ {frame_time:.2f}s")
                return None
        else:
            print("[PosterMaker] image_path 또는 video_path 중 하나를 지정해야 합니다.")
            return None

        scheme = event_config.get("color_scheme", "warm")

        if poster_mode == "feed":
            # ── 피드 버전: 4:5 커버 크롭, 그라디언트 없음 ──
            img = self._build_feed_canvas(frame, scheme, color_grade=color_grade)
            img = self._add_gradients(img, scheme, photo_zone_h=None)
            img = self._draw_overlay(img, event_config, scheme,
                                     data_zone_y=None, poster_mode="feed")
        else:
            # ── 사진 버전: 9:16 전용 새 레이아웃 ──
            # [상단] 위치 → 제목  /  [중앙] 러너 사진  /  [하단] km · 날짜 · 페이스
            img = self._build_916_canvas(frame, scheme, color_grade)
            img = self._add_gradients_916(img, scheme)
            img = self._draw_overlay_916(img, event_config, scheme)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "JPEG", quality=95)
        size_kb = Path(output_path).stat().st_size / 1024
        print(f"[PosterMaker] 저장: {output_path}  ({size_kb:.0f} KB)")
        return output_path

    # ── 이미지 / 프레임 소스 ─────────────────────────────────────

    def _load_image(self, image_path: str) -> Optional[np.ndarray]:
        """정지 이미지 파일 → RGB numpy array."""
        img = cv2.imread(image_path)
        if img is None:
            return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def _extract_frame(self, video_path: str, t_sec: float) -> Optional[np.ndarray]:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # ── 이벤트 레이아웃 캔버스 구성 ──────────────────────────────

    def _build_event_canvas(
        self,
        frame_rgb: np.ndarray,
        scheme: str,
        color_grade: bool = False,
    ) -> Tuple[Image.Image, int]:
        """
        이벤트 포스터 전용 캔버스 (4:5 인스타그램 피드 비율, 1080×1350).

        규칙:
          1. 사진 하단(bottom)은 절대 건드리지 않음
          2. 사진이 캔버스보다 길면 → 상단만 약간 크롭
          3. 사진이 캔버스보다 짧으면 → 하단 엣지 컬러 기반 자연스러운 그라디언트 확장
          4. 그라디언트: 열(column)별 실제 엣지 색상에서 시작해 부드럽게 어두워짐

        Returns:
            (canvas_image, data_zone_y)
              canvas_image : 1080×1350 RGB PIL 이미지
              data_zone_y  : 텍스트 데이터 존 시작 y 좌표
        """
        # ── 4:5 인스타그램 피드 캔버스 ─────────────────────────
        W = 1080
        H = 1350   # 4:5

        # ── 1. 색보정 (color_grade=True일 때만 적용) ─────────────
        if color_grade:
            cs  = _SCHEMES.get(scheme, _SCHEMES["warm"])
            raw = Image.fromarray(frame_rgb)
            raw = Enhance.Brightness(raw).enhance(cs["brightness"])
            raw = Enhance.Contrast(raw).enhance(cs["contrast"])
            raw = Enhance.Color(raw).enhance(cs["saturation"])
            r, g, b = raw.split()
            r = r.point(lambda x: min(255, int(x * cs["r_mult"])))
            g = g.point(lambda x: min(255, int(x * cs["g_mult"])))
            b = b.point(lambda x: min(255, int(x * cs["b_mult"])))
            photo_src = Image.merge("RGB", (r, g, b))
        else:
            photo_src = Image.fromarray(frame_rgb)

        src_w, src_h = photo_src.size

        # ── 2. 포스터 폭 기준 스케일 ────────────────────────────
        scale     = W / src_w
        photo_img = photo_src.resize((W, int(src_h * scale)), Image.LANCZOS)
        photo_w, photo_h = photo_img.size

        # ── 3. 사진 배치 결정 ────────────────────────────────────
        if photo_h >= H:
            # 사진이 캔버스보다 길거나 같음 → 상단만 크롭, 하단 보존
            crop_top   = photo_h - H          # 넘치는 픽셀
            photo_placed = photo_img.crop((0, crop_top, W, photo_h))
            extension_h  = 0
            data_zone_y  = int(H * 0.70)      # 하단 30%를 텍스트 영역으로 사용
        else:
            # 사진이 캔버스보다 짧음 → 전체 사용 + 아래 그라디언트 확장
            photo_placed = photo_img           # 하단 손대지 않음 (전체 표시)
            extension_h  = H - photo_h
            data_zone_y  = photo_h             # 그라디언트 시작 = 사진 끝

        if extension_h == 0:
            return photo_placed, data_zone_y

        # ── 4. 하단 엣지 컬러 감지 (열별 per-column, 마지막 10px) ──
        #   열(column)마다 실제 색상을 유지 → 수평 질감이 자연스럽게 이어짐
        bottom_strip = np.array(
            photo_placed.crop((0, photo_h - 10, W, photo_h))
        ).astype(float)                           # shape: (10, W, 3)
        edge_row = bottom_strip.mean(axis=0)      # shape: (W, 3) — 열별 평균 색상

        # 전체 평균 (그라디언트 끝 목표색 계산용)
        avg_color = edge_row.mean(axis=0)         # shape: (3,)

        # 그라디언트 끝: 평균색을 25% 밝기로 (너무 검지 않게)
        target_color = (avg_color * 0.25).clip(0, 255)

        # ── 5. 자연스러운 그라디언트 확장 생성 ──────────────────
        ext_arr = np.zeros((extension_h, W, 3), dtype=np.float32)
        for y in range(extension_h):
            t = (y / max(extension_h - 1, 1)) ** 1.4   # ease-in curve
            # 열별로 엣지 색상 → 목표색 보간
            ext_arr[y] = edge_row * (1.0 - t) + target_color * t

        ext_arr = ext_arr.clip(0, 255).astype(np.uint8)
        ext_img  = Image.fromarray(ext_arr)

        # 경계 상단 10px 미세 블러 → 사진↔그라디언트 이음새 자연스럽게
        seam_h    = min(10, extension_h)
        seam_crop = ext_img.crop((0, 0, W, seam_h))
        seam_blur = seam_crop.filter(ImageFilter.GaussianBlur(radius=2))
        ext_img.paste(seam_blur, (0, 0))

        # ── 6. 캔버스 합성 ───────────────────────────────────────
        canvas = Image.new("RGB", (W, H))
        canvas.paste(photo_placed, (0, 0))
        canvas.paste(ext_img, (0, photo_h))

        return canvas, data_zone_y

    # ════════════════════════════════════════════════════════════
    # 9:16 포스터 전용 메서드 (새 레이아웃)
    # ════════════════════════════════════════════════════════════

    def _build_916_canvas(
        self,
        frame_rgb: np.ndarray,
        scheme: str,
        color_grade: bool = False,
    ) -> Image.Image:
        """
        9:16 (1080×1920) 배경 캔버스 생성.

        원본 프레임을 9:16 비율로 **중앙 크롭** — 러너가 중앙에 오도록.
        세로가 더 긴 영상(9:16 이미 맞는 경우)은 그대로 리사이즈.
        """
        W, H = 1080, 1920

        if color_grade:
            photo = self._color_grade(frame_rgb, scheme)
        else:
            photo = Image.fromarray(frame_rgb)

        src_w, src_h = photo.size
        src_ratio = src_w / src_h
        tgt_ratio = W / H   # 0.5625

        if src_ratio > tgt_ratio:
            # 원본이 더 넓음(가로) → 높이 기준 스케일 후 좌우 중앙 크롭
            scale  = H / src_h
            new_w  = int(src_w * scale)
            scaled = photo.resize((new_w, H), Image.LANCZOS)
            x_off  = (new_w - W) // 2
            canvas = scaled.crop((x_off, 0, x_off + W, H))
        else:
            # 원본이 더 좁음(세로) → 폭 기준 스케일 후 상하 중앙 크롭
            scale  = W / src_w
            new_h  = int(src_h * scale)
            scaled = photo.resize((W, new_h), Image.LANCZOS)
            if new_h > H:
                y_off  = (new_h - H) // 2
                canvas = scaled.crop((0, y_off, W, y_off + H))
            else:
                canvas = scaled.resize((W, H), Image.LANCZOS)

        if canvas.size != (W, H):
            canvas = canvas.resize((W, H), Image.LANCZOS)

        return canvas

    def _add_gradients_916(
        self,
        img: Image.Image,
        scheme: str,
    ) -> Image.Image:
        """
        9:16 포스터 전용 그라디언트.

        상단 0 ~ 40% : 검정→투명  (위치·제목 가독성)
        하단 62 ~ 100%: 투명→검정 (스탯 데이터 가독성)
        """
        W, H = img.size
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        # 상단
        top_h = int(H * 0.40)
        for y in range(top_h):
            alpha = int(210 * (1 - y / top_h) ** 1.6)
            draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

        # 하단
        bot_start = int(H * 0.62)
        bot_h     = H - bot_start
        for y in range(bot_h):
            alpha = int(235 * (y / bot_h) ** 1.2)
            draw.line([(0, bot_start + y), (W, bot_start + y)], fill=(0, 0, 0, alpha))

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        return img.convert("RGB")

    def _draw_overlay_916(
        self,
        img: Image.Image,
        cfg: Dict,
        scheme: str,
    ) -> Image.Image:
        """
        9:16 포스터 텍스트 레이아웃.

        [상단]
          y ≈  5% : location (Avenir Medium)
          y ≈  9% : sublocation · time (Avenir, 소형)
          y ≈ 14% : title (Futura, 대형 + glow)

        [하단]
          y ≈ 70% : 가는 구분선
          y ≈ 72% : km 숫자 (Impact, 초대형) + "km" 단위
          y ≈ 87% : DATE | DAY | TIME | PACE 레이블+값 컬럼
          y ≈ 95% : branding
        """
        W, H = img.size
        cs     = _SCHEMES.get(scheme, _SCHEMES["warm"])
        MARGIN = int(W * 0.08)
        max_w  = W - MARGIN * 2
        draw   = ImageDraw.Draw(img)

        # ── 상단: location ──────────────────────────────────────
        location = cfg.get("location", "")
        subloc   = cfg.get("sublocation", "")
        time_txt = cfg.get("time", "")

        y = int(H * 0.050)
        if location:
            fnt   = _load_font("inter_semibold", int(W * 0.034))
            lines = self._wrap_text(location, fnt, max_w, draw)
            for line in lines:
                lw = draw.textlength(line, font=fnt)
                draw.text(((W - lw) // 2, y), line, font=fnt, fill=cs["title"])
                y += int(H * 0.036)

        sub_parts = [s for s in [subloc, time_txt] if s]
        if sub_parts:
            sub_txt = "  ·  ".join(sub_parts)
            fnt2    = _load_font("inter_regular", int(W * 0.024))
            lines2  = self._wrap_text(sub_txt, fnt2, max_w, draw)
            for line in lines2:
                sw = draw.textlength(line, font=fnt2)
                draw.text(((W - sw) // 2, y), line, font=fnt2, fill=cs["accent"])
                y += int(H * 0.026)

        # ── 상단: title ─────────────────────────────────────────
        title       = cfg.get("title", "RUN")
        fsize_title = int(W * 0.13)
        fnt_title   = _load_font("inter_black", fsize_title)
        glow_rgb    = cs.get("glow_rgb", (200, 200, 200))

        ty_start  = max(y + int(H * 0.015), int(H * 0.13))
        raw_lines = title.split("\n")
        t_lines: List[str] = []
        for raw in raw_lines:
            t_lines.extend(self._wrap_text(raw, fnt_title, max_w, draw))

        line_gap = fsize_title + int(H * 0.008)
        for li, line_text in enumerate(t_lines):
            bbox = draw.textbbox((0, 0), line_text, font=fnt_title)
            tw   = bbox[2] - bbox[0]
            tx   = (W - tw) // 2
            ty   = ty_start + li * line_gap

            # glow
            for glow_r in [8, 5, 3]:
                glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow_layer)
                gd.text((tx, ty), line_text, font=fnt_title, fill=(*glow_rgb, 55))
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_r))
                img  = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")

            draw = ImageDraw.Draw(img)
            draw.text((tx + 2, ty + 2), line_text, font=fnt_title, fill=(0, 0, 0))
            draw.text((tx, ty),         line_text, font=fnt_title, fill=cs["title"])

        # ── 하단: 구분선 ────────────────────────────────────────
        sep_y = int(H * 0.695)
        draw.line([(MARGIN, sep_y), (W - MARGIN, sep_y)],
                  fill=(180, 180, 200), width=1)

        # ── 하단: km 숫자 ────────────────────────────────────────
        dist_km = cfg.get("distance_km", 0.0)
        if dist_km and float(dist_km) > 0:
            fsize_km = int(W * 0.24)
            fnt_km   = _load_font("inter_black", fsize_km)
            km_str   = f"{float(dist_km):.1f}"
            bbox     = draw.textbbox((0, 0), km_str, font=fnt_km)
            kw       = bbox[2] - bbox[0]

            fsize_unit = int(W * 0.068)
            fnt_unit   = _load_font("inter_semibold", fsize_unit)
            unit_w     = int(draw.textlength("km", font=fnt_unit))
            gap        = int(W * 0.018)
            total_w    = kw + gap + unit_w
            kx         = (W - total_w) // 2
            ky         = int(H * 0.710)

            draw.text((kx + 3, ky + 3), km_str, font=fnt_km, fill=(0, 0, 0))
            draw.text((kx, ky),         km_str, font=fnt_km, fill=cs["title"])

            ux = kx + kw + gap
            uy = ky + fsize_km - fsize_unit - int(H * 0.004)
            draw.text((ux, uy), "km", font=fnt_unit, fill=cs["stat"])

        # ── 하단: DATE / DAY / TIME / PACE 컬럼 ─────────────────
        date_txt = cfg.get("date", "")
        day_txt  = cfg.get("day", "")
        run_time = cfg.get("run_time", "")
        pace_txt = cfg.get("pace", "")

        cols: List[Tuple[str, str]] = []
        if date_txt: cols.append(("DATE", date_txt))
        if day_txt:  cols.append(("DAY",  day_txt))
        if run_time: cols.append(("TIME", run_time))
        if pace_txt: cols.append(("PACE", pace_txt))

        if cols:
            row_y     = int(H * 0.872)
            fsize_lbl = int(W * 0.022)
            fnt_lbl   = _load_font("avenir",   fsize_lbl)
            fsize_val = int(W * 0.050)
            fnt_val   = _load_font("din_bold", fsize_val)

            col_w = (W - MARGIN * 2) // len(cols)
            for i, (label, value) in enumerate(cols):
                cx = MARGIN + col_w * i + col_w // 2

                lw = draw.textlength(label, font=fnt_lbl)
                draw.text((cx - lw // 2, row_y),
                          label, font=fnt_lbl, fill=cs["accent"])

                vw = draw.textlength(value, font=fnt_val)
                draw.text((cx - vw // 2, row_y + fsize_lbl + int(H * 0.008)),
                          value, font=fnt_val, fill=cs["title"])

            # 컬럼 구분선
            val_bottom = row_y + fsize_lbl + fsize_val + int(H * 0.010)
            for i in range(1, len(cols)):
                sx = MARGIN + col_w * i
                draw.line([(sx, row_y), (sx, val_bottom)],
                          fill=(120, 120, 120), width=1)

        # ── branding ─────────────────────────────────────────────
        draw = self._draw_branding(draw, cfg, cs, W, H)

        return img

    # ── 피드 버전 캔버스 (4:5 커버 크롭) ────────────────────────

    def _build_feed_canvas(
        self,
        frame_rgb: np.ndarray,
        scheme: str,
        color_grade: bool = False,
    ) -> Image.Image:
        """
        4:5 인스타그램 피드용 캔버스 (1080×1350).

        커버 크롭 전략:
          - 사진 비율 > 4:5 (가로가 더 넓음) → 높이 기준 스케일, 양쪽 가운데 크롭
          - 사진 비율 ≤ 4:5 (세로가 더 길거나 같음) → 폭 기준 스케일, 상단만 크롭 (하단 보존)
        그라디언트 확장 없음 — 사진만 크롭해서 캔버스 채움.
        """
        W, H = 1080, 1350   # 4:5

        photo = self._color_grade(frame_rgb, scheme) if color_grade else Image.fromarray(frame_rgb)
        src_w, src_h = photo.size
        src_ratio = src_w / src_h
        tgt_ratio = W / H   # 0.8

        if src_ratio > tgt_ratio:
            # 가로가 더 넓음 → 높이 기준 스케일 후 좌우 가운데 크롭
            scale  = H / src_h
            new_w  = int(src_w * scale)
            scaled = photo.resize((new_w, H), Image.LANCZOS)
            x_off  = (new_w - W) // 2
            canvas = scaled.crop((x_off, 0, x_off + W, H))
        else:
            # 세로가 더 길거나 같음 → 폭 기준 스케일 후 상단만 크롭 (하단 보존)
            scale  = W / src_w
            new_h  = int(src_h * scale)
            scaled = photo.resize((W, new_h), Image.LANCZOS)
            if new_h > H:
                crop_top = new_h - H
                canvas   = scaled.crop((0, crop_top, W, new_h))
            else:
                # 이미 충분히 짧음 → 그대로 사용 (하단 여백 없음)
                canvas = scaled.crop((0, 0, W, new_h))

        # 캔버스 크기가 정확히 W×H인지 확인 (부동소수점 오차 방지)
        if canvas.size != (W, H):
            canvas = canvas.resize((W, H), Image.LANCZOS)

        return canvas

    # ── 색감 조정 (스탯 레이아웃 전용) ───────────────────────────

    def _color_grade(self, frame_rgb: np.ndarray, scheme: str) -> Image.Image:
        cs = _SCHEMES.get(scheme, _SCHEMES["warm"])
        img = Image.fromarray(frame_rgb)
        img = Enhance.Brightness(img).enhance(cs["brightness"])
        img = Enhance.Contrast(img).enhance(cs["contrast"])
        img = Enhance.Color(img).enhance(cs["saturation"])
        r, g, b = img.split()
        r = r.point(lambda x: min(255, int(x * cs["r_mult"])))
        g = g.point(lambda x: min(255, int(x * cs["g_mult"])))
        b = b.point(lambda x: min(255, int(x * cs["b_mult"])))
        return Image.merge("RGB", (r, g, b))

    # ── 그라디언트 오버레이 ───────────────────────────────────────

    def _add_gradients(
        self,
        img: Image.Image,
        scheme: str,
        photo_zone_h: Optional[int] = None,
    ) -> Image.Image:
        """
        어두운 그라디언트 오버레이 추가.

        photo_zone_h 지정 시 (이벤트 레이아웃):
          - 상단: 검정→투명 (제목 가독성)
          - 포토존 하단 15%: 투명→어둠 (데이터존과 자연스러운 블렌드)
          - 데이터존: 별도 그라디언트로 이미 처리됨 → 건드리지 않음

        photo_zone_h 없음 (스탯 레이아웃):
          - 상단: 검정→투명 (상위 48%)
          - 하단: 투명→검정 (하위 60%)
        """
        W, H = img.size
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        # 상단 그라디언트 (공통)
        top_h = int(H * 0.45) if photo_zone_h else int(H * 0.48)
        for y in range(top_h):
            alpha = int(185 * (1 - y / top_h) ** 1.5)
            draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

        if photo_zone_h:
            # 포토존 하단 → 데이터존 블렌드
            blend_h     = int(photo_zone_h * 0.18)
            blend_start = photo_zone_h - blend_h
            for y in range(blend_h):
                alpha = int(160 * (y / blend_h) ** 1.3)
                draw.line(
                    [(0, blend_start + y), (W, blend_start + y)],
                    fill=(0, 0, 0, alpha),
                )
        else:
            # 하단 그라디언트
            bot_h     = int(H * 0.60)
            bot_start = H - bot_h
            for y in range(bot_h):
                alpha = int(225 * (y / bot_h) ** 1.3)
                draw.line(
                    [(0, bot_start + y), (W, bot_start + y)],
                    fill=(0, 0, 0, alpha),
                )

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        return img.convert("RGB")

    # ── 텍스트 줄바꿈 유틸리티 ───────────────────────────────────

    @staticmethod
    def _wrap_text(text: str, font: ImageFont.FreeTypeFont,
                   max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
        """
        텍스트가 max_width를 초과하면 띄어쓰기 기준으로 자동 줄바꿈.
        반환: 줄 문자열 리스트
        """
        if draw.textlength(text, font=font) <= max_width:
            return [text]

        words = text.split()
        lines, current = [], ""
        for word in words:
            test = f"{current} {word}".strip()
            if draw.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [text]

    # ── 텍스트 전체 레이아웃 ──────────────────────────────────────

    def _draw_overlay(
        self,
        img:          Image.Image,
        cfg:          Dict,
        scheme:       str,
        data_zone_y:  Optional[int] = None,
        poster_mode:  str = "photo",
    ) -> Image.Image:
        """
        텍스트/오버레이 전체 렌더링.

        poster_mode="feed":
          - 제목: 캔버스 위 8% 시작, 폰트 작게 (전체 40% 이내)
          - 날짜: 제목 직하
          - 하단: 스탯 블록 (km 수)

        poster_mode="photo" + data_zone_y 있음 (그라디언트 확장):
          - 제목: 10% 시작
          - 이벤트 블록: data_zone_y 이후

        poster_mode="photo" + data_zone_y 없음 (스탯):
          - 기존 배치 유지
        """
        W, H = img.size
        cs = _SCHEMES.get(scheme, _SCHEMES["warm"])
        MARGIN = int(W * 0.08)

        # ① 상단: 위치 정보
        img, draw = self._draw_location_header(img, cfg, cs, W, H)

        # ② 메인 타이틀
        if poster_mode == "feed":
            ty_ratio = 0.08
        elif data_zone_y:
            ty_ratio = 0.10
        else:
            ty_ratio = 0.20

        img, draw, title_bottom_y = self._draw_title(
            img, draw, cfg, cs, W, H,
            ty_ratio=ty_ratio,
            poster_mode=poster_mode,
        )

        # ③ 날짜 (스탯/피드 레이아웃용)
        if poster_mode == "feed" or not data_zone_y:
            draw = self._draw_date(draw, cfg, cs, W, H, title_bottom_y)

        # ④ 하단 스탯 / 이벤트 블록
        if data_zone_y and poster_mode == "photo":
            draw = self._draw_event_info_block(
                draw, cfg, cs, W, H, MARGIN, data_zone_y=data_zone_y
            )
        else:
            draw = self._draw_stats(draw, cfg, cs, W, H, MARGIN)

        # ⑤ 브랜딩 라벨 (맨 아래)
        draw = self._draw_branding(draw, cfg, cs, W, H)

        return img

    def _draw_location_header(self, img, cfg, cs, W, H):
        draw   = ImageDraw.Draw(img)
        MARGIN = int(W * 0.08)
        max_w  = W - MARGIN * 2

        location  = cfg.get("location", "")
        subloc    = cfg.get("sublocation", "")
        run_clock = cfg.get("time", "")

        y = int(H * 0.048)
        if location:
            fnt   = _load_font("inter_semibold", int(W * 0.034))
            lines = self._wrap_text(location, fnt, max_w, draw)
            for line in lines:
                lw = draw.textlength(line, font=fnt)
                draw.text(((W - lw) // 2, y), line, font=fnt, fill=cs["title"])
                y += int(W * 0.038)

        if subloc or run_clock:
            sub_txt = f"{subloc}  ·  {run_clock}" if subloc and run_clock else (subloc or run_clock)
            fnt2  = _load_font("inter_regular", int(W * 0.024))
            lines2 = self._wrap_text(sub_txt, fnt2, max_w, draw)
            for line in lines2:
                sw = draw.textlength(line, font=fnt2)
                draw.text(((W - sw) // 2, y), line, font=fnt2, fill=cs["accent"])
                y += int(W * 0.028)
        return img, draw

    def _draw_title(self, img, draw, cfg, cs, W, H,
                    ty_ratio: float = 0.20, poster_mode: str = "photo"):
        title      = cfg.get("title", "RUN")
        MARGIN     = int(W * 0.08)
        max_w      = W - MARGIN * 2
        # 피드: 폰트 작게 (전체 높이의 40% 이내 확보)
        # 사진: 기존 크기
        fsize      = int(W * 0.09) if poster_mode == "feed" else int(W * 0.13)
        fnt_title  = _load_font("inter_black", fsize)
        glow_rgb   = cs.get("glow_rgb", (200, 200, 200))
        ty_start   = int(H * ty_ratio)

        raw_lines  = title.split("\n")
        lines: List[str] = []
        for raw in raw_lines:
            lines.extend(self._wrap_text(raw, fnt_title, max_w, draw))

        line_gap = fsize + int(H * 0.008)

        for li, line_text in enumerate(lines):
            bbox = draw.textbbox((0, 0), line_text, font=fnt_title)
            tw = bbox[2] - bbox[0]
            tx = (W - tw) // 2
            ty = ty_start + li * line_gap

            # 글로우 레이어
            for glow_r in [8, 5, 3]:
                glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow_layer)
                gd.text((tx, ty), line_text, font=fnt_title,
                        fill=(*glow_rgb, 55))
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_r))
                img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")

            draw = ImageDraw.Draw(img)
            draw.text((tx + 2, ty + 2), line_text, font=fnt_title,
                      fill=(0, 0, 0))
            draw.text((tx, ty), line_text, font=fnt_title, fill=cs["title"])

        title_bottom_y = ty_start + len(lines) * line_gap
        return img, draw, title_bottom_y

    def _draw_date(self, draw, cfg, cs, W, H, title_bottom_y):
        date_txt = cfg.get("date", "")
        if not date_txt:
            return draw
        fnt = _load_font("din_alt", int(W * 0.030))
        dw = draw.textlength(date_txt, font=fnt)
        draw.text(((W - dw) // 2, title_bottom_y + int(H * 0.010)),
                  date_txt, font=fnt, fill=cs["accent"])
        return draw

    def _draw_stats(self, draw, cfg, cs, W, H, MARGIN):
        dist_km  = cfg.get("distance_km", 0.0)
        run_time = cfg.get("run_time", "")
        pace     = cfg.get("pace", "")

        # ── no-stats 모드: 기존 레이아웃에서도 이벤트 블록으로 대체 ──
        has_stats = (dist_km and float(dist_km) > 0) or run_time or pace
        if not has_stats:
            return self._draw_event_info_block(draw, cfg, cs, W, H, MARGIN)

        # 구분선
        line_y = int(H * 0.72)
        draw.line([(MARGIN, line_y), (W - MARGIN, line_y)],
                  fill=(200, 200, 200), width=1)

        # 거리 (대형 Inter Black)
        fsize_dist = int(W * 0.22)
        fnt_dist   = _load_font("inter_black", fsize_dist)
        dist_str   = f"{dist_km:.1f}" if isinstance(dist_km, float) else str(dist_km)
        bbox = draw.textbbox((0, 0), dist_str, font=fnt_dist)
        dw   = bbox[2] - bbox[0]
        dx   = (W - dw) // 2
        dy   = int(H * 0.73)
        draw.text((dx + 4, dy + 4), dist_str, font=fnt_dist, fill=(0, 0, 0))
        draw.text((dx, dy), dist_str, font=fnt_dist, fill=cs["title"])

        # "km" 단위
        fsize_unit = int(W * 0.062)
        fnt_unit   = _load_font("inter_semibold", fsize_unit)
        ux = dx + dw + int(W * 0.018)
        uy = dy + fsize_dist - fsize_unit - int(H * 0.008)
        draw.text((ux, uy), "km", font=fnt_unit, fill=cs["stat"])

        # 시간 + 페이스 (나란히 or 단독)
        y_sub = dy + fsize_dist + int(H * 0.010)
        fsize_sub = int(W * 0.052)
        fnt_sub   = _load_font("din_bold", fsize_sub)

        if run_time and pace:
            cx = W // 4
            tw = draw.textlength(run_time, font=fnt_sub)
            draw.text((cx - tw // 2, y_sub), run_time, font=fnt_sub, fill=cs["title"])
            draw.line([(W // 2, y_sub + int(fsize_sub * 0.1)),
                       (W // 2, y_sub + int(fsize_sub * 0.9))],
                      fill=(130, 130, 130), width=1)
            cx2 = W * 3 // 4
            pw  = draw.textlength(pace, font=fnt_sub)
            draw.text((cx2 - pw // 2, y_sub), pace, font=fnt_sub, fill=cs["stat"])
        elif run_time:
            tw = draw.textlength(run_time, font=fnt_sub)
            draw.text(((W - tw) // 2, y_sub), run_time, font=fnt_sub, fill=cs["title"])
        elif pace:
            pw = draw.textlength(pace, font=fnt_sub)
            draw.text(((W - pw) // 2, y_sub), pace, font=fnt_sub, fill=cs["stat"])

        return draw

    def _draw_event_info_block(
        self,
        draw,
        cfg,
        cs,
        W: int,
        H: int,
        MARGIN: int,
        data_zone_y: Optional[int] = None,
    ):
        """
        이벤트 정보(날짜·시간·장소)만 표시하는 하단 블록.

        data_zone_y 지정 시 (이벤트 레이아웃):
          - data_zone_y 를 기준으로 내부 비율로 배치
          - 날짜 대형 / 시간·장소 중소형

        data_zone_y 없음 (스탯 레이아웃 fallback):
          - 기존 H 비율 기반 배치
        """
        max_w = W - MARGIN * 2

        if data_zone_y is not None:
            # ── 이벤트 레이아웃 배치 ──────────────────────────
            data_h   = H - data_zone_y
            sep_y    = data_zone_y + int(data_h * 0.05)
            date_y   = data_zone_y + int(data_h * 0.14)
            time_y   = data_zone_y + int(data_h * 0.60)
        else:
            # ── 스탯 레이아웃 fallback 배치 ───────────────────
            sep_y  = int(H * 0.72)
            date_y = int(H * 0.735)
            time_y = int(H * 0.855)
            data_h = H - int(H * 0.72)

        # 구분선
        draw.line(
            [(MARGIN, sep_y), (W - MARGIN, sep_y)],
            fill=(180, 180, 200), width=1,
        )

        # ── 날짜 (대형 Futura) ────────────────────────────────
        date_txt = cfg.get("date", "")
        if date_txt:
            fsize = int(W * 0.12)
            fnt   = _load_font("futura", fsize)
            lines = self._wrap_text(date_txt, fnt, max_w, draw)
            y     = date_y
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=fnt)
                tw   = bbox[2] - bbox[0]
                draw.text(((W - tw) // 2 + 2, y + 2), line,
                          font=fnt, fill=(0, 0, 0))
                draw.text(((W - tw) // 2, y), line,
                          font=fnt, fill=cs["title"])
                y += fsize + int(H * 0.006)

        # ── 시간 (중간 크기 Avenir) ────────────────────────────
        time_txt = cfg.get("time", "")
        fnt_time = _load_font("avenir", int(W * 0.046))
        y_sub    = time_y

        if time_txt:
            lines = self._wrap_text(time_txt, fnt_time, max_w, draw)
            for line in lines:
                tw = draw.textlength(line, font=fnt_time)
                draw.text(((W - tw) // 2, y_sub), line,
                          font=fnt_time, fill=cs["stat"])
                y_sub += int(W * 0.054)

        # ── 장소 (소형 Avenir) ────────────────────────────────
        loc_txt = cfg.get("location", cfg.get("sublocation", ""))
        if loc_txt:
            fnt_loc = _load_font("avenir", int(W * 0.031))
            lines   = self._wrap_text(loc_txt, fnt_loc, max_w, draw)
            for line in lines:
                tw = draw.textlength(line, font=fnt_loc)
                draw.text(((W - tw) // 2, y_sub), line,
                          font=fnt_loc, fill=cs["branding"])
                y_sub += int(W * 0.036)

        return draw

    def _draw_branding(self, draw, cfg, cs, W, H):
        branding = cfg.get("branding", "")
        if not branding:
            loc  = cfg.get("location", "")
            date = cfg.get("date", "")
            branding = f"{loc}  /  {date}" if loc and date else (loc or date)
        if not branding:
            return draw
        MARGIN = int(W * 0.08)
        max_w  = W - MARGIN * 2
        fnt    = _load_font("avenir", int(W * 0.024))
        lines  = self._wrap_text(branding, fnt, max_w, draw)
        y      = int(H * 0.940)
        for line in lines:
            lw = draw.textlength(line, font=fnt)
            draw.text(((W - lw) // 2, y), line, font=fnt, fill=cs["branding"])
            y += int(W * 0.028)
        return draw


# ════════════════════════════════════════════════════════════════════
# 베스트 포스터 프레임 선택
# ════════════════════════════════════════════════════════════════════

def find_best_poster_frame(
    video_path: str,
    candidate_times: List[float],
    model_path: str = "models/pose_landmarker_full.task",
    target_size_ratio: float = 0.33,   # 러너가 화면 높이의 몇 배가 이상적인지
    verbose: bool = True,
) -> float:
    """
    후보 프레임 중 베스트컷 조건에 가장 맞는 프레임의 타임스탬프 반환.

    베스트컷 조건:
      1. 러너가 화면 중앙에 위치 (x, y 모두 화면 중심에 가까울수록 좋음)
      2. 러너 크기가 화면 높이의 약 1/3 (target_size_ratio)

    점수 = 0.5 * center_score + 0.5 * size_score
      - center_score: 1 - (|cx - 0.5| + |cy - 0.5|) * 2  (범위 0~1)
      - size_score:   1 - |person_h_ratio - target| * 3   (범위 0~1)

    MediaPipe 실패 또는 포즈 미감지 프레임은 제외.
    모든 프레임에서 감지 실패 시 candidate_times[0] 반환.

    Args:
        video_path:        영상 경로 (rotation-fixed)
        candidate_times:   후보 타임스탬프 목록 (초)
        model_path:        MediaPipe PoseLandmarker 모델 경로
        target_size_ratio: 이상적인 러너 높이 비율 (기본 0.33 = 화면 1/3)
        verbose:           로그 출력 여부

    Returns:
        최적 타임스탬프 (초)
    """
    if not candidate_times:
        return 0.0

    # ── 1순위: MediaPipe PoseLandmarker ──────────────────────────────
    if Path(model_path).exists():
        result = _best_frame_mediapipe(
            video_path, candidate_times, model_path, target_size_ratio, verbose
        )
        if result is not None:
            return result

    # ── 2순위: OpenCV HOG 사람 감지기 (MediaPipe 없을 때 자동 fallback) ─
    if verbose:
        print("  [BestFrame] HOG 사람 감지기로 베스트컷 선택 중...")
    result = _best_frame_hog(video_path, candidate_times, verbose)
    if result is not None:
        return result

    # ── 최후 fallback: 영상 중간 지점 ────────────────────────────────
    mid = candidate_times[len(candidate_times) // 2]
    if verbose:
        print(f"  [BestFrame] 감지 실패 → 중간 프레임 {mid:.2f}s 사용")
    return mid


def find_top_poster_frames(
    video_path: str,
    candidate_times: List[float],
    top_n: int = 3,
    model_path: str = "models/pose_landmarker_full.task",
    target_size_ratio: float = 0.65,
    verbose: bool = True,
) -> List[float]:
    """
    후보 프레임 중 베스트컷 조건 상위 N개 타임스탬프 반환.

    MediaPipe로 각 후보를 스코어링 → 상위 top_n개 반환.
    서로 최소 0.5초 이상 간격이 있는 프레임만 선택.
    MediaPipe 실패 시 candidate_times 앞에서 top_n개 반환.
    """
    if not candidate_times:
        return []

    if Path(model_path).exists():
        scored = _score_frames_mediapipe(
            video_path, candidate_times, model_path, target_size_ratio, verbose
        )
        if scored:
            # 점수 내림차순 정렬, 최소 0.5초 간격 보장
            scored.sort(key=lambda x: x[1], reverse=True)
            selected: List[float] = []
            for t, score in scored:
                if all(abs(t - s) >= 0.5 for s in selected):
                    selected.append(t)
                    if len(selected) >= top_n:
                        break
            if selected:
                return sorted(selected)

    # fallback: 앞에서 top_n개
    return sorted(candidate_times[:top_n])


def _score_frames_mediapipe(
    video_path: str,
    candidate_times: List[float],
    model_path: str,
    target_size_ratio: float,
    verbose: bool,
) -> List[Tuple[float, float]]:
    """모든 후보 프레임을 MediaPipe로 스코어링 → [(timestamp, score), ...]"""
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker, PoseLandmarkerOptions, RunningMode,
        )
    except ImportError:
        return []

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.25,
        min_pose_presence_confidence=0.25,
    )
    cap = cv2.VideoCapture(video_path)
    scored: List[Tuple[float, float]] = []

    with PoseLandmarker.create_from_options(options) as landmarker:
        for t in candidate_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame_bgr = cap.read()
            if not ret:
                continue
            detect_frame = cv2.convertScaleAbs(frame_bgr, alpha=2.5, beta=40)
            rgb    = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            try:
                res = landmarker.detect(mp_img)
            except Exception:
                continue
            if not res.pose_landmarks:
                continue
            lms = res.pose_landmarks[0]
            xs, ys = [lm.x for lm in lms], [lm.y for lm in lms]
            cx, cy, ph = sum(xs)/len(xs), sum(ys)/len(ys), max(ys)-min(ys)
            center_score = max(0.0, 1.0 - (abs(cx-0.5) + abs(cy-0.5)) * 2.0)
            size_score   = max(0.0, 1.0 - abs(ph - target_size_ratio) * 2.5)
            total        = 0.35 * center_score + 0.65 * size_score
            scored.append((t, total))
            if verbose:
                print(f"  [TopFrames·MP] {t:.2f}s  size={ph:.2f}  score={total:.3f}")

    cap.release()
    return scored


def _best_frame_mediapipe(
    video_path: str,
    candidate_times: List[float],
    model_path: str,
    target_size_ratio: float,
    verbose: bool,
) -> Optional[float]:
    """MediaPipe PoseLandmarker로 베스트 프레임 선택. 실패 시 None 반환."""
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker, PoseLandmarkerOptions, RunningMode,
        )
    except ImportError:
        if verbose:
            print("  [BestFrame] MediaPipe 없음 → HOG fallback")
        return None

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.25,
        min_pose_presence_confidence=0.25,
    )

    cap = cv2.VideoCapture(video_path)
    best_t, best_score = candidate_times[0], -1.0
    scored = []

    with PoseLandmarker.create_from_options(options) as landmarker:
        for t in candidate_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame_bgr = cap.read()
            if not ret:
                continue

            detect_frame = cv2.convertScaleAbs(frame_bgr, alpha=2.5, beta=40)
            rgb    = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            try:
                res = landmarker.detect(mp_img)
            except Exception:
                continue

            if not res.pose_landmarks:
                continue

            lms = res.pose_landmarks[0]
            xs  = [lm.x for lm in lms]
            ys  = [lm.y for lm in lms]
            cx  = sum(xs) / len(xs)
            cy  = sum(ys) / len(ys)
            ph  = max(ys) - min(ys)

            # 포스터 기준: 러너가 크고(0.65↑) 화면 중앙에 가까울수록 고점
            center_score = max(0.0, 1.0 - (abs(cx - 0.5) + abs(cy - 0.5)) * 2.0)
            size_score   = max(0.0, 1.0 - abs(ph - target_size_ratio) * 2.5)
            total        = 0.35 * center_score + 0.65 * size_score  # 크기 우선

            scored.append((t, total))
            if verbose:
                print(f"  [BestFrame·MP] {t:.2f}s  center=({cx:.2f},{cy:.2f})  "
                      f"size={ph:.2f}  score={total:.3f}")
            if total > best_score:
                best_score, best_t = total, t

    cap.release()

    if not scored:
        return None
    if verbose:
        print(f"  [BestFrame·MP] 선택: {best_t:.2f}s  (score={best_score:.3f})")
    return best_t


def _best_frame_hog(
    video_path: str,
    candidate_times: List[float],
    verbose: bool,
) -> Optional[float]:
    """
    OpenCV HOG 사람 감지기로 베스트 포스터 프레임 선택.

    채점 기준:
      - 감지된 사람 박스가 클수록 (화면 대비 높이) 고점 → 러너가 크게 나온 프레임
      - 감지된 사람이 화면 중앙에 가까울수록 고점
      - 크기 가중치(0.70) > 중심 가중치(0.30)
    """
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    cap = cv2.VideoCapture(video_path)
    best_t, best_score = None, -1.0

    for t in candidate_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame_bgr = cap.read()
        if not ret:
            continue

        fh, fw = frame_bgr.shape[:2]

        # HOG는 작은 이미지에서 더 안정적 → 최대 640px로 리사이즈
        scale = min(1.0, 640 / max(fw, fh))
        small = cv2.resize(frame_bgr, (int(fw * scale), int(fh * scale)))

        rects, weights = hog.detectMultiScale(
            small,
            winStride=(6, 6),
            padding=(8, 8),
            scale=1.05,
        )

        if len(rects) == 0:
            if verbose:
                print(f"  [BestFrame·HOG] {t:.2f}s → 사람 미감지")
            continue

        # 가장 신뢰도 높은 검출 박스 선택
        best_idx  = int(np.argmax(weights))
        x, y, rw, rh = rects[best_idx]

        # 원본 해상도 기준으로 환산
        cx_ratio   = (x + rw / 2) / small.shape[1]
        cy_ratio   = (y + rh / 2) / small.shape[0]
        size_ratio = rh / small.shape[0]   # 프레임 높이 대비 사람 높이

        # 크기 점수: 0.6 근방이 이상적 (너무 작거나 꽉 차면 감점)
        size_score   = max(0.0, 1.0 - abs(size_ratio - 0.60) * 2.0)
        # 중심 점수: 화면 중앙에 가까울수록
        center_score = max(0.0, 1.0 - (abs(cx_ratio - 0.5) + abs(cy_ratio - 0.5)) * 2.0)

        total = 0.30 * center_score + 0.70 * size_score

        if verbose:
            print(f"  [BestFrame·HOG] {t:.2f}s  "
                  f"center=({cx_ratio:.2f},{cy_ratio:.2f})  "
                  f"size={size_ratio:.2f}  score={total:.3f}")

        if total > best_score:
            best_score, best_t = total, t

    cap.release()

    if best_t is None:
        return None
    if verbose:
        print(f"  [BestFrame·HOG] 선택: {best_t:.2f}s  (score={best_score:.3f})")
    return best_t
