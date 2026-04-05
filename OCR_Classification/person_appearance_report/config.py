from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReportConfig:
    video_source: str = ""
    mode: str = "file"  # file | live
    live_source: str = "0"  # webcam index ("0") or RTSP URL
    output_dir: str = "appearance_report_output"

    yolo_model_path: str = "yolov8n.pt"
    yolo_conf: float = 0.35
    yolo_iou: float = 0.45
    person_class_names: tuple[str, ...] = ("person",)
    use_gpu_yolo: bool = True

    tracker_iou_threshold: float = 0.25
    tracker_max_missed: int = 20

    ocr_backend: str = "easyocr"  # easyocr | paddleocr | noop
    use_gpu_ocr: bool = True
    easyocr_langs: list[str] = field(default_factory=lambda: ["en"])
    ocr_interval_frames: int = 5
    ocr_min_confidence: float = 0.25
    ocr_label_pattern: str = r"^[A-Z0-9]{2,8}$"
    bib_roi_rel_in_person: tuple[float, float, float, float] = (0.2, 0.08, 0.8, 0.45)
    label_decision_policy: str = "confidence"  # confidence | frequency

    log_recognition: bool = True
    progress_log_interval_frames: int = 120
    live_read_retry_sec: float = 0.2

    def output_path(self) -> Path:
        return Path(self.output_dir)
