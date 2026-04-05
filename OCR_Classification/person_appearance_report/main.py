from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .analyzer import run_report
from .config import ReportConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Person appearance pipeline (file/live): detect+track+OCR+timeline clips"
    )
    p.add_argument("--mode", choices=("file", "live"), default="file")
    p.add_argument("--video", type=str, default="", help="입력 영상 경로(file 모드)")
    p.add_argument("--source", type=str, default="0", help="라이브 입력 소스(live 모드): 0, 1, rtsp://...")
    p.add_argument("--out", type=str, default="appearance_report_output")
    p.add_argument("--ocr-backend", choices=("easyocr", "paddleocr", "noop"), default="easyocr")
    p.add_argument("--ocr-interval", type=int, default=5)
    p.add_argument(
        "--label-policy",
        choices=("confidence", "frequency"),
        default="confidence",
        help="track 최종 라벨 결정 방식",
    )
    p.add_argument("--progress-log-interval", type=int, default=120)
    p.add_argument("--quiet-ocr-log", action="store_true")
    p.add_argument("--no-gpu-yolo", action="store_true")
    p.add_argument("--no-gpu-ocr", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    mode = str(args.mode).strip().lower()
    video_source = ""
    if mode == "file":
        if not args.video:
            raise SystemExit("--mode file 에서는 --video 가 필요합니다.")
        video_path = Path(args.video)
        if not video_path.exists():
            raise SystemExit(f"입력 영상이 없습니다: {video_path}")
        video_source = str(video_path)

    cfg = ReportConfig(
        mode=mode,
        video_source=video_source,
        live_source=args.source,
        output_dir=args.out,
        ocr_backend=args.ocr_backend,
        ocr_interval_frames=max(1, args.ocr_interval),
        label_decision_policy=args.label_policy,
        progress_log_interval_frames=max(1, args.progress_log_interval),
        log_recognition=not args.quiet_ocr_log,
        use_gpu_yolo=not args.no_gpu_yolo,
        use_gpu_ocr=not args.no_gpu_ocr,
    )
    result = run_report(cfg)
    log.info(
        "Done: events=%s label_clips=%s",
        result["events_count"],
        result["label_clips_count"],
    )
    log.info("events_json: %s", result["outputs"]["events_json"])
    log.info("clips_dir: %s", result["outputs"]["clips_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
