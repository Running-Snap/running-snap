"""자세 분석 백그라운드 작업"""
import json
import os
import random
import tempfile

import numpy as np
import pandas as pd

from core.database import SessionLocal
from core.models import AnalysisJob
from core.config import POSE_ANALYZER_AVAILABLE, POSE_MODEL_PATH, POSE_OUTPUT_FOLDER, ANTHROPIC_API_KEY
from core.celery_app import celery_app
from services.video import download_from_s3_if_needed


def _calc_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ba = a - b
    bc = c - b
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc)) + 1e-8
    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))))


def _compute_frame_analysis(work_dir: str, pose_stats: dict) -> tuple:
    """
    pose_frames.csv + pose_events.csv 에서 frame_refs, frame_guides 계산.
    Returns: (frame_refs, frame_guides)
    """
    frame_refs = {"elbow": [], "vertical_oscillation": [], "overstride": [], "asymmetry": []}
    frame_guides = {"elbow": [], "vertical_oscillation": [], "overstride": [], "asymmetry": []}

    try:
        frame_csv = os.path.join(work_dir, "pose_frames.csv")
        event_csv = os.path.join(work_dir, "pose_events.csv")

        if not os.path.exists(frame_csv) or not os.path.exists(event_csv):
            print(f"[ANALYSIS] CSV 파일 없음: {work_dir}")
            return frame_refs, frame_guides

        df_frame = pd.read_csv(frame_csv)
        df_event = pd.read_csv(event_csv)
        print(f"[ANALYSIS] 프레임 수: {len(df_frame)}, 이벤트 수: {len(df_event)}")

        # ── 팔꿈치 각도 (오른쪽: shoulder12 - elbow14 - wrist16) ──
        elbow_data = []
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
                    elbow_data.append((int(row["frame_i"]), float(row["t_sec"]), ang))

        if elbow_data:
            ideal = 90.0
            elbow_data.sort(key=lambda x: abs(x[2] - ideal), reverse=True)
            top3 = elbow_data[:3]
            frame_refs["elbow"] = [fi for fi, _, _ in top3]
            for fi, ts, ang in top3:
                diff = ang - ideal
                dir_str = "펼쳐져" if diff > 0 else "굽혀져"
                frame_guides["elbow"].append(
                    f"프레임 {fi} ({ts:.1f}초): 팔꿈치 {ang:.0f}° — 이상(90°)보다 {abs(diff):.0f}° {dir_str} 있음"
                )

        # ── 수직 진폭 (머리 lm00 y 좌표) ──
        if "lm00_y_px" in df_frame.columns:
            detected = df_frame[df_frame["detected"] == 1]
            if len(detected) > 0:
                max_row = detected.loc[detected["lm00_y_px"].idxmax()]
                min_row = detected.loc[detected["lm00_y_px"].idxmin()]
                frame_refs["vertical_oscillation"] = [int(max_row["frame_i"]), int(min_row["frame_i"])]
                osc_px = float(detected["lm00_y_px"].max() - detected["lm00_y_px"].min())
                quality = "양호 (일반 범위)" if osc_px < 50 else "과도한 상하 출렁임 (에너지 손실 위험)"
                frame_guides["vertical_oscillation"].append(
                    f"프레임 {int(max_row['frame_i'])} ({max_row['t_sec']:.1f}초): 머리 최저점 — 하강 극대"
                )
                frame_guides["vertical_oscillation"].append(
                    f"프레임 {int(min_row['frame_i'])} ({min_row['t_sec']:.1f}초): 머리 최고점 — 상승 극대"
                )
                frame_guides["vertical_oscillation"].append(
                    f"수직 진폭: {osc_px:.0f}px — {quality}"
                )

        # ── 오버스트라이드 ──
        if len(df_event) > 0:
            overstride_ev = df_event[df_event["grade"] == "OVERSTRIDE"]
            if len(overstride_ev) > 0:
                top3_os = overstride_ev.nlargest(3, "impact_z")
                frame_refs["overstride"] = top3_os["frame_i"].astype(int).tolist()
                for _, ev in top3_os.iterrows():
                    frame_guides["overstride"].append(
                        f"프레임 {int(ev['frame_i'])} ({ev['t_sec']:.1f}초): Impact Z {ev['impact_z']:.3f} — 오버스트라이드 착지 (중심보다 앞 착지, 제동력 발생)"
                    )
            else:
                # 오버스트라이드 없음 — 상위 3개 착지 이벤트 표시
                top3_ev = df_event.nlargest(3, "impact_z")
                frame_refs["overstride"] = top3_ev["frame_i"].astype(int).tolist()
                for _, ev in top3_ev.iterrows():
                    grade_str = ev.get("grade", "NORMAL")
                    frame_guides["overstride"].append(
                        f"프레임 {int(ev['frame_i'])} ({ev['t_sec']:.1f}초): Impact Z {ev['impact_z']:.3f} — {grade_str} 착지"
                    )

        # ── 비대칭 ──
        if len(df_event) > 1:
            left_ev = df_event.iloc[0::2].reset_index(drop=True)
            right_ev = df_event.iloc[1::2].reset_index(drop=True)
            min_len = min(len(left_ev), len(right_ev))
            if min_len > 0:
                diffs = np.abs(
                    left_ev["impact_z"][:min_len].values - right_ev["impact_z"][:min_len].values
                )
                top_idxs = diffs.argsort()[-3:][::-1]
                for i in top_idxs:
                    li = int(left_ev.iloc[i]["frame_i"])
                    ri = int(right_ev.iloc[i]["frame_i"])
                    lz = float(left_ev.iloc[i]["impact_z"])
                    rz = float(right_ev.iloc[i]["impact_z"])
                    frame_refs["asymmetry"].extend([li, ri])
                    frame_guides["asymmetry"].append(
                        f"프레임 {li} vs {ri}: 좌 {lz:.3f} / 우 {rz:.3f} — 차이 {diffs[i]:.3f}"
                    )

    except Exception as e:
        print(f"[ANALYSIS] frame_refs 계산 오류: {e}")

    return frame_refs, frame_guides


def _call_claude_enhanced(pose_stats: dict, frame_refs: dict, frame_guides: dict, api_key: str) -> str:
    """프레임 데이터를 포함한 강화된 Claude 코칭 리포트 생성."""
    def fmt_frames(key):
        frames = frame_refs.get(key, [])
        return ", ".join(map(str, frames)) if frames else "없음"

    def fmt_guides(key):
        guides = frame_guides.get(key, [])
        return "\n".join([f"- {g}" for g in guides]) if guides else "- 없음"

    def build_frame_action_block():
        labels = {
            "elbow": "팔꿈치",
            "vertical_oscillation": "수직 진폭",
            "overstride": "오버스트라이드",
            "asymmetry": "비대칭",
        }
        lines = ["[프레임별 자세 분석 + 개선 방법 (자동 생성)]"]
        for key in ["elbow", "vertical_oscillation", "overstride", "asymmetry"]:
            lines.append(f"[{labels[key]}]")
            guides = frame_guides.get(key, [])
            lines.extend([f"- {g}" for g in guides] if guides else ["- 없음"])
            lines.append("")
        return "\n".join(lines).strip()

    if not api_key:
        return build_frame_action_block()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""당신은 데이터 기반의 생체역학 마라톤 코치입니다.
'전체 프레임 기록'과 '착지 이벤트 데이터'를 통합 분석한 결과입니다.
이 러너의 마라톤 완주 가능성과 자세 결함을 분석하십시오.

[통합 데이터 지표]
- 평균 케이던스: {pose_stats['cadence']} SPM
- 수직 진폭(상하 출렁임): {pose_stats['v_oscillation']} px
- 평균 오버스트라이드(Impact Z): {pose_stats['avg_impact_z']} (0.2 미만 권장)
- 좌우 착지 비대칭률: {pose_stats['asymmetry']}%
- 평균 팔꿈치 각도: {pose_stats['elbow_angle']}도

[자세 분석 근거 프레임 번호]
- 팔꿈치 각도 근거 프레임: {fmt_frames('elbow')}
- 수직 진폭 근거 프레임: {fmt_frames('vertical_oscillation')}
- 오버스트라이드 근거 프레임: {fmt_frames('overstride')}
- 비대칭 근거 프레임: {fmt_frames('asymmetry')}

[프레임별 자세 분석 + 개선 방법]
[팔꿈치]
{fmt_guides('elbow')}

[수직 진폭]
{fmt_guides('vertical_oscillation')}

[오버스트라이드]
{fmt_guides('overstride')}

[비대칭]
{fmt_guides('asymmetry')}

[분석 필수 포인트]
1. **팔꿈치-케이던스 협응:** 팔꿈치 각도가 현재 {pose_stats['cadence']} SPM 리듬을 얼마나 잘 지지하고 있는가?
2. **오버스트라이드 진단:** Impact Z 수치가 지면 제동을 얼마나 억제하고 있는가?
3. **에너지 효율:** 수직 진폭이 마라톤 후반부 근피로에 미치는 영향.
4. **비대칭 경고:** {pose_stats['asymmetry']}%의 비대칭이 30km 이후 부상으로 이어질 시나리오.
5. **마라톤 팁:** 풀코스 완주를 위해 반드시 고쳐야 할 가장 치명적인 포인트 1가지.

[출력 형식 필수]
- 불필요한 서론 없이 즉시 리포트 시작.
- 각 분석 항목 끝에 반드시 `(근거 프레임: N, N, ...)` 형식으로 표기.
- 근거 프레임은 반드시 위 [자세 분석 근거 프레임 번호]에 있는 번호만 사용.
- 데이터 중심의 냉철한 분석 후, 따뜻한 코칭 제언으로 마무리."""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        llm_text = message.content[0].text
        print(f"[ANALYSIS] Claude 코칭 리포트 생성 성공")
        return f"{llm_text}\n\n{build_frame_action_block()}"
    except Exception as e:
        print(f"[ANALYSIS] Claude API 호출 실패: {e}")
        return f"Claude API 호출 실패: {e}\n\n{build_frame_action_block()}"


def build_mock_result() -> dict:
    score = random.randint(65, 92)
    return {
        "score": score,
        "feedbacks": [
            {
                "title": "무릎 각도",
                "status": "good" if score >= 75 else "warning",
                "message": "무릎 각도가 적절합니다" if score >= 75 else "무릎을 조금 더 구부려 충격을 흡수하세요",
            },
            {
                "title": "보폭",
                "status": "warning" if score < 80 else "good",
                "message": "보폭을 조금 더 넓히는 것을 권장합니다" if score < 80 else "보폭이 안정적입니다",
            },
            {"title": "상체 각도", "status": "good", "message": "상체 자세가 안정적입니다"},
            {
                "title": "착지",
                "status": "bad" if score < 70 else "good",
                "message": "중족부 착지를 연습하세요" if score < 70 else "착지 자세가 좋습니다",
            },
        ],
        "pose_stats": {
            "cadence":      round(random.uniform(155, 175), 1),
            "v_oscillation":round(random.uniform(6.0, 10.0), 1),
            "avg_impact_z": round(random.uniform(0.18, 0.38), 2),
            "asymmetry":    round(random.uniform(0.5, 3.5), 1),
            "elbow_angle":  round(random.uniform(75, 105), 1),
        },
        "coaching_report": "분석 모듈을 사용할 수 없어 기본 피드백을 제공합니다.",
        "impact_events": [],
        "frame_refs": {},
        "frame_guides": {},
    }


@celery_app.task(name="analysis.run", bind=True, max_retries=2)
def run_analysis_task(self, job_id: int, video_path: str):
    db = SessionLocal()
    tmp_path = None

    # 상태를 먼저 processing으로 변경
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            db.close()
            return
        job.status = "processing"
        db.commit()
    except Exception as e:
        db.close()
        return

    try:
        print(f"[ANALYSIS] job_id={job_id} 분석 시작")

        # S3 URL인 경우 임시 파일로 다운로드
        actual_path, is_tmp = download_from_s3_if_needed(video_path)
        if is_tmp:
            tmp_path = actual_path
        if not actual_path:
            print(f"[ANALYSIS] job_id={job_id} S3 다운로드 실패")
        elif is_tmp:
            print(f"[ANALYSIS] job_id={job_id} S3 다운로드 완료")

        result = None
        if POSE_ANALYZER_AVAILABLE and os.path.exists(actual_path) and os.path.exists(POSE_MODEL_PATH):
            try:
                import pose_analyzer
                work_dir = os.path.join(POSE_OUTPUT_FOLDER, str(job_id))
                print(f"[ANALYSIS] job_id={job_id} MediaPipe 포즈 분석 중...")

                result = pose_analyzer.analyze_video(
                    video_path=actual_path,
                    work_dir=work_dir,
                    model_path=POSE_MODEL_PATH,
                    gemini_api_key="",
                )
                print(f"[ANALYSIS] job_id={job_id} 포즈 분석 완료 (score={result.get('score')})")

                print(f"[ANALYSIS] job_id={job_id} 프레임별 분석 시작...")
                frame_refs, frame_guides = _compute_frame_analysis(work_dir, result.get("pose_stats", {}))
                result["frame_refs"] = frame_refs
                result["frame_guides"] = frame_guides
                print(f"[ANALYSIS] job_id={job_id} 프레임별 분석 완료")

                print(f"[ANALYSIS] job_id={job_id} Gemini 코칭 리포트 생성 중...")
                result["coaching_report"] = _call_claude_enhanced(
                    result.get("pose_stats", {}),
                    frame_refs,
                    frame_guides,
                    ANTHROPIC_API_KEY,
                )
                print(f"[ANALYSIS] job_id={job_id} 코칭 리포트 완료")

            except Exception as e:
                print(f"[POSE ANALYSIS ERROR] {e}")
                result = None
        else:
            print(f"[ANALYSIS] job_id={job_id} MOCK 결과 사용")

        if result is None:
            result = build_mock_result()

        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if job:
            job.result_json = json.dumps(result, ensure_ascii=False)
            job.status      = "done"
            db.commit()
        print(f"[ANALYSIS] job_id={job_id} DB 저장 완료")

    except Exception as e:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if job:
            job.status      = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
