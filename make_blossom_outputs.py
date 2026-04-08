"""
BLOSSOM RUNNING — 통합 출력 스크립트
  - 베스트컷 포스터 (JPG)
  - 인증영상       (MP4, Nike 스타일)
  - 자세분석 영상  (MP4, skeleton + feedback)
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.running_pipeline import RunningPipeline

# ── 소스 영상 ─────────────────────────────────────────────────────
SRC = "/Users/khy/Downloads/IMG_0716.MOV"

# ── 이벤트 정보 (포스터 + 인증영상 공통) ─────────────────────────
EVENT_CONFIG = {
    # ── 포스터 전용 ─────────────────────────────────────────────
    "title":        "BLOSSOM\nRUNNING",
    "location":     "Chungnam National Univ.",
    "sublocation":  "N9-2",
    "time":         "P.M. 03:00",
    "branding":     "BLOSSOM RUN  /  CNU N9-2  /  2026.04.03",
    "color_scheme": "warm",

    # ── 인증영상 + 포스터 공통 ──────────────────────────────────
    "date":         "2026.04.03",
    "distance_km":  5.2,         # 총 거리 (km)

    # ── 인증영상 러닝 기록 (Nike Running App 수집 항목 전체) ────
    # 추후 Nike Running Club API / 수동 입력으로 대체 예정
    "pace":           "6'35\"/km",  # 평균 페이스
    "run_time":       "34'18\"",    # 총 소요 시간
    "calories":       "312 kcal",   # 소모 칼로리
    "elevation_gain": "48 m",       # 고도 상승
    "avg_heart_rate": "152 bpm",    # 평균 심박수
    "cadence":        "163 spm",    # 평균 케이던스 (steps per min)
}

# ── 자세분석 피드백 JSON ──────────────────────────────────────────
FEEDBACK_DATA = {
    "score": 60,
    "feedbacks": [
        {
            "title": "팔꿈치 각도",
            "message": "팔꿈치를 약 90도로 유지하세요. 현재 너무 벌어져 있어 에너지 손실이 발생합니다.",
            "status": "warning",
        },
        {
            "title": "착지 충격",
            "message": "발 앞꿈치 착지를 유지하고 있으나 충격 흡수가 부족합니다. 무릎을 더 구부려보세요.",
            "status": "warning",
        },
        {
            "title": "케이던스",
            "message": "케이던스가 158 SPM으로 목표치(170+)보다 낮습니다. 보폭을 줄이고 회전수를 높이세요.",
            "status": "bad",
        },
        {
            "title": "상체 자세",
            "message": "상체가 약간 앞으로 기울어져 있습니다. 시선을 정면으로 유지하면 자연스럽게 교정됩니다.",
            "status": "good",
        },
    ],
    "pose_stats": {
        "cadence":       158,
        "elbow_angle":   110,
        "avg_impact_z":  "보통",
        "asymmetry":     12,
        "v_oscillation": 68,
    },
}

if __name__ == "__main__":
    # DashScope API 키 (있으면 클라우드, 없으면 Ollama 로컬 qwen2.5vl:7b 자동 사용)
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")

    pipeline = RunningPipeline(qwen_api_key=api_key or None, verbose=True)

    result = pipeline.run(
        video_path   = SRC,
        event_config = EVENT_CONFIG,
        feedback_data= FEEDBACK_DATA,
        output_dir   = "outputs/blossom",
        name_prefix  = "blossom",
        cert_mode    = "simple",   # 슬로우모·줌 없이 원본 1x 재생
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
