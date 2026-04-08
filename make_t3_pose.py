"""
t3.mp4 자세분석 영상 생성 스크립트
제공된 분석 JSON → FEEDBACK_DATA 변환 → pose 영상 출력
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.running_pipeline import RunningPipeline

SRC = "/Users/khy/Downloads/t3.mp4"

# ── 제공된 result_json 파싱 ────────────────────────────────────────
FEEDBACK_DATA = {
    "score": 55,
    "feedbacks": [
        {
            "frame":   4,             # t ≈ 0.13s — 비대칭 발현 시점
            "title":   "좌우 균형",
            "status":  "bad",
            "message": "좌우 비대칭 19.6% — 부상 위험, 코어·둔근 강화 권장",
        },
        {
            "frame":   21,            # t ≈ 0.70s — 착지 충격 최고점
            "title":   "착지",
            "status":  "warning",
            "message": "약간의 오버스트라이드 — 착지를 몸 중심에 가깝게 조정하세요",
        },
        {
            "frame":   60,            # t ≈ 2.0s — 케이던스 대표 구간
            "title":   "케이던스",
            "status":  "bad",
            "message": "케이던스 63.4 SPM — 발걸음이 너무 느립니다",
        },
        {
            "frame":   134,           # t ≈ 4.5s — 팔꿈치 각도 최악
            "title":   "팔꿈치 각도",
            "status":  "warning",
            "message": "팔꿈치 116.5° — 80~100° 사이를 유지하세요",
        },
    ],
    "pose_stats": {
        "cadence":       63.4,    # SPM
        "elbow_angle":   116.5,   # °
        "avg_impact_z":  0.245,   # 착지 충격 (raw)
        "asymmetry":     19.6,    # % 좌우 비대칭
        "v_oscillation": 45.0,    # px 수직 진폭
    },
    # 분석에서 뽑아낸 주요 프레임 타임스탬프 (초)
    # 팔꿈치 worst: 4.5s / 1.0s / 1.1s
    # 수직진폭: 최저 1.9s, 최고 4.2s
    # 착지 worst: 0.7s (Impact Z 0.397)
    # 비대칭: 0.1s vs 0.3s
    "frame_refs": {
        "elbow":                [134, 31, 32],   # 4.5s, 1.0s, 1.1s
        "vertical_oscillation": [58, 125],        # 1.9s, 4.2s
        "overstride":           [21, 36, 4],      # 0.7s, 1.2s, 0.1s
        "asymmetry":            [4, 9, 14, 21],
    },
    "impact_events": [
        {"t_sec": 0.133, "impact_z": 0.253, "grade": "NORMAL"},
        {"t_sec": 0.300, "impact_z": 0.036, "grade": "ELITE"},
        {"t_sec": 0.467, "impact_z": 0.247, "grade": "NORMAL"},
        {"t_sec": 0.700, "impact_z": 0.397, "grade": "NORMAL"},
        {"t_sec": 1.200, "impact_z": 0.294, "grade": "NORMAL"},
    ],
}

# ── 이벤트 정보 (포스터/인증영상용, 자세분석에도 일부 사용) ──────
EVENT_CONFIG = {
    "title":        "RUNNING\nANALYSIS",
    "location":     "Seoul Olympic Park",
    "sublocation":  "5K Training Course",
    "time":         "A.M. 07:30",
    "date":         "2026.04.07",
    "day":          "TUE",
    "distance_km":  5.0,
    "run_time":     "29'00\"",
    "pace":         "5'48\"/km",
    "color_scheme": "cool",
}

if __name__ == "__main__":
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    pipeline = RunningPipeline(qwen_api_key=api_key or None, verbose=True)

    result = pipeline.run(
        video_path    = SRC,
        event_config  = EVENT_CONFIG,
        feedback_data = FEEDBACK_DATA,
        output_dir    = "outputs/t3",
        name_prefix   = "t3",
        cert_mode     = "simple",
    )

    print("\n" + "=" * 60)
    if result.success:
        print("  완료!")
        if result.poster_path: print(f"  포스터    : {result.poster_path}")
        if result.cert_path:   print(f"  인증영상  : {result.cert_path}")
        if result.pose_path:   print(f"  자세분석  : {result.pose_path}")
    else:
        print(f"  실패: {result.error}")
    print("=" * 60)
