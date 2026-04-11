"""
cert_builder.py
===============
Nike 스타일 러닝 인증영상 Instruction 빌더.

두 가지 모드를 지원:
  - full  : intro → buildup → slowmo → stats 구간 (일반 인증영상)
  - simple: 원본 영상 1x 그대로 + 후반 그래픽 (슬로우모 없는 단편 버전)

사용:
    from src.cert_builder import CertBuilder

    # 일반 인증영상 (루프 영상 사용)
    instruction = CertBuilder.build_full(info, event_config, highlights)

    # 슬로우모 없는 단편
    instruction = CertBuilder.build_simple(orig_duration, event_config)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .preprocessor import VideoInfo


# ── 색조 프리셋 ─────────────────────────────────────────────────────
_COLOR_GRADE: Dict[str, Dict[str, Any]] = {
    # brightness/contrast/saturation 모두 0 → 색보정 없이 원본 그대로
    "warm":    {"overall_tone": "warm",    "brightness": 0,  "contrast": 0,  "saturation": 0,   "temperature": 0},
    "cool":    {"overall_tone": "cool",    "brightness": 0,  "contrast": 0,  "saturation": 0,   "temperature": 0},
    "neutral": {"overall_tone": "natural", "brightness": 0,  "contrast": 0,  "saturation": 0,   "temperature": 0},
}

# ── 오버레이 레이아웃 상수 ───────────────────────────────────────────
# x 3열 중앙 기준 (%)
_C1, _C2, _C3 = 20, 50, 80
# row1: Pace | Time | Calories
# row2: Elevation | Avg HR | Cadence
_R1_LBL, _R1_VAL = 58, 65   # row1 레이블 y%, 값 y%
_R2_LBL, _R2_VAL = 74, 81   # row2 레이블 y%, 값 y%


class CertBuilder:
    """Nike 스타일 인증영상 Instruction 생성기."""

    # ── Public API ────────────────────────────────────────────────────

    @classmethod
    def build_full(
        cls,
        info: VideoInfo,
        event_config: Dict[str, Any],
        highlights: List[float],
    ) -> Dict[str, Any]:
        """
        일반 인증영상 instruction.

        구성:
          1. intro  — wide 앵글 (0 → t_wide_end)
          2. buildup— 접근 (t_wide_end → t_slow_start)
          3. slowmo — 슬로우모션 0.35x (t_slow_start → t_slow_end)
          4. stats  — 원본 처음→끝 1x 재생 (그래픽 오버레이)

        Args:
            info:         VideoInfo (preprocessor 결과)
            event_config: 이벤트 설정 dict (하단 참조)
            highlights:   Qwen VLM 하이라이트 타임스탬프 목록

        event_config 지원 키:
            title          (str)   — 이벤트 명칭 e.g. "BLOSSOM\\nRUNNING"
            distance_km    (float) — 총 거리 km
            pace           (str)   — 평균 페이스 e.g. "6'35\"/km"
            run_time       (str)   — 소요 시간  e.g. "34'18\""
            calories       (str)   — 칼로리     e.g. "312 kcal"
            elevation_gain (str)   — 고도 상승  e.g. "48 m"
            avg_heart_rate (str)   — 평균 심박수 e.g. "152 bpm"
            cadence        (str)   — 케이던스   e.g. "163 spm"
            date           (str)   — 날짜       e.g. "2026.04.03"
            color_scheme   (str)   — warm / cool / neutral
        """
        orig = info.original_duration or info.duration
        cg   = _COLOR_GRADE.get(event_config.get("color_scheme", "warm"), _COLOR_GRADE["warm"])

        # ── 세그먼트 경계 계산 ──────────────────────────────────────
        if highlights and len(highlights) >= 2:
            t_wide_end   = min(highlights[0],       orig * 0.25)
            t_slow_start = min(highlights[1] - 0.5, orig * 0.45)
            t_slow_end   = min(highlights[1] + 0.8, orig * 0.70)
        else:
            t_wide_end   = orig * 0.22
            t_slow_start = orig * 0.42
            t_slow_end   = orig * 0.65

        dur_wide     = t_wide_end
        dur_approach = t_slow_start - t_wide_end
        dur_slowmo   = (t_slow_end - t_slow_start) / 0.35
        dur_stats    = orig   # 스탯 구간 = 원본 전체 (처음~끝 1x)
        total_dur    = round(dur_wide + dur_approach + dur_slowmo + dur_stats, 3)

        def r(t: float) -> float:
            return round(t / total_dur, 4)

        r_wide_end     = r(dur_wide)
        r_approach_end = r(dur_wide + dur_approach)
        r_slowmo_end   = r(dur_wide + dur_approach + dur_slowmo)

        ov_start = r_slowmo_end
        ov_grid  = r(dur_wide + dur_approach + dur_slowmo + dur_stats * 0.15)

        overlays = cls._build_overlays(event_config, ov_start, ov_grid)

        return {
            "version":     "1.0",
            "template_id": "cert_nike_v2",
            "meta": {
                "aspect_ratio":            "9:16",
                "target_duration_seconds": total_dur,
                "color_grade":             cg["overall_tone"],
                "crop_zoom":               1.20,
            },
            "timeline": {
                "total_duration_seconds": total_dur,
                "segments": [
                    {
                        "id": "s0_wide", "type": "intro",
                        "source_start_sec": 0.0,
                        "source_end_sec":   round(t_wide_end, 3),
                        "speed": 1.0,
                        "start_ratio": 0.0, "end_ratio": r_wide_end,
                    },
                    {
                        "id": "s1_approach", "type": "buildup",
                        "source_start_sec": round(t_wide_end, 3),
                        "source_end_sec":   round(t_slow_start, 3),
                        "speed": 1.0,
                        "start_ratio": r_wide_end, "end_ratio": r_approach_end,
                    },
                    {
                        "id": "s2_slowmo", "type": "peak",
                        "source_start_sec": round(t_slow_start, 3),
                        "source_end_sec":   round(t_slow_end, 3),
                        "speed": 0.35,
                        "start_ratio": r_approach_end, "end_ratio": r_slowmo_end,
                    },
                    {
                        "id": "s3_stats", "type": "action",
                        "source_start_sec": 0.0,
                        "source_end_sec":   round(orig, 3),
                        "speed": 1.0,
                        "start_ratio": r_slowmo_end, "end_ratio": 1.0,
                    },
                ],
                "cuts": [
                    {"position_ratio": r_wide_end,     "type": "hard_cut"},
                    {"position_ratio": r_approach_end, "type": "flash"},
                    {"position_ratio": r_slowmo_end,   "type": "hard_cut"},
                ],
                "overlays": overlays,
            },
            "speed_changes": [
                {"start_ratio": r_approach_end, "end_ratio": r_slowmo_end, "speed": 0.35},
            ],
            "effects": [
                {"type": "zoom_in", "start_ratio": 0.0,            "end_ratio": r_wide_end,     "intensity": 0.06},
                {"type": "zoom_in", "start_ratio": r_wide_end,     "end_ratio": r_approach_end, "intensity": 0.10},
                {"type": "zoom_in", "start_ratio": r_approach_end, "end_ratio": r_slowmo_end,   "intensity": 0.16},
            ],
            "overlays": overlays,
            "color_grade": cls._color_grade_block(cg),
        }

    @classmethod
    def build_simple(
        cls,
        orig: float,
        event_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        슬로우모 없는 단편 인증영상 instruction.

        원본 영상을 1x 그대로 한 번 재생하면서
        영상 40% 지점부터 Nike 기록 그래픽이 순차적으로 등장.

        Args:
            orig:         원본 영상 길이 (초)
            event_config: 이벤트 설정 dict (build_full과 동일 키)
        """
        cg = _COLOR_GRADE.get(event_config.get("color_scheme", "warm"), _COLOR_GRADE["warm"])

        # 그래픽 등장 비율: 40% 지점부터, 그리드는 50%부터
        ov_start = 0.40
        ov_grid  = 0.50

        overlays = cls._build_overlays(event_config, ov_start, ov_grid)

        return {
            "version":     "1.0",
            "template_id": "cert_simple_v1",
            "meta": {
                "aspect_ratio":            "9:16",
                "target_duration_seconds": round(orig, 3),
                "color_grade":             cg["overall_tone"],
                "crop_zoom":               1.0,   # 줌 없음 — 원본 화질 그대로
            },
            "timeline": {
                "total_duration_seconds": round(orig, 3),
                "segments": [
                    {
                        "id": "s0_full", "type": "action",
                        "source_start_sec": 0.0,
                        "source_end_sec":   round(orig, 3),
                        "speed": 1.0,
                        "start_ratio": 0.0, "end_ratio": 1.0,
                    },
                ],
                "cuts":     [],
                "overlays": overlays,
            },
            "speed_changes": [],
            "effects": [],
            "overlays":    overlays,
            "color_grade": cls._color_grade_block(cg),
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────

    @classmethod
    def _build_overlays(
        cls,
        event_config: Dict[str, Any],
        ov_start: float,
        ov_grid: float,
    ) -> List[Dict[str, Any]]:
        """
        Nike 스타일 기록 오버레이 목록 생성.

        레이아웃 (y% 기준):
          y= 7  — 이벤트 타이틀
          y=33  — km 대형 카운터
          y=47  — "km" 서브레이블
          y=58/65 — Row1 레이블/값  (Pace | Time | Calories)
          y=74/81 — Row2 레이블/값  (Elevation | Avg HR | Cadence)
          y=91  — 날짜

        overlay 등장 규칙:
          - 이벤트 타이틀 + km 카운터: ov_start 시점부터
          - stat 그리드 + 날짜:        ov_grid  시점부터 (약간 딜레이)
        """
        dist_km        = event_config.get("distance_km", 0.0)
        pace           = event_config.get("pace", "")
        run_time       = event_config.get("run_time", "")
        calories       = event_config.get("calories", "")
        elevation_gain = event_config.get("elevation_gain", "")
        avg_heart_rate = event_config.get("avg_heart_rate", "")
        cadence        = event_config.get("cadence", "")
        date           = event_config.get("date", "")
        event_title    = event_config.get("title", "").replace("\n", " ").strip()

        def _lbl(id_: str, text: str, x: int, y: int) -> Dict:
            """소형 레이블 — 소프트 그림자로 가독성 확보."""
            return {
                "id": id_, "type": "text", "content": text,
                "position_pct": {"x": x, "y": y},
                "start_ratio": ov_grid, "end_ratio": 1.00,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 600, "font_size_ratio": 0.022,
                    "color": "#CCCCCC", "opacity": 0.90,
                },
            }

        def _val(id_: str, text: str, x: int, y: int) -> Dict:
            """대형 흰색 값 — 소프트 그림자로 가독성 확보."""
            return {
                "id": id_, "type": "text", "content": text,
                "position_pct": {"x": x, "y": y},
                "start_ratio": ov_grid, "end_ratio": 1.00,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 800, "font_size_ratio": 0.050,
                    "color": "#FFFFFF", "opacity": 1.0,
                },
            }

        overlays: List[Dict] = []

        # ① 이벤트 타이틀
        if event_title:
            overlays.append({
                "id": "ov_event_title", "type": "text", "content": event_title,
                "position_pct": {"x": 50, "y": 7},
                "start_ratio": ov_start, "end_ratio": 1.00,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 800, "font_size_ratio": 0.030,
                    "color": "#FFFFFF", "opacity": 1.0,
                },
            })

        # ② km 카운터 (대형 숫자, ease_out 카운팅) — dist_km > 0 일 때만 표시
        if dist_km and float(dist_km) > 0:
            overlays.append({
                "id": "ov_km", "type": "counter",
                "content": str(dist_km),
                "position_pct": {"x": 50, "y": 33},
                "start_ratio": ov_start, "end_ratio": 1.00,
                "counter_config": {
                    "start_value": 0.0, "end_value": dist_km,
                    "unit": "", "decimal_places": 1,
                    "count_up": True, "easing": "ease_out",
                },
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 900, "font_size_ratio": 0.20,
                    "color": "#FFFFFF", "opacity": 1.0,
                },
            })

            # ③ "km" 서브레이블 (카운터 있을 때만)
            overlays.append({
                "id": "ov_km_label", "type": "text", "content": "km",
                "position_pct": {"x": 50, "y": 47},
                "start_ratio": ov_start, "end_ratio": 1.00,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 500, "font_size_ratio": 0.030,
                    "color": "#FFFFFF", "opacity": 0.80,
                },
            })

        # ④ Row 1: Pace | Time | Calories  (레이블 작게, 값 크게, 그림자 없음)
        row1 = [
            ("AVG PACE", pace,     _C1),
            ("TIME",     run_time, _C2),
            ("CALORIES", calories, _C3),
        ]
        for label, value, x in row1:
            if value:
                slug = label.lower().replace(" ", "_")
                overlays.append(_lbl(f"ov_r1_lbl_{slug}", label, x, _R1_LBL))
                overlays.append(_val(f"ov_r1_val_{slug}", value, x, _R1_VAL))

        # ⑤ Row 2: Elevation | Avg HR | Cadence
        row2 = [
            ("ELEVATION", elevation_gain,  _C1),
            ("AVG HR",    avg_heart_rate,  _C2),
            ("CADENCE",   cadence,         _C3),
        ]
        for label, value, x in row2:
            if value:
                slug = label.lower().replace(" ", "_")
                overlays.append(_lbl(f"ov_r2_lbl_{slug}", label, x, _R2_LBL))
                overlays.append(_val(f"ov_r2_val_{slug}", value, x, _R2_VAL))

        # ⑥ 날짜 (최하단)
        if date:
            overlays.append({
                "id": "ov_date", "type": "text", "content": date,
                "position_pct": {"x": 50, "y": 91},
                "start_ratio": ov_grid, "end_ratio": 1.00,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 500, "font_size_ratio": 0.024,
                    "color": "#DDCCBB", "opacity": 0.75,
                },
            })

        return overlays

    @staticmethod
    def _color_grade_block(cg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "overall_tone": cg["overall_tone"],
            "adjustment_params": {
                "brightness":  cg["brightness"],
                "contrast":    cg["contrast"],
                "saturation":  cg["saturation"],
                "temperature": cg["temperature"],
            },
        }
