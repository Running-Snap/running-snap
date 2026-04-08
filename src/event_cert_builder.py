"""
event_cert_builder.py
=====================
이벤트 스타일 인증영상 Instruction 빌더.

러닝 통계 데이터(거리·페이스·칼로리 등) 없이
이벤트명 / 날짜 / 시간 / 장소 정보만으로 깔끔한 마라톤 인증영상 제작.

사용:
    from src.event_cert_builder import EventCertBuilder

    instruction = EventCertBuilder.build(orig_duration, event_config)

event_config 지원 키:
    title        (str)  — 이벤트명, \\n으로 2줄 가능
                          e.g. "2026\\nMIRACLE MARATHON"
    date         (str)  — 날짜    e.g. "2026. 04. 19"
    time         (str)  — 시간    e.g. "SUN. AM 08:00"
    location     (str)  — 장소    e.g. "Gapcheon, Daejeon, Republic of Korea"
    color_scheme (str)  — warm / cool / neutral  (기본: cool)
"""
from __future__ import annotations

from typing import Any, Dict, List


# ── 색조 프리셋 (색보정 파라미터 모두 0 = 원본 그대로) ─────────────
_COLOR_GRADE: Dict[str, Dict[str, Any]] = {
    "warm":    {"overall_tone": "warm",    "brightness": 0, "contrast": 0,
                "saturation": 0, "temperature": 0},
    "cool":    {"overall_tone": "cool",    "brightness": 0, "contrast": 0,
                "saturation": 0, "temperature": 0},
    "neutral": {"overall_tone": "natural", "brightness": 0, "contrast": 0,
                "saturation": 0, "temperature": 0},
}

# ── 오버레이 컬러 팔레트 (scheme별) ──────────────────────────────────
# 각 요소별 역할:
#   year      : 연도 소제목  — 악센트 컬러 (scheme 톤 반영)
#   title     : 메인 타이틀  — 항상 흰색 (최우선 가독성)
#   sep       : 구분선       — 악센트 컬러 저채도 버전
#   date      : 날짜         — 거의 흰색에 scheme 색감 살짝
#   time      : 시간         — 중간 밝기 악센트
#   location  : 장소         — 낮은 계층, 악센트 낮은 채도
_PALETTE: Dict[str, Dict[str, str]] = {
    "cool": {
        # 차가운 블루-실버 계열
        "year":     "#88C4DC",   # 밝은 하늘색
        "title":    "#FFFFFF",   # 순백 (최우선)
        "sep":      "#4A8FAA",   # 중간 파랑 (구분선)
        "date":     "#E8F4FA",   # 살짝 푸른 흰색
        "time":     "#98C4D8",   # 연한 하늘색
        "location": "#6899AA",   # 차분한 청회색
    },
    "warm": {
        # 따뜻한 골드-앰버 계열
        "year":     "#D4A868",   # 골드
        "title":    "#FFFFFF",
        "sep":      "#B08040",   # 다크 골드
        "date":     "#FFF4E4",   # 살짝 따뜻한 흰색
        "time":     "#D4B882",   # 연한 골드
        "location": "#A88855",   # 차분한 브라운-골드
    },
    "neutral": {
        # 무채색 실버 계열
        "year":     "#B0B8C0",   # 중간 회색
        "title":    "#FFFFFF",
        "sep":      "#707880",   # 다크 그레이
        "date":     "#F0F2F4",   # 거의 흰색
        "time":     "#C0C8D0",   # 연한 실버
        "location": "#808890",   # 차분한 슬레이트
    },
}


class EventCertBuilder:
    """
    이벤트 스타일 인증영상 Instruction 생성기.

    레이아웃 (y% 기준):
      상단 블록 (영상 시작 5%부터 등장):
        y= 8  — 연도 소제목  (작게, 회색)
        y=16  — 이벤트 타이틀 (크게, 굵게, 흰색)
        y=24  — 상단 구분선

      하단 블록 (영상 40%부터 fade-in):
        y=73  — 하단 구분선
        y=80  — 날짜
        y=86  — 시간
        y=92  — 장소
    """

    @classmethod
    def build(cls, orig: float, event_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        이벤트 인증영상 Instruction 생성.

        Args:
            orig:         원본 영상 길이 (초)
            event_config: 이벤트 설정 dict

        Returns:
            TemplateExecutor.execute()에 전달할 Instruction dict
        """
        cg       = _COLOR_GRADE.get(event_config.get("color_scheme", "cool"),
                                    _COLOR_GRADE["cool"])
        overlays = cls._build_overlays(event_config)

        return {
            "version":     "1.0",
            "template_id": "event_cert_v1",
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
            "effects":       [],
            "overlays":      overlays,
            "color_grade": {
                "overall_tone": cg["overall_tone"],
                "adjustment_params": {
                    "brightness":  cg["brightness"],
                    "contrast":    cg["contrast"],
                    "saturation":  cg["saturation"],
                    "temperature": cg["temperature"],
                },
            },
        }

    # ── 오버레이 생성 ─────────────────────────────────────────────

    @classmethod
    def _build_overlays(cls, event_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        이벤트 스타일 오버레이 목록 생성.

        상단 블록 (영상 5%부터):
          연도 소제목 → 메인 타이틀 → 구분선

        하단 블록 (영상 40%부터):
          구분선 → 날짜 → 시간 → 장소

        컬러:
          - 연도/구분선: scheme 악센트 컬러
          - 타이틀/날짜: 흰색 계열 (최우선 가독성)
          - 시간:        중간 밝기 악센트
          - 장소:        낮은 계층, 차분한 악센트
        """
        raw_title = event_config.get("title", "")
        date      = event_config.get("date", "")
        time_str  = event_config.get("time", "")
        location  = event_config.get("location", "")
        scheme    = event_config.get("color_scheme", "cool")

        pal      = _PALETTE.get(scheme, _PALETTE["cool"])
        ov_title = 0.05
        ov_info  = 0.40

        overlays: List[Dict[str, Any]] = []

        # ─── 상단 블록 ───────────────────────────────────────────

        # ① 연도 소제목 — scheme 악센트 컬러
        year = ""
        if date:
            year = date.split(".")[0].strip()
        elif raw_title:
            first = raw_title.replace("\n", " ").split()[0]
            if first.isdigit():
                year = first
        if year:
            overlays.append({
                "id": "ov_year", "type": "text", "content": year,
                "position_pct": {"x": 50, "y": 8},
                "start_ratio": ov_title, "end_ratio": 1.0,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 300, "font_size_ratio": 0.025,
                    "color": pal["year"], "opacity": 1.0,
                },
            })

        # ② 메인 타이틀 — 흰색, 최대 가독성
        title = raw_title.replace("\n", " ").strip()
        if year:
            title = title.replace(year, "").strip()
        if title:
            overlays.append({
                "id": "ov_title", "type": "text", "content": title,
                "position_pct": {"x": 50, "y": 16},
                "start_ratio": ov_title, "end_ratio": 1.0,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 900, "font_size_ratio": 0.060,
                    "color": pal["title"], "opacity": 1.0,
                },
            })

        # ③ 상단 구분선
        overlays.append({
            "id": "ov_sep_top", "type": "text",
            "content": "━━━━━━━━━━━━━━",
            "position_pct": {"x": 50, "y": 24},
            "start_ratio": ov_title, "end_ratio": 1.0,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.018,
                "color": pal["sep"], "opacity": 0.70,
            },
        })

        # ─── 하단 블록 ───────────────────────────────────────────

        # ④ 하단 구분선
        overlays.append({
            "id": "ov_sep_bot", "type": "text",
            "content": "━━━━━━━━━━━━━━",
            "position_pct": {"x": 50, "y": 73},
            "start_ratio": ov_info, "end_ratio": 1.0,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300, "font_size_ratio": 0.018,
                "color": pal["sep"], "opacity": 0.70,
            },
        })

        # ⑤ 날짜 — 굵게, 그림자로 가시성 확보
        if date:
            overlays.append({
                "id": "ov_date", "type": "text", "content": date,
                "position_pct": {"x": 50, "y": 80},
                "start_ratio": ov_info, "end_ratio": 1.0,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 700, "font_size_ratio": 0.040,
                    "color": pal["date"], "opacity": 1.0,
                },
            })

        # ⑥ 시간
        if time_str:
            overlays.append({
                "id": "ov_time", "type": "text", "content": time_str,
                "position_pct": {"x": 50, "y": 87},
                "start_ratio": ov_info, "end_ratio": 1.0,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 600, "font_size_ratio": 0.032,
                    "color": pal["time"], "opacity": 1.0,
                },
            })

        # ⑦ 장소
        if location:
            overlays.append({
                "id": "ov_location", "type": "text", "content": location,
                "position_pct": {"x": 50, "y": 93},
                "start_ratio": ov_info, "end_ratio": 1.0,
                "animation_in": "fade_in",
                "style": {
                    "font_weight": 400, "font_size_ratio": 0.022,
                    "color": pal["location"], "opacity": 1.0,
                },
            })

        return overlays
