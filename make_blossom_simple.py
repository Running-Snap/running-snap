"""
BLOSSOM 단순 인증영상 (슬로우모 없음)
  - 원본 영상 1x 그대로 재생 (루프 없음)
  - 영상 후반부(40%~)부터 Nike 스타일 기록 그래픽 순차 등장
  - 원본 길이에 딱 맞춰 종료

사용:
    python make_blossom_simple.py
    python make_blossom_simple.py /path/to/video.mp4
"""
import sys, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.preprocessor    import preprocess
from src.template_executor import TemplateExecutor
from src.cert_builder    import CertBuilder

# ── 소스 영상 ─────────────────────────────────────────────────────
SRC = sys.argv[1] if len(sys.argv) > 1 else \
      "/Users/khy/Downloads/IMG_0716.MOV"

# ── 이벤트 정보 ───────────────────────────────────────────────────
EVENT_CONFIG = {
    "title":          "BLOSSOM\nRUNNING",
    "date":           "2026.04.03",
    "distance_km":    5.2,
    "pace":           "6'35\"/km",
    "run_time":       "34'18\"",
    "calories":       "312 kcal",
    "elevation_gain": "48 m",
    "avg_heart_rate": "152 bpm",
    "cadence":        "163 spm",
    "color_scheme":   "warm",
}

if __name__ == "__main__":
    if not Path(SRC).exists():
        print(f"[오류] 파일 없음: {SRC}")
        sys.exit(1)

    out_dir = "outputs/blossom"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"{out_dir}/blossom_simple_{ts}.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        print("[1/3] 전처리 (rotation fix, 루프 없음)...")
        # target_duration을 원본과 같게 → 루프 없이 rotation만 교정
        info = preprocess(SRC, target_duration=3.5, tmpdir=tmpdir)
        orig = info.original_duration or info.duration
        print(f"  원본 길이: {orig:.2f}s  ({info.width}x{info.height})")

        print("[2/3] instruction 빌드...")
        instruction = CertBuilder.build_simple(orig, EVENT_CONFIG)

        print(f"[3/3] 렌더링 → {out}")
        TemplateExecutor(verbose=True).execute(instruction, info.path, out)

    if Path(out).exists():
        print(f"\n완료: {out}")
        import subprocess
        subprocess.run(["open", out])
    else:
        print("실패")
