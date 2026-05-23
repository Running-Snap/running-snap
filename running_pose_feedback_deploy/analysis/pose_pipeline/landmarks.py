"""MediaPipe BlazePose landmark indices and joint groups."""

from __future__ import annotations

import mediapipe as mp

PoseLandmark = mp.solutions.pose.PoseLandmark

# Indices for numpy arrays (0..32)
LANDMARK_NAMES = [lm.name for lm in PoseLandmark]

LEFT_LEG = (
    int(PoseLandmark.LEFT_HIP),
    int(PoseLandmark.LEFT_KNEE),
    int(PoseLandmark.LEFT_ANKLE),
    int(PoseLandmark.LEFT_HEEL),
    int(PoseLandmark.LEFT_FOOT_INDEX),
)
RIGHT_LEG = (
    int(PoseLandmark.RIGHT_HIP),
    int(PoseLandmark.RIGHT_KNEE),
    int(PoseLandmark.RIGHT_ANKLE),
    int(PoseLandmark.RIGHT_HEEL),
    int(PoseLandmark.RIGHT_FOOT_INDEX),
)

LEFT_ARM = (
    int(PoseLandmark.LEFT_SHOULDER),
    int(PoseLandmark.LEFT_ELBOW),
    int(PoseLandmark.LEFT_WRIST),
)
RIGHT_ARM = (
    int(PoseLandmark.RIGHT_SHOULDER),
    int(PoseLandmark.RIGHT_ELBOW),
    int(PoseLandmark.RIGHT_WRIST),
)

# Pairs of (proximal, distal) for bone-length normalization
BONE_PAIRS = (
    (int(PoseLandmark.LEFT_HIP), int(PoseLandmark.LEFT_KNEE)),
    (int(PoseLandmark.LEFT_KNEE), int(PoseLandmark.LEFT_ANKLE)),
    (int(PoseLandmark.RIGHT_HIP), int(PoseLandmark.RIGHT_KNEE)),
    (int(PoseLandmark.RIGHT_KNEE), int(PoseLandmark.RIGHT_ANKLE)),
    (int(PoseLandmark.LEFT_SHOULDER), int(PoseLandmark.LEFT_ELBOW)),
    (int(PoseLandmark.LEFT_ELBOW), int(PoseLandmark.LEFT_WRIST)),
    (int(PoseLandmark.RIGHT_SHOULDER), int(PoseLandmark.RIGHT_ELBOW)),
    (int(PoseLandmark.RIGHT_ELBOW), int(PoseLandmark.RIGHT_WRIST)),
)

ANGLE_TRIPLETS = {
    "left_hip_deg": (
        int(PoseLandmark.LEFT_SHOULDER),
        int(PoseLandmark.LEFT_HIP),
        int(PoseLandmark.LEFT_KNEE),
    ),
    "right_hip_deg": (
        int(PoseLandmark.RIGHT_SHOULDER),
        int(PoseLandmark.RIGHT_HIP),
        int(PoseLandmark.RIGHT_KNEE),
    ),
    "left_knee_deg": (
        int(PoseLandmark.LEFT_HIP),
        int(PoseLandmark.LEFT_KNEE),
        int(PoseLandmark.LEFT_ANKLE),
    ),
    "right_knee_deg": (
        int(PoseLandmark.RIGHT_HIP),
        int(PoseLandmark.RIGHT_KNEE),
        int(PoseLandmark.RIGHT_ANKLE),
    ),
    "left_ankle_deg": (
        int(PoseLandmark.LEFT_KNEE),
        int(PoseLandmark.LEFT_ANKLE),
        int(PoseLandmark.LEFT_FOOT_INDEX),
    ),
    "right_ankle_deg": (
        int(PoseLandmark.RIGHT_KNEE),
        int(PoseLandmark.RIGHT_ANKLE),
        int(PoseLandmark.RIGHT_FOOT_INDEX),
    ),
}

NUM_LANDMARKS = 33

LEFT_ANKLE = int(PoseLandmark.LEFT_ANKLE)
RIGHT_ANKLE = int(PoseLandmark.RIGHT_ANKLE)
LEFT_HEEL = int(PoseLandmark.LEFT_HEEL)
RIGHT_HEEL = int(PoseLandmark.RIGHT_HEEL)
LEFT_FOOT_INDEX = int(PoseLandmark.LEFT_FOOT_INDEX)
RIGHT_FOOT_INDEX = int(PoseLandmark.RIGHT_FOOT_INDEX)
LEFT_SHOULDER = int(PoseLandmark.LEFT_SHOULDER)
RIGHT_SHOULDER = int(PoseLandmark.RIGHT_SHOULDER)
LEFT_ELBOW = int(PoseLandmark.LEFT_ELBOW)
RIGHT_ELBOW = int(PoseLandmark.RIGHT_ELBOW)
LEFT_WRIST = int(PoseLandmark.LEFT_WRIST)
RIGHT_WRIST = int(PoseLandmark.RIGHT_WRIST)
LEFT_HIP = int(PoseLandmark.LEFT_HIP)
RIGHT_HIP = int(PoseLandmark.RIGHT_HIP)
LEFT_KNEE = int(PoseLandmark.LEFT_KNEE)
RIGHT_KNEE = int(PoseLandmark.RIGHT_KNEE)
