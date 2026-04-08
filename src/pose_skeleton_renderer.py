"""
pose_skeleton_renderer.py  (v2)
================================
MediaPipe skeleton을 소스 영상에 입히는 렌더러.

개선사항 (v2):
  - 자동 회전 감지: 세로 영상은 CW90 스킵
  - RunningMode.VIDEO → MediaPipe 내부 temporal smoothing → 지터 제거
  - 피드백 JSON 타임라인 직접 지원 (build_feedback_timeline)
  - 어두운 환경 강화: 글로우 강도 1.5배, 검정 외곽선 2배 두꺼이
  - visibility threshold 0.0 (어두운 야간 영상 발/다리 포함)

파이프라인:
    [원본 소스] → [skeleton 오버레이] → [template_executor 편집] → [출력]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# ── MediaPipe 연결 정의 ───────────────────────────────────────────
CONNECTIONS = [
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (11, 23), (12, 24),
    (23, 24),
    (23, 25), (25, 27), (27, 29), (27, 31),
    (24, 26), (26, 28), (28, 30), (28, 32),
]

LEFT_SET  = {11, 13, 15, 23, 25, 27, 29, 31}
RIGHT_SET = {12, 14, 16, 24, 26, 28, 30, 32}

_DEFAULT_COLOR = (200, 200, 200)
_DIM_ALPHA     = 0.25   # 흐린 배경 레이어

# ── 단일 하이라이트 색상 ──────────────────────────────────────────
# 모든 피드백 섹션에서 동일한 색으로 강조 — 어느 부위든 같은 색, 관절 위치만 달라짐
# BGR 기준: (0, 80, 255) = 주황-빨강
HIGHLIGHT_COLOR: Tuple[int, int, int] = (0, 80, 255)

# ── 피드백 title → 강조할 랜드마크 인덱스 ────────────────────────
#
# MediaPipe 33개 랜드마크 인덱스:
#   어깨:   11(왼), 12(오)   |   팔꿈치: 13(왼), 14(오)   |   손목: 15(왼), 16(오)
#   엉덩이: 23(왼), 24(오)   |   무릎:   25(왼), 26(오)
#   발목:   27(왼), 28(오)   |   뒤꿈치: 29(왼), 30(오)   |   발끝: 31(왼), 32(오)

TITLE_MAP: Dict[str, List[int]] = {
    # 케이던스: 엉덩이·무릎·발목·발끝 — 하체 리듬 전체
    "케이던스":    [23, 24, 25, 26, 27, 28, 29, 30, 31, 32],

    # 착지: 무릎부터 발끝까지 — 충격 접지 포인트
    "착지":        [25, 26, 27, 28, 29, 30, 31, 32],

    # 팔꿈치 각도: 어깨·팔꿈치·손목 — 팔 전체 체인
    "팔꿈치 각도": [11, 12, 13, 14, 15, 16],

    # 좌우 균형: 양 어깨만 — 좌우 대칭 기준점
    "좌우 균형":   [11, 12],
}

# 부분 키워드 폴백 (title이 TITLE_MAP에 없을 때)
_KEYWORD_FALLBACK: List[Tuple[List[str], List[int]]] = [
    (["팔", "팔꿈치", "손목"],               [11, 12, 13, 14, 15, 16]),
    (["발", "착지", "발목", "오버스트라이드"], [25, 26, 27, 28, 29, 30, 31, 32]),
    (["케이던스", "보폭", "스트라이드"],      [23, 24, 25, 26, 27, 28]),
    (["균형", "좌우", "비대칭"],             [11, 12]),
    (["상체", "몸통", "골반"],              [11, 12, 23, 24]),
]


def _match_highlight(title: str, issue: str = "") -> Tuple[Optional[List[int]], Tuple, bool]:
    """
    피드백 title → (강조 랜드마크 리스트, BGR 색상, is_asymmetry).

    색상은 항상 HIGHLIGHT_COLOR (단일 색) — 부위별로 색이 다르지 않음.

    1순위: TITLE_MAP 정확 매칭
    2순위: TITLE_MAP 부분 포함 매칭
    3순위: _KEYWORD_FALLBACK 키워드 매칭
    """
    # 1순위: 정확 매칭
    if title in TITLE_MAP:
        return TITLE_MAP[title], HIGHLIGHT_COLOR, False

    # 2순위: 부분 포함
    for key, lm_list in TITLE_MAP.items():
        if key in title or title in key:
            return lm_list, HIGHLIGHT_COLOR, False

    # 3순위: 키워드 폴백
    text = title + " " + issue
    for keywords, lm_list in _KEYWORD_FALLBACK:
        if any(kw in text for kw in keywords):
            return lm_list, HIGHLIGHT_COLOR, False

    return None, _DEFAULT_COLOR, False


# ── 피드백 JSON 타임라인 생성 ─────────────────────────────────────

def _dist_ts(n: int, duration: float, padding: float = 0.10) -> List[float]:
    """duration 내에 n개 타임스탬프를 균등 분배 (양끝 padding 여백)."""
    if n == 0:
        return []
    start = duration * padding
    end   = duration * (1.0 - padding)
    if n == 1:
        return [round((start + end) / 2, 3)]
    step = (end - start) / (n - 1)
    return [round(start + i * step, 3) for i in range(n)]


def build_feedback_timeline(
    feedback_data: Dict[str, Any],
    source_duration: float,
    loop_count: int = 3,
    highlights: Optional[List[float]] = None,
) -> List[Dict]:
    """
    feedback JSON → skeleton highlight timeline.

    Args:
        feedback_data:   {"feedbacks": [...], ...}
        source_duration: 전체 소스(루프 포함) 길이 (초)
        loop_count:      루프 반복 횟수
        highlights:      Qwen 분석으로 얻은 타임스탬프 (초) — 제공 시 우선 사용
    """
    feedbacks = feedback_data.get("feedbacks", [])
    # frame 번호 오름차순 정렬 (시간 순서 보장)
    feedbacks = sorted(feedbacks, key=lambda f: f.get("frame", 0))
    n = len(feedbacks)
    one_loop = source_duration / max(loop_count, 1)

    # ── 타임스탬프 결정 (우선순위) ─────────────────────────────────
    # 1순위: feedbacks에 frame 번호가 있으면 frame → 비례 타임스탬프 변환
    # 2순위: Qwen highlights
    # 3순위: 균등 분배
    frame_nums = [f.get("frame", 0) for f in feedbacks]
    max_frame  = max(frame_nums) if frame_nums else 1

    def frame_to_ts(fn: int) -> float:
        ratio = fn / max(max_frame, 1)
        return round(one_loop * (0.05 + ratio * 0.85), 3)

    if any(fn > 0 for fn in frame_nums):
        raw_timestamps = [frame_to_ts(fn) for fn in frame_nums]
    elif highlights and len(highlights) >= n:
        raw_timestamps = [round(h, 3) for h in sorted(highlights)[:n]]
    else:
        raw_timestamps = _dist_ts(n, one_loop)

    # ── 한 루프 내 timeline 구간 생성 ─────────────────────────────
    single_loop_tl: List[Dict] = []
    for i, (fb, t) in enumerate(zip(feedbacks, raw_timestamps)):
        title = fb.get("title", "")
        lm_list, color, is_asym = _match_highlight(title)
        ts_start = max(0.0, t - 0.4)
        ts_end   = raw_timestamps[i + 1] if i + 1 < n else one_loop
        single_loop_tl.append({
            "ts_start":    ts_start,
            "ts_end":      ts_end,
            "lm_indices":  lm_list,
            "color":       color,
            "is_asymmetry": is_asym,
        })

    # 전체 루프로 확장
    full_tl: List[Dict] = []
    for loop_i in range(loop_count):
        offset = loop_i * one_loop
        for seg in single_loop_tl:
            full_tl.append({
                "ts_start":    seg["ts_start"] + offset,
                "ts_end":      min(seg["ts_end"] + offset, source_duration),
                "lm_indices":  seg["lm_indices"],
                "color":       seg["color"],
                "is_asymmetry": seg["is_asymmetry"],
            })

    return full_tl


def _build_source_timeline(parsed_json: Dict) -> List[Dict]:
    """기존 sections/findings 포맷 → timeline (하위 호환 유지)"""
    events = []
    for sec in parsed_json.get("sections", []):
        title = sec.get("title", "")
        lm_list, color, is_asym = _match_highlight(title)
        for f in sec.get("findings", []):
            ts    = f.get("timestamp_sec", 0.0)
            issue = f.get("issue", "")
            lm2, c2, ia2 = _match_highlight(title, issue) if not lm_list else (lm_list, color, is_asym)
            events.append({"ts": ts, "lm_indices": lm2, "color": c2, "is_asymmetry": ia2})

    events.sort(key=lambda e: e["ts"])
    timeline = []
    for i, ev in enumerate(events):
        ts_start = max(0.0, ev["ts"] - 0.5)
        ts_end   = events[i + 1]["ts"] if i + 1 < len(events) else 9999.0
        timeline.append({"ts_start": ts_start, "ts_end": ts_end,
                         "lm_indices": ev["lm_indices"], "color": ev["color"],
                         "is_asymmetry": ev["is_asymmetry"]})
    return timeline


def _get_highlight_at(timeline: List[Dict], t: float) -> Tuple:
    for seg in timeline:
        if seg["ts_start"] <= t < seg["ts_end"]:
            return seg["lm_indices"], seg["color"], seg["is_asymmetry"]
    return None, _DEFAULT_COLOR, False


# ── 네온 글로우 스켈레톤 렌더 ─────────────────────────────────────

def _neon(c: Tuple, mult: float = 1.0) -> Tuple:
    return tuple(min(255, int(v * mult)) for v in c)


def _draw_skeleton(
    frame: np.ndarray,
    landmarks: List,
    highlight_lm: Optional[List[int]],
    color: Tuple,
    is_asymmetry: bool = False,
) -> np.ndarray:
    H, W = frame.shape[:2]
    highlight_set = set(highlight_lm) if highlight_lm else set()

    def lm_px(idx):
        if idx >= len(landmarks):
            return None
        lm = landmarks[idx]
        if getattr(lm, "visibility", 1.0) < 0.0:
            return None
        x, y = int(lm.x * W), int(lm.y * H)
        if not (0 <= x < W and 0 <= y < H):
            return None
        return x, y

    def hi_color(idx):
        """하이라이트 관절 색상 — TITLE_MAP에서 정해진 단일 색상 반환"""
        return color

    # 사람 bbox 기반 크기 계산
    all_px = [lm_px(i) for i in range(33) if lm_px(i) is not None]
    if not all_px:
        return frame
    ys = [p[1] for p in all_px]
    person_h = max(max(ys) - min(ys), 1)

    # 작은 사람 보정 (320px 기준)
    size_scale = max(1.0, 320.0 / max(person_h, 1))
    lw_hi  = max(2, int(person_h * 0.010 * size_scale))  # 하이라이트 선
    lw_dim = max(1, int(person_h * 0.004 * size_scale))  # 배경 선
    r_hi   = max(3, int(person_h * 0.010 * size_scale))  # 하이라이트 관절 반지름
    r_dot  = max(2, int(person_h * 0.005 * size_scale))  # 배경 관절 반지름

    # ── Layer 1: 배경 skeleton — 전신 회색 (끊김 없이) ─────────────
    # skip 조건: 양 끝 모두 highlight일 때만 (한쪽만 highlight면 gray로 그려줌)
    # → 강조 관절에 연결된 뼈대도 회색으로 남아 스켈레톤 전체 이어짐
    DIM_COLOR = (185, 185, 185)
    dim_layer = frame.copy()
    for i, j in CONNECTIONS:
        if i in highlight_set and j in highlight_set:
            continue   # 둘 다 강조 → highlight 레이어에서 그림
        p1, p2 = lm_px(i), lm_px(j)
        if p1 is None or p2 is None:
            continue
        cv2.line(dim_layer, p1, p2, DIM_COLOR, lw_dim, cv2.LINE_AA)
    for idx in range(33):
        if idx in highlight_set:
            continue   # 강조 관절은 highlight 레이어에서 그림
        p = lm_px(idx)
        if p is None:
            continue
        cv2.circle(dim_layer, p, r_dot, DIM_COLOR, -1, cv2.LINE_AA)
    # 0.45 alpha → 회색 스켈레톤이 확실히 보임 (기존 0.22는 너무 희미)
    result = cv2.addWeighted(dim_layer, 0.45, frame, 0.55, 0)

    if not highlight_set:
        return result

    # ── Layer 2: 소프트 글로우 (하이라이트 부위만) ───────────────
    glow_layer = np.zeros_like(frame, dtype=np.uint8)
    for i, j in CONNECTIONS:
        if not (i in highlight_set or j in highlight_set):
            continue
        p1, p2 = lm_px(i), lm_px(j)
        if p1 is None or p2 is None:
            continue
        ci, cj = hi_color(i), hi_color(j)
        lc = ((ci[0]+cj[0])//2, (ci[1]+cj[1])//2, (ci[2]+cj[2])//2)
        cv2.line(glow_layer, p1, p2, _neon(lc, 1.8), lw_hi * 4, cv2.LINE_AA)
    for idx in highlight_set:
        p = lm_px(idx)
        if p is None:
            continue
        cv2.circle(glow_layer, p, r_hi * 3, _neon(hi_color(idx), 1.8), -1, cv2.LINE_AA)
    blur_k = max(5, (lw_hi * 6) | 1)
    result = cv2.addWeighted(result, 1.0,
                             cv2.GaussianBlur(glow_layer, (blur_k, blur_k), 0), 0.55, 0)

    # ── Layer 3: 선명한 하이라이트 선 ────────────────────────────
    for i, j in CONNECTIONS:
        if not (i in highlight_set or j in highlight_set):
            continue
        p1, p2 = lm_px(i), lm_px(j)
        if p1 is None or p2 is None:
            continue
        ci, cj = hi_color(i), hi_color(j)
        lc = ((ci[0]+cj[0])//2, (ci[1]+cj[1])//2, (ci[2]+cj[2])//2)
        cv2.line(result, p1, p2, (0, 0, 0),    lw_hi + 2, cv2.LINE_AA)  # 검정 외곽
        cv2.line(result, p1, p2, lc,            lw_hi,     cv2.LINE_AA)  # 컬러
        cv2.line(result, p1, p2, (230, 230, 230), max(1, lw_hi // 3), cv2.LINE_AA)  # 중앙 하이라이트

    # ── Layer 4: 링 스타일 관절 (하이라이트 전용) ─────────────────
    # 외곽 검정 링 → 컬러 링(아웃라인) → 내부 흰 점
    for idx in highlight_set:
        p = lm_px(idx)
        if p is None:
            continue
        c = hi_color(idx)
        cv2.circle(result, p, r_hi + 3, (0, 0, 0), 2,            cv2.LINE_AA)  # 검정 외곽
        cv2.circle(result, p, r_hi,     c,          2,            cv2.LINE_AA)  # 컬러 링
        cv2.circle(result, p, max(2, r_hi // 3), (255, 255, 255), -1, cv2.LINE_AA)  # 흰 내부 점

    return result


# ── 메인 함수 ─────────────────────────────────────────────────────

def apply_skeleton_to_source(
    source_video: str,
    output_video: str,
    parsed_json: Dict,
    model_path: str = "models/pose_landmarker_full.task",
) -> bool:
    """기존 sections/findings 포맷용 (하위 호환)"""
    timeline = _build_source_timeline(parsed_json)
    return _render_skeleton(source_video, output_video, timeline, model_path)


def apply_skeleton_feedback(
    source_video: str,
    output_video: str,
    feedback_data: Dict[str, Any],
    loop_count: int = 3,
    model_path: str = "models/pose_landmarker_full.task",
    highlights: Optional[List[float]] = None,
) -> bool:
    """피드백 JSON 포맷용 (v2)"""
    import cv2 as _cv2
    cap = _cv2.VideoCapture(source_video)
    raw_dur = cap.get(_cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(_cv2.CAP_PROP_FPS), 1)
    cap.release()
    timeline = build_feedback_timeline(
        feedback_data, source_duration=raw_dur,
        loop_count=loop_count, highlights=highlights,
    )
    return _render_skeleton(source_video, output_video, timeline, model_path)


def _render_skeleton(
    source_video: str,
    output_video: str,
    timeline: List[Dict],
    model_path: str,
) -> bool:
    print(f"[Skeleton v2] {source_video}")

    model_path_obj = Path(model_path)
    if not model_path_obj.exists():
        print(f"  [오류] 모델 없음: {model_path}")
        return False

    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker, PoseLandmarkerOptions, RunningMode,
    )

    # ── VIDEO 모드: MediaPipe 내부 temporal smoothing 활성화 ──────
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path_obj)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.50,
        min_pose_presence_confidence=0.50,
        min_tracking_confidence=0.50,
    )
    landmarker = PoseLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(source_video)
    raw_W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    raw_H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # ── 자동 회전 감지 (v2 핵심) ──────────────────────────────────
    # raw_H > raw_W → 이미 세로 → 회전 불필요
    # raw_W > raw_H → 가로 → CW90 필요
    needs_rotation = (raw_W > raw_H)
    out_W = raw_H if needs_rotation else raw_W
    out_H = raw_W if needs_rotation else raw_H
    print(f"  raw={raw_W}x{raw_H}  needs_rotation={needs_rotation}  out={out_W}x{out_H}  {total}f@{fps:.1f}")

    tmp_path = str(Path(output_video).with_suffix("")) + "_skel_tmp.avi"
    fourcc   = cv2.VideoWriter_fourcc(*"XVID")
    writer   = cv2.VideoWriter(tmp_path, fourcc, fps, (out_W, out_H))

    prev_lm = None
    for fi in range(total):
        ret, frame_raw = cap.read()
        if not ret:
            break
        t_ms = int(fi * 1000 / fps)
        t_s  = fi / fps

        # 회전 (필요한 경우만)
        frame = cv2.rotate(frame_raw, cv2.ROTATE_90_CLOCKWISE) if needs_rotation else frame_raw

        lm_list, color, is_asym = _get_highlight_at(timeline, t_s)

        # ── 원본 프레임 그대로 MediaPipe 탐지 (밝기 조작 없음) ────────
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detected = False
        try:
            res = landmarker.detect_for_video(mp_img, t_ms)
            if res.pose_landmarks:
                prev_lm  = res.pose_landmarks[0]
                detected = True
        except Exception:
            pass

        # 탐지 실패 시 이전 랜드마크 초기화 (오탐 잔류 방지)
        if not detected:
            prev_lm = None

        if prev_lm is not None:
            frame = _draw_skeleton(frame, prev_lm, lm_list, color, is_asym)

        writer.write(frame)
        if (fi + 1) % 15 == 0:
            print(f"  [{fi+1}/{total}] {t_s:.2f}s", end="\r", flush=True)

    print()
    cap.release()
    writer.release()
    landmarker.close()

    # ── 오디오 머지 ──────────────────────────────────────────────
    ffmpeg = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
    ret = os.system(
        f'"{ffmpeg}" -y -i "{tmp_path}" -i "{source_video}" '
        f'-c:v libx264 -crf 17 -preset fast '
        f'-c:a aac -map 0:v:0 -map 1:a:0 '
        f'"{output_video}" -loglevel error'
    )
    if ret != 0:
        os.system(f'"{ffmpeg}" -y -i "{tmp_path}" -c:v libx264 -crf 17 "{output_video}" -loglevel error')
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    size = Path(output_video).stat().st_size / 1024 / 1024 if Path(output_video).exists() else 0
    print(f"  [완료] {output_video} ({size:.1f} MB)")
    return True
