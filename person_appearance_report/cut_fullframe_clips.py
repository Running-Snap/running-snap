from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2


def _safe_label(s: str) -> str:
    return re.sub(r"[^\w\-.]", "_", s)[:120]


def _load_ranges_from_label_summary(path: Path, include_unknown: bool) -> list[tuple[str, float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, float, float]] = []
    for row in data:
        label = str(row.get("label", "")).strip()
        if not label:
            continue
        if (not include_unknown) and label.startswith("unknown_"):
            continue
        s = float(row["first_appearance_sec"])
        e = float(row["last_exit_sec"])
        if e <= s:
            continue
        out.append((label, s, e))
    return out


def _load_ranges_from_track_events(path: Path, include_unknown: bool) -> list[tuple[str, float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    by_label: dict[str, tuple[float, float]] = {}
    for row in data:
        label = str(row.get("label", "")).strip()
        if not label:
            continue
        if (not include_unknown) and label.startswith("unknown_"):
            continue
        s = float(row["start_sec"])
        e = float(row["end_sec"])
        cur = by_label.get(label)
        if cur is None:
            by_label[label] = (s, e)
        else:
            by_label[label] = (min(cur[0], s), max(cur[1], e))
    out: list[tuple[str, float, float]] = []
    for label, (s, e) in by_label.items():
        if e > s:
            out.append((label, s, e))
    out.sort(key=lambda x: x[1])
    return out


def _sec_to_frame(sec: float, fps: float) -> int:
    return max(0, int(round(sec * fps)))


def cut_clips(
    video_path: Path,
    ranges: list[tuple[str, float, float]],
    output_dir: Path,
) -> None:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 1.0:
            fps = 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()

    output_dir.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    for label, s_sec, e_sec in ranges:
        start_f = _sec_to_frame(s_sec, fps)
        end_f = _sec_to_frame(e_sec, fps)
        if total > 0:
            start_f = min(start_f, max(0, total - 1))
            end_f = min(end_f, max(0, total - 1))
        if end_f <= start_f:
            continue

        out_name = f"{_safe_label(label)}_f{start_f}-f{end_f}.mp4"
        out_path = output_dir / out_name

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot reopen video: {video_path}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_f))
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError(f"Cannot open writer: {out_path}")
        try:
            idx = start_f
            while idx <= end_f:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                writer.write(frame)
                idx += 1
        finally:
            writer.release()
            cap.release()


def main() -> int:
    p = argparse.ArgumentParser(description="Cut full-frame clips by label time ranges")
    p.add_argument("--video", required=True, help="원본 풀영상 경로")
    p.add_argument("--label-summary", default="", help="label_summary.json 경로")
    p.add_argument("--track-events", default="", help="track_events.json 경로")
    p.add_argument("--include-unknown", action="store_true", help="unknown_* 라벨도 포함")
    p.add_argument("--out", required=True, help="출력 폴더")
    args = p.parse_args()

    label_summary = Path(args.label_summary) if args.label_summary else None
    track_events = Path(args.track_events) if args.track_events else None
    if not label_summary and not track_events:
        raise SystemExit("Either --label-summary or --track-events is required.")

    ranges: list[tuple[str, float, float]]
    if label_summary:
        ranges = _load_ranges_from_label_summary(label_summary, args.include_unknown)
    else:
        ranges = _load_ranges_from_track_events(track_events, args.include_unknown)  # type: ignore[arg-type]

    cut_clips(Path(args.video), ranges, Path(args.out))
    print(f"done: {len(ranges)} label ranges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
