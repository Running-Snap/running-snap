"""
front_side_view_rotated.mp4 → 자세분석버전 데모
스켈레톤 제대로 나오는 영상으로 전체 파이프라인 확인
"""
import sys, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor            import TemplateExecutor
from src.feedback_json_to_instruction import FeedbackJsonConverter
from src.pose_skeleton_renderer       import apply_skeleton_feedback
from moviepy import VideoFileClip, concatenate_videoclips

SRC   = "front_side_view_rotated.mp4"   # 1280x720 landscape → CW90 → 720x1280 portrait
OUT   = Path("outputs/videos")
OUT.mkdir(parents=True, exist_ok=True)
ts    = datetime.now().strftime("%Y%m%d_%H%M%S")

FEEDBACK_DATA = {
    "score": 70,
    "feedbacks": [
        {"title": "케이던스",    "status": "bad",  "message": "케이던스 41.1 SPM — 발걸음이 너무 느립니다"},
        {"title": "착지",        "status": "good", "message": "발이 골반 아래 착지 — 제동력이 거의 없습니다"},
        {"title": "팔꿈치 각도", "status": "good", "message": "팔꿈치 83.1° — 이상적인 각도입니다"},
        {"title": "좌우 균형",   "status": "bad",  "message": "좌우 비대칭 103.8% — 부상 위험, 코어·둔근 강화 권장"},
    ],
    "pose_stats": {
        "cadence": 41.1, "v_oscillation": 604.2,
        "avg_impact_z": 0.115, "asymmetry": 103.8, "elbow_angle": 83.1,
    },
}

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:

        # ── 소스 3x 루프 (5.5s → 16.5s) ─────────────────────────
        loop_path = os.path.join(tmpdir, "loop.mp4")
        print("[전처리] 3x 루프...")
        clip = VideoFileClip(SRC)
        looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
        looped.write_videofile(loop_path, codec="libx264", audio_codec="aac",
                               fps=30, preset="fast", threads=4, logger=None)
        src_dur = looped.duration
        looped.close(); clip.close()
        print(f"  완료: {src_dur:.1f}s")

        # ── 스켈레톤 적용 ─────────────────────────────────────────
        skel_path = os.path.join(tmpdir, "loop_skel.mp4")
        print("[스켈레톤] MediaPipe 적용...")
        apply_skeleton_feedback(
            loop_path, skel_path, FEEDBACK_DATA,
            loop_count=3, model_path="models/pose_landmarker_full.task",
        )
        src_for_template = skel_path if Path(skel_path).exists() else loop_path

        # ── EditInstruction 생성 ──────────────────────────────────
        print("[변환] feedback JSON → EditInstruction...")
        converter   = FeedbackJsonConverter()
        instruction = converter.convert(FEEDBACK_DATA, source_duration=src_dur)
        target_dur  = instruction["meta"]["target_duration_seconds"]
        print(f"  {len(instruction['timeline']['segments'])}개 세그먼트, {target_dur:.1f}s")

        # ── 렌더링 ───────────────────────────────────────────────
        out_path = str(OUT / f"sideview_pose_demo_{ts}.mp4")
        executor = TemplateExecutor(verbose=True)
        executor.execute(instruction, src_for_template, out_path)

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"\n완료: {out_path}  ({size_mb:.1f} MB)")
