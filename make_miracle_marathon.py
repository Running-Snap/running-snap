"""
2026 MIRACLE MARATHON — 통합 출력 스크립트
==========================================
이벤트명·날짜·시간·장소 정보만으로 (러닝 통계 없이)
포스터 + 인증영상을 생성하는 재사용 가능한 모듈.

지원 영상:
  - /Users/khy/Downloads/t3.mp4
  - /Users/khy/Downloads/IMG_0716.MOV

출력:
  outputs/miracle/<prefix>_poster_<ts>.jpg
  outputs/miracle/<prefix>_cert_<ts>.mp4

커스터마이징 포인트:
  - EVENT_CONFIG : 이벤트명·날짜·시간·장소·색상 테마 변경
  - VIDEOS       : 처리할 영상 목록 (경로, 출력 prefix)
  - cert_mode    : "event" (이벤트 스타일) | "simple" (Nike 스타일)
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.running_pipeline import RunningPipeline

# ══════════════════════════════════════════════════════════════════
#  이벤트 설정  ← 여기만 바꾸면 다른 대회에 재사용 가능
# ══════════════════════════════════════════════════════════════════
EVENT_CONFIG = {
    # ── 포스터 + 인증영상 공통 ──────────────────────────────────
    "title":       "2026\nMIRACLE MARATHON",
    "date":        "2026. 04. 19",
    "time":        "SUN. AM 08:00",
    "location":    "Gapcheon, Daejeon, Republic of Korea",

    # ── 포스터 전용 ─────────────────────────────────────────────
    "sublocation": "Republic of Korea",          # 포스터 소제목 위치
    "branding":    "2026 MIRACLE MARATHON  /  Gapcheon, Daejeon  /  2026.04.19",
    "color_scheme": "cool",                      # warm / cool / neutral

    # ── 인증영상 러닝 통계 (event 모드에서는 표시 안 됨) ─────────
    # 이 필드들은 cert_mode="event"일 때 무시됨
    "distance_km":  0,
}

# ══════════════════════════════════════════════════════════════════
#  처리할 영상 목록
# ══════════════════════════════════════════════════════════════════
VIDEOS = [
    {
        "src":    "/Users/khy/Downloads/t3.mp4",
        "prefix": "miracle_t3",
    },
    {
        "src":    "/Users/khy/Downloads/IMG_0716.MOV",
        "prefix": "miracle_img0716",
    },
]

OUTPUT_DIR = "outputs/miracle"

# ══════════════════════════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    api_key  = os.environ.get("DASHSCOPE_API_KEY", "")
    pipeline = RunningPipeline(qwen_api_key=api_key or None, verbose=True)

    for v in VIDEOS:
        if not Path(v["src"]).exists():
            print(f"\n[건너뜀] 파일 없음: {v['src']}")
            continue

        print(f"\n{'#'*60}")
        print(f"  처리: {v['src']}")
        print(f"{'#'*60}")

        result = pipeline.run(
            video_path    = v["src"],
            event_config  = EVENT_CONFIG,
            feedback_data = None,          # 자세분석 없음
            output_dir    = OUTPUT_DIR,
            name_prefix   = v["prefix"],
            cert_mode     = "event",       # 이벤트 스타일 (통계 없이)
        )

        print(f"\n{'='*60}")
        if result.success:
            print(f"  ✓ 완료: {v['prefix']}")
            if result.poster_path: print(f"    포스터   : {result.poster_path}")
            if result.cert_path:   print(f"    인증영상 : {result.cert_path}")
        else:
            print(f"  ✗ 실패: {result.error}")
        print(f"{'='*60}")
