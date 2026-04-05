from __future__ import annotations

from dataclasses import dataclass

from .config import ReportConfig


@dataclass
class TrackedPerson:
    track_id: int
    bbox_xyxy: tuple[int, int, int, int]


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    bbox: tuple[int, int, int, int]
    missed: int = 0


class TrackerManager:
    def __init__(self, cfg: ReportConfig):
        self._iou_thr = cfg.tracker_iou_threshold
        self._max_missed = cfg.tracker_max_missed
        self._next_id = 1
        self._tracks: dict[int, _Track] = {}

    def update(
        self, detections: list[tuple[int, int, int, int]]
    ) -> list[TrackedPerson]:
        assigned: dict[int, tuple[int, int, int, int]] = {}
        used = set()
        for tid, tr in list(self._tracks.items()):
            best_j = -1
            best_iou = self._iou_thr
            for j, bb in enumerate(detections):
                if j in used:
                    continue
                score = _iou(tr.bbox, bb)
                if score > best_iou:
                    best_iou = score
                    best_j = j
            if best_j >= 0:
                tr.bbox = detections[best_j]
                tr.missed = 0
                used.add(best_j)
                assigned[tid] = tr.bbox
            else:
                tr.missed += 1
                if tr.missed > self._max_missed:
                    del self._tracks[tid]
        for j, bb in enumerate(detections):
            if j in used:
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks[tid] = _Track(track_id=tid, bbox=bb, missed=0)
            assigned[tid] = bb
        return [TrackedPerson(track_id=tid, bbox_xyxy=bb) for tid, bb in assigned.items()]

    def active_track_ids(self) -> set[int]:
        return set(self._tracks.keys())
