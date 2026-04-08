"""
사진 1장으로 BLOSSOM RUNNING 포스터 생성.
사용: python make_blossom_photo_poster.py /path/to/photo.jpg
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.poster_maker import PosterMaker

# ── 사진 경로: 인자로 받거나 아래에 직접 지정 ──────────────────────
if len(sys.argv) > 1:
    IMAGE_PATH = sys.argv[1]
else:
    IMAGE_PATH = "/Users/khy/Downloads/blossom_bg.jpg"   # ← 여기에 경로 입력

# ── 이벤트 설정 ─────────────────────────────────────────────────────
EVENT_CONFIG = {
    "title":        "BLOSSOM\nRUNNING",
    "location":     "Chungnam National Univ.",
    "sublocation":  "N9-2",
    "time":         "P.M. 03:00",
    "date":         "2026.04.03",
    "distance_km":  5.2,
    "run_time":     "34'18\"",
    "pace":         "6'35\"/km",
    "color_scheme": "warm",
    "branding":     "BLOSSOM RUN  /  CNU N9-2  /  2026.04.03",
}

if __name__ == "__main__":
    if not Path(IMAGE_PATH).exists():
        print(f"[오류] 파일 없음: {IMAGE_PATH}")
        print("사용법: python make_blossom_photo_poster.py /경로/사진.jpg")
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"outputs/blossom/blossom_photo_poster_{ts}.jpg"
    Path("outputs/blossom").mkdir(parents=True, exist_ok=True)

    result = PosterMaker().make(
        image_path   = IMAGE_PATH,
        event_config = EVENT_CONFIG,
        output_path  = out,
    )

    if result:
        print(f"\n완료: {result}")
        import subprocess
        subprocess.run(["open", result])
    else:
        print("실패")
