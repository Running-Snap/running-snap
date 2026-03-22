"""OpenCV 기반 프레임 추출 및 코칭 영상 생성"""
import os
import shutil
import subprocess
from datetime import datetime


def extract_frames(video_path: str, photo_count: int, output_dir: str) -> list:
    """균등 간격으로 프레임을 추출해 JPEG 저장 후 결과 리스트 반환"""
    try:
        import cv2
    except ImportError:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0

    if total_frames <= 0:
        cap.release()
        return []

    descriptions = [
        "완벽한 착지 자세", "이상적인 팔 스윙", "균형 잡힌 상체 자세",
        "최적의 보폭 구간", "힘찬 킥 동작", "안정적인 코어 자세",
        "효율적인 호흡 구간", "강한 추진력 순간", "리듬감 있는 발걸음", "최고 속도 구간",
    ]

    start  = int(total_frames * 0.1)
    end    = int(total_frames * 0.9)
    usable = max(1, end - start)
    indices = [start + int(i * usable / (photo_count + 1)) for i in range(1, photo_count + 1)]

    os.makedirs(output_dir, exist_ok=True)
    ts_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    photos = []

    for i, idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        ts_sec = idx / fps
        ts_str = f"{int(ts_sec // 60)}:{int(ts_sec % 60):02d}"
        filename = f"bestcut_{ts_prefix}_{i+1}.jpg"
        cv2.imwrite(os.path.join(output_dir, filename), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        photos.append({
            "photo_url":   f"/outputs/photos/{filename}",
            "timestamp":   ts_str,
            "description": descriptions[i % len(descriptions)],
        })

    cap.release()
    return photos


def create_coaching_video(video_path: str, coaching_text: str, output_path: str) -> bool:
    """코칭 텍스트 자막을 영상 하단에 오버레이하여 저장"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False

    fps         = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames= int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    sentences = [s.strip() for s in coaching_text.replace("\n", ". ").split(".") if s.strip()]
    if not sentences:
        sentences = [coaching_text[:40]]
    frames_per_sentence = max(1, total_frames // max(1, len(sentences)))

    import tempfile
    tmp_path = output_path + ".tmp.mp4"
    out = cv2.VideoWriter(tmp_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not out.isOpened():
        cap.release()
        return False

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        text    = sentences[min(frame_count // frames_per_sentence, len(sentences) - 1)]
        overlay = frame.copy()
        bar_h   = max(60, height // 8)
        cv2.rectangle(overlay, (0, height - bar_h), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        cv2.putText(
            frame, text[:60], (20, height - bar_h // 3),
            cv2.FONT_HERSHEY_SIMPLEX, max(0.5, width / 1280), (255, 255, 255), 2, cv2.LINE_AA,
        )
        out.write(frame)
        frame_count += 1

    cap.release()
    out.release()

    if frame_count == 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    ffmpeg_bin = shutil.which("ffmpeg")
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-y", "-i", tmp_path, "-vcodec", "libx264", "-an", "-movflags", "+faststart", output_path],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            os.remove(tmp_path)
            return True
        if os.path.exists(tmp_path):
            shutil.move(tmp_path, output_path)
        return os.path.exists(output_path)
    except Exception:
        if os.path.exists(tmp_path):
            shutil.move(tmp_path, output_path)
        return os.path.exists(output_path)
