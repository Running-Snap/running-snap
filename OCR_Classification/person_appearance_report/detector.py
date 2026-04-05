from __future__ import annotations

import logging

import numpy as np

from .config import ReportConfig

log = logging.getLogger(__name__)


class PersonDetector:
    def __init__(self, cfg: ReportConfig):
        self._cfg = cfg
        try:
            from ultralytics import YOLO

            self._model = YOLO(cfg.yolo_model_path)
            self._ok = True
        except Exception as e:
            log.warning("YOLO load failed (%s).", e)
            self._ok = False
            self._model = None

    @property
    def available(self) -> bool:
        return self._ok and self._model is not None

    def detect(self, frame_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        if not self.available:
            return []
        device: str | int = "cpu"
        if self._cfg.use_gpu_yolo:
            try:
                import torch

                device = 0 if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        res = self._model.predict(
            source=frame_bgr,
            verbose=False,
            conf=self._cfg.yolo_conf,
            iou=self._cfg.yolo_iou,
            device=device,
        )
        if not res:
            return []
        r = res[0]
        if r.boxes is None or len(r.boxes) == 0:
            return []
        names = r.names or {}
        xyxy = r.boxes.xyxy.cpu().numpy()
        clss = r.boxes.cls.cpu().numpy().astype(int)
        out: list[tuple[int, int, int, int]] = []
        for i in range(len(xyxy)):
            cname = names.get(int(clss[i]), str(int(clss[i])))
            if cname not in self._cfg.person_class_names:
                continue
            out.append(tuple(map(int, xyxy[i])))
        return out
