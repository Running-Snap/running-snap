from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve


YOLOV8N_URL = "https://github.com/ultralytics/assets/releases/latest/download/yolov8n.pt"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download yolov8n.pt into project directory")
    p.add_argument(
        "--out",
        default="yolov8n.pt",
        help="Output model path (default: yolov8n.pt)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Redownload even if file already exists",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print(f"[skip] already exists: {out_path}")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] {YOLOV8N_URL}")
    print(f"[to] {out_path}")
    try:
        urlretrieve(YOLOV8N_URL, out_path)
    except URLError as e:
        raise SystemExit(f"download failed: {e}") from e

    if not out_path.exists() or out_path.stat().st_size <= 0:
        raise SystemExit("download failed: empty file")

    print(f"[done] {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
