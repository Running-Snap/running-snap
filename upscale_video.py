"""
upscale_video.py
================
AIImageEnhancer (Real-ESRGAN) 기반 영상 화질 개선

사용법:
    python upscale_video.py --input outputs/videos/half_record_cert.mp4
    python upscale_video.py --input outputs/videos/half_record_cert.mp4 --scale 2.0 --output outputs/videos/half_record_cert_hq.mp4
"""

import argparse
import sys
import os
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from src.photographers.super_resolution import AIImageEnhancer, MotionDeblurrer


def _cv_upscale(frame_bgr: np.ndarray, scale: float, deblur: bool) -> np.ndarray:
    """torch 없을 때 OpenCV fallback: Lanczos 업스케일 + Unsharp 샤프닝"""
    if deblur:
        deblurrer = MotionDeblurrer()
        frame_bgr = deblurrer.deblur(frame_bgr, unsharp_strength=1.5)
    h, w = frame_bgr.shape[:2]
    return cv2.resize(frame_bgr, (int(w * scale), int(h * scale)),
                      interpolation=cv2.INTER_LANCZOS4)


def _check_torch() -> bool:
    try:
        import torch  # noqa
        return True
    except ImportError:
        return False


def upscale_video(
    input_path: str,
    output_path: str,
    scale: float = 2.0,
    deblur: bool = True,
):
    print("=" * 60)
    print("  AI 영상 화질 개선 (Real-ESRGAN)")
    print("=" * 60)
    print(f"  입력  : {input_path}")
    print(f"  출력  : {output_path}")
    print(f"  배율  : {scale}x")
    print(f"  디블러: {deblur}")
    print()

    # ── 입력 영상 열기 ──────────────────────────────────────────────
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {input_path}")

    src_w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dst_w  = int(src_w * scale)
    dst_h  = int(src_h * scale)

    print(f"  원본 해상도: {src_w}×{src_h}")
    print(f"  출력 해상도: {dst_w}×{dst_h}")
    print(f"  총 프레임  : {total}  ({total/fps:.1f}s @ {fps}fps)")
    print()

    # ── 출력 영상 설정 (임시 — AVI 사용: macOS에서 moov 누락 문제 방지) ──
    tmp_path = output_path.replace(".mp4", "_noaudio_tmp.avi")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"XVID")   # AVI + XVID (항상 헤더 먼저 기록)
    writer = cv2.VideoWriter(tmp_path, fourcc, fps, (dst_w, dst_h))
    if not writer.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")   # fallback: MJPEG
        writer = cv2.VideoWriter(tmp_path, fourcc, fps, (dst_w, dst_h))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter 열기 실패")

    # ── AI 향상기 초기화 ────────────────────────────────────────────
    BATCH_SIZE = 4          # MPS 배치 추론 (4프레임 동시 처리 → ~4배 빠름)
    ESRGAN_IN_W, ESRGAN_IN_H = 640, 360

    has_torch = _check_torch()
    if has_torch:
        import torch
        from src.photographers.super_resolution import RealESRGANUpscaler, MotionDeblurrer

        print(f"[모드] Real-ESRGAN 4x 배치{BATCH_SIZE} (입력 {ESRGAN_IN_W}×{ESRGAN_IN_H} → 출력 {dst_w}×{dst_h})")
        upscaler  = RealESRGANUpscaler(
            model_path=str(Path(__file__).parent / "models" / "RealESRGAN_x4plus.pth")
        )
        upscaler._load_model()          # 미리 로드
        device    = upscaler.device
        deblurrer = MotionDeblurrer() if deblur else None

        def frames_to_tensor(frames_bgr):
            """BGR frame 리스트 → MPS tensor (N,C,H,W)"""
            tensors = []
            for f in frames_bgr:
                img = deblurrer.deblur(f) if deblurrer else f
                small = cv2.resize(img, (ESRGAN_IN_W, ESRGAN_IN_H), interpolation=cv2.INTER_LANCZOS4)
                rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                t     = torch.from_numpy(rgb).float() / 255.0
                tensors.append(t.permute(2, 0, 1))   # (C,H,W)
            batch = torch.stack(tensors).to(device)   # (N,C,H,W)
            return batch

        def batch_upscale(frames_bgr):
            """N프레임 배치 추론 → BGR frame 리스트"""
            batch = frames_to_tensor(frames_bgr)
            with torch.no_grad():
                out = upscaler._model(batch)           # (N,C,H_out,W_out)
            results = []
            for j in range(out.shape[0]):
                f = out[j].permute(1, 2, 0).float().clamp(0, 1).cpu().numpy()
                results.append(cv2.cvtColor((f * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
            return results

    else:
        BATCH_SIZE = 1
        print("[모드] OpenCV Lanczos 업스케일 (torch 미설치 — fallback)")
        def batch_upscale(frames_bgr):
            return [_cv_upscale(f, scale, deblur) for f in frames_bgr]

    # ── 배치 처리 루프 ──────────────────────────────────────────────
    print("[처리 시작] 배치 AI 화질 개선 중...")
    t_start  = time.time()
    done     = 0
    buf      = []

    while True:
        ret, frame_bgr = cap.read()
        if ret:
            buf.append(frame_bgr)

        if len(buf) >= BATCH_SIZE or (not ret and buf):
            enhanced_list = batch_upscale(buf)
            for ef in enhanced_list:
                writer.write(ef)
            done += len(buf)
            buf = []
            elapsed  = time.time() - t_start
            fps_proc = done / elapsed
            eta      = (total - done) / fps_proc if fps_proc > 0 else 0
            print(f"  [{done:3d}/{total}] {fps_proc:.2f} fps  ETA {eta:.0f}s", end="\r", flush=True)

        if not ret:
            break

    print()
    cap.release()
    writer.release()

    # ── 오디오 합성 (ffmpeg) ────────────────────────────────────────
    ffmpeg = "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(ffmpeg):
        ffmpeg = "ffmpeg"   # PATH에 있으면 사용

    print("[오디오] 원본 오디오 합성 + H.264 변환 중...")
    ret = os.system(
        f'"{ffmpeg}" -y -i "{tmp_path}" -i "{input_path}" '
        f'-c:v libx264 -crf 18 -preset medium '
        f'-c:a aac -map 0:v:0 -map 1:a:0 '
        f'"{output_path}" -loglevel error'
    )
    if ret != 0:
        print("  [주의] 오디오 합성 실패 — 영상만 저장")
        os.system(
            f'"{ffmpeg}" -y -i "{tmp_path}" '
            f'-c:v libx264 -crf 18 -preset medium '
            f'"{output_path}" -loglevel error'
        )

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    total_t = time.time() - t_start
    print()
    print("=" * 60)
    print(f"  완료!  {size_mb:.1f} MB  (소요: {total_t:.0f}s)")
    print(f"  → {output_path}")
    print("=" * 60)


def main():
    ap = argparse.ArgumentParser(description="AI 영상 화질 개선 (Real-ESRGAN)")
    ap.add_argument("--input",  required=True,  help="입력 영상 경로")
    ap.add_argument("--output", default=None,   help="출력 영상 경로 (기본: _hq 접미사)")
    ap.add_argument("--scale",  type=float, default=2.0, help="업스케일 배율 (기본 2.0)")
    ap.add_argument("--no-deblur", action="store_true",  help="디블러 비활성화")
    args = ap.parse_args()

    in_path  = args.input
    out_path = args.output or str(
        Path(in_path).with_stem(Path(in_path).stem + "_hq")
    )

    upscale_video(
        input_path=in_path,
        output_path=out_path,
        scale=args.scale,
        deblur=not args.no_deblur,
    )


if __name__ == "__main__":
    main()
