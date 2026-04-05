from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2

from .config import ReportConfig
from .cut_fullframe_clips import cut_clips
from .detector import PersonDetector
from .ocr import OCRManager
from .tracker import TrackerManager

log = logging.getLogger(__name__)


@dataclass
class _TrackState:
    first_frame: int
    last_frame: int
    last_ocr_frame: int = -10**9
    ocr_votes: Counter[str] = None  # type: ignore[assignment]
    conf_scores: dict[str, float] = None  # type: ignore[assignment]
    ocr_frame_candidates: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ocr_votes is None:
            self.ocr_votes = Counter()
        if self.conf_scores is None:
            self.conf_scores = {}
        if self.ocr_frame_candidates is None:
            self.ocr_frame_candidates = []


@dataclass
class _LiveClipSlot:
    path: Path
    writer: cv2.VideoWriter
    start_frame: int
    end_frame: int


def _to_sec(frame_idx: int, fps: float) -> float:
    return float(frame_idx) / (fps if fps > 0 else 30.0)


def _decide_label(st: _TrackState, tid: int, policy: str) -> str:
    if not st.ocr_votes:
        return f"unknown_{tid}"
    if policy == "frequency":
        return st.ocr_votes.most_common(1)[0][0]
    if st.conf_scores:
        return sorted(st.conf_scores.items(), key=lambda x: x[1], reverse=True)[0][0]
    return st.ocr_votes.most_common(1)[0][0]


def _aggregate_label_first_last(events: list[dict], include_unknown: bool = False) -> list[tuple[str, float, float]]:
    by_label: dict[str, tuple[float, float]] = {}
    for e in events:
        lb = str(e["label"])
        if (not include_unknown) and lb.startswith("unknown_"):
            continue
        s = float(e["start_sec"])
        t = float(e["end_sec"])
        cur = by_label.get(lb)
        if cur is None:
            by_label[lb] = (s, t)
        else:
            by_label[lb] = (min(cur[0], s), max(cur[1], t))
    out: list[tuple[str, float, float]] = []
    for lb, (s, t) in by_label.items():
        if t > s:
            out.append((lb, s, t))
    out.sort(key=lambda x: x[1])
    return out


def _safe_label(s: str) -> str:
    return re.sub(r"[^\w\-.]", "_", s)[:120]


def _capture_source_from_text(source: str) -> str | int:
    s = str(source).strip()
    if s.isdigit():
        return int(s)
    return s


def _build_event(
    st: _TrackState,
    tid: int,
    final_label: str,
    policy: str,
    fps: float,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> dict:
    sf = st.first_frame if start_frame is None else int(start_frame)
    ef = st.last_frame if end_frame is None else int(end_frame)
    return {
        "track_id": tid,
        "label": final_label,
        "start_frame": sf,
        "end_frame": ef,
        "start_sec": round(_to_sec(sf, fps), 3),
        "end_sec": round(_to_sec(ef, fps), 3),
        "duration_sec": round(_to_sec(ef - sf + 1, fps), 3),
        "votes": dict(st.ocr_votes),
        "confidence_scores": {k: round(v, 4) for k, v in st.conf_scores.items()},
        "decision_policy": policy,
        "ocr_frame_candidates": st.ocr_frame_candidates,
    }


def _run_file_report(cfg: ReportConfig) -> dict:
    det = PersonDetector(cfg)
    trk = TrackerManager(cfg)
    ocr = OCRManager(cfg)
    log.info(
        "file report start | video=%s | ocr_backend=%s | ocr_interval=%s | label_policy=%s",
        cfg.video_source,
        cfg.ocr_backend,
        cfg.ocr_interval_frames,
        cfg.label_decision_policy,
    )

    cap = cv2.VideoCapture(str(cfg.video_source))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {cfg.video_source}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1.0:
        fps = 30.0
    log.info("video opened | fps=%.3f", fps)

    states: dict[int, _TrackState] = {}
    prev_active: set[int] = set()
    events: list[dict] = []
    frame_idx = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            boxes = det.detect(frame)
            tracked = trk.update(boxes)
            matched_ids = {t.track_id for t in tracked}
            active_ids = trk.active_track_ids()

            for t in tracked:
                st = states.get(t.track_id)
                if st is None:
                    st = _TrackState(first_frame=frame_idx, last_frame=frame_idx)
                    states[t.track_id] = st
                    log.info("track appear | tid=%s | frame=%s", t.track_id, frame_idx)
                st.last_frame = frame_idx

                candidates: list[tuple[str, float]] = []
                ocr_ran = frame_idx - st.last_ocr_frame >= cfg.ocr_interval_frames
                if ocr_ran:
                    st.last_ocr_frame = frame_idx
                    candidates = ocr.read_candidates(frame, t.bbox_xyxy)
                    for lb, cf in candidates:
                        st.ocr_votes[lb] += 1
                        st.conf_scores[lb] = st.conf_scores.get(lb, 0.0) + float(cf)
                st.ocr_frame_candidates.append(
                    {
                        "frame": frame_idx,
                        "ocr_ran": bool(ocr_ran),
                        "candidates": [
                            {"label": lb, "confidence": round(float(cf), 4)} for lb, cf in candidates
                        ],
                    }
                )
                if cfg.log_recognition and ocr_ran:
                    log.info(
                        "ocr frame | tid=%s | frame=%s | candidates=%s | votes=%s",
                        t.track_id,
                        frame_idx,
                        [(lb, round(cf, 3)) for lb, cf in candidates],
                        dict(st.ocr_votes),
                    )

            disappeared = prev_active - active_ids
            for tid in disappeared:
                st = states.pop(tid, None)
                if st is None:
                    continue
                final_label = _decide_label(st, tid, cfg.label_decision_policy)
                log.info(
                    "track disappear | tid=%s | frame=%s | final_label=%s | interval=%s~%s",
                    tid,
                    frame_idx,
                    final_label,
                    st.first_frame,
                    st.last_frame,
                )
                events.append(_build_event(st, tid, final_label, cfg.label_decision_policy, fps))

            prev_active = active_ids
            if (
                cfg.progress_log_interval_frames > 0
                and frame_idx > 0
                and frame_idx % cfg.progress_log_interval_frames == 0
            ):
                log.info(
                    "progress | frame=%s | matched_tracks=%s | active_tracks=%s | finalized_events=%s",
                    frame_idx,
                    len(matched_ids),
                    len(active_ids),
                    len(events),
                )
            frame_idx += 1
    finally:
        cap.release()

    for tid, st in list(states.items()):
        final_label = _decide_label(st, tid, cfg.label_decision_policy)
        events.append(_build_event(st, tid, final_label, cfg.label_decision_policy, fps))

    out_dir = cfg.output_path()
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "track_events.json"
    clips_dir = out_dir / "fullframe_label_clips"
    events_sorted = sorted(events, key=lambda x: (x["start_frame"], x["track_id"]))
    events_path.write_text(json.dumps(events_sorted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ranges = _aggregate_label_first_last(events_sorted, include_unknown=False)
    cut_clips(Path(cfg.video_source), ranges, clips_dir)

    log.info(
        "report done | frames=%s | track_events=%s | label_clips=%s",
        frame_idx,
        len(events_sorted),
        len(ranges),
    )
    return {
        "fps": fps,
        "total_frames": frame_idx,
        "events_count": len(events_sorted),
        "label_clips_count": len(ranges),
        "mode": "file",
        "outputs": {
            "events_json": str(events_path),
            "clips_dir": str(clips_dir),
        },
    }


def _run_live_report(cfg: ReportConfig) -> dict:
    det = PersonDetector(cfg)
    trk = TrackerManager(cfg)
    ocr = OCRManager(cfg)
    source = _capture_source_from_text(cfg.live_source)
    log.info(
        "live report start | source=%s | ocr_backend=%s | ocr_interval=%s | label_policy=%s",
        cfg.live_source,
        cfg.ocr_backend,
        cfg.ocr_interval_frames,
        cfg.label_decision_policy,
    )

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open live source: {cfg.live_source}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1.0:
        fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    log.info("live source opened | fps=%.3f | size=%sx%s", fps, width, height)

    out_dir = cfg.output_path()
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "track_events.json"
    clips_dir = out_dir / "fullframe_label_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    states: dict[int, _TrackState] = {}
    slots: dict[int, _LiveClipSlot] = {}
    prev_active: set[int] = set()
    events: list[dict] = []
    frame_idx = 0
    label_clip_count = 0

    def _finalize_tid(tid: int) -> None:
        nonlocal label_clip_count
        st = states.pop(tid, None)
        slot = slots.pop(tid, None)
        if st is None:
            if slot is not None:
                slot.writer.release()
            return
        final_label = _decide_label(st, tid, cfg.label_decision_policy)
        start_frame = st.first_frame
        end_frame = st.last_frame
        if slot is not None:
            slot.writer.release()
            start_frame = slot.start_frame
            end_frame = slot.end_frame
            if final_label.startswith("unknown_"):
                try:
                    if slot.path.exists():
                        slot.path.unlink()
                except Exception as e:
                    log.warning("failed to remove unknown clip (%s): %s", slot.path, e)
            else:
                final_name = f"{_safe_label(final_label)}_f{start_frame}-f{end_frame}.mp4"
                final_path = clips_dir / final_name
                try:
                    slot.path.replace(final_path)
                    label_clip_count += 1
                except Exception as e:
                    log.warning("failed to rename live clip (%s): %s", slot.path, e)
        ev = _build_event(
            st,
            tid,
            final_label,
            cfg.label_decision_policy,
            fps,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        events.append(ev)
        log.info(
            "track finalized | tid=%s | label=%s | frames=%s~%s",
            tid,
            final_label,
            start_frame,
            end_frame,
        )

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(max(0.01, cfg.live_read_retry_sec))
                continue

            boxes = det.detect(frame)
            tracked = trk.update(boxes)
            matched_ids = {t.track_id for t in tracked}
            active_ids = trk.active_track_ids()

            for t in tracked:
                st = states.get(t.track_id)
                if st is None:
                    st = _TrackState(first_frame=frame_idx, last_frame=frame_idx)
                    states[t.track_id] = st
                    temp_name = f"_tmp_tid{t.track_id}_f{frame_idx}_{int(time.time() * 1000)}.mp4"
                    temp_path = clips_dir / temp_name
                    wr = cv2.VideoWriter(str(temp_path), fourcc, fps, (width, height))
                    if not wr.isOpened():
                        raise RuntimeError(f"Cannot open live clip writer: {temp_path}")
                    slots[t.track_id] = _LiveClipSlot(
                        path=temp_path,
                        writer=wr,
                        start_frame=frame_idx,
                        end_frame=frame_idx,
                    )
                    log.info("track appear | tid=%s | frame=%s", t.track_id, frame_idx)
                st.last_frame = frame_idx

                candidates: list[tuple[str, float]] = []
                ocr_ran = frame_idx - st.last_ocr_frame >= cfg.ocr_interval_frames
                if ocr_ran:
                    st.last_ocr_frame = frame_idx
                    candidates = ocr.read_candidates(frame, t.bbox_xyxy)
                    for lb, cf in candidates:
                        st.ocr_votes[lb] += 1
                        st.conf_scores[lb] = st.conf_scores.get(lb, 0.0) + float(cf)
                st.ocr_frame_candidates.append(
                    {
                        "frame": frame_idx,
                        "ocr_ran": bool(ocr_ran),
                        "candidates": [
                            {"label": lb, "confidence": round(float(cf), 4)} for lb, cf in candidates
                        ],
                    }
                )

                if cfg.log_recognition and ocr_ran:
                    log.info(
                        "ocr frame | tid=%s | frame=%s | candidates=%s | votes=%s",
                        t.track_id,
                        frame_idx,
                        [(lb, round(cf, 3)) for lb, cf in candidates],
                        dict(st.ocr_votes),
                    )

            for tid in active_ids:
                slot = slots.get(tid)
                if slot is None:
                    continue
                slot.writer.write(frame)
                slot.end_frame = frame_idx

            disappeared = prev_active - active_ids
            for tid in disappeared:
                _finalize_tid(tid)

            prev_active = active_ids
            if (
                cfg.progress_log_interval_frames > 0
                and frame_idx > 0
                and frame_idx % cfg.progress_log_interval_frames == 0
            ):
                log.info(
                    "live progress | frame=%s | matched_tracks=%s | active_tracks=%s | finalized_events=%s | clips=%s",
                    frame_idx,
                    len(matched_ids),
                    len(active_ids),
                    len(events),
                    label_clip_count,
                )
            frame_idx += 1
    except KeyboardInterrupt:
        log.info("live stop requested by user")
    finally:
        cap.release()
        for tid in list(states.keys()):
            _finalize_tid(tid)

    events_sorted = sorted(events, key=lambda x: (x["start_frame"], x["track_id"]))
    events_path.write_text(json.dumps(events_sorted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info(
        "live report done | frames=%s | track_events=%s | label_clips=%s",
        frame_idx,
        len(events_sorted),
        label_clip_count,
    )
    return {
        "fps": fps,
        "total_frames": frame_idx,
        "events_count": len(events_sorted),
        "label_clips_count": label_clip_count,
        "mode": "live",
        "outputs": {
            "events_json": str(events_path),
            "clips_dir": str(clips_dir),
        },
    }


def run_report(cfg: ReportConfig) -> dict:
    mode = str(cfg.mode or "file").strip().lower()
    if mode == "live":
        return _run_live_report(cfg)
    return _run_file_report(cfg)
