"""자세분석 영상 생성 백그라운드 작업"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from core.database import SessionLocal
from core.models import PoseVideoJob
from core.config import VIDEO_EDITOR_PATH, OUTPUT_COACHING_FOLDER
from services.video import upload_to_s3, download_from_s3_if_needed

POSE_MODEL_CANDIDATES = [
    "/home/ubuntu/backend/pose_landmarker_heavy.task",
    os.environ.get("POSE_MODEL_PATH", ""),
]


def _find_pose_model() -> str:
    for p in POSE_MODEL_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return ""


def run_pose_video_task(job_id: int, video_path: str, feedback_data: dict):
    db = SessionLocal()
    tmp_path = None
    try:
        job = db.query(PoseVideoJob).filter(PoseVideoJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # S3 URL이면 로컬로 다운로드
        local_path, is_tmp = download_from_s3_if_needed(video_path) if video_path else ("", False)
        if is_tmp:
            tmp_path = local_path
        video_path = local_path or video_path

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"영상 파일 없음: {video_path}")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"pose_video_{job_id}_{ts}.mp4"
        output_path = os.path.abspath(os.path.join(OUTPUT_COACHING_FOLDER, output_filename))
        os.makedirs(OUTPUT_COACHING_FOLDER, exist_ok=True)

        model_path = _find_pose_model()
        success = False

        if VIDEO_EDITOR_PATH and os.path.exists(VIDEO_EDITOR_PATH):
            orig_dir = os.getcwd()
            os.chdir(VIDEO_EDITOR_PATH)
            if VIDEO_EDITOR_PATH not in sys.path:
                sys.path.insert(0, VIDEO_EDITOR_PATH)
            try:
                from src.preprocessor import preprocess
                from src.pose_skeleton_renderer import apply_skeleton_feedback
                from src.instruction_builder import InstructionBuilder
                from src.template_executor import TemplateExecutor

                with tempfile.TemporaryDirectory() as tmpdir:
                    # 피드백 수에 따라 목표 길이 계산
                    n_feedbacks = len(feedback_data.get("feedbacks", [])) if feedback_data else 0
                    target_duration = 6.0 + n_feedbacks * 3.5 if n_feedbacks > 0 else 12.0

                    # 전처리 (회전 보정, 루프)
                    info = preprocess(video_path, target_duration, tmpdir)

                    # 1단계: 골격 오버레이
                    skel_path = os.path.join(tmpdir, "skel.mp4")
                    ok = apply_skeleton_feedback(
                        source_video=info.path,
                        output_video=skel_path,
                        feedback_data=feedback_data,
                        loop_count=info.loop_count,
                        model_path=model_path,
                        highlights=None,
                    )
                    if not ok or not Path(skel_path).exists():
                        print(f"[POSE_VIDEO] skeleton 실패 → 원본으로 진행")
                        skel_path = info.path

                    # 2단계: 피드백 카드 오버레이
                    builder = InstructionBuilder(style="action")
                    instruction = builder.build(
                        source_info=info,
                        target_duration=info.duration,
                        feedback_data=feedback_data,
                        highlights=None,
                    )
                    executor = TemplateExecutor(verbose=True)
                    executor.execute(instruction, skel_path, output_path)
                    success = os.path.exists(output_path)

            except Exception as e:
                print(f"[POSE_VIDEO] 오류: {e}")
                import traceback
                traceback.print_exc()
                success = False
            finally:
                os.chdir(orig_dir)

        if success and os.path.exists(output_path):
            s3_url = upload_to_s3(output_path, "coaching")
            job.output_filename = s3_url if s3_url else output_filename
            job.status = "done"
            print(f"[POSE_VIDEO] job_id={job_id} 완료: {job.output_filename}")
        else:
            job.status = "failed"
            print(f"[POSE_VIDEO] job_id={job_id} 실패")
        db.commit()

    except Exception as e:
        print(f"[POSE_VIDEO] job_id={job_id} 오류: {e}")
        job = db.query(PoseVideoJob).filter(PoseVideoJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
