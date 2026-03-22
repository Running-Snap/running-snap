"""카메라 클립 GPS 매칭 및 자동 처리"""
import os
from datetime import datetime, timedelta

from database import SessionLocal
from models import AnalysisJob, BestCutJob, ShortformJob, CameraClip, ClipMatch, UserLocation
from core.config import CAMERA_CLIPS_FOLDER, TRIMMED_CLIPS_FOLDER
from services.video import haversine_m, trim_clip, concat_clips
from services.analysis import run_analysis_task
from services.bestcut import run_bestcut_task
from services.shortform import run_shortform_task

PROXIMITY_M = 50.0


def auto_process(user_id: int, trimmed_path: str):
    """트림된 영상으로 분석/베스트컷/숏폼 자동 실행"""
    print(f"[AUTO] 유저 {user_id} 자동 처리 시작: {os.path.basename(trimmed_path)}")
    db = SessionLocal()
    try:
        analysis_job  = AnalysisJob(user_id=user_id, status="pending")
        bestcut_job   = BestCutJob(user_id=user_id, video_ids_json="[]", photo_count=5, status="pending")
        shortform_job = ShortformJob(user_id=user_id, video_ids_json="[]", style="action", duration_sec=30.0, status="pending")
        db.add_all([analysis_job, bestcut_job, shortform_job])
        db.commit()
        db.refresh(analysis_job)
        db.refresh(bestcut_job)
        db.refresh(shortform_job)
        a_id, b_id, s_id = analysis_job.id, bestcut_job.id, shortform_job.id
    except Exception as e:
        print(f"[AUTO] 잡 생성 실패: {e}")
        return
    finally:
        db.close()

    run_analysis_task(a_id, trimmed_path)
    run_bestcut_task(b_id, [trimmed_path], 5)
    run_shortform_task(s_id, [trimmed_path], "action", 30.0)
    print(f"[AUTO] 유저 {user_id} 자동 처리 완료")


def process_clip_matching(clip_id: int):
    """클립 업로드 후 50m 이내 유저와 매칭 → 구간 잘라내기"""
    db = SessionLocal()
    try:
        clip = db.query(CameraClip).filter(CameraClip.id == clip_id).first()
        if not clip:
            return

        print(f"[MATCH] 클립 {clip_id} | 카메라 위치: ({clip.camera_lat}, {clip.camera_lng}) | 시간: {clip.clip_start} ~ {clip.clip_end}")

        locations = db.query(UserLocation).filter(
            UserLocation.recorded_at >= clip.clip_start,
            UserLocation.recorded_at <= clip.clip_end,
        ).all()

        print(f"[MATCH] 클립 {clip_id} | 시간대 내 GPS 기록 {len(locations)}개")
        for loc in locations:
            dist = haversine_m(loc.lat, loc.lng, clip.camera_lat, clip.camera_lng)
            print(f"[MATCH]   유저 {loc.user_id} | 거리: {dist:.1f}m | 위치: ({loc.lat}, {loc.lng})")

        # 50m 이내 유저별 진입/이탈 시각 수집
        matched: dict[int, dict] = {}
        for loc in locations:
            dist = haversine_m(loc.lat, loc.lng, clip.camera_lat, clip.camera_lng)
            if dist <= PROXIMITY_M:
                uid = loc.user_id
                if uid not in matched:
                    matched[uid] = {"enter": loc.recorded_at, "exit": loc.recorded_at}
                    print(f"[MATCH] 유저 {uid} 범위 진입 - {loc.recorded_at} (거리: {dist:.1f}m)")
                else:
                    if loc.recorded_at < matched[uid]["enter"]:
                        matched[uid]["enter"] = loc.recorded_at
                    if loc.recorded_at > matched[uid]["exit"]:
                        matched[uid]["exit"] = loc.recorded_at

        for uid, times in matched.items():
            print(f"[MATCH] 유저 {uid} | 진입:{times['enter']} ~ 이탈:{times['exit']}")

        clip_path = os.path.join(CAMERA_CLIPS_FOLDER, clip.filename)

        for user_id, times in matched.items():
            # 중복 매칭 스킵
            if db.query(ClipMatch).filter(ClipMatch.user_id == user_id, ClipMatch.clip_id == clip_id).first():
                continue

            match = ClipMatch(
                user_id=user_id, clip_id=clip_id,
                enter_time=times["enter"], exit_time=times["exit"],
                status="processing",
            )
            db.add(match)
            db.commit()
            db.refresh(match)

            # 트림 구간 계산
            clip_duration = (clip.clip_end - clip.clip_start).total_seconds()
            start_sec     = max(0.0, (times["enter"] - clip.clip_start).total_seconds() - 2)
            end_sec       = min(clip_duration, (times["exit"] - clip.clip_start).total_seconds() + 2)
            # exit 시점이 클립 종료 10초 이내면 끝까지 포함 (GPS 끊김 대응)
            if clip_duration - end_sec <= 10:
                end_sec = clip_duration

            ts               = datetime.now().strftime("%Y%m%d_%H%M%S")
            trimmed_filename = f"trimmed_{user_id}_{clip_id}_{ts}.mp4"
            trimmed_path     = os.path.join(TRIMMED_CLIPS_FOLDER, trimmed_filename)

            if not trim_clip(clip_path, trimmed_path, start_sec, end_sec):
                match.status = "failed"
                db.commit()
                print(f"[MATCH] 유저 {user_id} 트림 실패")
                continue

            match.trimmed_filename = trimmed_filename
            match.status           = "done"
            db.commit()

            # 이전 연속 클립과 합치기 (25초 이내면 merge)
            prev = (
                db.query(ClipMatch)
                .filter(
                    ClipMatch.user_id == user_id,
                    ClipMatch.id != match.id,
                    ClipMatch.status == "done",
                    ClipMatch.exit_time >= clip.clip_start - timedelta(seconds=25),
                    ClipMatch.exit_time <= clip.clip_start + timedelta(seconds=5),
                )
                .order_by(ClipMatch.created_at.desc())
                .first()
            )

            if prev and prev.trimmed_filename:
                prev_path = os.path.join(TRIMMED_CLIPS_FOLDER, prev.trimmed_filename)
                if os.path.exists(prev_path):
                    ts2             = datetime.now().strftime("%Y%m%d_%H%M%S")
                    merged_filename = f"merged_{user_id}_{ts2}.mp4"
                    merged_path     = os.path.join(TRIMMED_CLIPS_FOLDER, merged_filename)
                    if concat_clips([prev_path, trimmed_path], merged_path):
                        prev.trimmed_filename = merged_filename
                        prev.exit_time        = match.exit_time
                        match.status          = "merged"
                        db.commit()
                        try:
                            os.remove(trimmed_path)
                        except Exception:
                            pass
                        print(f"[MATCH] 유저 {user_id} 클립 합치기 완료 → {merged_filename}")
                        auto_process(user_id, merged_path)
                        continue

            print(f"[MATCH] 유저 {user_id} 영상 전송 완료 → {trimmed_filename}")
            auto_process(user_id, trimmed_path)

    except Exception as e:
        print(f"[CLIP MATCHING ERROR] {e}")
    finally:
        db.close()
