"""
TemplateExecutor — 템플릿 기반 영상 자동 편집기

searchingmodule이 생성한 EditInstruction JSON을 받아
실제 영상을 템플릿 주문대로 편집.

흐름:
  [EditInstruction JSON]
        ↓
  [TemplateExecutor.execute()]
        ↓  ratio → 실제 초 계산
        ↓  세그먼트별 클립 추출 + 속도 변환
        ↓  이펙트 적용 (줌인, 비네팅)
        ↓  컬러 그레이딩
        ↓  텍스트/카운터 오버레이 (PIL)
        ↓
  [최종 MP4 출력]

searchingmodule EditorAdapter (방법 B) 연결용:
  def apply_template(instruction, input_video, output_video) -> bool
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from moviepy import VideoFileClip, ImageClip, concatenate_videoclips


# ────────────────────────────────────────────────────────────────
# 메인 실행기
# ────────────────────────────────────────────────────────────────

class TemplateExecutor:
    """
    EditInstruction → 실제 영상 편집 실행기

    searchingmodule의 EditInstruction JSON 포맷을 읽어
    기존 video-editor 기술로 영상을 편집.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def execute(
        self,
        instruction: Dict,
        input_video: str,
        output_video: str
    ) -> bool:
        """
        편집 지시서대로 영상 편집

        Args:
            instruction: EditInstruction dict (searchingmodule 포맷)
            input_video: 원본 영상 경로
            output_video: 출력 영상 경로

        Returns:
            True if success
        """
        self._log(f"=== TemplateExecutor 시작 ===")
        self._log(f"템플릿: {instruction.get('template_id', 'unknown')}")
        self._log(f"원본: {input_video}")

        # 출력 디렉토리
        Path(output_video).parent.mkdir(parents=True, exist_ok=True)

        # ── 1. 원본 영상 로드 ──────────────────────────────────────
        self._log("[1/5] 원본 영상 로드...")
        source = self._load_video(input_video)
        src_duration = source.duration
        self._log(f"    원본 길이: {src_duration:.1f}초, 크기: {source.w}x{source.h}")

        try:
            # ── 1b. 인물 확대 크롭 (meta.crop_zoom > 1.0) ─────────
            crop_zoom = instruction.get("meta", {}).get("crop_zoom", 1.0)
            if crop_zoom > 1.01:
                source = self._center_crop_zoom(source, crop_zoom)
                self._log(f"    크롭 줌 {crop_zoom:.1f}x 적용 (인물 확대)")

            # ── 2. 세그먼트별 클립 생성 ───────────────────────────
            self._log("[2/5] 세그먼트 편집...")
            clips = self._build_segments(source, instruction, src_duration)

            # ── 3. 클립 연결 ──────────────────────────────────────
            self._log("[3/5] 클립 연결...")
            if len(clips) == 1:
                final = clips[0]
            else:
                final = concatenate_videoclips(clips, method="compose")

            # ── 4. 컬러 그레이딩 ──────────────────────────────────
            color_config = instruction.get("color_grade", {})
            params = color_config.get("adjustment_params", {})
            # 모든 파라미터가 0이면 프레임 변환 없이 완전 스킵
            _needs_grade = any(v != 0 for v in params.values()) if params else False
            if _needs_grade:
                self._log("[4/5] 컬러 그레이딩...")
                final = self._apply_color_grade(final, color_config)
            else:
                self._log("[4/5] 컬러 그레이딩 (스킵 — 파라미터 전부 0)")

            # ── 5. 오버레이 렌더 (PIL) ────────────────────────────
            overlays = instruction.get("overlays", [])
            target_duration = instruction["meta"]["target_duration_seconds"]
            overall_tone = instruction.get("color_grade", {}).get("overall_tone", "neutral")

            if overlays:
                self._log(f"[5/5] 오버레이 {len(overlays)}개 적용...")
                final = self._apply_overlays(final, overlays, target_duration, overall_tone)
            else:
                self._log("[5/5] 오버레이 없음")

            # ── 저장 ─────────────────────────────────────────────
            self._log(f"저장 중: {output_video}")
            final.write_videofile(
                output_video,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                preset="slow",          # medium → slow: 동일 파일크기에서 화질 ↑
                ffmpeg_params=[
                    "-crf", "16",        # 기본값(23) 대신 16 → 고화질 (낮을수록 좋음)
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                ],
                threads=4,
                logger=None
            )

            self._log(f"=== 완료: {output_video} ===")
            return True

        finally:
            source.close()

    def execute_from_file(
        self,
        instruction_path: str,
        input_video: str,
        output_video: str
    ) -> bool:
        """JSON 파일에서 로드해서 실행"""
        with open(instruction_path, encoding="utf-8") as f:
            instruction = json.load(f)
        return self.execute(instruction, input_video, output_video)

    # ── 세그먼트 빌더 ────────────────────────────────────────────

    def _build_segments(
        self,
        source: VideoFileClip,
        instruction: Dict,
        src_duration: float
    ) -> List[VideoFileClip]:
        """
        타임라인 세그먼트 → 실제 클립 리스트

        핵심 계산:
          - 각 세그먼트의 output_duration = ratio * target_duration
          - speed < 1.0 (슬로모션): source에서 더 적은 분량을 가져와 늘림
            source_portion = output_duration * speed
          - source 포지션은 순차적으로 누적
        """
        segments = instruction["timeline"]["segments"]
        speed_changes = instruction.get("speed_changes", [])
        effects = instruction.get("effects", [])
        target_duration = instruction["meta"]["target_duration_seconds"]

        # speed_changes를 ratio 범위 → speed 딕셔너리로 변환
        speed_map = {
            (sc["start_ratio"], sc["end_ratio"]): sc["speed"]
            for sc in speed_changes
        }

        clips = []
        source_pos = 0.0  # 소스 영상에서 현재 위치 (순차 소비용)

        for seg in segments:
            sr = seg["start_ratio"]
            er = seg["end_ratio"]

            # ── source_start_sec / source_end_sec 직접 지정 지원 ────
            # 자세 분석처럼 특정 타임스탬프로 점프해야 할 때 사용.
            # 지정된 경우: ratio/speed_map 무시하고 해당 구간 직접 사용.
            has_explicit_src = (
                "source_start_sec" in seg and "source_end_sec" in seg
            )
            if has_explicit_src:
                seg_speed = seg.get("speed", 1.0)
                src_start = float(seg["source_start_sec"])
                src_end   = min(float(seg["source_end_sec"]), src_duration)
                # source_pos를 최댓값으로 갱신 (이후 순차 세그먼트 대비)
                source_pos = max(source_pos, src_end)
                output_dur = (src_end - src_start) / max(seg_speed, 0.001)
            else:
                seg_speed  = self._get_segment_speed(sr, er, speed_map, seg.get("speed", 1.0))
                output_dur = (er - sr) * target_duration
                source_needed = output_dur * seg_speed
                src_start = source_pos
                src_end   = min(source_pos + source_needed, src_duration)
                source_pos = src_end

            # ── freeze 세그먼트: 소스 길이가 0이므로 duration 체크 전에 먼저 처리 ──
            if seg.get("type") == "freeze":
                freeze_dur = float(seg.get("freeze_duration", 2.0))
                frame_t    = max(0.0, min(src_start, src_duration - 0.001))
                frame      = source.get_frame(frame_t)
                clip       = ImageClip(frame, duration=freeze_dur)
                clips.append(clip)
                self._log(f"    [{seg['id']}] freeze: "
                          f"t={frame_t:.3f}s → hold {freeze_dur:.2f}s")
                continue

            actual_src_dur = src_end - src_start
            if actual_src_dur < 0.05:
                self._log(f"    [{seg['id']}] 소스 부족, 스킵")
                continue

            self._log(f"    [{seg['id']}] {seg['type']}: "
                      f"src={src_start:.2f}~{src_end:.2f}s, "
                      f"speed={seg_speed:.2f}x, "
                      f"output={output_dur:.2f}s"
                      + (" [explicit]" if has_explicit_src else ""))

            # 클립 추출
            clip = source.subclipped(src_start, src_end)

            # 슬로모션 (0.35x 등)
            if abs(seg_speed - 1.0) > 0.01:
                clip = clip.with_speed_scaled(seg_speed)

            # 세그먼트에 걸친 이펙트 적용
            seg_effects = [
                eff for eff in effects
                if eff["start_ratio"] >= sr - 0.01 and eff["end_ratio"] <= er + 0.01
                and eff["type"] != "vignette"  # 비네팅은 전체에 적용
            ]
            for eff in seg_effects:
                clip = self._apply_effect_to_clip(clip, eff)

            clips.append(clip)

        if not clips:
            raise ValueError("생성된 클립이 없습니다 — 소스 영상이 너무 짧습니다")

        return clips

    def _get_segment_speed(
        self,
        sr: float,
        er: float,
        speed_map: Dict,
        default: float = 1.0
    ) -> float:
        """세그먼트 ratio 범위에 해당하는 speed 찾기"""
        for (map_sr, map_er), speed in speed_map.items():
            # 범위가 겹치면 적용
            if abs(map_sr - sr) < 0.05 and abs(map_er - er) < 0.05:
                return speed
        return default

    # ── 이펙트 ───────────────────────────────────────────────────

    def _apply_effect_to_clip(self, clip: VideoFileClip, effect: Dict) -> VideoFileClip:
        """단일 이펙트 적용"""
        eff_type = effect.get("type", "")
        intensity = effect.get("intensity", 0.3)

        if eff_type == "zoom_in":
            return self._zoom(clip, 1.0, 1.0 + intensity)
        elif eff_type == "zoom_out":
            return self._zoom(clip, 1.0 + intensity, 1.0)
        elif eff_type == "shake":
            return self._shake(clip, intensity * 8)
        else:
            return clip

    def _center_crop_zoom(self, clip: VideoFileClip, factor: float) -> VideoFileClip:
        """
        중앙 크롭 줌 — 원본 해상도를 유지하면서 factor 배율만큼 인물 확대.

        factor=1.3 → 중앙 77% 영역(1/1.3)을 원본 크기로 업스케일.
        pose analysis 영상처럼 인물이 작을 때 사용.
        """
        w, h = clip.w, clip.h
        crop_w = int(w / factor)
        crop_h = int(h / factor)
        x0 = (w - crop_w) // 2
        y0 = (h - crop_h) // 2

        def do_crop(frame):
            cropped = frame[y0:y0 + crop_h, x0:x0 + crop_w]
            return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LANCZOS4)

        return clip.image_transform(do_crop)

    def _zoom(self, clip: VideoFileClip, start_scale: float, end_scale: float) -> VideoFileClip:
        """점진적 줌 이펙트"""
        def zoom_frame(get_frame, t):
            frame = get_frame(t)
            prog = t / max(clip.duration, 0.001)
            scale = start_scale + (end_scale - start_scale) * prog
            if abs(scale - 1.0) < 0.001:
                return frame
            h, w = frame.shape[:2]
            nh, nw = int(h * scale), int(w * scale)
            zoomed = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
            y0 = max(0, (nh - h) // 2)
            x0 = max(0, (nw - w) // 2)
            return zoomed[y0:y0+h, x0:x0+w]
        return clip.transform(zoom_frame, apply_to=["video"])

    def _shake(self, clip: VideoFileClip, intensity: float = 5.0) -> VideoFileClip:
        """카메라 쉐이크"""
        rng = np.random.default_rng(42)
        n = max(1, int(clip.duration * 30))
        offsets = rng.uniform(-intensity, intensity, (n, 2))

        def shake_frame(get_frame, t):
            frame = get_frame(t)
            idx = min(int(t * 30), n - 1)
            dx, dy = offsets[idx]
            h, w = frame.shape[:2]
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            return cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        return clip.transform(shake_frame, apply_to=["video"])

    # ── 컬러 그레이딩 ────────────────────────────────────────────

    def _apply_color_grade(self, clip: VideoFileClip, color_config: Dict) -> VideoFileClip:
        """
        편집 지시서의 adjustment_params + overall_tone + filter_style로 색보정.

        adjustment_params: brightness/contrast/saturation (-100~+100)
        overall_tone: dark / moody / warm / cool / neutral → 비네팅 강도 결정
        filter_style: "film" → 필름틱 색감 (채도↓, 대비↑, 약간 warm)
        has_filter: True면 filter_style 적용
        """
        params        = color_config.get("adjustment_params", {})
        overall_tone  = color_config.get("overall_tone", "neutral")
        has_filter    = color_config.get("has_filter", False)
        filter_style  = color_config.get("filter_style", "")

        brightness = params.get("brightness", 0) / 200.0    # → -0.5~+0.5
        contrast   = 1.0 + params.get("contrast", 0) / 100.0
        saturation = 1.0 + params.get("saturation", 0) / 100.0

        # filter_style: "film" → 필름 룩 추가 보정
        film_sat_adj  = 0.0
        film_con_adj  = 0.0
        film_warm_adj = 0.0
        if has_filter and "film" in filter_style.lower():
            film_sat_adj  = -0.12   # 채도 살짝 낮춤
            film_con_adj  =  0.08   # 대비 살짝 올림
            film_warm_adj =  0.03   # 살짝 warm

        saturation += film_sat_adj
        contrast   += film_con_adj

        # 비네팅 강도: tone에 따라 결정
        vign_strength = {
            "dark":    0.35,
            "moody":   0.28,
            "cool":    0.0,
            "warm":    0.0,
            "neutral": 0.0,
        }.get(overall_tone, 0.10)

        def grade(frame):
            img = frame.astype(np.float32) / 255.0

            if brightness:
                img = img + brightness
            if contrast != 1.0:
                img = (img - 0.5) * contrast + 0.5
            if saturation != 1.0:
                gray = img.mean(axis=2, keepdims=True)
                img  = gray + (img - gray) * saturation
            # 필름 warm
            if film_warm_adj:
                img[:, :, 0] = img[:, :, 0] + film_warm_adj * 0.08  # R↑
                img[:, :, 2] = img[:, :, 2] - film_warm_adj * 0.06  # B↓

            # 비네팅
            if vign_strength > 0:
                h, w = img.shape[:2]
                Y, X = np.ogrid[:h, :w]
                cy, cx = h / 2, w / 2
                dist = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
                vign = 1 - np.clip(dist * vign_strength, 0, vign_strength * 0.85)
                img  = img * vign[:, :, np.newaxis]

            return np.clip(img * 255, 0, 255).astype(np.uint8)

        return clip.image_transform(grade)

    # ── 오버레이 (PIL 텍스트 — Nike Running 스타일) ──────────────

    # Helvetica Neue face index 상수
    _HN = "/System/Library/Fonts/HelveticaNeue.ttc"
    _HN_REGULAR        = 0
    _HN_BOLD           = 1
    _HN_CONDENSED_BOLD = 4
    _HN_ULTRALIGHT     = 5
    _HN_LIGHT          = 7
    _HN_CONDENSED_BLK  = 9   # Condensed Black — 나이키 숫자 스타일
    _HN_MEDIUM         = 10
    _HN_THIN           = 12
    _KO  = "/System/Library/Fonts/AppleSDGothicNeo.ttc"   # 한글 메인 (6굵기)
    # index: 0=Regular 2=Medium 4=SemiBold 6=Bold 8=Light 10=Thin
    _KO_IDX = {
        "thin":     10,
        "light":     8,
        "regular":   0,
        "medium":    2,
        "semibold":  4,
        "bold":      6,
    }

    # 스포츠 전용 폰트 (Impact / DIN Condensed)
    _IMPACT    = "/System/Library/Fonts/Supplemental/Impact.ttf"
    _DIN_COND  = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
    _DIN_ALT   = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
    _AVENIR_CN = "/System/Library/Fonts/Avenir Next Condensed.ttc"

    # 나이키 스타일 컬러 팔레트 (overall_tone 별)
    _NIKE_PALETTE = {
        "dark":    {"title": (255,255,255), "number": (255,255,255), "label": (180,180,180), "accent": (255,200,0)},
        "moody":   {"title": (255,255,255), "number": (255,255,255), "label": (200,200,200), "accent": (255,140,0)},
        "cool":    {"title": (255,255,255), "number": (255,255,255), "label": (160,210,255), "accent": (80,180,255)},
        "warm":    {"title": (255,255,255), "number": (255,255,255), "label": (255,220,160), "accent": (255,160,60)},
        "neutral": {"title": (255,255,255), "number": (255,255,255), "label": (200,200,200), "accent": (255,255,255)},
    }

    def _apply_overlays(
        self,
        clip: VideoFileClip,
        overlays: List[Dict],
        target_duration: float,
        overall_tone: str = "neutral"
    ) -> VideoFileClip:
        """
        Nike Running 스타일 오버레이 렌더러.

        개선 사항:
        - Helvetica Neue Condensed Black(숫자) / Light(레이블) — 나이키 폰트
        - 텍스트 폭이 화면 벗어나면 자동 폰트 크기 축소
        - 활성 오버레이 겹침 자동 감지 후 y 위치 재배치
        - 비디오 밝기 기반 자동 색상 가시성 보정
        - 미해결 플레이스홀더({time} 등) 스킵
        """
        W, H = clip.w, clip.h
        PAD = int(H * 0.03)          # 가장자리 여백 (3%)
        GAP = int(H * 0.015)         # 오버레이 간 최소 여백 (1.5%)
        palette = self._NIKE_PALETTE.get(overall_tone, self._NIKE_PALETTE["neutral"])

        # ── 오버레이 메타데이터 사전 계산 (프레임마다 반복 X) ────
        ov_meta = []
        dummy_draw = ImageDraw.Draw(Image.new("RGBA", (W, H)))
        for ov in overlays:
            ov_start = ov.get("start_seconds", ov["start_ratio"] * target_duration)
            ov_end   = ov.get("end_seconds",   ov["end_ratio"]   * target_duration)
            ov_type  = ov.get("type", "text")
            style    = ov.get("style", {})
            pos_pct  = ov.get("position_pct", {"x": 50, "y": 50})
            weight   = style.get("font_weight", 400)
            size_ratio = style.get("font_size_ratio", 0.05)
            # 비ASCII 문자(한글·기호·특수문자)가 하나라도 있으면 AppleSDGothicNeo 사용.
            # HelveticaNeue는 ASCII/Latin 전용이라 ◀ 같은 기호도 tofu로 깨짐.
            needs_ko_font = any(ord(ch) > 0x7F for ch in ov.get("content", ""))
            base_size  = max(20, int(H * size_ratio))

            # 폰트 선택 (나이키 스타일)
            font = self._nike_font(base_size, ov_type, weight, needs_ko_font)

            # 목표 x/y (화면 퍼센트)
            cx = int(W * pos_pct["x"] / 100)
            cy = int(H * pos_pct["y"] / 100)

            # 색상 선택 (template 색상 → palette 보정)
            raw_color = style.get("color", "#FFFFFF")
            r, g, b = self._smart_color(raw_color, ov_type, palette)

            ov_meta.append({
                "ov": ov, "ov_start": ov_start, "ov_end": ov_end,
                "ov_type": ov_type, "style": style,
                "base_size": base_size, "font": font,
                "cx": cx, "cy": cy,
                "r": r, "g": g, "b": b,
                "needs_ko_font": needs_ko_font, "weight": weight,
            })

        def draw_frame(get_frame, t):
            frame = get_frame(t)
            pil   = Image.fromarray(frame)
            draw  = ImageDraw.Draw(pil)

            # 1. 활성 오버레이 + 콘텐츠 계산
            items = []
            for meta in ov_meta:
                ov = meta["ov"]
                ov_start, ov_end = meta["ov_start"], meta["ov_end"]
                if not (ov_start <= t < ov_end):
                    continue

                content = self._resolve_content(ov, t, ov_start, ov_end)
                if not content:
                    continue

                # color emoji(U+1F000 이상)는 PIL/FreeType이 렌더링 불가 → strip
                content = self._strip_emoji(content)
                if not content:
                    continue

                # 비ASCII 문자가 있으면 AppleSDGothicNeo 사용 (◀ 등 기호도 포함)
                needs_ko_font = any(ord(ch) > 0x7F for ch in content)

                # 카운터 progress 계산 (ease_out)
                counter_prog = None
                if meta["ov_type"] == "counter" and meta["ov"].get("counter_config"):
                    raw_p = (t - ov_start) / max(ov_end - ov_start, 0.001)
                    counter_prog = min(1.0 - (1.0 - min(raw_p, 1.0)) ** 2, 1.0)

                # 카운터: progress에 따라 폰트 크기 pulse (빠를 때 크게 → 느려지면 정상)
                effective_size = meta["base_size"]
                if counter_prog is not None:
                    scale_up = 1.0 + 0.28 * (1.0 - counter_prog)  # 128% → 100%
                    effective_size = int(meta["base_size"] * scale_up)

                font = self._nike_font(effective_size, meta["ov_type"],
                                       meta["weight"], needs_ko_font)

                # 텍스트 폭 측정 → 줄바꿈 우선, 최후 수단만 폰트 축소
                raw_lines = content.split("\n")
                font, line_height, text_w, text_h, lines = self._fit_font(
                    draw, raw_lines, font, effective_size, W, PAD, needs_ko_font,
                    meta["ov_type"], meta["weight"]
                )

                # 페이드 alpha
                fade = 0.35
                alpha_f = min((t - ov_start) / fade, (ov_end - t) / fade, 1.0)
                text_alpha = int(meta["style"].get("opacity", 1.0) * alpha_f * 255)

                items.append({
                    "content": content, "lines": lines,
                    "font": font, "line_height": line_height,
                    "text_w": text_w, "text_h": text_h,
                    "cx": meta["cx"], "cy": meta["cy"],
                    "r": meta["r"], "g": meta["g"], "b": meta["b"],
                    "alpha": text_alpha, "style": meta["style"],
                    "ov_type": meta["ov_type"],
                    "counter_prog": counter_prog,   # None이면 일반 텍스트
                })

            if not items:
                return np.array(pil)

            # 2. 겹침 해소 — y 재배치
            items = self._resolve_overlaps(items, W, H, PAD, GAP)

            # 3. 드로잉
            for item in items:
                self._draw_overlay_item(draw, item, frame, W, H)

            return np.array(pil)

        return clip.transform(draw_frame, apply_to=["video"])

    def _resolve_content(self, ov: Dict, t: float, ov_start: float, ov_end: float) -> str:
        """오버레이 콘텐츠 문자열 계산 (카운터 포함)"""
        content = ov.get("content", "")
        # 카운터 타입
        if ov.get("type") == "counter" and ov.get("counter_config"):
            cfg  = ov["counter_config"]
            prog = (t - ov_start) / max(ov_end - ov_start, 0.001)
            prog = 1 - (1 - prog) ** 2   # ease_out
            val  = cfg["start_value"] + (cfg["end_value"] - cfg["start_value"]) * prog
            dp   = cfg.get("decimal_places", 1)
            unit = cfg.get("unit", "")
            content = f"{val:.{dp}f} {unit}".strip()
        # 미해결 플레이스홀더 스킵 ({time}, {pace} 등)
        import re
        if re.fullmatch(r"\{[^}]+\}", content.strip()):
            return ""
        # 메타 설명 텍스트 스킵 — 소문자로 시작하고 4단어 이상인 영문 문장
        # 예: "running stats card with multiple data fields", "Garmin app screen showing..."
        words = content.strip().split()
        if (len(words) >= 4
                and content.strip()[0].islower()
                and not any('\uAC00' <= ch <= '\uD7A3' for ch in content)):
            return ""
        return content

    @staticmethod
    def _strip_emoji(text: str) -> str:
        """PIL/FreeType이 렌더링 불가한 color emoji 제거 (U+1F000 이상).
        ◀ ▶ → 등 일반 기호(U+2000~U+2FFF)는 AppleSDGothicNeo가 지원하므로 유지.
        """
        return "".join(ch for ch in text if ord(ch) < 0x1F000).strip()

    def _ko_font(self, size: int, weight: int) -> ImageFont.ImageFont:
        """Apple SD Gothic Neo — weight에 따라 실제 굵기 선택."""
        if weight >= 700:
            key = "bold"
        elif weight >= 600:
            key = "semibold"
        elif weight >= 500:
            key = "medium"
        elif weight >= 350:
            key = "regular"
        elif weight >= 250:
            key = "light"
        else:
            key = "thin"
        idx = self._KO_IDX[key]
        try:
            return ImageFont.truetype(self._KO, size, index=idx)
        except Exception:
            return ImageFont.load_default()

    def _nike_font(self, size: int, ov_type: str, weight: int, korean: bool) -> ImageFont.ImageFont:
        """스포츠 스타일 폰트 선택 (Impact / DIN Condensed 우선)"""
        if korean:
            return self._ko_font(size, weight)

        # 카운터 숫자 → Impact (두껍고 임팩트 있는 스포츠 숫자)
        if ov_type == "counter":
            for path in [self._IMPACT, self._DIN_COND]:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
            # Impact 없으면 HN Condensed Black fallback
            try:
                return ImageFont.truetype(self._HN, size, index=self._HN_CONDENSED_BLK)
            except Exception:
                pass

        # 굵은 제목 → DIN Condensed Bold
        if weight >= 700:
            for path in [self._DIN_COND, self._DIN_ALT]:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
            try:
                return ImageFont.truetype(self._HN, size, index=self._HN_BOLD)
            except Exception:
                pass

        # 일반 레이블 → DIN Alternate Bold (깔끔하고 모던)
        for path in [self._DIN_ALT, self._AVENIR_CN]:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

        # Helvetica Neue fallback
        if weight <= 300:
            idx = self._HN_LIGHT
        else:
            idx = self._HN_REGULAR
        for i in [idx, self._HN_BOLD, 0]:
            try:
                return ImageFont.truetype(self._HN, size, index=i)
            except Exception:
                pass

        return ImageFont.load_default()

    def _wrap_lines(self, draw, lines: List[str], font, max_w: int) -> List[str]:
        """
        한 줄이 max_w를 초과하면 공백 기준으로 가장 중간에 가까운 지점에서 분리.
        재귀적으로 처리하여 여전히 넘치면 다시 분리.
        """
        result = []
        for line in lines:
            try:
                lw = draw.textbbox((0, 0), line, font=font)[2]
            except Exception:
                lw = len(line) * 20

            if lw <= max_w or ' ' not in line.strip():
                result.append(line)
                continue

            # 공백 위치 목록
            words = line.split(' ')
            if len(words) < 2:
                result.append(line)
                continue

            # 전체 char 수 기준으로 50%에 가장 가까운 split point
            total = len(line)
            best_i, best_diff = 1, float('inf')
            cum = 0
            for i, w in enumerate(words[:-1]):
                cum += len(w) + 1          # +1 for space
                diff = abs(cum - total / 2)
                if diff < best_diff:
                    best_diff = diff
                    best_i = i + 1

            left  = ' '.join(words[:best_i])
            right = ' '.join(words[best_i:])
            # 재귀: 분리된 각 부분이 여전히 넘치면 다시 분리
            result.extend(self._wrap_lines(draw, [left, right], font, max_w))

        return result

    def _fit_font(
        self, draw, lines: List[str], font, base_size: int,
        W: int, PAD: int, korean: bool, ov_type: str, weight: int
    ):
        """
        텍스트가 화면 폭에 맞도록 처리.
        우선순위: 1) 줄바꿈(공백 기준)  2) 최후 수단 — 폰트 축소
        반환: (font, line_height, text_w, total_h, wrapped_lines)
        """
        max_w = W - PAD * 2
        size  = base_size

        # 1단계: 줄바꿈으로 해결
        wrapped = self._wrap_lines(draw, lines, font, max_w)

        # 2단계: 줄바꿈으로도 안 되는 단어(공백 없는 긴 단어)만 폰트 축소
        while size > 14:
            max_line_w = max(
                (draw.textbbox((0, 0), ln, font=font)[2]
                 if hasattr(font, 'size') else len(ln) * size // 2)
                for ln in wrapped
            )
            if max_line_w <= max_w:
                break
            size = int(size * 0.88)
            font = self._nike_font(size, ov_type, weight, korean)
            wrapped = self._wrap_lines(draw, lines, font, max_w)

        line_height = size + int(size * 0.2)
        text_w, text_h = 0, size
        for ln in wrapped:
            try:
                bb = draw.textbbox((0, 0), ln, font=font)
                text_w = max(text_w, bb[2] - bb[0])
                text_h = bb[3] - bb[1]
            except Exception:
                text_w = max(text_w, len(ln) * size // 2)
        total_h = line_height * len(wrapped)
        return font, line_height, text_w, total_h, wrapped

    def _resolve_overlaps(
        self, items: List[Dict], W: int, H: int, PAD: int, GAP: int
    ) -> List[Dict]:
        """
        활성 오버레이의 y 위치를 재배치해 겹침 제거.
        1. 각 아이템의 실제 bounding box 계산
        2. cy(중심y) 기준 정렬
        3. 위→아래 순서로 겹치면 아래 아이템 밀어내기
        4. 화면 밖으로 나가면 위 아이템을 당겨올리기
        """
        # 1. cx/cy를 실제 좌상단 x/y로 변환
        for item in items:
            item["rx"] = max(PAD, min(W - item["text_w"] - PAD, item["cx"] - item["text_w"] // 2))
            item["ry"] = item["cy"] - item["text_h"] // 2

        # 2. y 기준 정렬
        items.sort(key=lambda x: x["ry"])

        # 3. 겹침 해소 (최대 10 패스) — X 축 겹침 확인 후 Y 밀어내기
        for _ in range(10):
            changed = False
            for i in range(len(items) - 1):
                a, b = items[i], items[i + 1]
                # X 범위가 겹치지 않으면 같은 행의 다른 열 → Y 밀 필요 없음
                a_right = a["rx"] + a["text_w"]
                b_right = b["rx"] + b["text_w"]
                x_overlaps = not (a_right + GAP <= b["rx"] or b_right + GAP <= a["rx"])
                if not x_overlaps:
                    continue
                a_bot = a["ry"] + a["text_h"]
                b_top = b["ry"]
                if a_bot + GAP > b_top:
                    shift = a_bot + GAP - b_top
                    b["ry"] += shift
                    changed = True
            if not changed:
                break

        # 4. 화면 하단 초과 처리 (역방향으로 위로 밀어올리기)
        for i in range(len(items) - 1, -1, -1):
            item = items[i]
            bottom = item["ry"] + item["text_h"]
            if bottom > H - PAD:
                item["ry"] -= bottom - (H - PAD)
        # 상단 초과 처리
        for item in items:
            item["ry"] = max(PAD, item["ry"])

        return items

    def _smart_color(self, raw_color: str, ov_type: str, palette: Dict) -> Tuple:
        """
        템플릿 색상 + 오버레이 타입 → 최적 RGB 결정.
        - CSS 이름 색상 → 나이키 팔레트로 교체 (더 어울리게)
        - hex 색상 → 그대로 사용
        """
        raw = raw_color.strip().lower()
        # 나이키 팔레트에서 타입별 색상 매핑
        type_map = {
            "counter": palette["number"],
            "stats":   palette["label"],
            "text":    palette["title"],
        }
        base_rgb = type_map.get(ov_type, palette["title"])

        # CSS 이름이면 나이키 팔레트 사용, hex면 그대로
        if not raw.startswith("#"):
            # 예외: orange → accent 색상
            if raw in ("orange", "yellow", "gold"):
                return palette["accent"]
            return base_rgb
        # hex 파싱
        return self._parse_color(raw_color)

    def _draw_overlay_item(self, draw: ImageDraw.Draw, item: Dict, frame: np.ndarray, W: int, H: int):
        """단일 오버레이 아이템 드로잉 (그림자 + 글로우 + 텍스트)"""
        x0       = item["rx"]
        y0       = item["ry"]
        lines    = item["lines"]
        font     = item["font"]
        lh       = item["line_height"]
        r, g, b  = item["r"], item["g"], item["b"]
        alpha    = item["alpha"]
        style    = item["style"]
        counter_prog = item.get("counter_prog")   # None = 일반 텍스트

        # 카운터 색상 애니메이션: 오렌지(빠름) → 흰색(정착)
        if counter_prog is not None:
            ease = counter_prog          # 0→빠름, 1→정착
            accent = (255, 130, 0)      # 오렌지
            r = int(accent[0] + (r - accent[0]) * ease)
            g = int(accent[1] + (g - accent[1]) * ease)
            b = int(accent[2] + (b - accent[2]) * ease)

        # 비디오 배경 밝기 기반 그림자 강도 결정
        region_y1 = max(0, y0)
        region_y2 = min(frame.shape[0], y0 + item["text_h"])
        region_x1 = max(0, x0)
        region_x2 = min(frame.shape[1], x0 + item["text_w"])
        if region_y2 > region_y1 and region_x2 > region_x1:
            region = frame[region_y1:region_y2, region_x1:region_x2]
            bg_brightness = float(region.mean()) / 255.0
        else:
            bg_brightness = 0.3

        shadow_alpha = int(min(alpha, 255) * (0.4 + bg_brightness * 0.5))
        no_shadow = style.get("no_shadow", False)

        for li, line in enumerate(lines):
            try:
                bb = draw.textbbox((0, 0), line, font=font)
                lw = bb[2] - bb[0]
            except Exception:
                lw = len(line) * font.size // 2

            # 라인별 수평 중앙 정렬
            lx = x0 + (item["text_w"] - lw) // 2
            ly = y0 + li * lh

            if not no_shadow:
                # ── 카운터 전용: 오렌지 글로우 (카운팅 속도에 비례) ──────
                if counter_prog is not None:
                    glow_strength = max(0.0, 1.0 - counter_prog)  # 빠를수록 강한 글로우
                    glow_alpha = int(alpha * glow_strength * 0.55)
                    if glow_alpha > 8:
                        for radius in [7, 5, 3]:
                            ga = glow_alpha // (radius // 2 + 1)
                            for dx, dy in [(0, radius), (0, -radius), (radius, 0), (-radius, 0),
                                           (radius, radius), (-radius, -radius),
                                           (radius, -radius), (-radius, radius)]:
                                draw.text((lx + dx, ly + dy), line, font=font,
                                          fill=(255, 130, 0, ga))

                    # ── 소프트 드롭 섀도 (아웃라인 대체) ──────────────────
                    # 반경별로 분산 → blur 효과와 유사한 부드러운 그림자
                    for s_radius, s_alpha_ratio in [(4, 0.55), (2, 0.75), (1, 0.90)]:
                        sa = int(shadow_alpha * s_alpha_ratio)
                        for sdx, sdy in [(s_radius, s_radius), (0, s_radius), (s_radius, 0)]:
                            draw.text((lx + sdx, ly + sdy), line, font=font,
                                      fill=(0, 0, 0, sa))
                else:
                    # 일반 소프트 드롭 섀도 — 여러 오프셋으로 번짐 효과
                    for (sdx, sdy), sa_ratio in [((3, 3), 0.60), ((2, 2), 0.80), ((1, 1), 0.95)]:
                        draw.text((lx + sdx, ly + sdy), line, font=font,
                                  fill=(0, 0, 0, int(shadow_alpha * sa_ratio)))

            # 본 텍스트
            draw.text((lx, ly), line, font=font, fill=(r, g, b, alpha))

    def _get_font(self, size: int, korean: bool = False) -> ImageFont.ImageFont:
        """하위 호환용 — _nike_font 위임"""
        return self._nike_font(size, "text", 400, korean)

    @staticmethod
    def _parse_color(color: str) -> tuple:
        """색상 문자열 → (R, G, B) 튜플. hex(#RRGGBB)와 CSS 이름 모두 지원."""
        named = {
            "white": (255, 255, 255), "black": (0, 0, 0),
            "red": (255, 0, 0),       "green": (0, 200, 0),
            "blue": (0, 100, 255),    "yellow": (255, 230, 0),
            "orange": (255, 140, 0),  "pink": (255, 100, 150),
            "gray": (150, 150, 150),  "grey": (150, 150, 150),
            "cyan": (0, 220, 220),    "purple": (160, 50, 220),
        }
        c = color.strip().lower()
        if c in named:
            return named[c]
        if c.startswith("#") and len(c) == 7:
            try:
                return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            except ValueError:
                pass
        return (255, 255, 255)  # 파싱 실패 시 흰색

    # ── 유틸 ────────────────────────────────────────────────────

    def _load_video(self, path: str) -> VideoFileClip:
        """안전한 영상 로드 (iPhone MOV 등 호환)"""
        try:
            return VideoFileClip(path)
        except Exception as e:
            self._log(f"    일반 로드 실패, ffmpeg 변환 시도: {e}")
            return self._load_via_ffmpeg(path)

    def _load_via_ffmpeg(self, path: str) -> VideoFileClip:
        """ffmpeg로 호환 mp4로 변환 후 로드"""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        subprocess.run([
            "ffmpeg", "-y", "-i", path,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-map_metadata", "-1",
            tmp.name
        ], capture_output=True, timeout=180)
        return VideoFileClip(tmp.name)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)


# ────────────────────────────────────────────────────────────────
# searchingmodule EditorAdapter (방법 B) 연결 함수
# ────────────────────────────────────────────────────────────────

def apply_template(
    instruction: dict,
    input_video: str,
    output_video: str
) -> bool:
    """
    searchingmodule PythonModuleAdapter 진입점.

    searchingmodule의 adapter.py에서 다음처럼 호출:
        adapter = PythonModuleAdapter(
            module_path="video-editor/src/template_executor.py",
            apply_func="apply_template"
        )
        adapter.apply(instruction, input_video, output_video)
    """
    executor = TemplateExecutor(verbose=True)
    return executor.execute(instruction, input_video, output_video)
