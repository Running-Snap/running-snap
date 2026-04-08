"""
export_skeleton_json.py
========================
MediaPipe PoseLandmarker로 영상 분석 → JSON 결과 저장
  - 프레임별 33개 랜드마크 좌표 + visibility + presence
  - 전체 detection 통계 (감지율, 주요 관절 평균 visibility)
  - 출력: outputs/skeleton_data_<ts>.json
"""
import sys, os, json
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

# ── 설정 ──────────────────────────────────────────────────────────
SOURCE = "front_side_view_rotated.mp4"   # 바꿔서 쓰기
MODEL  = "models/pose_landmarker_full.task"
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_JSON = str(OUT_DIR / f"skeleton_data_{ts}.json")

# MediaPipe 33개 랜드마크 이름
LM_NAMES = [
    "nose",           # 0
    "left_eye_inner", # 1
    "left_eye",       # 2
    "left_eye_outer", # 3
    "right_eye_inner",# 4
    "right_eye",      # 5
    "right_eye_outer",# 6
    "left_ear",       # 7
    "right_ear",      # 8
    "mouth_left",     # 9
    "mouth_right",    # 10
    "left_shoulder",  # 11
    "right_shoulder", # 12
    "left_elbow",     # 13
    "right_elbow",    # 14
    "left_wrist",     # 15
    "right_wrist",    # 16
    "left_pinky",     # 17
    "right_pinky",    # 18
    "left_index",     # 19
    "right_index",    # 20
    "left_thumb",     # 21
    "right_thumb",    # 22
    "left_hip",       # 23
    "right_hip",      # 24
    "left_knee",      # 25
    "right_knee",     # 26
    "left_ankle",     # 27
    "right_ankle",    # 28
    "left_heel",      # 29
    "right_heel",     # 30
    "left_foot_index",# 31
    "right_foot_index"# 32
]

# 주요 관절 그룹 (분석용)
KEY_GROUPS = {
    "head":     [0, 7, 8],
    "shoulders":[11, 12],
    "elbows":   [13, 14],
    "wrists":   [15, 16],
    "hips":     [23, 24],
    "knees":    [25, 26],
    "ankles":   [27, 28],
    "feet":     [29, 30, 31, 32],
}


def run():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker, PoseLandmarkerOptions, RunningMode,
    )

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.20,   # 낮게 → 최대한 검출 시도
        min_pose_presence_confidence=0.20,
        min_tracking_confidence=0.20,
    )
    landmarker = PoseLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(SOURCE)
    raw_W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    raw_H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    needs_rotation = (raw_W > raw_H)
    out_W = raw_H if needs_rotation else raw_W
    out_H = raw_W if needs_rotation else raw_H

    print(f"소스: {SOURCE}")
    print(f"  raw={raw_W}x{raw_H}  rotation={needs_rotation}  → out={out_W}x{out_H}")
    print(f"  {total}f @ {fps:.1f}fps  ({total/fps:.2f}s)")
    print()

    frames_data = []
    detected_count = 0

    for fi in range(total):
        ret, frame_raw = cap.read()
        if not ret:
            break
        t_ms = int(fi * 1000 / fps)
        t_s  = round(fi / fps, 4)

        frame = cv2.rotate(frame_raw, cv2.ROTATE_90_CLOCKWISE) if needs_rotation else frame_raw
        H, W = frame.shape[:2]

        # 야간 영상 밝기 boost (검출용)
        detect_frame = cv2.convertScaleAbs(frame, alpha=3.0, beta=60)
        rgb    = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        detected = False
        landmarks_list = []

        try:
            res = landmarker.detect_for_video(mp_img, t_ms)
            if res.pose_landmarks:
                detected = True
                detected_count += 1
                lms = res.pose_landmarks[0]

                # 사람 bbox
                xs = [lm.x for lm in lms]
                ys = [lm.y for lm in lms]
                bbox = {
                    "x_min": round(min(xs), 4), "x_max": round(max(xs), 4),
                    "y_min": round(min(ys), 4), "y_max": round(max(ys), 4),
                    "width_ratio":  round(max(xs) - min(xs), 4),
                    "height_ratio": round(max(ys) - min(ys), 4),
                    "person_px_height": round((max(ys) - min(ys)) * H),
                }

                for idx, lm in enumerate(lms):
                    landmarks_list.append({
                        "index":      idx,
                        "name":       LM_NAMES[idx] if idx < len(LM_NAMES) else f"lm_{idx}",
                        "x":          round(lm.x, 5),
                        "y":          round(lm.y, 5),
                        "z":          round(lm.z, 5),
                        "visibility": round(getattr(lm, "visibility", 0.0), 4),
                        "presence":   round(getattr(lm, "presence", 0.0), 4),
                        "px":         int(lm.x * W),
                        "py":         int(lm.y * H),
                    })

                # 그룹별 평균 visibility
                group_vis = {}
                for gname, idxs in KEY_GROUPS.items():
                    vis_vals = [landmarks_list[i]["visibility"] for i in idxs if i < len(landmarks_list)]
                    group_vis[gname] = round(sum(vis_vals) / max(len(vis_vals), 1), 3)

                frame_rec = {
                    "frame":      fi,
                    "time_sec":   t_s,
                    "detected":   True,
                    "bbox":       bbox,
                    "landmarks":  landmarks_list,
                    "group_visibility": group_vis,
                }
            else:
                frame_rec = {"frame": fi, "time_sec": t_s, "detected": False}
        except Exception as e:
            frame_rec = {"frame": fi, "time_sec": t_s, "detected": False, "error": str(e)}

        frames_data.append(frame_rec)

        if (fi + 1) % 30 == 0:
            print(f"  [{fi+1:4d}/{total}]  {t_s:.2f}s  감지: {detected_count}/{fi+1}", end="\r", flush=True)

    cap.release()
    landmarker.close()
    print()

    # ── 통계 ─────────────────────────────────────────────────────
    det_frames = [f for f in frames_data if f.get("detected")]
    det_rate = detected_count / max(total, 1)

    # 감지된 프레임 기준 그룹 visibility 평균
    avg_group_vis = {}
    if det_frames:
        for gname in KEY_GROUPS:
            vals = [f["group_visibility"][gname] for f in det_frames if "group_visibility" in f]
            avg_group_vis[gname] = round(sum(vals) / max(len(vals), 1), 3)

    # 개별 landmark 평균 visibility (감지 프레임)
    avg_lm_vis = []
    if det_frames:
        for idx in range(33):
            vis_vals = [f["landmarks"][idx]["visibility"] for f in det_frames
                        if "landmarks" in f and idx < len(f["landmarks"])]
            avg_lm_vis.append({
                "index": idx,
                "name": LM_NAMES[idx] if idx < len(LM_NAMES) else f"lm_{idx}",
                "avg_visibility": round(sum(vis_vals) / max(len(vis_vals), 1), 3),
            })

    # 사람 크기 통계 (감지 프레임)
    person_heights = [f["bbox"]["person_px_height"] for f in det_frames if "bbox" in f]

    stats = {
        "source": SOURCE,
        "video_info": {
            "raw_resolution": f"{raw_W}x{raw_H}",
            "output_resolution": f"{out_W}x{out_H}",
            "fps": fps,
            "total_frames": total,
            "duration_sec": round(total / fps, 3),
            "needs_rotation": needs_rotation,
        },
        "detection": {
            "detected_frames":   detected_count,
            "total_frames":      total,
            "detection_rate":    round(det_rate, 4),
            "detection_rate_pct": round(det_rate * 100, 1),
        },
        "person_size_px": {
            "min":  int(min(person_heights)) if person_heights else 0,
            "max":  int(max(person_heights)) if person_heights else 0,
            "mean": int(sum(person_heights) / max(len(person_heights), 1)) if person_heights else 0,
            "frame_height": out_H,
            "mean_ratio_pct": round(
                sum(person_heights) / max(len(person_heights), 1) / max(out_H, 1) * 100, 1
            ) if person_heights else 0,
        },
        "avg_group_visibility": avg_group_vis,
        "avg_landmark_visibility": avg_lm_vis,
    }

    output = {
        "meta": stats,
        "frames": frames_data,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── 콘솔 요약 ────────────────────────────────────────────────
    print("=" * 60)
    print(f"[완료] {OUT_JSON}")
    print(f"  감지율: {detected_count}/{total} ({det_rate*100:.1f}%)")
    print(f"  사람 크기: 평균 {stats['person_size_px']['mean']}px "
          f"/ {out_H}px = {stats['person_size_px']['mean_ratio_pct']}%")
    print()
    print("  그룹별 평균 visibility (감지 프레임 기준):")
    for gname, v in avg_group_vis.items():
        bar = "#" * int(v * 20)
        print(f"    {gname:12s}  {bar:<20s}  {v:.3f}")
    print()
    print("  관절별 평균 visibility:")
    for lm in avg_lm_vis:
        bar = "#" * int(lm["avg_visibility"] * 20)
        print(f"    [{lm['index']:2d}] {lm['name']:20s}  {bar:<20s}  {lm['avg_visibility']:.3f}")
    print("=" * 60)

    return OUT_JSON


if __name__ == "__main__":
    run()
