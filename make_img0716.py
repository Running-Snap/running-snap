"""
IMG_0716.MOV  자세분석 + 인증영상 + 포스터 생성 스크립트
result_json (id=51, video_id=35) 기반
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.running_pipeline import RunningPipeline

SRC = "/Users/khy/Downloads/IMG_0716.MOV"

# ── 분석 결과 (result_json 파싱) ──────────────────────────────────
FEEDBACK_DATA = {
    "score": 70,
    "feedbacks": [
        {
            "frame":   43,             # t ≈ 1.8s — 팔꿈치 37° 구간 (대표 프레임)
            "title":   "팔꿈치 각도",
            "status":  "good",
            "message": "팔꿈치 86.9° — 이상적인 각도입니다",
        },
        {
            "frame":   47,             # t ≈ 2.0s — 좌우 비대칭 최대 구간
            "title":   "좌우 균형",
            "status":  "warning",
            "message": "좌우 비대칭 4.9% — 한쪽에 부담이 쏠릴 수 있습니다",
        },
        {
            "frame":   60,             # t ≈ 2.5s — 케이던스 대표 구간
            "title":   "케이던스",
            "status":  "bad",
            "message": "케이던스 102.9 SPM — 발걸음이 너무 느립니다",
        },
        {
            "frame":   95,             # t ≈ 4.0s — 착지 충격 최고점 (Impact Z 0.383)
            "title":   "착지",
            "status":  "warning",
            "message": "약간의 오버스트라이드 — 착지를 몸 중심에 가깝게 조정하세요",
        },
    ],
    "pose_stats": {
        "cadence":       102.9,   # SPM
        "elbow_angle":    86.9,   # °
        "avg_impact_z":   0.233,  # 착지 충격
        "asymmetry":       4.9,   # % 좌우 비대칭
        "v_oscillation": 220.9,   # px 수직 진폭
    },
    "frame_refs": {
        "elbow":                [109, 42, 43],
        "vertical_oscillation": [109, 107],
        "overstride":           [95, 69, 93],
        "asymmetry":            [47, 62, 69, 77, 93, 95],
    },
    "impact_events": [
        {"t_sec": 1.292, "impact_z": 0.233, "grade": "NORMAL"},
        {"t_sec": 1.750, "impact_z": 0.301, "grade": "NORMAL"},
        {"t_sec": 1.958, "impact_z": 0.251, "grade": "NORMAL"},
        {"t_sec": 2.583, "impact_z": 0.024, "grade": "ELITE"},
        {"t_sec": 2.875, "impact_z": 0.354, "grade": "NORMAL"},
        {"t_sec": 3.208, "impact_z": 0.197, "grade": "NORMAL"},
        {"t_sec": 3.875, "impact_z": 0.302, "grade": "NORMAL"},
        {"t_sec": 3.958, "impact_z": 0.383, "grade": "NORMAL"},
        {"t_sec": 4.083, "impact_z": 0.049, "grade": "ELITE"},
    ],
}

# ── 이벤트 설정 ───────────────────────────────────────────────────
EVENT_CONFIG = {
    "title":        "2026\nMIRACLE MARATHON",
    "date":         "2026.04.19",
    "time":         "SUN. AM 08:00",
    "location":     "Gapcheon, Daejeon, Republic of Korea",
    "sublocation":  "Republic of Korea",
    "branding":     "2026 MIRACLE MARATHON  /  Gapcheon, Daejeon  /  2026.04.19",
    "color_scheme": "cool",
    # 인증영상 통계 (simple 모드에서 Nike 스타일로 표시)
    "distance_km":  0.0,    # 거리 미제공 — 카운터 숨김
    "cadence":      "102.9 spm",
}

if __name__ == "__main__":
    api_key  = os.environ.get("DASHSCOPE_API_KEY", "")
    pipeline = RunningPipeline(qwen_api_key=api_key or None, verbose=True)

    result = pipeline.run(
        video_path    = SRC,
        event_config  = EVENT_CONFIG,
        feedback_data = FEEDBACK_DATA,
        output_dir    = "outputs/img0716",
        name_prefix   = "img0716",
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
