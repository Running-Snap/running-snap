
import os
import cv2
import numpy as np
import pandas as pd
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ── 임계값 상수 ────────────────────────────────────────────────────────
_IMPACT_GATE = 0.4           # 이 값 미만일 때만 착지 이벤트로 인정
_ELITE_THRESHOLD = 0.18      # 엘리트 착지 상한
_OVERSTRIDE_THRESHOLD = 0.4  # 오버스트라이드 하한
_TARGET_FPS = 30.0           # 처리 목표 FPS


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────

def _make_landmarker(model_path: str) -> vision.PoseLandmarker:
    base_options = python.BaseOptions(
        model_asset_path=model_path,
        delegate=python.BaseOptions.Delegate.CPU,
    )
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def _calc_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """b를 꼭짓점으로 하는 세 점의 각도(도)를 벡터 내적으로 계산."""
    ba = a - b
    bc = c - b
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc)) + 1e-8
    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))))


# ── Step 1. 영상 → CSV 추출 ───────────────────────────────────────────

def extract_pose_csv(video_path: str, out_dir: str, model_path: str) -> tuple:
    """
    영상에서 MediaPipe 포즈를 추출하여 두 CSV 파일을 저장한다.
    Returns: (frame_csv_path, event_csv_path)
    """
    os.makedirs(out_dir, exist_ok=True)
    frame_csv = os.path.join(out_dir, "pose_frames.csv")
    event_csv = os.path.join(out_dir, "pose_events.csv")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(src_fps / _TARGET_FPS)))
    proc_fps = src_fps / stride
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    landmarker = _make_landmarker(model_path)
    frame_rows, event_rows = [], []

    frame_src = -1
    used_idx = 0
    prev_z = 999.0
    is_descending = False
    last_impact_z = np.nan

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_src += 1
        if frame_src % stride != 0:
            continue

        t_sec = used_idx / proc_fps
        t_ms = int(t_sec * 1000.0)
        used_idx += 1

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        res = landmarker.detect_for_video(mp_image, t_ms)

        row: dict = {
            "frame_i": used_idx - 1,
            "frame_src": frame_src,
            "t_sec": float(t_sec),
            "detected": 0,
        }
        for k in range(33):
            row[f"lm{k:02d}_x_px"] = np.nan
            row[f"lm{k:02d}_y_px"] = np.nan
            row[f"lm{k:02d}_z"] = np.nan
            row[f"lm{k:02d}_vis"] = np.nan
        row["z_norm"] = np.nan
        row["impact_flag"] = 0
        row["impact_grade"] = None

        is_impact_frame = False
        impact_grade = None
        curr_z = np.nan

        if res.pose_landmarks:
            lm = res.pose_landmarks[0]
            row["detected"] = 1

            for k in range(min(33, len(lm))):
                row[f"lm{k:02d}_x_px"] = float(lm[k].x * w)
                row[f"lm{k:02d}_y_px"] = float(lm[k].y * h)
                row[f"lm{k:02d}_z"] = float(getattr(lm[k], "z", np.nan))
                row[f"lm{k:02d}_vis"] = float(getattr(lm[k], "visibility", np.nan))

            # z_norm: 골반-발뒤꿈치 거리 / 몸통 길이 정규화
            shoulder_z = (float(lm[11].z) + float(lm[12].z)) / 2.0
            hip_z = (float(lm[23].z) + float(lm[24].z)) / 2.0
            torso_z = abs(shoulder_z - hip_z)
            curr_z = (
                abs(float(lm[23].z) - float(lm[29].z)) / torso_z
                if torso_z > 1e-8 else 0.0
            )
            row["z_norm"] = float(curr_z)

            # 착지 이벤트 감지: z_norm 로컬 미니멈 탐지
            if curr_z < prev_z:
                is_descending = True
            elif curr_z > prev_z and is_descending:
                if prev_z < _IMPACT_GATE:
                    last_impact_z = float(prev_z)
                    is_impact_frame = True
                    if last_impact_z <= _ELITE_THRESHOLD:
                        impact_grade = "ELITE"
                    elif last_impact_z >= _OVERSTRIDE_THRESHOLD:
                        impact_grade = "OVERSTRIDE"
                    else:
                        impact_grade = "NORMAL"
                is_descending = False
            prev_z = float(curr_z)

        if is_impact_frame:
            row["impact_flag"] = 1
            row["impact_grade"] = impact_grade
            event_rows.append({
                "event_id": len(event_rows),
                "event_type": "IMPACT",
                "frame_i": int(row["frame_i"]),
                "frame_src": int(row["frame_src"]),
                "t_sec": float(row["t_sec"]),
                "impact_z": float(last_impact_z),
                "grade": impact_grade,
                "z_norm_at_frame": float(row["z_norm"]) if np.isfinite(row["z_norm"]) else np.nan,
            })

        frame_rows.append(row)

    cap.release()
    landmarker.close()

    pd.DataFrame(frame_rows).to_csv(frame_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame(event_rows).to_csv(event_csv, index=False, encoding="utf-8-sig")

    return frame_csv, event_csv


# ── Step 2. CSV → 생체역학 지표 계산 ─────────────────────────────────

def compute_stats(frame_csv: str, event_csv: str) -> dict:
    """pose_frames.csv + pose_events.csv → 5가지 생체역학 지표 dict."""
    df_frame = pd.read_csv(frame_csv)
    df_event = pd.read_csv(event_csv)

    # 팔꿈치 각도: 오른쪽 어깨(12) - 팔꿈치(14) - 손목(16)
    elbow_angles = []
    for _, row in df_frame.iterrows():
        coords, valid = [], True
        for lm_idx in [12, 14, 16]:
            x = row.get(f"lm{lm_idx:02d}_x_px")
            y = row.get(f"lm{lm_idx:02d}_y_px")
            if pd.isna(x) or pd.isna(y):
                valid = False
                break
            coords.append(np.array([float(x), float(y)]))
        if valid:
            ang = _calc_angle(coords[0], coords[1], coords[2])
            if np.isfinite(ang):
                elbow_angles.append(ang)

    elbow_angle_avg = float(np.mean(elbow_angles)) if elbow_angles else 0.0
    v_oscillation = float(df_frame["lm00_y_px"].max() - df_frame["lm00_y_px"].min())

    # 착지 이벤트가 없는 경우 기본값 반환
    if len(df_event) == 0:
        return {
            "cadence": 0.0,
            "v_oscillation": round(v_oscillation, 1),
            "avg_impact_z": 0.0,
            "asymmetry": 0.0,
            "elbow_angle": round(elbow_angle_avg, 1),
        }

    duration = float(df_frame["t_sec"].max() - df_frame["t_sec"].min())
    cadence = (len(df_event) / duration) * 60.0 if duration > 0 else 0.0
    avg_impact_z = float(df_event["impact_z"].mean())

    # 홀수/짝수 인덱스를 좌/우 발로 구분해 비대칭 계산
    left_z = df_event.iloc[0::2]["impact_z"]
    right_z = df_event.iloc[1::2]["impact_z"]
    if avg_impact_z > 0 and len(left_z) > 0 and len(right_z) > 0:
        asymmetry = abs(left_z.mean() - right_z.mean()) / avg_impact_z * 100.0
    else:
        asymmetry = 0.0

    return {
        "cadence": round(cadence, 1),
        "v_oscillation": round(v_oscillation, 1),
        "avg_impact_z": round(avg_impact_z, 3),
        "asymmetry": round(asymmetry, 1),
        "elbow_angle": round(elbow_angle_avg, 1),
    }


# ── Step 3. 지표 → 점수 + 피드백 (규칙 기반) ─────────────────────────

def _stats_to_score(stats: dict) -> int:
    score = 75

    iz = stats["avg_impact_z"]
    if iz <= _ELITE_THRESHOLD:
        score += 10
    elif iz >= _OVERSTRIDE_THRESHOLD:
        score -= 15

    c = stats["cadence"]
    if 160 <= c <= 185:
        score += 5
    elif c < 140:
        score -= 10

    if stats["asymmetry"] < 2.0:
        score += 5
    elif stats["asymmetry"] > 5.0:
        score -= 10

    if 80 <= stats["elbow_angle"] <= 100:
        score += 5

    return max(30, min(100, score))


def _stats_to_feedbacks(stats: dict) -> list:
    feedbacks = []

    c = stats["cadence"]
    if c >= 170:
        feedbacks.append({"title": "케이던스", "status": "good",
                          "message": f"케이던스 {c} SPM — 이상적인 리듬입니다"})
    elif c >= 150:
        feedbacks.append({"title": "케이던스", "status": "warning",
                          "message": f"케이던스 {c} SPM — 170 SPM 이상으로 높여보세요"})
    else:
        feedbacks.append({"title": "케이던스", "status": "bad",
                          "message": f"케이던스 {c} SPM — 발걸음이 너무 느립니다"})

    iz = stats["avg_impact_z"]
    if iz <= _ELITE_THRESHOLD:
        feedbacks.append({"title": "착지", "status": "good",
                          "message": "발이 골반 아래 착지 — 제동력이 거의 없습니다"})
    elif iz <= 0.35:
        feedbacks.append({"title": "착지", "status": "warning",
                          "message": "약간의 오버스트라이드 — 착지를 몸 중심에 가깝게 조정하세요"})
    else:
        feedbacks.append({"title": "착지", "status": "bad",
                          "message": "심한 오버스트라이드 — 무릎·정강이 부상 위험이 높습니다"})

    ea = stats["elbow_angle"]
    if 80 <= ea <= 100:
        feedbacks.append({"title": "팔꿈치 각도", "status": "good",
                          "message": f"팔꿈치 {ea}° — 이상적인 각도입니다"})
    else:
        feedbacks.append({"title": "팔꿈치 각도", "status": "warning",
                          "message": f"팔꿈치 {ea}° — 80~100° 사이를 유지하세요"})

    asym = stats["asymmetry"]
    if asym < 2.0:
        feedbacks.append({"title": "좌우 균형", "status": "good",
                          "message": f"좌우 비대칭 {asym}% — 균형이 잘 잡혀 있습니다"})
    elif asym < 5.0:
        feedbacks.append({"title": "좌우 균형", "status": "warning",
                          "message": f"좌우 비대칭 {asym}% — 한쪽에 부담이 쏠릴 수 있습니다"})
    else:
        feedbacks.append({"title": "좌우 균형", "status": "bad",
                          "message": f"좌우 비대칭 {asym}% — 부상 위험, 코어·둔근 강화 권장"})

    return feedbacks


# ── Step 4. Gemini API 코칭 리포트 생성 ───────────────────────────────

def generate_coaching_report(stats: dict, api_key: str) -> str:
    from google import genai as google_genai

    client = google_genai.Client(api_key=api_key)

    prompt = f"""
당신은 데이터 기반의 생체역학 마라톤 코치입니다.
분석된 지표를 바탕으로 러너의 마라톤 완주 가능성과 자세 결함을 분석하십시오.

[데이터 지표]
- 평균 케이던스: {stats['cadence']} SPM
- 수직 진폭(상하 출렁임): {stats['v_oscillation']} px
- 평균 오버스트라이드(Impact Z): {stats['avg_impact_z']} (0.2 미만 권장)
- 좌우 착지 비대칭률: {stats['asymmetry']}%
- 평균 팔꿈치 각도: {stats['elbow_angle']}도

[분석 필수 포인트]
1. 팔꿈치-케이던스 협응 분석
2. 오버스트라이드(Impact Z) 진단
3. 수직 진폭과 에너지 효율 관계
4. 비대칭 경고 및 부상 시나리오
5. 풀코스 완주를 위한 가장 치명적인 포인트 1가지 교정 제언

[출력 스타일]
- 냉철한 데이터 분석 후 따뜻한 코칭으로 마무리.
- 불필요한 서론 없이 즉시 리포트 시작.
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


# ── 공개 인터페이스 — main.py에서 이것만 호출 ────────────────────────

def analyze_video(video_path: str, work_dir: str, model_path: str, gemini_api_key: str = "") -> dict:
    """
    영상 한 편을 분석하고 결과 dict를 반환한다.

    Args:
        video_path:      분석할 영상 절대 경로
        work_dir:        임시 CSV 저장 디렉토리 (job별로 분리 권장)
        model_path:      pose_landmarker_heavy.task 파일 경로
        gemini_api_key:  Gemini API 키 (비어 있으면 LLM 리포트 생략)

    Returns:
        {
            "score": int,
            "feedbacks": [...],
            "pose_stats": {...},
            "coaching_report": str,
        }
    """
    frame_csv, event_csv = extract_pose_csv(video_path, work_dir, model_path)
    stats = compute_stats(frame_csv, event_csv)

    coaching_report = ""
    if gemini_api_key:
        try:
            coaching_report = generate_coaching_report(stats, gemini_api_key)
        except Exception as e:
            coaching_report = f"Gemini API 호출 실패: {e}"

    return {
        "score": _stats_to_score(stats),
        "feedbacks": _stats_to_feedbacks(stats),
        "pose_stats": stats,
        "coaching_report": coaching_report,
    }
