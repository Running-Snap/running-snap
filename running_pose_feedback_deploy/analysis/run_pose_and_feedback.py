"""
단일 영상 MediaPipe 전처리 (배포·run_single_video.sh용).

  python analysis/run_pose_and_feedback.py preprocess \\
    --video my_run.mp4 \\
    --pose-dir work/pose \\
    --profiles-dir work/profiles
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_marathon_postprocess_rules import export_postprocess_track  # noqa: E402
from plot_normal_phase_profiles import process_video_dir  # noqa: E402
from validate_validation_dataset import video_output_name  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-video pose preprocess for deploy bundle")
    p.add_argument("command", choices=("preprocess",))
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--pose-dir", type=Path, default=Path("work/pose"))
    p.add_argument("--profiles-dir", type=Path, default=Path("work/profiles"))
    p.add_argument("--frame-stride", type=int, default=3)
    p.add_argument("--width", type=int, default=960)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    video = args.video.resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")

    args.pose_dir.mkdir(parents=True, exist_ok=True)
    args.profiles_dir.mkdir(parents=True, exist_ok=True)

    print(f"video: {video.name}")
    print(f"output_name: {video_output_name(video)}")

    summary = export_postprocess_track(
        video,
        args.pose_dir,
        frame_stride=args.frame_stride,
        target_width=args.width,
    )
    if not summary:
        raise SystemExit("Pose export failed (too few frames?)")

    pdir = args.pose_dir / summary["video_dir"]
    prof = process_video_dir(
        pdir,
        args.profiles_dir,
        min_cycle_sec=0.45,
        max_cycle_sec=1.8,
        min_cycles=2,
        show_individual_cycles=False,
    )
    print("pose:", summary["csv"])
    print("profile:", prof)


if __name__ == "__main__":
    main()
