"""
0031ex1.MOV → 자세분석 데모
야간 트랙 러닝 영상 (아이폰 세로 촬영, rotation=-90 메타데이터)

파이프라인:
  0031ex1.MOV
    → [ffmpeg 회전 fix → portrait mp4]
    → [3x 루프]
    → [MediaPipe 스켈레톤 오버레이]
    → [FeedbackJsonConverter + TemplateExecutor]
    → outputs/videos/0031ex1_pose_<ts>.mp4
"""
import sys, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor            import TemplateExecutor
from src.feedback_json_to_instruction import FeedbackJsonConverter
from src.pose_skeleton_renderer       import apply_skeleton_feedback
from moviepy import VideoFileClip, concatenate_videoclips

SRC_RAW = "/Users/khy/Downloads/0031ex1.MOV"
OUT_DIR  = Path("outputs/videos")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

FFMPEG = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"

# ── 임시 피드백 데이터 (더미) ──────────────────────────────────────
FEEDBACK_DATA = {
    "score": 78,
    "feedbacks": [
        {
            "title": "케이던스",
            "status": "good",
            "message": "케이던스 168 SPM — 적절한 보폭 리듬입니다",
        },
        {
            "title": "착지",
            "status": "bad",
            "message": "발 앞꿈치 과착지 — 무릎 부하가 높습니다. 미드풋 착지를 연습하세요",
        },
        {
            "title": "팔꿈치 각도",
            "status": "good",
            "message": "팔꿈치 88° — 이상적인 각도를 유지하고 있습니다",
        },
        {
            "title": "좌우 균형",
            "status": "bad",
            "message": "좌우 비대칭 108% — 오른쪽 편중, 코어 강화 권장",
        },
    ],
    "pose_stats": {
        "cadence":       168.0,
        "v_oscillation": 512.0,
        "avg_impact_z":  0.132,
        "asymmetry":     108.0,
        "elbow_angle":   88.0,
    },
}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:

        # ── STEP 1: rotation 메타데이터 제거 + 올바른 portrait mp4로 변환 ──
        # ffmpeg 기본: rotation 메타데이터를 자동 적용해서 디코딩
        fixed_path = os.path.join(tmpdir, "fixed.mp4")
        print("[Step 1] rotation 메타데이터 fix → portrait mp4 변환...")
        ret = os.system(
            f'"{FFMPEG}" -y -i "{SRC_RAW}" '
            f'-vf "transpose=cclock" '          # rotation=-90 → CCW90으로 올바른 portrait
            f'-c:v libx264 -preset fast -crf 18 '
            f'-an '                             # 오디오 제거 (루프 편의)
            f'"{fixed_path}" -loglevel error'
        )
        if ret != 0 or not Path(fixed_path).exists():
            print("  [폴백] transpose 없이 재시도...")
            os.system(
                f'"{FFMPEG}" -y -i "{SRC_RAW}" '
                f'-c:v libx264 -preset fast -crf 18 -an '
                f'"{fixed_path}" -loglevel error'
            )

        # 변환된 영상 크기 확인
        import cv2
        cap_check = cv2.VideoCapture(fixed_path)
        fix_W = int(cap_check.get(cv2.CAP_PROP_FRAME_WIDTH))
        fix_H = int(cap_check.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fix_fps = cap_check.get(cv2.CAP_PROP_FPS)
        fix_frames = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
        cap_check.release()
        print(f"  변환 완료: {fix_W}x{fix_H}  {fix_frames}f @ {fix_fps:.1f}fps  ({fix_frames/fix_fps:.2f}s)")

        # ── STEP 2: 3x 루프 ──────────────────────────────────────────
        loop_path = os.path.join(tmpdir, "loop.mp4")
        print("[Step 2] 3x 루프 생성...")
        clip = VideoFileClip(fixed_path)
        looped = concatenate_videoclips([clip, clip.copy(), clip.copy()])
        looped.write_videofile(
            loop_path, codec="libx264", audio_codec="aac",
            fps=30, preset="fast", threads=4, logger=None,
        )
        src_dur = looped.duration
        looped.close(); clip.close()
        print(f"  루프 완료: {src_dur:.1f}s")

        # ── STEP 3: MediaPipe 스켈레톤 적용 ───────────────────────────
        skel_path = os.path.join(tmpdir, "loop_skel.mp4")
        print("[Step 3] MediaPipe 스켈레톤 적용...")
        apply_skeleton_feedback(
            loop_path, skel_path, FEEDBACK_DATA,
            loop_count=3,
            model_path="models/pose_landmarker_full.task",
        )
        src_for_template = skel_path if Path(skel_path).exists() else loop_path

        # ── STEP 4: EditInstruction 생성 + 렌더링 ────────────────────
        print("[Step 4] FeedbackJsonConverter → TemplateExecutor...")
        converter   = FeedbackJsonConverter()
        instruction = converter.convert(FEEDBACK_DATA, source_duration=src_dur)

        n_seg = len(instruction["timeline"]["segments"])
        n_ov  = len(instruction["overlays"])
        tgt   = instruction["meta"]["target_duration_seconds"]
        print(f"  세그먼트: {n_seg}개  오버레이: {n_ov}개  목표: {tgt:.1f}s")

        out_path = str(OUT_DIR / f"0031ex1_pose_{ts}.mp4")
        executor = TemplateExecutor(verbose=True)
        executor.execute(instruction, src_for_template, out_path)

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    print(f"\n완료: {out_path}  ({size_mb:.1f} MB)")
