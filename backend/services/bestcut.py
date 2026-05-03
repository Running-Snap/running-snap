"""베스트컷 추출 백그라운드 작업"""
import json
import os

from core.database import SessionLocal
from core.models import BestCutJob
from core.config import (
    VIDEO_EDITOR_AVAILABLE, VIDEO_EDITOR_LOCK, VIDEO_EDITOR_PATH,
    ANTHROPIC_API_KEY, OUTPUT_FOLDER,
    OUTPUT_PHOTOS_BESTCUT_FOLDER, OUTPUT_PHOTOS_POSTER_FOLDER,
)
from core.utils import KST
from core.celery_app import celery_app
from services.opencv import extract_frames
from services.video import upload_to_s3, download_from_s3_if_needed


@celery_app.task(name="bestcut.run", bind=True, max_retries=2)
def run_bestcut_task(self, job_id: int, video_paths: list, photo_count: int, poster_config: dict = None, user_id: int = 0, bib: str = ""):
    db = SessionLocal()
    tmp_paths = []
    try:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # S3 URL이면 로컬로 다운로드
        local_video_paths = []
        for vp in video_paths:
            local, is_tmp = download_from_s3_if_needed(vp) if vp else ("", False)
            if local:
                local_video_paths.append(local)
                if is_tmp:
                    tmp_paths.append(local)

        primary_path = local_video_paths[0] if local_video_paths else None
        photos       = []
        posters      = []

        # 1순위: Ollama 로컬 (설치되면 자동 사용)
        if VIDEO_EDITOR_AVAILABLE and primary_path and os.path.exists(primary_path):
            try:
                import requests as req
                ollama_ok = req.get("http://localhost:11434/api/version", timeout=2).status_code == 200
            except Exception:
                ollama_ok = False

            if ollama_ok:
                try:
                    from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode
                    config = VideoEditorConfig(
                        mode=ProcessingMode.LOCAL,
                        ollama_model="qwen2.5vl:7b",
                        output_dir=OUTPUT_FOLDER,
                        cache_enabled=False,
                    )
                    with VIDEO_EDITOR_LOCK:
                        orig = os.getcwd()
                        os.chdir(VIDEO_EDITOR_PATH)
                        try:
                            result = VideoEditorAPI(config).process(
                                video_path=primary_path,
                                duration=10,
                                style="action",
                                photo_count=photo_count,
                                photo_preset="sports_action",
                            )
                        finally:
                            os.chdir(orig)
                    if result.success and result.photos:
                        import shutil
                        from datetime import datetime
                        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
                        bib_part = bib if bib else str(job_id)
                        for idx, photo_path in enumerate(result.photos, 1):
                            ext = os.path.splitext(photo_path)[1] or ".jpg"
                            new_name = f"bestcut_{user_id}_{bib_part}_{ts}_{idx}{ext}"
                            dest = os.path.join(OUTPUT_PHOTOS_BESTCUT_FOLDER, new_name)
                            if os.path.exists(photo_path):
                                shutil.move(photo_path, dest)
                            photos.append({"photo_url": f"/outputs/photos/bestcut/{new_name}", "timestamp": "0:00", "description": "AI 선정 베스트 컷"})
                except Exception as e:
                    print(f"[BESTCUT] Ollama 처리 실패: {e}, OpenCV로 전환")

        # 2순위: OpenCV
        if not photos and primary_path and os.path.exists(primary_path):
            photos = extract_frames(primary_path, photo_count, OUTPUT_PHOTOS_BESTCUT_FOLDER, user_id=user_id, bib=bib)

        # 3순위: 추가 영상에서 보충
        if len(photos) < photo_count and len(local_video_paths) > 1:
            remaining = photo_count - len(photos)
            for vpath in local_video_paths[1:]:
                if len(photos) >= photo_count:
                    break
                if os.path.exists(vpath):
                    extra = extract_frames(vpath, remaining, OUTPUT_PHOTOS_BESTCUT_FOLDER, user_id=user_id, bib=bib)
                    photos.extend(extra)
                    remaining -= len(extra)

        # 포스터 생성 (PosterMaker 연결)
        if photos and VIDEO_EDITOR_AVAILABLE:
            try:
                import sys
                sys.path.insert(0, VIDEO_EDITOR_PATH)
                from src.poster_maker import PosterMaker
                orig = os.getcwd()
                os.chdir(VIDEO_EDITOR_PATH)
                try:
                    from datetime import datetime
                    poster_ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
                    today_str = datetime.now(KST).strftime("%Y.%m.%d")
                    maker = PosterMaker()
                    bib_part = bib if bib else str(job_id)
                    pc = poster_config or {}
                    event_config = {
                        "title":        pc.get("title", "2026\nMIRACLE MARATHON"),
                        "location":     pc.get("location", "Daejeon, Republic of Korea"),
                        "sublocation":  pc.get("sublocation", "Gapcheon"),
                        "time":         "A.M. 08:00",  # 임시 고정
                        "date":         today_str,
                        "distance_km":  pc.get("distance_km", 0.0),
                        "run_time":     "",  # 임시 비활성화
                        "pace":         "",  # 임시 비활성화
                        "color_scheme": pc.get("color_scheme", "warm"),
                        "branding":     f"{pc.get('location', 'RUNNING DIARY')}  /  {today_str}",
                    }
                    print(f"[BESTCUT] 포스터 생성 시작 - {len(photos)}장")
                    for p_idx, photo in enumerate(photos, 1):
                        base = os.path.basename(photo["photo_url"])
                        src_path = os.path.join(OUTPUT_PHOTOS_BESTCUT_FOLDER, base)
                        if os.path.exists(src_path):
                            print(f"[BESTCUT] 포스터 {p_idx}/{len(photos)} 생성 중: {base}")
                            poster_name = f"poster_{user_id}_{bib_part}_{poster_ts}_{p_idx}.jpg"
                            poster_path = os.path.join(OUTPUT_PHOTOS_POSTER_FOLDER, poster_name)
                            result = maker.make(
                                image_path=src_path,
                                event_config=event_config,
                                output_path=poster_path,
                                poster_mode="photo",
                                color_grade=True,
                            )
                            if result:
                                posters.append({"photo_url": f"/outputs/photos/poster/{poster_name}", "timestamp": photo["timestamp"], "description": "AI 포스터 베스트 컷"})
                                print(f"[BESTCUT] 포스터 {p_idx}/{len(photos)} 완료")
                            else:
                                print(f"[BESTCUT] 포스터 {p_idx}/{len(photos)} 실패")
                    print(f"[BESTCUT] 포스터 생성 완료 - {len(posters)}장")
                finally:
                    os.chdir(orig)
            except Exception as e:
                print(f"[BESTCUT] 포스터 생성 실패: {e}")

        # S3 업로드 - bestcut
        for photo in photos:
            local_path = os.path.join(OUTPUT_PHOTOS_BESTCUT_FOLDER, os.path.basename(photo["photo_url"]))
            s3_url = upload_to_s3(local_path, "photos/bestcut")
            if s3_url:
                photo["photo_url"] = s3_url

        # S3 업로드 - poster
        for poster in posters:
            local_path = os.path.join(OUTPUT_PHOTOS_POSTER_FOLDER, os.path.basename(poster["photo_url"]))
            s3_url = upload_to_s3(local_path, "photos/poster")
            if s3_url:
                poster["photo_url"] = s3_url

        result_data = {"bestcut": photos, "poster": posters}
        job.result_json = json.dumps(result_data, ensure_ascii=False)
        job.status      = "done"
        db.commit()
    except Exception as e:
        job = db.query(BestCutJob).filter(BestCutJob.id == job_id).first()
        if job:
            job.status      = "failed"
            job.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
    finally:
        db.close()
        for tp in tmp_paths:
            if os.path.exists(tp):
                os.remove(tp)
