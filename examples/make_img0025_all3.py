"""
IMG_0025_black1.mov → 3가지 버전 동시 생성
  1. 자세분석버전  (run_pose_analysis 파이프라인)
  2. 인증버전      (record_cert 템플릿 재실행)
  3. 베스트컷버전  (새 동적 멀티컷 템플릿)
"""
import sys, os, json, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor      import TemplateExecutor
from src.pose_analysis_parser   import PoseAnalysisParser
from src.pose_to_chronological  import PoseToChronological

try:
    from moviepy import VideoFileClip, concatenate_videoclips
    HAS_MOVIEPY = True
except ImportError:
    HAS_MOVIEPY = False

# ─── 공통 설정 ─────────────────────────────────────────────────────
SRC_VIDEO    = "/Users/khy/Downloads/IMG_0025_black1.mov"
ANALYSIS_TXT = "data/sample_pose_analysis.txt"
OUT_DIR      = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

RUN_DATE    = "2026.04.02"
DISTANCE_KM = 5.2
PACE_STR    = "5'47\"/km"

# ─── 소스 루프 전처리 (2.9s → 8.7s) ──────────────────────────────
def make_looped_source(tmpdir: str) -> str:
    """원본이 짧아서 3x 루프 임시 파일 생성"""
    loop_path = os.path.join(tmpdir, "looped_src.mp4")
    print("  [전처리] 소스 3x 루프...")
    clip = VideoFileClip(SRC_VIDEO)
    looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
    looped.write_videofile(
        loop_path, codec="libx264", audio_codec="aac",
        fps=30, preset="fast", threads=4, logger=None,
    )
    dur = looped.duration
    looped.close(); clip.close()
    print(f"  [전처리] 완료: {dur:.1f}s → {loop_path}")
    return loop_path, dur


# ═══════════════════════════════════════════════════════════════════
# 1. 자세분석버전
# ═══════════════════════════════════════════════════════════════════

def make_pose_analysis(loop_path: str, src_dur: float):
    print("\n" + "=" * 60)
    print("  [1/3] 자세분석버전 생성")
    print("=" * 60)

    # 분석 파싱
    parser = PoseAnalysisParser()
    analysis = parser.parse_file(ANALYSIS_TXT)
    print(f"  섹션 {len(analysis['sections'])}개 파싱 완료")
    for s in analysis["sections"]:
        print(f"    Rank {s['rank']}: {s['title']} ({len(s['findings'])}건)")

    # EditInstruction 생성
    converter = PoseToChronological()
    instruction, tts_script = converter.convert(analysis, source_duration=src_dur)

    print(f"  세그먼트 {len(instruction['timeline']['segments'])}개")
    print(f"  오버레이 {len(instruction['overlays'])}개")
    print(f"  목표 길이: {instruction['meta']['target_duration_seconds']:.1f}s")

    out_path = str(OUT_DIR / f"IMG0025_pose_{ts}.mp4")
    executor = TemplateExecutor(verbose=True)
    executor.execute(instruction, loop_path, out_path)

    # SRT 자막 저장
    srt_path = str(OUT_DIR / f"IMG0025_pose_{ts}.srt")
    _save_srt(instruction, srt_path)

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"  → 완료: {out_path} ({size_mb:.1f} MB)")
    return out_path


def _save_srt(instruction: dict, srt_path: str) -> None:
    total = instruction["meta"]["target_duration_seconds"]
    subtitle_ovs = [
        ov for ov in instruction["overlays"]
        if ov["id"].startswith(("issue_", "correction_", "corr_"))
    ]
    subtitle_ovs.sort(key=lambda o: o["start_ratio"])

    def to_srt_time(sec: float) -> str:
        total_ms = int(round(sec * 1000))
        ms = total_ms % 1000
        s  = (total_ms // 1000) % 60
        m  = (total_ms // 60000) % 60
        h  = total_ms // 3600000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, ov in enumerate(subtitle_ovs, 1):
        start = ov["start_ratio"] * total
        end   = ov["end_ratio"]   * total
        lines += [str(i), f"{to_srt_time(start)} --> {to_srt_time(end)}", ov["content"], ""]

    with open(srt_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(lines))
    print(f"  → SRT: {srt_path}")


# ═══════════════════════════════════════════════════════════════════
# 2. 인증버전 재실행
# ═══════════════════════════════════════════════════════════════════

CERT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "img0025_cert_v2",
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
            {"id": "seg_0", "type": "intro",        "start_ratio": 0.00, "end_ratio": 0.25, "shot_type": "wide",     "speed": 1.0},
            {"id": "seg_1", "type": "buildup",       "start_ratio": 0.25, "end_ratio": 0.50, "shot_type": "medium",   "speed": 1.0},
            {"id": "seg_2", "type": "peak",          "start_ratio": 0.50, "end_ratio": 0.60, "shot_type": "close_up", "speed": 0.5},
            {"id": "seg_3", "type": "stats_reveal",  "start_ratio": 0.60, "end_ratio": 1.00, "shot_type": "medium",   "speed": 1.0},
        ],
        "cuts": [
            {"position_ratio": 0.25, "type": "hard_cut"},
            {"position_ratio": 0.50, "type": "flash"},
            {"position_ratio": 0.60, "type": "hard_cut"},
        ],
    },
    "speed_changes": [{"start_ratio": 0.50, "end_ratio": 0.60, "speed": 0.5}],
    "effects": [
        {"type": "zoom_in",  "start_ratio": 0.00, "end_ratio": 0.25, "intensity": 0.10},
        {"type": "zoom_in",  "start_ratio": 0.50, "end_ratio": 0.60, "intensity": 0.08},
        {"type": "vignette", "start_ratio": 0.00, "end_ratio": 1.00, "intensity": 0.40},
    ],
    "overlays": [
        {
            "id": "overlay_title", "type": "text", "content": "NIGHT\nRUN",
            "position_pct": {"x": 50, "y": 12},
            "start_ratio": 0.0, "end_ratio": 0.25,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 700, "font_size_ratio": 0.082, "color": "#FFFFFF", "opacity": 0.95},
        },
        {
            "id": "overlay_counter_km", "type": "counter", "content": f"{DISTANCE_KM} km",
            "position_pct": {"x": 50, "y": 40},
            "start_ratio": 0.60, "end_ratio": 1.0,
            "counter_config": {"start_value": 0.0, "end_value": DISTANCE_KM, "unit": "km",
                               "decimal_places": 1, "count_up": True, "easing": "ease_out"},
            "style": {"font_weight": 900, "font_size_ratio": 0.15, "color": "#FFFFFF", "opacity": 1.0},
        },
        {
            "id": "overlay_pace_label", "type": "text", "content": "PACE",
            "position_pct": {"x": 50, "y": 58},
            "start_ratio": 0.60, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.032, "color": "#AADDFF", "opacity": 0.85},
        },
        {
            "id": "overlay_pace", "type": "text", "content": PACE_STR,
            "position_pct": {"x": 50, "y": 65},
            "start_ratio": 0.60, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.055, "color": "#FFFFFF", "opacity": 0.90},
        },
        {
            "id": "overlay_date", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.60, "end_ratio": 1.0,
            "style": {"font_weight": 300, "font_size_ratio": 0.030, "color": "#99BBDD", "opacity": 0.75},
        },
    ],
    "color_grade": {
        "overall_tone": "cool",
        "adjustment_params": {"brightness": -8, "contrast": 18, "saturation": -12, "temperature": -20},
    },
}


def make_cert_video(loop_path: str):
    print("\n" + "=" * 60)
    print("  [2/3] 인증버전 재생성")
    print("=" * 60)
    out_path = str(OUT_DIR / f"IMG0025_cert_{ts}.mp4")
    executor = TemplateExecutor(verbose=True)
    executor.execute(CERT_INSTRUCTION, loop_path, out_path)
    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"  → 완료: {out_path} ({size_mb:.1f} MB)")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 3. 베스트컷버전 — 새 동적 멀티컷 템플릿
# ═══════════════════════════════════════════════════════════════════
# 전략: 같은 소스를 6개 컷으로 재편집
#  ① 와이드 풀샷 (분위기)
#  ② 줌인 슬로우 (러너 클로즈업)
#  ③ 원래 속도 컷백
#  ④ 줌인×2 초클로즈 슬로우 (발/몸)
#  ⑤ 와이드 復귀 (극적 효과)
#  ⑥ 타이틀 freeze 카드
#
# source_start_sec / source_end_sec 직접 지정 → 순서 자유롭게 배치

BESTCUT_INSTRUCTION = {
    "version": "1.0",
    "template_id": "img0025_bestcut_v1",
    "meta": {
        "aspect_ratio": "9:16",
        "target_duration_seconds": 9.0,
        "color_grade": "dark",
        "crop_zoom": 1.0,                   # 전체 crop_zoom은 off — 세그먼트별 effect로 처리
        "vibe_tags": ["bestcut", "dynamic", "night", "cinematic"],
    },
    "timeline": {
        "total_duration_seconds": 9.0,
        "narrative_flow": "wide_open → slowmo_zoom → cutback → ultra_close → wide_return → title_card",
        "segments": [
            # ① 와이드 오프닝 — 전체 트랙 분위기
            {
                "id": "cut_0", "type": "intro",
                "source_start_sec": 0.0, "source_end_sec": 1.5,
                "shot_type": "wide", "speed": 1.0,
                "start_ratio": 0.00, "end_ratio": 0.167,
                "description": "와이드 오프닝 — 야간 트랙 전경",
            },
            # ② 러너 등장 — 슬로우로 긴장감
            {
                "id": "cut_1", "type": "buildup",
                "source_start_sec": 0.7, "source_end_sec": 1.1,
                "shot_type": "medium", "speed": 0.35,
                "start_ratio": 0.167, "end_ratio": 0.37,
                "description": "러너 실루엣 슬로우 — 0.35× 드라마틱",
            },
            # ③ 빠른 컷백 — 속도감
            {
                "id": "cut_2", "type": "action",
                "source_start_sec": 1.1, "source_end_sec": 1.8,
                "shot_type": "medium", "speed": 1.0,
                "start_ratio": 0.37, "end_ratio": 0.50,
                "description": "빠른 컷백 — 실제 속도 복귀",
            },
            # ④ 울트라 슬로우 클로즈업 — 2번째 루프 구간 재사용
            {
                "id": "cut_3", "type": "peak",
                "source_start_sec": 3.0, "source_end_sec": 3.5,
                "shot_type": "close_up", "speed": 0.30,
                "start_ratio": 0.50, "end_ratio": 0.685,
                "description": "울트라 슬로우 클로즈업 — 0.30× 몸통",
            },
            # ⑤ 와이드 리턴 — 극적 전환
            {
                "id": "cut_4", "type": "outro_lead",
                "source_start_sec": 2.0, "source_end_sec": 2.9,
                "shot_type": "wide", "speed": 1.0,
                "start_ratio": 0.685, "end_ratio": 0.80,
                "description": "와이드 복귀 — 전경 재등장",
            },
            # ⑥ 타이틀 카드 — 마지막 프레임 freeze + 오버레이
            {
                "id": "cut_5", "type": "freeze",
                "source_start_sec": 0.9, "source_end_sec": 0.9,
                "freeze_duration": 1.8,
                "shot_type": "wide", "speed": 1.0,
                "start_ratio": 0.80, "end_ratio": 1.00,
                "description": "타이틀 카드 freeze",
            },
        ],
        "cuts": [
            {"position_ratio": 0.167, "type": "hard_cut"},
            {"position_ratio": 0.37,  "type": "flash"},
            {"position_ratio": 0.50,  "type": "hard_cut"},
            {"position_ratio": 0.685, "type": "flash"},
            {"position_ratio": 0.80,  "type": "dissolve"},
        ],
    },
    "speed_changes": [
        {"start_ratio": 0.167, "end_ratio": 0.37,  "speed": 0.35},
        {"start_ratio": 0.50,  "end_ratio": 0.685, "speed": 0.30},
    ],
    "effects": [
        # 각 컷마다 다른 줌 강도 → 다른 카메라처럼 느껴지는 효과
        {"type": "zoom_in", "start_ratio": 0.00,  "end_ratio": 0.167, "intensity": 0.06},   # 와이드 — 미세 줌
        {"type": "zoom_in", "start_ratio": 0.167, "end_ratio": 0.37,  "intensity": 0.20},   # 슬로우 — 적극 줌인
        {"type": "zoom_in", "start_ratio": 0.50,  "end_ratio": 0.685, "intensity": 0.15},   # 클로즈업 슬로우
        {"type": "zoom_in", "start_ratio": 0.685, "end_ratio": 0.80,  "intensity": 0.05},   # 와이드 리턴
        {"type": "vignette","start_ratio": 0.00,  "end_ratio": 1.00,  "intensity": 0.45},   # 전체 비네팅
    ],
    "overlays": [
        # 오프닝 — 우상단 작은 날짜
        {
            "id": "ov_date_top", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 88, "y": 8},
            "start_ratio": 0.0, "end_ratio": 0.167,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 300, "font_size_ratio": 0.028,
                      "color": "#CCDDFF", "opacity": 0.70},
        },
        # ④ 클로즈업 구간 — 좌하단 작은 설명
        {
            "id": "ov_label_slo", "type": "text", "content": "0.3×",
            "position_pct": {"x": 12, "y": 88},
            "start_ratio": 0.50, "end_ratio": 0.685,
            "animation_in": "fade_in", "animation_out": "fade_out",
            "style": {"font_weight": 700, "font_size_ratio": 0.035,
                      "color": "#FF9944", "opacity": 0.85},
        },
        # ⑥ 타이틀 카드 — 메인 텍스트
        {
            "id": "ov_title", "type": "text", "content": "NIGHT\nRUN",
            "position_pct": {"x": 50, "y": 35},
            "start_ratio": 0.80, "end_ratio": 1.00,
            "animation_in": "fade_in", "animation_out": "none",
            "style": {"font_weight": 700, "font_size_ratio": 0.11,
                      "color": "#FFFFFF", "opacity": 0.95, "letter_spacing": 10},
        },
        {
            "id": "ov_dist", "type": "text", "content": f"{DISTANCE_KM} km  /  {PACE_STR}",
            "position_pct": {"x": 50, "y": 65},
            "start_ratio": 0.80, "end_ratio": 1.00,
            "animation_in": "fade_in", "animation_out": "none",
            "style": {"font_weight": 300, "font_size_ratio": 0.040,
                      "color": "#AADDFF", "opacity": 0.88},
        },
        {
            "id": "ov_date_bot", "type": "text", "content": RUN_DATE,
            "position_pct": {"x": 50, "y": 88},
            "start_ratio": 0.80, "end_ratio": 1.00,
            "animation_in": "fade_in", "animation_out": "none",
            "style": {"font_weight": 300, "font_size_ratio": 0.028,
                      "color": "#99BBCC", "opacity": 0.65},
        },
    ],
    "color_grade": {
        "overall_tone": "dark",
        "adjustment_params": {
            "brightness": -12,
            "contrast": 22,
            "saturation": -18,
            "temperature": -10,
        },
    },
}


def make_bestcut_video(loop_path: str):
    print("\n" + "=" * 60)
    print("  [3/3] 베스트컷버전 생성")
    print("=" * 60)
    print("  스토리보드:")
    for seg in BESTCUT_INSTRUCTION["timeline"]["segments"]:
        src_s = seg.get("source_start_sec", "?")
        src_e = seg.get("source_end_sec", "?")
        spd   = seg.get("speed", 1.0)
        frz   = seg.get("freeze_duration")
        if frz:
            print(f"    [{seg['id']}] {seg['description'][:30]}  freeze {frz}s")
        else:
            print(f"    [{seg['id']}] src={src_s}~{src_e}s  ×{spd}  — {seg['description'][:30]}")

    out_path = str(OUT_DIR / f"IMG0025_bestcut_{ts}.mp4")
    executor = TemplateExecutor(verbose=True)
    executor.execute(BESTCUT_INSTRUCTION, loop_path, out_path)
    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"  → 완료: {out_path} ({size_mb:.1f} MB)")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        loop_path, src_dur = make_looped_source(tmpdir)

        pose_out    = make_pose_analysis(loop_path, src_dur)
        cert_out    = make_cert_video(loop_path)
        bestcut_out = make_bestcut_video(loop_path)

    print("\n" + "=" * 60)
    print("  ✅ 전체 완료!")
    print(f"  자세분석버전 : {pose_out}")
    print(f"  인증버전     : {cert_out}")
    print(f"  베스트컷버전 : {bestcut_out}")
    print("=" * 60)
