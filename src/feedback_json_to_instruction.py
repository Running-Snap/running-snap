"""
feedback_json_to_instruction.py
================================
LLM이 반환한 feedback JSON → EditInstruction 변환기

입력 JSON 구조:
  {
    "score": 70,
    "feedbacks": [
      {"title": "케이던스", "status": "bad",  "message": "..."},
      {"title": "착지",     "status": "good", "message": "..."},
      ...
    ],
    "pose_stats": {
      "cadence": 41.1, "v_oscillation": 604.2,
      "avg_impact_z": 0.115, "asymmetry": 103.8, "elbow_angle": 83.1
    },
    "coaching_report": "..."
  }

영상 흐름:
  [score_card]  점수 freeze (2.5s)
  → 피드백마다: [normal] → [slowmo 0.30x lead-in 0.5s] → [freeze + 자막]
  → [stats_card] 수치 요약 freeze (4.0s)
  → [outro]     소스 마지막 2s
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple

# ── 색상 (BGR hex for PIL renderer — actually RGB strings) ──────────
BAD_COLOR  = "#FF5533"    # 빨강-오렌지  (bad 피드백)
GOOD_COLOR = "#44DD88"    # 청록-초록   (good 피드백)
LABEL_COLOR = "#AADDFF"   # 하늘색 레이블
SCORE_COLOR = "#FFFFFF"
STATS_LABEL_COLOR = "#99BBCC"

SLOWMO_SPEED = 0.30
LEAD_IN      = 0.50        # 슬로우 lead-in 소스 구간 (초)
MIN_FREEZE   = 3.0         # 최소 freeze 시간 (초)
READING_CPS  = 11.0        # 한국어 읽기 속도 (자/초)
SCORE_FREEZE = 2.5
STATS_FREEZE = 4.0
OUTRO_DUR    = 2.0


class FeedbackJsonConverter:
    """feedback JSON → EditInstruction + 타임라인 자동 계산"""

    # 피드백별 소스 타임스탬프 자동 배분 (루프 소스 8.7s 기준)
    # 2.9s 원본 안에 고르게, 피드백 개수에 따라 조정
    _DEFAULT_TIMESTAMPS = [0.7, 1.4, 2.0, 2.7, 3.4, 4.1]

    def convert(
        self,
        data: Dict[str, Any],
        source_duration: float = 8.7,
    ) -> Dict[str, Any]:
        """
        Returns: EditInstruction dict
        """
        score     = data.get("score", 0)
        feedbacks = data.get("feedbacks", [])
        stats     = data.get("pose_stats", {})

        # ── 1. 피드백별 소스 타임스탬프 배분 ──────────────────────
        n = len(feedbacks)
        timestamps = self._DEFAULT_TIMESTAMPS[:n]
        # 소스 범위를 벗어나면 clamp
        timestamps = [min(t, source_duration - 0.1) for t in timestamps]

        # ── 2. 세그먼트 + 오버레이 빌드 ───────────────────────────
        segments: List[Dict] = []
        overlays: List[Dict] = []
        cur_output_time = 0.0   # 현재까지 쌓인 출력 시간 누적
        seg_id = 0

        # ─── score_card freeze ────────────────────────────────────
        segments.append({
            "id": f"seg_{seg_id:02d}_score_freeze",
            "type": "freeze",
            "source_start_sec": 0.0,
            "source_end_sec":   0.0,
            "freeze_duration":  SCORE_FREEZE,
            "start_ratio": 0.0, "end_ratio": 0.0,  # 더미 (executor가 freeze_duration 사용)
        })
        seg_id += 1
        score_start = cur_output_time
        cur_output_time += SCORE_FREEZE

        # ─── 피드백 반복 ──────────────────────────────────────────
        prev_src = 0.0

        for i, (fb, t_src) in enumerate(zip(feedbacks, timestamps)):
            lead_start = max(prev_src, t_src - LEAD_IN)

            # ① 이전 ending → lead_in 시작까지 normal
            if lead_start > prev_src + 0.05:
                dur_normal = lead_start - prev_src
                segments.append({
                    "id": f"seg_{seg_id:02d}_normal",
                    "type": "normal",
                    "source_start_sec": prev_src,
                    "source_end_sec":   lead_start,
                    "speed": 1.0,
                    "start_ratio": 0.0, "end_ratio": 0.0,
                })
                seg_id += 1
                cur_output_time += dur_normal

            # ② slowmo lead-in
            slowmo_src_dur = t_src - lead_start
            slowmo_out_dur = slowmo_src_dur / SLOWMO_SPEED
            segments.append({
                "id": f"seg_{seg_id:02d}_slowmo",
                "type": "peak",
                "source_start_sec": lead_start,
                "source_end_sec":   t_src,
                "speed": SLOWMO_SPEED,
                "start_ratio": 0.0, "end_ratio": 0.0,
            })
            seg_id += 1
            cur_output_time += slowmo_out_dur

            # ③ freeze
            title_txt = fb.get("title", "")
            msg_txt   = fb.get("message", "")
            freeze_dur = max(MIN_FREEZE, (len(msg_txt)) / READING_CPS)

            segments.append({
                "id": f"seg_{seg_id:02d}_freeze",
                "type": "freeze",
                "source_start_sec": t_src,
                "source_end_sec":   t_src,
                "freeze_duration":  round(freeze_dur, 2),
                "start_ratio": 0.0, "end_ratio": 0.0,
            })
            seg_id += 1

            freeze_start = cur_output_time
            freeze_end   = cur_output_time + freeze_dur
            cur_output_time = freeze_end

            # 이 freeze 구간에 오버레이 등록
            status  = fb.get("status", "")
            col     = BAD_COLOR if status == "bad" else GOOD_COLOR
            badge   = "BAD" if status == "bad" else "GOOD"

            overlays.append({
                "id": f"ov_{i}_badge",
                "type": "text",
                "content": badge,
                "position_pct": {"x": 50, "y": 12},
                "_start_seconds": freeze_start,
                "_end_seconds":   freeze_end,
                "animation_in": "fade_in",
                "animation_out": "fade_out",
                "style": {
                    "font_weight": 700,
                    "font_size_ratio": 0.038,
                    "color": col,
                    "opacity": 0.95,
                },
            })
            overlays.append({
                "id": f"ov_{i}_title",
                "type": "text",
                "content": title_txt,
                "position_pct": {"x": 50, "y": 20},
                "_start_seconds": freeze_start,
                "_end_seconds":   freeze_end,
                "style": {
                    "font_weight": 700,
                    "font_size_ratio": 0.065,
                    "color": col,
                    "opacity": 1.0,
                },
            })
            overlays.append({
                "id": f"ov_{i}_msg",
                "type": "text",
                "content": msg_txt,
                "position_pct": {"x": 50, "y": 72},
                "_start_seconds": freeze_start,
                "_end_seconds":   freeze_end,
                "style": {
                    "font_weight": 300,
                    "font_size_ratio": 0.038,
                    "color": "#FFFFFF",
                    "opacity": 0.92,
                },
            })

            prev_src = t_src

        # ─── stats_card freeze ────────────────────────────────────
        stat_lines = _build_stats_text(stats, feedbacks)
        segments.append({
            "id": f"seg_{seg_id:02d}_stats_freeze",
            "type": "freeze",
            "source_start_sec": timestamps[-1] if timestamps else 0.5,
            "source_end_sec":   timestamps[-1] if timestamps else 0.5,
            "freeze_duration":  STATS_FREEZE,
            "start_ratio": 0.0, "end_ratio": 0.0,
        })
        seg_id += 1
        stats_start = cur_output_time
        cur_output_time += STATS_FREEZE

        # score overlay on stats card
        overlays.append({
            "id": "ov_score_label",
            "type": "text",
            "content": "SCORE",
            "position_pct": {"x": 50, "y": 12},
            "_start_seconds": stats_start,
            "_end_seconds":   stats_start + STATS_FREEZE,
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.030,
                "color": LABEL_COLOR,
                "opacity": 0.80,
            },
        })
        overlays.append({
            "id": "ov_score_num",
            "type": "counter",
            "content": f"{score}",
            "position_pct": {"x": 50, "y": 22},
            "_start_seconds": stats_start,
            "_end_seconds":   stats_start + STATS_FREEZE,
            "counter_config": {
                "start_value": 0,
                "end_value": score,
                "unit": "",
                "decimal_places": 0,
                "count_up": True,
                "easing": "ease_out",
            },
            "style": {
                "font_weight": 900,
                "font_size_ratio": 0.13,
                "color": _score_color(score),
                "opacity": 1.0,
            },
        })
        # divider hint: 작은 텍스트로 표현
        overlays.append({
            "id": "ov_stats_body",
            "type": "text",
            "content": stat_lines,
            "position_pct": {"x": 50, "y": 62},
            "_start_seconds": stats_start,
            "_end_seconds":   stats_start + STATS_FREEZE,
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.036,
                "color": "#DDEEFF",
                "opacity": 0.90,
            },
        })

        # ─── score_card overlays ──────────────────────────────────
        overlays.append({
            "id": "ov_score_intro_label",
            "type": "text",
            "content": "TODAY'S SCORE",
            "position_pct": {"x": 50, "y": 35},
            "_start_seconds": score_start,
            "_end_seconds":   score_start + SCORE_FREEZE,
            "animation_in": "fade_in",
            "style": {
                "font_weight": 300,
                "font_size_ratio": 0.032,
                "color": LABEL_COLOR,
                "opacity": 0.80,
            },
        })
        overlays.append({
            "id": "ov_score_intro_num",
            "type": "counter",
            "content": f"{score}",
            "position_pct": {"x": 50, "y": 50},
            "_start_seconds": score_start,
            "_end_seconds":   score_start + SCORE_FREEZE,
            "counter_config": {
                "start_value": 0,
                "end_value": score,
                "unit": "",
                "decimal_places": 0,
                "count_up": True,
                "easing": "ease_out",
            },
            "style": {
                "font_weight": 900,
                "font_size_ratio": 0.20,
                "color": _score_color(score),
                "opacity": 1.0,
            },
        })

        # ─── outro (소스 마지막 2s) ───────────────────────────────
        outro_start_src = min(prev_src + 0.2, source_duration - OUTRO_DUR)
        segments.append({
            "id": f"seg_{seg_id:02d}_outro",
            "type": "outro",
            "source_start_sec": outro_start_src,
            "source_end_sec":   min(outro_start_src + OUTRO_DUR, source_duration),
            "speed": 1.0,
            "start_ratio": 0.0, "end_ratio": 0.0,
        })
        cur_output_time += OUTRO_DUR

        # ── 3. ratio 계산 (target_duration 기준) ──────────────────
        target_duration = round(cur_output_time, 2)
        _assign_ratios(overlays, target_duration)

        # ── 4. EditInstruction 조립 ───────────────────────────────
        instruction = {
            "version": "1.0",
            "template_id": "pose_feedback_v1",
            "meta": {
                "aspect_ratio": "9:16",
                "target_duration_seconds": target_duration,
                "color_grade": "dark",
                "crop_zoom": 1.3,
                "vibe_tags": ["pose_analysis", "feedback", "coaching"],
            },
            "timeline": {
                "total_duration_seconds": target_duration,
                "narrative_flow": "score_card → feedback×N → stats_card → outro",
                "segments": segments,
                "cuts": [],
            },
            "speed_changes": [],
            "effects": [
                {"type": "vignette", "start_ratio": 0.0, "end_ratio": 1.0, "intensity": 0.40},
            ],
            "overlays": overlays,
            "color_grade": {
                "overall_tone": "dark",
                "adjustment_params": {
                    "brightness": -10, "contrast": 20,
                    "saturation": -15, "temperature": -8,
                },
            },
        }
        return instruction


# ── 헬퍼 ────────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 80:
        return "#44EE88"
    if score >= 60:
        return "#FFCC44"
    return "#FF5533"


def _build_stats_text(stats: Dict, feedbacks: List[Dict]) -> str:
    """pose_stats → 멀티라인 요약 문자열"""
    # 피드백 status 맵
    status_map = {fb["title"]: fb["status"] for fb in feedbacks}

    lines = []
    if "cadence" in stats:
        s = status_map.get("케이던스", "")
        mark = "X" if s == "bad" else ("OK" if s == "good" else "")
        lines.append(f"케이던스   {stats['cadence']} SPM  {mark}")
    if "elbow_angle" in stats:
        s = status_map.get("팔꿈치 각도", "")
        mark = "X" if s == "bad" else ("OK" if s == "good" else "")
        lines.append(f"팔꿈치 각도  {stats['elbow_angle']}  {mark}")
    if "avg_impact_z" in stats:
        s = status_map.get("착지", "")
        mark = "X" if s == "bad" else ("OK" if s == "good" else "")
        lines.append(f"착지 Z   {stats['avg_impact_z']}  {mark}")
    if "asymmetry" in stats:
        s = status_map.get("좌우 균형", "")
        mark = "X" if s == "bad" else ("OK" if s == "good" else "")
        lines.append(f"비대칭   {stats['asymmetry']}%  {mark}")
    if "v_oscillation" in stats:
        lines.append(f"수직 진폭  {stats['v_oscillation']} px")
    return "\n".join(lines)


def _assign_ratios(overlays: List[Dict], target_duration: float) -> None:
    """_start_seconds / _end_seconds → start_ratio / end_ratio 변환"""
    for ov in overlays:
        if "_start_seconds" in ov:
            ov["start_ratio"] = round(ov.pop("_start_seconds") / target_duration, 4)
        if "_end_seconds" in ov:
            ov["end_ratio"]   = round(ov.pop("_end_seconds")   / target_duration, 4)
