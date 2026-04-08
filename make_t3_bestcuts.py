"""
t3.mp4 베스트컷 3장 + 포스터 1장 생성 스크립트

출력:
  outputs/t3/bestcuts/
    ├── cut_1_raw.jpg   ← 베스트컷 후보 #1 (텍스트 없음, 원본 크롭)
    ├── cut_2_raw.jpg   ← 베스트컷 후보 #2
    ├── cut_3_raw.jpg   ← 베스트컷 후보 #3
    └── poster.jpg      ← #1을 9:16 포스터로 완성 (텍스트 오버레이 포함)
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np
from PIL import Image

from src.poster_maker import PosterMaker, find_top_poster_frames
from src.preprocessor import preprocess
import tempfile

SRC = "/Users/khy/Downloads/t3.mp4"

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

OUT_DIR = Path("outputs/t3/bestcuts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 55)
print("  베스트컷 3장 + 포스터 1장 생성")
print("=" * 55)

# ── 1. 전처리 (rotation fix) ─────────────────────────────────
print("\n[1/3] 영상 전처리...")
with tempfile.TemporaryDirectory() as tmpdir:
    info = preprocess(SRC, target_duration=20.0, tmpdir=tmpdir)
    print(f"  {info.width}x{info.height}  원본={info.original_duration:.2f}s")

    # ── 2. 후보 타임스탬프 — 원본 구간 전체 균등 15개 ──────────────
    orig = info.original_duration or info.duration
    n_cand = 15
    candidates = [round(orig * (0.05 + i * 0.90 / (n_cand - 1)), 2) for i in range(n_cand)]
    print(f"  후보 프레임: {n_cand}개  ({candidates[0]:.2f}s ~ {candidates[-1]:.2f}s)")

    # ── 3. 상위 3개 타임스탬프 선택 ──────────────────────────────
    print("\n[2/3] MediaPipe 스코어링 → 상위 3개 선택...")
    top3 = find_top_poster_frames(
        video_path        = info.path,
        candidate_times   = candidates,
        top_n             = 3,
        model_path        = "models/pose_landmarker_full.task",
        target_size_ratio = 0.65,
        verbose           = True,
    )
    print(f"\n  선택된 베스트컷: {[f'{t:.2f}s' for t in top3]}")

    # ── 4. 각 프레임 추출 → raw 베스트컷 (9:16 크롭, 텍스트 없음) ──
    print("\n[3/3] 이미지 저장...")
    cap = cv2.VideoCapture(info.path)
    W_OUT, H_OUT = 1080, 1920

    raw_paths = []
    for i, t in enumerate(top3, 1):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame_bgr = cap.read()
        if not ret:
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(frame_rgb)

        # 9:16 center crop
        sw, sh = pil.size
        tgt_r = W_OUT / H_OUT
        src_r = sw / sh
        if src_r > tgt_r:
            new_w = int(sh * tgt_r)
            x0 = (sw - new_w) // 2
            pil = pil.crop((x0, 0, x0 + new_w, sh))
        else:
            new_h = int(sw / tgt_r)
            y0 = (sh - new_h) // 2
            pil = pil.crop((0, y0, sw, y0 + new_h))
        pil = pil.resize((W_OUT, H_OUT), Image.LANCZOS)

        out_path = str(OUT_DIR / f"cut_{i}_raw.jpg")
        pil.save(out_path, "JPEG", quality=93)
        raw_paths.append(out_path)
        print(f"  cut_{i}_raw.jpg  ← {t:.2f}s")

    cap.release()

    # ── 5. 포스터: 1등 프레임에 오버레이 적용 ────────────────────
    if top3:
        poster_path = str(OUT_DIR / "poster.jpg")
        PosterMaker().make(
            video_path   = info.path,
            frame_time   = top3[0],
            event_config = EVENT_CONFIG,
            output_path  = poster_path,
            color_grade  = True,
        )
        print(f"  poster.jpg      ← {top3[0]:.2f}s (9:16 오버레이 포함)")

print("\n" + "=" * 55)
print(f"  완료! → {OUT_DIR}/")
for f in sorted(OUT_DIR.iterdir()):
    kb = f.stat().st_size // 1024
    print(f"    {f.name}  ({kb} KB)")
print("=" * 55)
