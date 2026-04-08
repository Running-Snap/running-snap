"""
KakaoTalk_Video_2026-04-03-21-23-30.mp4 → 3가지 버전 생성
  1. 자세분석버전  (MediaPipe 스켈레톤 + FeedbackJsonConverter)
  2. 인증버전      (기록 인증 카드)
  3. 베스트컷버전  (동적 멀티컷)

실제 피드백 JSON:
  score=60, cadence=73.8, asymmetry=30.7, elbow_angle=98.2
"""
import sys, os, json, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor            import TemplateExecutor
from src.feedback_json_to_instruction import FeedbackJsonConverter
from src.pose_skeleton_renderer       import apply_skeleton_feedback
from moviepy import VideoFileClip, concatenate_videoclips

# ── 공통 설정 ────────────────────────────────────────────────────────
SRC_RAW  = "/Users/khy/Downloads/KakaoTalk_Video_2026-04-03-21-23-30.mp4"
OUT_DIR  = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
FFMPEG = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"

RUN_DATE    = "2026.04.03"
DISTANCE_KM = 3.8
PACE_STR    = "6'42\"/km"

# ── 피드백 JSON ──────────────────────────────────────────────────────
FEEDBACK_DATA = {
    "score": 60,
    "feedbacks": [
        {"title": "케이던스",    "status": "bad",     "message": "케이던스 73.8 SPM — 발걸음이 너무 느립니다"},
        {"title": "착지",        "status": "warning",  "message": "약간의 오버스트라이드 — 착지를 몸 중심에 가깝게 조정하세요"},
        {"title": "팔꿈치 각도", "status": "good",    "message": "팔꿈치 98.2° — 이상적인 각도입니다"},
        {"title": "좌우 균형",   "status": "bad",     "message": "좌우 비대칭 30.7% — 부상 위험, 코어·둔근 강화 권장"},
    ],
    "pose_stats": {
        "cadence": 73.8, "v_oscillation": 75.6,
        "avg_impact_z": 0.187, "asymmetry": 30.7, "elbow_angle": 98.2,
    },
}


# ════════════════════════════════════════════════════════════════════
# 공통 전처리: rotation fix + 3x 루프
# ════════════════════════════════════════════════════════════════════
def preprocess(tmpdir: str):
    """rotation fix → 3x loop → (loop_path, src_duration)"""
    fixed = os.path.join(tmpdir, "fixed.mp4")
    loop  = os.path.join(tmpdir, "loop.mp4")

    print("[전처리] rotation fix...")
    os.system(
        f'"{FFMPEG}" -y -i "{SRC_RAW}" '
        f'-c:v libx264 -preset fast -crf 18 -an "{fixed}" -loglevel error'
    )

    import cv2
    cap = cv2.VideoCapture(fixed)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"  변환: {W}x{H}  {n}f @ {fps:.0f}fps  ({n/fps:.2f}s)")

    print("[전처리] 3x 루프...")
    clip = VideoFileClip(fixed)
    looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
    looped.write_videofile(loop, codec="libx264", audio_codec="aac",
                           fps=30, preset="fast", threads=4, logger=None)
    dur = looped.duration
    looped.close(); clip.close()
    print(f"  루프: {dur:.1f}s\n")
    return loop, dur


# ════════════════════════════════════════════════════════════════════
# 1. 자세분석버전 — MediaPipe 스켈레톤 + 피드백 오버레이
# ════════════════════════════════════════════════════════════════════
def make_pose_analysis(loop_path: str, src_dur: float, tmpdir: str) -> str:
    print("=" * 60)
    print("  [1/3] 자세분석버전")
    print("=" * 60)

    skel = os.path.join(tmpdir, "loop_skel.mp4")
    apply_skeleton_feedback(
        loop_path, skel, FEEDBACK_DATA,
        loop_count=3, model_path="models/pose_landmarker_full.task",
    )
    src = skel if Path(skel).exists() else loop_path

    converter   = FeedbackJsonConverter()
    instruction = converter.convert(FEEDBACK_DATA, source_duration=src_dur)

    out = str(OUT_DIR / f"kakao_pose_{ts}.mp4")
    TemplateExecutor(verbose=True).execute(instruction, src, out)
    print(f"  → {out} ({Path(out).stat().st_size/1024/1024:.1f} MB)\n")
    return out


# ════════════════════════════════════════════════════════════════════
# 2. 인증버전
# ════════════════════════════════════════════════════════════════════
CERT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "kakao_cert_v1",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 7.0,
        "color_grade": "warm",
        "vibe_tags": ["record", "certification", "spring", "road"],
    },
    "timeline": {
        "total_duration_seconds": 7.0,
        "narrative_flow": "intro → buildup → peak_slowmo → stats_reveal",
        "segments": [
            {"id": "seg_0", "type": "intro",       "start_ratio": 0.00, "end_ratio": 0.28, "speed": 1.0},
            {"id": "seg_1", "type": "buildup",      "start_ratio": 0.28, "end_ratio": 0.52, "speed": 1.0},
            {"id": "seg_2", "type": "peak",         "start_ratio": 0.52, "end_ratio": 0.62, "speed": 0.4},
            {"id": "seg_3", "type": "stats_reveal", "start_ratio": 0.62, "end_ratio": 1.00, "speed": 1.0},
        ],
        "cuts": [
            {"position_ratio": 0.28, "type": "hard_cut"},
            {"position_ratio": 0.52, "type": "flash"},
            {"position_ratio": 0.62, "type": "hard_cut"},
        ],
    },
    "speed_changes": [{"start_ratio": 0.52, "end_ratio": 0.62, "speed": 0.4}],
    "effects": [
        {"type": "zoom_in",  "start_ratio": 0.00, "end_ratio": 0.28, "intensity": 0.08},
        {"type": "zoom_in",  "start_ratio": 0.52, "end_ratio": 0.62, "intensity": 0.12},
        {"type": "vignette", "start_ratio": 0.00, "end_ratio": 1.00, "intensity": 0.35},
    ],
    "overlays": [
        {
            "id": "ov_title", "type": "text", "content": "SPRING\nRUN",
            "position_pct": {"x": 50, "y": 12},
            "start_ratio": 0.0, "end_ratio": 0.28,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 700, "font_size_ratio": 0.082,
                      "color": "#FFFFFF", "opacity": 0.95},
        },
        {
            "id": "ov_score_label", "type": "text", "content": "TODAY'S SCORE",
            "position_pct": {"x": 50, "y": 28},
            "start_ratio": 0.62, "end_ratio": 1.0,
            "animation_in": "fade_in",
            "style": {"font_weight": 300, "font_size_ratio": 0.032,
                      "color": "#FFDDAA", "opacity": 0.85},
        },
        {
            "id": "ov_score", "type": "counter", "content": f"{FEEDBACK_DATA['score']}",
            "position_pct": {"x": 50, "y": 42},
            "start_ratio": 0.62, "end_ratio": 1.0,
            "counter_config": {
                "start_value": 0, "end_value": FEEDBACK_DATA["score"],
                "unit": "", "decimal_places": 0, "count_up": True, "easing": "ease_out",
            },
            "style": {"font_weight": 900, "font_size_ratio": 0.16,
                      "color": "#FFAA33", "opacity": 1.0},
        },
        {
            "id": "ov_dist_label", "type": "text", "content": "DISTANCE",
            "position_pct": {"x": 50, "y": 60},
            "start_ratio": 0.62, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.030,
                      "color": "#FFDDAA", "opacity": 0.80},
        },
        {
            "id": "ov_dist", "type": "text", "content": f"{DISTANCE_KM} km  /  {PACE_STR}",
            "position_pct": {"x": 50, "y": 68},
            "start_ratio": 0.62, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.048,
                      "color": "#FFFFFF", "opacity": 0.92},
        },
        {
            "id": "ov_date", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.62, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.030,
                      "color": "#FFDDBB", "opacity": 0.70},
        },
    ],
    "color_grade": {
        "overall_tone": "warm",
        "adjustment_params": {"brightness": 5, "contrast": 15, "saturation": 8, "temperature": 15},
    },
}


def make_cert_video(loop_path: str) -> str:
    print("=" * 60)
    print("  [2/3] 인증버전")
    print("=" * 60)
    out = str(OUT_DIR / f"kakao_cert_{ts}.mp4")
    TemplateExecutor(verbose=True).execute(CERT_INSTRUCTION, loop_path, out)
    print(f"  → {out} ({Path(out).stat().st_size/1024/1024:.1f} MB)\n")
    return out


# ════════════════════════════════════════════════════════════════════
# 3. 베스트컷버전
# ════════════════════════════════════════════════════════════════════
BESTCUT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "kakao_bestcut_v1",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 10.0,
        "color_grade": "vibrant",
        "crop_zoom": 1.0,
        "vibe_tags": ["bestcut", "dynamic", "spring", "cinematic"],
    },
    "timeline": {
        "total_duration_seconds": 10.0,
        "narrative_flow": "wide → runner_approach → slowmo_close → cutback → freeze_title",
        "segments": [
            # ① 오프닝: 배경 와이드 (벚꽃 도로)
            {
                "id": "cut_0", "type": "intro",
                "source_start_sec": 0.0, "source_end_sec": 1.8,
                "shot_type": "wide", "speed": 1.0,
                "start_ratio": 0.00, "end_ratio": 0.18,
                "description": "벚꽃 도로 와이드 오프닝",
            },
            # ② 러너 접근 — 실제 속도
            {
                "id": "cut_1", "type": "buildup",
                "source_start_sec": 1.5, "source_end_sec": 3.2,
                "shot_type": "medium", "speed": 1.0,
                "start_ratio": 0.18, "end_ratio": 0.40,
                "description": "러너 접근 — 자연스러운 속도",
            },
            # ③ 슬로우 클로즈업 — 러너 가까울 때
            {
                "id": "cut_2", "type": "peak",
                "source_start_sec": 3.8, "source_end_sec": 5.0,
                "shot_type": "close_up", "speed": 0.35,
                "start_ratio": 0.40, "end_ratio": 0.62,
                "description": "슬로우 클로즈업 0.35×",
            },
            # ④ 2루프 구간 컷백 — 속도감 복귀
            {
                "id": "cut_3", "type": "action",
                "source_start_sec": 6.7, "source_end_sec": 8.0,
                "shot_type": "medium", "speed": 1.0,
                "start_ratio": 0.62, "end_ratio": 0.75,
                "description": "2루프 컷백 복귀",
            },
            # ⑤ 울트라 슬로우 클로즈업 (3루프)
            {
                "id": "cut_4", "type": "peak2",
                "source_start_sec": 10.5, "source_end_sec": 11.2,
                "shot_type": "close_up", "speed": 0.28,
                "start_ratio": 0.75, "end_ratio": 0.86,
                "description": "울트라 슬로우 0.28×",
            },
            # ⑥ 타이틀 freeze 카드
            {
                "id": "cut_5", "type": "freeze",
                "source_start_sec": 4.2, "source_end_sec": 4.2,
                "freeze_duration": 1.4,
                "shot_type": "close_up", "speed": 1.0,
                "start_ratio": 0.86, "end_ratio": 1.00,
                "description": "타이틀 카드 freeze",
            },
        ],
        "cuts": [
            {"position_ratio": 0.18,  "type": "hard_cut"},
            {"position_ratio": 0.40,  "type": "flash"},
            {"position_ratio": 0.62,  "type": "hard_cut"},
            {"position_ratio": 0.75,  "type": "flash"},
            {"position_ratio": 0.86,  "type": "dissolve"},
        ],
    },
    "speed_changes": [
        {"start_ratio": 0.40, "end_ratio": 0.62, "speed": 0.35},
        {"start_ratio": 0.75, "end_ratio": 0.86, "speed": 0.28},
    ],
    "effects": [
        {"type": "zoom_in",  "start_ratio": 0.00, "end_ratio": 0.18,  "intensity": 0.05},
        {"type": "zoom_in",  "start_ratio": 0.18, "end_ratio": 0.40,  "intensity": 0.12},
        {"type": "zoom_in",  "start_ratio": 0.40, "end_ratio": 0.62,  "intensity": 0.18},
        {"type": "zoom_in",  "start_ratio": 0.75, "end_ratio": 0.86,  "intensity": 0.15},
        {"type": "vignette", "start_ratio": 0.00, "end_ratio": 1.00,  "intensity": 0.40},
    ],
    "overlays": [
        # 오프닝 날짜
        {
            "id": "ov_date_top", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 88, "y": 8},
            "start_ratio": 0.0, "end_ratio": 0.18,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 300, "font_size_ratio": 0.028,
                      "color": "#FFFFCC", "opacity": 0.75},
        },
        # 슬로우 배속 표시
        {
            "id": "ov_slo1", "type": "text", "content": "0.35×",
            "position_pct": {"x": 12, "y": 90},
            "start_ratio": 0.40, "end_ratio": 0.62,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 700, "font_size_ratio": 0.034,
                      "color": "#FFAA33", "opacity": 0.85},
        },
        {
            "id": "ov_slo2", "type": "text", "content": "0.28×",
            "position_pct": {"x": 12, "y": 90},
            "start_ratio": 0.75, "end_ratio": 0.86,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 700, "font_size_ratio": 0.034,
                      "color": "#FF6633", "opacity": 0.85},
        },
        # 타이틀 카드
        {
            "id": "ov_title", "type": "text", "content": "SPRING\nRUN",
            "position_pct": {"x": 50, "y": 32},
            "start_ratio": 0.86, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {"font_weight": 700, "font_size_ratio": 0.11,
                      "color": "#FFFFFF", "opacity": 0.95, "letter_spacing": 8},
        },
        {
            "id": "ov_stats", "type": "text",
            "content": f"SCORE {FEEDBACK_DATA['score']}  /  {DISTANCE_KM} km  /  {PACE_STR}",
            "position_pct": {"x": 50, "y": 64},
            "start_ratio": 0.86, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {"font_weight": 300, "font_size_ratio": 0.032,
                      "color": "#FFEECC", "opacity": 0.88},
        },
        {
            "id": "ov_date_bot", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.86, "end_ratio": 1.00,
            "animation_in": "fade_in",
            "style": {"font_weight": 300, "font_size_ratio": 0.026,
                      "color": "#CCBBAA", "opacity": 0.65},
        },
    ],
    "color_grade": {
        "overall_tone": "vibrant",
        "adjustment_params": {
            "brightness": 8, "contrast": 20, "saturation": 15, "temperature": 10,
        },
    },
}


def make_bestcut_video(loop_path: str) -> str:
    print("=" * 60)
    print("  [3/3] 베스트컷버전")
    print("=" * 60)
    for seg in BESTCUT_INSTRUCTION["timeline"]["segments"]:
        s = seg.get("source_start_sec", "?"); e = seg.get("source_end_sec", "?")
        spd = seg.get("speed", 1.0); frz = seg.get("freeze_duration")
        if frz:
            print(f"    [{seg['id']}] freeze {frz}s  — {seg['description']}")
        else:
            print(f"    [{seg['id']}] {s:.1f}~{e:.1f}s  x{spd}  — {seg['description']}")

    out = str(OUT_DIR / f"kakao_bestcut_{ts}.mp4")
    TemplateExecutor(verbose=True).execute(BESTCUT_INSTRUCTION, loop_path, out)
    print(f"  → {out} ({Path(out).stat().st_size/1024/1024:.1f} MB)\n")
    return out


# ════════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        loop_path, src_dur = preprocess(tmpdir)

        pose_out    = make_pose_analysis(loop_path, src_dur, tmpdir)
        cert_out    = make_cert_video(loop_path)
        bestcut_out = make_bestcut_video(loop_path)

    print("=" * 60)
    print("  전체 완료!")
    print(f"  자세분석 : {pose_out}")
    print(f"  인증영상  : {cert_out}")
    print(f"  베스트컷  : {bestcut_out}")
    print("=" * 60)
