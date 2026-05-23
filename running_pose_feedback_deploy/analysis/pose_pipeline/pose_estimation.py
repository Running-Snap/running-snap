"""MediaPipe BlazePose keypoint extraction."""

from __future__ import annotations

from dataclasses import dataclass

import mediapipe as mp
import numpy as np

from .landmarks import NUM_LANDMARKS


@dataclass
class PoseEstimationConfig:
    model_complexity: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    smooth_landmarks: bool = True
    enable_segmentation: bool = False


def extract_keypoints(
    frames: list[np.ndarray],
    config: PoseEstimationConfig | None = None,
) -> np.ndarray:
    """
    Run BlazePose on each frame.

    Returns:
        keypoints: (T, 33, 3) with normalized x, y in [0, 1] and visibility score.
    """
    config = config or PoseEstimationConfig()
    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=config.model_complexity,
        smooth_landmarks=config.smooth_landmarks,
        enable_segmentation=config.enable_segmentation,
        min_detection_confidence=config.min_detection_confidence,
        min_tracking_confidence=config.min_tracking_confidence,
    )

    sequence = np.full((len(frames), NUM_LANDMARKS, 3), np.nan, dtype=np.float32)
    try:
        for t, frame in enumerate(frames):
            result = pose.process(frame)
            if not result.pose_landmarks:
                continue
            for idx, lm in enumerate(result.pose_landmarks.landmark):
                sequence[t, idx, 0] = lm.x
                sequence[t, idx, 1] = lm.y
                sequence[t, idx, 2] = lm.visibility
    finally:
        pose.close()

    return sequence
