"""
사진으로 마라톤 포스터 만들기
  - 피드용  : 4:5 (1080×1350), 커버 크롭, 스탯 포함
  - 사진용  : 원본 비율, 그라디언트 확장, 이벤트 블록

사용: python3 make_marathon_poster_from_photo.py [이미지경로]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.poster_maker import PosterMaker

# ── 사진 경로 (CLI 인자 or 기본값) ───────────────────────────────
IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/khy/Downloads/marathon_photo.jpg"

# ── 이벤트 정보 ────────────────────────────────────────────────────
EVENT_CONFIG_FEED = {
    "title":        "2026\nMIRACLE MARATHON",
    "location":     "Gapcheon, Daejeon",
    "sublocation":  "Republic of Korea",
    "time":         "SUN. AM 08:00",
    "date":         "2026. 04. 19",
    "branding":     "2026 MIRACLE MARATHON  ·  Gapcheon, Daejeon  ·  2026.04.19",
    "color_scheme": "cool",
    # 피드용: km 수 예시
    "distance_km":  10,
}

EVENT_CONFIG_PHOTO = {
    "title":        "2026\nMIRACLE MARATHON",
    "location":     "Gapcheon, Daejeon",
    "sublocation":  "Republic of Korea",
    "time":         "SUN. AM 08:00",
    "date":         "2026. 04. 19",
    "branding":     "2026 MIRACLE MARATHON  ·  Gapcheon, Daejeon  ·  2026.04.19",
    "color_scheme": "cool",
    "distance_km":  0,   # 통계 없음 → 날짜/시간/장소 블록 표시
}

OUT_FEED  = "outputs/miracle/miracle_poster_feed.jpg"
OUT_PHOTO = "outputs/miracle/miracle_poster_photo.jpg"

if __name__ == "__main__":
    if not Path(IMAGE_PATH).exists():
        print(f"[오류] 이미지 파일 없음: {IMAGE_PATH}")
        print("사용법: python3 make_marathon_poster_from_photo.py /path/to/photo.jpg")
        sys.exit(1)

    maker = PosterMaker()

    print("── 피드용 (4:5) 생성 중...")
    path_feed = maker.make(
        image_path   = IMAGE_PATH,
        event_config = EVENT_CONFIG_FEED,
        output_path  = OUT_FEED,
        poster_mode  = "feed",
    )
    print(f"완료: {path_feed}")

    print("\n── 사진용 생성 중...")
    path_photo = maker.make(
        image_path   = IMAGE_PATH,
        event_config = EVENT_CONFIG_PHOTO,
        output_path  = OUT_PHOTO,
        poster_mode  = "photo",
    )
    print(f"완료: {path_photo}")
