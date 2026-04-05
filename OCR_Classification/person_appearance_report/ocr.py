from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import cv2
import numpy as np

from .config import ReportConfig

log = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float


def normalize_label(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _extract_candidates(text: str, min_len: int = 2, max_len: int = 8) -> list[str]:
    raw = re.sub(r"[^A-Za-z0-9]+", "", text.upper())
    if not raw:
        return []
    out: list[str] = []
    for m in re.finditer(r"[A-Z0-9]{%d,%d}" % (min_len, max_len), raw):
        out.append(m.group())
    if not out and min_len <= len(raw) <= max_len:
        out.append(raw)
    return out


class _NoopOCREngine:
    def read_text(self, gray_frame: np.ndarray) -> list[OCRResult]:
        return []


class _EasyOCREngine:
    def __init__(self, langs: list[str], use_gpu: bool = False):
        import easyocr

        self._reader = easyocr.Reader(langs, gpu=use_gpu)

    def read_text(self, gray_frame: np.ndarray) -> list[OCRResult]:
        arr = self._reader.readtext(gray_frame, detail=1, paragraph=False)
        out: list[OCRResult] = []
        for item in arr:
            if len(item) < 3:
                continue
            _, text, conf = item[0], item[1], item[2]
            out.append(OCRResult(str(text), float(conf)))
        return out


class _PaddleOCREngine:
    def __init__(self, use_gpu: bool = False):
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=use_gpu, show_log=False)

    def read_text(self, gray_frame: np.ndarray) -> list[OCRResult]:
        arr = self._ocr.ocr(gray_frame, cls=False)
        out: list[OCRResult] = []
        if not arr:
            return out
        for line in arr[0]:
            try:
                text = str(line[1][0])
                conf = float(line[1][1])
                out.append(OCRResult(text, conf))
            except Exception:
                continue
        return out


class OCRManager:
    def __init__(self, cfg: ReportConfig):
        self._cfg = cfg
        self._pattern = re.compile(cfg.ocr_label_pattern)
        self._engine = self._build_engine()

    def _build_engine(self):
        backend = self._cfg.ocr_backend
        use_gpu = self._resolve_ocr_gpu()
        if backend == "easyocr":
            return _EasyOCREngine(self._cfg.easyocr_langs, use_gpu=use_gpu)
        if backend == "paddleocr":
            return _PaddleOCREngine(use_gpu=use_gpu)
        return _NoopOCREngine()

    def _resolve_ocr_gpu(self) -> bool:
        if not self._cfg.use_gpu_ocr:
            return False
        try:
            import torch

            has_cuda = bool(torch.cuda.is_available())
            if not has_cuda:
                log.info("OCR GPU requested but CUDA not available; fallback to CPU")
            return has_cuda
        except Exception:
            log.info("torch not available for CUDA check; OCR fallback to CPU")
            return False

    def _bib_roi(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return np.array([])
        pw, ph = x2 - x1, y2 - y1
        rx0, ry0, rx1, ry1 = self._cfg.bib_roi_rel_in_person
        xa = int(x1 + rx0 * pw)
        ya = int(y1 + ry0 * ph)
        xb = int(x1 + rx1 * pw)
        yb = int(y1 + ry1 * ph)
        xa, ya = max(0, xa), max(0, ya)
        xb, yb = min(w, xb), min(h, yb)
        if xb <= xa or yb <= ya:
            return np.array([])
        return frame[ya:yb, xa:xb].copy()

    def read_candidates(
        self, frame_bgr: np.ndarray, bbox: tuple[int, int, int, int]
    ) -> list[tuple[str, float]]:
        roi = self._bib_roi(frame_bgr, bbox)
        if roi.size == 0:
            return []
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 5, 40, 40)
        results = self._engine.read_text(gray)
        out: list[tuple[str, float]] = []
        for r in results:
            if float(r.confidence) < self._cfg.ocr_min_confidence:
                continue
            for cand in _extract_candidates(str(r.text)):
                n = normalize_label(cand)
                if not n or not self._pattern.match(n):
                    continue
                out.append((n, float(r.confidence)))
        out.sort(key=lambda x: x[1], reverse=True)
        return out
