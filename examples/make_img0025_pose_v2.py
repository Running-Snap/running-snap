"""
IMG_0025_black1.mov + feedback JSON → 자세분석 영상 v2
"""
import sys, os, json, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor            import TemplateExecutor
from src.feedback_json_to_instruction import FeedbackJsonConverter
from src.pose_skeleton_renderer       import apply_skeleton_feedback
from moviepy import VideoFileClip, concatenate_videoclips

SRC_VIDEO = "/Users/khy/Downloads/IMG_0025_black1.mov"
OUT_DIR   = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# ─── 실제 분석 데이터 ───────────────────────────────────────────────
FEEDBACK_DATA = {
    "score": 70,
    "feedbacks": [
        {"title": "케이던스",    "status": "bad",  "message": "케이던스 41.1 SPM — 발걸음이 너무 느립니다"},
        {"title": "착지",        "status": "good", "message": "발이 골반 아래 착지 — 제동력이 거의 없습니다"},
        {"title": "팔꿈치 각도", "status": "good", "message": "팔꿈치 83.1° — 이상적인 각도입니다"},
        {"title": "좌우 균형",   "status": "bad",  "message": "좌우 비대칭 103.8% — 부상 위험, 코어·둔근 강화 권장"},
    ],
    "pose_stats": {
        "cadence":       41.1,
        "v_oscillation": 604.2,
        "avg_impact_z":  0.115,
        "asymmetry":     103.8,
        "elbow_angle":   83.1,
    },
}

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:

        # ── 소스 3x 루프 ─────────────────────────────────────────
        loop_path = os.path.join(tmpdir, "loop.mp4")
        print("[전처리] 소스 3x 루프...")
        clip = VideoFileClip(SRC_VIDEO)
        looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
        looped.write_videofile(
            loop_path, codec="libx264", audio_codec="aac",
            fps=30, preset="fast", threads=4, logger=None,
        )
        src_dur = looped.duration
        looped.close(); clip.close()
        print(f"  루프 완료: {src_dur:.1f}s")

        # ── 스켈레톤 오버레이 (루프 소스에 먼저 입힘) ────────────────
        skel_path = os.path.join(tmpdir, "loop_skel.mp4")
        print("[스켈레톤] MediaPipe skeleton 적용...")
        apply_skeleton_feedback(
            loop_path, skel_path, FEEDBACK_DATA,
            loop_count=3,
            model_path="models/pose_landmarker_full.task",
        )
        # 스켈레톤 성공 시 사용, 실패 시 원본으로 fallback
        src_for_template = skel_path if Path(skel_path).exists() else loop_path

        # ── EditInstruction 생성 ──────────────────────────────────
        print("[변환] feedback JSON → EditInstruction...")
        converter   = FeedbackJsonConverter()
        instruction = converter.convert(FEEDBACK_DATA, source_duration=src_dur)

        print(f"  세그먼트 {len(instruction['timeline']['segments'])}개")
        print(f"  오버레이 {len(instruction['overlays'])}개")
        print(f"  목표 길이: {instruction['meta']['target_duration_seconds']:.1f}s")
        print()
        print("  타임라인:")
        for seg in instruction["timeline"]["segments"]:
            t = seg.get("freeze_duration")
            if t:
                print(f"    {seg['id']:35s}  freeze {t:.1f}s")
            else:
                s = seg.get("source_start_sec", 0)
                e = seg.get("source_end_sec", 0)
                spd = seg.get("speed", 1.0)
                out = (e - s) / spd
                print(f"    {seg['id']:35s}  src={s:.2f}~{e:.2f}s  ×{spd}  → {out:.2f}s out")

        # ── 렌더링 ───────────────────────────────────────────────
        out_path = str(OUT_DIR / f"IMG0025_pose_v2_{ts}.mp4")
        executor = TemplateExecutor(verbose=True)
        executor.execute(instruction, src_for_template, out_path)

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"\n완료: {out_path}  ({size_mb:.1f} MB)")
