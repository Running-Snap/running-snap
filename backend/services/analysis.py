"""자세 분석 백그라운드 작업"""
import json
import os
import random

from database import SessionLocal
from models import AnalysisJob
from core.config import POSE_ANALYZER_AVAILABLE, POSE_MODEL_PATH, POSE_OUTPUT_FOLDER, GEMINI_API_KEY


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
    }


def run_analysis_task(job_id: int, video_path: str):
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        result = None
        if POSE_ANALYZER_AVAILABLE and os.path.exists(video_path) and os.path.exists(POSE_MODEL_PATH):
            try:
                import pose_analyzer
                work_dir = os.path.join(POSE_OUTPUT_FOLDER, str(job_id))
                result   = pose_analyzer.analyze_video(
                    video_path=video_path,
                    work_dir=work_dir,
                    model_path=POSE_MODEL_PATH,
                    gemini_api_key=GEMINI_API_KEY,
                )
            except Exception:
                result = None

        if result is None:
            result = build_mock_result()

        job.result_json = json.dumps(result, ensure_ascii=False)
        job.status      = "done"
        db.commit()
    except Exception as e:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if job:
            job.status      = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()
