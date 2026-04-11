"""
instruction_builder.py
======================
style + source_info + (optional) feedback_data → EditInstruction dict

핵심 수정사항 (구 FeedbackJsonConverter 대비):
  1. 타임스탬프를 source_duration에 비례해 자동 분배
     → 하드코딩된 [0.7, 1.4, 2.0, 2.7] 제거
  2. status "warning" 지원 (WARN 뱃지, 노란색)
  3. 낮/야간 자동 컬러그레이딩 (style preset 사용)
  4. feedback 없는 순수 영상편집 모드 지원
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .style_presets import StylePreset, get_preset, score_to_color
from .preprocessor import VideoInfo


# ── 상수 ─────────────────────────────────────────────────────────────
LEAD_IN_RATIO  = 0.08   # slowmo lead-in: source_original_dur * 이 비율
OUTRO_DUR      = 2.0    # 아웃트로 길이 (초)
READING_CPS    = 11.0   # 한국어 읽기 속도 (자/초)
MIN_FREEZE     = 2.5    # 최소 freeze 길이 (초)

STATUS_COLOR = {
    "bad":     "#FF5533",
    "warning": "#FFCC22",
    "good":    "#44DD88",
}
STATUS_BADGE = {
    "bad":     "BAD",
    "warning": "WARN",
    "good":    "GOOD",
}


class InstructionBuilder:
    """
    EditInstruction 생성기.

    사용 예:
        builder = InstructionBuilder(style="instagram")
        instruction = builder.build(
            source_info=video_info,
            target_duration=30.0,
            feedback_data=feedback_json,   # 선택
        )
    """

    def __init__(self, style: str):
        self.style  = style
        self.preset = get_preset(style)

    # ════════════════════════════════════════════════════════════════
    # 공개 메서드
    # ════════════════════════════════════════════════════════════════

    def build(
        self,
        source_info: VideoInfo,
        target_duration: float,
        feedback_data: Optional[Dict[str, Any]] = None,
        highlights: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Args:
            source_info:     Preprocessor가 반환한 VideoInfo
            target_duration: 목표 출력 길이 (초)
            feedback_data:   {"score":, "feedbacks":[], "pose_stats":{}}
                             None이면 순수 베스트컷 모드
            highlights:      Qwen 분석으로 얻은 사용자 등장 타임스탬프 목록 (초).
                             제공되면 _distribute_timestamps 대신 이 값을 우선 사용.
        Returns:
            EditInstruction dict
        """
        if feedback_data:
            return self._build_feedback_instruction(
                source_info, target_duration, feedback_data, highlights
            )
        return self._build_bestcut_instruction(source_info, target_duration, highlights)

    # ════════════════════════════════════════════════════════════════
    # 피드백 기반 instruction
    # ════════════════════════════════════════════════════════════════

    def _build_feedback_instruction(
        self,
        info: VideoInfo,
        target_duration: float,
        data: Dict[str, Any],
        highlights: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        자세분석 영상 Instruction 생성.

        영상은 처음부터 끝까지 단 한 번만 재생.
        각 피드백 프레임에서 슬로우모 → 프리즈 → 텍스트 표시 후 계속 진행.
        피드백은 frame 번호 오름차순(= 시간순)으로 처리.
        스코어 인트로 카드 / 스탯 카드 제거.
        """
        p      = self.preset
        fbs_raw = data.get("feedbacks", [])
        orig_dur = info.original_duration or info.duration

        # ── 1. 프레임 순서 정렬 (frame 번호 오름차순) ──────────────
        fbs = sorted(fbs_raw, key=lambda f: f.get("frame", 0))

        # ── 2. 타임스탬프 결정 ─────────────────────────────────────
        # frame 번호 → orig_dur 내 비례 위치 매핑 (5%~95% 범위)
        frame_nums = [f.get("frame", 0) for f in fbs]
        max_frame  = max(frame_nums) if frame_nums else 1

        def frame_to_ts(fn: int) -> float:
            ratio = fn / max(max_frame, 1)
            return round(orig_dur * (0.05 + ratio * 0.85), 3)

        # frame 번호가 명시된 경우 항상 우선 — highlights보다 더 정확한 위치
        if any(f.get("frame") for f in fbs):
            timestamps = [frame_to_ts(fn) for fn in frame_nums]
        elif highlights and len(highlights) >= len(fbs):
            timestamps = [round(h, 3) for h in sorted(highlights)[:len(fbs)]]
        else:
            timestamps = _distribute_timestamps(len(fbs), orig_dur)

        segments:  List[Dict] = []
        overlays:  List[Dict] = []
        cur_t  = 0.0
        seg_n  = 0
        prev_src = 0.0
        lead_in  = orig_dur * LEAD_IN_RATIO

        # ── 3-0. 스코어 인트로 (처음 3초: 점수 카운트업 + freeze) ──
        score = data.get("score", 0)
        SCORE_INTRO_DUR = 3.0
        if score > 0:
            segments.append(_freeze_seg(seg_n, 0.0, SCORE_INTRO_DUR))
            overlays += _score_intro_overlays(score, p, cur_t, cur_t + SCORE_INTRO_DUR)
            cur_t += SCORE_INTRO_DUR
            seg_n += 1
            # prev_src = 0.0 유지 — 인트로 후 영상은 처음부터 재생

        # ── 3. 피드백 섹션 (한 번만 재생) ─────────────────────────
        for i, (fb, t_src) in enumerate(zip(fbs, timestamps)):
            lead_start = max(prev_src, t_src - lead_in)

            # ① normal — 이전 지점 → slowmo 시작점
            if lead_start > prev_src + 0.05:
                segments.append(_normal_seg(seg_n, prev_src, lead_start))
                cur_t += lead_start - prev_src
                seg_n += 1

            # ② slowmo lead-in
            slowmo_src_dur = max(t_src - lead_start, 0.05)
            slowmo_out_dur = slowmo_src_dur / p.slowmo_speed
            segments.append(_slowmo_seg(seg_n, lead_start, t_src, p.slowmo_speed))
            cur_t += slowmo_out_dur
            seg_n += 1

            # ③ freeze + 피드백 텍스트
            msg    = fb.get("message", "")
            f_dur  = max(p.freeze_dur, len(msg) / READING_CPS)
            status = fb.get("status", "good").lower()
            col    = STATUS_COLOR.get(status, STATUS_COLOR["good"])
            badge  = STATUS_BADGE.get(status, "GOOD")
            title  = fb.get("title", "")

            segments.append(_freeze_seg(seg_n, t_src, round(f_dur, 2)))
            f_start = cur_t
            f_end   = cur_t + f_dur
            cur_t   = f_end
            seg_n  += 1

            overlays += _feedback_overlays(i, badge, title, msg, col, f_start, f_end)
            prev_src = t_src

        # ── 4. 마지막 피드백 이후 → 영상 끝까지 normal 재생 ───────
        if prev_src < orig_dur - 0.1:
            segments.append(_normal_seg(seg_n, prev_src, orig_dur))
            cur_t += orig_dur - prev_src
            seg_n += 1

        # ── 5. ratio 계산 + instruction 조립 ──────────────────────
        total_dur = round(cur_t, 2)
        _assign_ratios(overlays, total_dur)

        return self._wrap(segments, overlays, total_dur, p)

    # ════════════════════════════════════════════════════════════════
    # 순수 베스트컷 instruction (feedback 없음)
    # ════════════════════════════════════════════════════════════════

    def _build_bestcut_instruction(
        self,
        info: VideoInfo,
        target_duration: float,
        highlights: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """스타일 기반 자동 멀티컷 instruction 생성"""
        p     = self.preset
        src   = info.duration
        orig  = info.original_duration or src

        # 컷 수: 리듬별
        n_cuts = {"fast": 6, "medium": 4, "slow": 3}.get(p.cut_rhythm, 4)
        segs: List[Dict] = []
        ovs:  List[Dict] = []

        # 구간 분배: Qwen highlights 우선, 없으면 균등 분배
        if highlights and len(highlights) >= n_cuts:
            src_points = [round(h, 3) for h in highlights[:n_cuts]]
        else:
            src_points = _distribute_timestamps(n_cuts, orig, padding=0.05)

        # 각 구간 길이
        seg_targets = [target_duration / n_cuts] * n_cuts

        n = 0
        for i, t in enumerate(src_points):
            half = orig / n_cuts / 2
            s_start = max(0.0, t - half)
            s_end   = min(orig, t + half)

            is_peak = (i == n_cuts // 2)   # 중간 구간 슬로우
            speed   = p.slowmo_speed if is_peak else 1.0
            seg_type = "peak" if is_peak else ("intro" if i == 0 else "action")

            segs.append({
                "id": f"cut_{n:02d}", "type": seg_type,
                "source_start_sec": round(s_start, 3),
                "source_end_sec":   round(s_end, 3),
                "speed": speed,
                "start_ratio": 0.0, "end_ratio": 0.0,
            })
            n += 1

        # 마지막: freeze 타이틀 카드
        segs.append({
            "id": f"cut_{n:02d}", "type": "freeze",
            "source_start_sec": src_points[n_cuts // 2],
            "source_end_sec":   src_points[n_cuts // 2],
            "freeze_duration": 1.5,
            "start_ratio": 0.0, "end_ratio": 0.0,
        })

        return self._wrap(segs, ovs, target_duration, p)

    # ════════════════════════════════════════════════════════════════
    # 공통: EditInstruction 포장
    # ════════════════════════════════════════════════════════════════

    def _wrap(
        self,
        segments: List[Dict],
        overlays: List[Dict],
        total_dur: float,
        p: StylePreset,
    ) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "template_id": f"{self.style}_v1",
            "meta": {
                "aspect_ratio": "9:16",
                "target_duration_seconds": total_dur,
                "color_grade": p.color_tone,
                "crop_zoom": p.crop_zoom,
                "vibe_tags": [self.style],
            },
            "timeline": {
                "total_duration_seconds": total_dur,
                "segments": segments,
                "cuts": [],
            },
            "speed_changes": [],
            "effects": [
                {"type": "vignette", "start_ratio": 0.0,
                 "end_ratio": 1.0, "intensity": p.vignette},
            ],
            "overlays": overlays,
            "color_grade": {
                "overall_tone": p.color_tone,
                "adjustment_params": {
                    "brightness":  p.brightness,
                    "contrast":    p.contrast,
                    "saturation":  p.saturation,
                    "temperature": p.temperature,
                },
            },
        }


# ════════════════════════════════════════════════════════════════════
# 세그먼트 헬퍼
# ════════════════════════════════════════════════════════════════════

def _freeze_seg(n: int, src_t: float, dur: float) -> Dict:
    return {
        "id": f"seg_{n:02d}_freeze", "type": "freeze",
        "source_start_sec": src_t, "source_end_sec": src_t,
        "freeze_duration": dur,
        "start_ratio": 0.0, "end_ratio": 0.0,
    }

def _normal_seg(n: int, src_s: float, src_e: float) -> Dict:
    return {
        "id": f"seg_{n:02d}_normal", "type": "normal",
        "source_start_sec": src_s, "source_end_sec": src_e,
        "speed": 1.0, "start_ratio": 0.0, "end_ratio": 0.0,
    }

def _slowmo_seg(n: int, src_s: float, src_e: float, speed: float) -> Dict:
    return {
        "id": f"seg_{n:02d}_slowmo", "type": "peak",
        "source_start_sec": src_s, "source_end_sec": src_e,
        "speed": speed, "start_ratio": 0.0, "end_ratio": 0.0,
    }


# ════════════════════════════════════════════════════════════════════
# 오버레이 헬퍼
# ════════════════════════════════════════════════════════════════════

def _feedback_overlays(
    i: int, badge: str, title: str, msg: str,
    col: str, t_start: float, t_end: float,
) -> List[Dict]:
    return [
        # BAD / WARN / GOOD — 영문 뱃지 (얇게, 작게, 컬러)
        {
            "id": f"ov_{i}_badge", "type": "text", "content": badge,
            "position_pct": {"x": 50, "y": 11},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 300, "font_size_ratio": 0.030,
                      "color": col, "opacity": 0.80},
        },
        # 제목 — SemiBold, 크고 선명하게
        {
            "id": f"ov_{i}_title", "type": "text", "content": title,
            "position_pct": {"x": 50, "y": 18},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "animation_in": "fade_in",
            "style": {"font_weight": 600, "font_size_ratio": 0.068,
                      "color": col, "opacity": 1.0},
        },
        # 메시지 — Light, 읽기 편하게
        {
            "id": f"ov_{i}_msg", "type": "text", "content": msg,
            "position_pct": {"x": 50, "y": 73},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "style": {"font_weight": 300, "font_size_ratio": 0.036,
                      "color": "#FFFFFF", "opacity": 0.88},
        },
    ]


def _stats_overlays(
    score: int, stats: Dict, fbs: List, p: StylePreset,
    t_start: float, t_end: float,
) -> List[Dict]:
    status_map = {fb["title"]: fb.get("status", "") for fb in fbs}

    def mark(title: str) -> str:
        s = status_map.get(title, "")
        return {"bad": "X", "warning": "!", "good": "OK"}.get(s, "")

    lines = []
    if "cadence"       in stats: lines.append(f"케이던스    {stats['cadence']} SPM  {mark('케이던스')}")
    if "elbow_angle"   in stats: lines.append(f"팔꿈치 각도  {stats['elbow_angle']}°  {mark('팔꿈치 각도')}")
    if "avg_impact_z"  in stats: lines.append(f"착지 충격   {stats['avg_impact_z']}  {mark('착지')}")
    if "asymmetry"     in stats: lines.append(f"비대칭      {stats['asymmetry']}%  {mark('좌우 균형')}")
    if "v_oscillation" in stats: lines.append(f"수직 진폭   {stats['v_oscillation']} px")

    sc = score_to_color(score, p)

    return [
        {
            "id": "ov_stats_score_label", "type": "text", "content": "SCORE",
            "position_pct": {"x": 50, "y": 12},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "style": {"font_weight": 300, "font_size_ratio": 0.030,
                      "color": "#AADDFF", "opacity": 0.80},
        },
        {
            "id": "ov_stats_score_num", "type": "counter", "content": f"{score}",
            "position_pct": {"x": 50, "y": 22},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "counter_config": {"start_value": 0, "end_value": score,
                               "unit": "", "decimal_places": 0,
                               "count_up": True, "easing": "ease_out"},
            "style": {"font_weight": 900, "font_size_ratio": 0.13,
                      "color": sc, "opacity": 1.0},
        },
        {
            "id": "ov_stats_body", "type": "text", "content": "\n".join(lines),
            "position_pct": {"x": 50, "y": 62},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "style": {"font_weight": 300, "font_size_ratio": 0.036,
                      "color": "#DDEEFF", "opacity": 0.90},
        },
    ]


def _score_intro_overlays(
    score: int, p: StylePreset, t_start: float, t_end: float,
) -> List[Dict]:
    sc = score_to_color(score, p)
    return [
        {
            "id": "ov_score_intro_label", "type": "text",
            "content": "TODAY'S SCORE",
            "position_pct": {"x": 50, "y": 35},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "animation_in": "fade_in",
            "style": {"font_weight": 300, "font_size_ratio": 0.032,
                      "color": "#AADDFF", "opacity": 0.80},
        },
        {
            "id": "ov_score_intro_num", "type": "counter", "content": f"{score}",
            "position_pct": {"x": 50, "y": 52},
            "_start_seconds": t_start, "_end_seconds": t_end,
            "counter_config": {"start_value": 0, "end_value": score,
                               "unit": "", "decimal_places": 0,
                               "count_up": True, "easing": "ease_out"},
            "style": {"font_weight": 900, "font_size_ratio": 0.20,
                      "color": sc, "opacity": 1.0},
        },
    ]


# ════════════════════════════════════════════════════════════════════
# 타임스탬프 분배
# ════════════════════════════════════════════════════════════════════

def _distribute_timestamps(
    n: int,
    source_duration: float,
    padding: float = 0.10,
) -> List[float]:
    """
    source_duration 안에 N개 타임스탬프를 균등 분배.

    padding=0.10 → 앞뒤 10% 여백 (첫 프레임/마지막 프레임 피함)
    """
    if n == 0:
        return []
    start = source_duration * padding
    end   = source_duration * (1.0 - padding)
    if n == 1:
        return [round((start + end) / 2, 3)]
    step = (end - start) / (n - 1)
    return [round(start + i * step, 3) for i in range(n)]


def _assign_ratios(overlays: List[Dict], total_duration: float) -> None:
    """_start_seconds / _end_seconds → start_ratio / end_ratio 변환"""
    for ov in overlays:
        if "_start_seconds" in ov:
            ov["start_ratio"] = round(ov.pop("_start_seconds") / total_duration, 4)
        if "_end_seconds" in ov:
            ov["end_ratio"]   = round(ov.pop("_end_seconds")   / total_duration, 4)
