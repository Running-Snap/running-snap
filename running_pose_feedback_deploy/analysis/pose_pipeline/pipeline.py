"""End-to-end running pose analysis pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .angles import extract_joint_angles
from .features import extract_gait_features
from .gait_events import detect_gait_events
from .pose_estimation import PoseEstimationConfig, extract_keypoints
from .postprocess import PosePostProcessor, PostProcessConfig
from .video import load_video


def run_pipeline(
    video_path: str | Path,
    *,
    target_width: int = 960,
    max_frames: int | None = None,
    postprocess_config: PostProcessConfig | None = None,
    pose_config: PoseEstimationConfig | None = None,
    save_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Full pipeline: video → pose → post-process → angles → gait events → features.

    Returns:
        {
            "angles": {joint_name: np.ndarray},
            "gait_features": {...},
            "events": [...],
            "keypoints_raw": (T, 33, 3),
            "keypoints_processed": (T, 33, 3),
            "fps": float,
        }
    """
    video = load_video(video_path, max_frames=max_frames, target_width=target_width)
    raw_keypoints = extract_keypoints(video.frames, config=pose_config)

    processor = PosePostProcessor(video.fps, config=postprocess_config)
    processed = processor.process(raw_keypoints)

    angles = extract_joint_angles(processed)
    events = detect_gait_events(processed, video.fps)
    gait_features = extract_gait_features(events, video.fps)

    result: dict[str, Any] = {
        "video": str(video_path),
        "fps": video.fps,
        "frame_count": video.frame_count,
        "angles": {k: v.tolist() for k, v in angles.items()},
        "gait_features": gait_features,
        "events": gait_features.get("events", []),
        "keypoints_raw": raw_keypoints,
        "keypoints_processed": processed,
    }

    if save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        np.save(save_dir / "keypoints_raw.npy", raw_keypoints)
        np.save(save_dir / "keypoints_processed.npy", processed)
        export = {
            "video": result["video"],
            "fps": result["fps"],
            "frame_count": result["frame_count"],
            "angles": result["angles"],
            "gait_features": result["gait_features"],
            "events": result["events"],
        }
        (save_dir / "pipeline_output.json").write_text(
            json.dumps(export, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return result


def run_pipeline_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Stable MediaPipe running pose pipeline")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path("analysis/results_pose_pipeline"))
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--width", type=int, default=960)
    args = parser.parse_args()

    out_dir = args.output / args.video.stem
    result = run_pipeline(
        args.video,
        max_frames=args.max_frames,
        target_width=args.width,
        save_dir=out_dir,
    )
    print(f"Saved: {out_dir}")
    print(f"Cadence SPM: {result['gait_features'].get('cadence_spm', 0)}")
    print(f"Events: {len(result['events'])}")


