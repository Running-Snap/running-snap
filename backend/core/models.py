from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text
from datetime import datetime
from core.database import Base, engine


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    bib_number = Column(String, nullable=True, index=True)  # 마라톤 배번 (OCR 매칭용)
    created_at = Column(DateTime, default=datetime.utcnow)



class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String, unique=True, index=True)
    upload_time = Column(DateTime, default=datetime.utcnow)


# 러닝 영상 자세 분석 작업
class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    status = Column(String, default="pending")          # pending / processing / done / failed
    result_json = Column(Text, nullable=True)           # JSON 문자열로 분석 결과 저장
    created_at = Column(DateTime, default=datetime.utcnow)


# 숏폼 영상 생성 작업
class ShortformJob(Base):
    __tablename__ = "shortform_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    video_ids_json = Column(Text, nullable=True)        # 전체 video_id 목록 (JSON 배열)
    style = Column(String, default="action")            # action/instagram/tiktok/humor/documentary
    duration_sec = Column(Float, default=30.0)          # 목표 길이 (초)
    status = Column(String, default="pending")          # pending / processing / done / failed
    output_filename = Column(String, nullable=True)     # 생성된 영상 파일명
    created_at = Column(DateTime, default=datetime.utcnow)


# 베스트 컷 사진 추출 작업
class BestCutJob(Base):
    __tablename__ = "bestcut_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    video_ids_json = Column(Text, nullable=True)        # 전체 video_id 목록 (JSON 배열)
    photo_count = Column(Integer, default=5)            # 추출할 사진 개수
    status = Column(String, default="pending")          # pending / processing / done / failed
    result_json = Column(Text, nullable=True)           # JSON 배열: [{timestamp, photo_url, description}]
    created_at = Column(DateTime, default=datetime.utcnow)


# 카메라 클립
class CameraClip(Base):
    __tablename__ = "camera_clips"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, unique=True)        # 저장된 파일명
    s3_url = Column(String, nullable=True)        # S3 업로드 URL
    camera_id = Column(String, nullable=True)     # 카메라 식별자 (예: "cam1", "cam2")
    clip_start = Column(DateTime)                # 클립 시작 시각 (UTC)
    clip_end = Column(DateTime)                  # 클립 종료 시각 (UTC)
    created_at = Column(DateTime, default=datetime.utcnow)


# 유저-클립 매칭 결과
class ClipMatch(Base):
    __tablename__ = "clip_matches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    clip_id = Column(Integer, ForeignKey("camera_clips.id"))
    trimmed_filename = Column(String, nullable=True)  # 잘라낸 영상 파일명
    enter_time = Column(DateTime)                # 50m 진입 시각
    exit_time = Column(DateTime)                 # 50m 이탈 시각
    status = Column(String, default="pending")   # pending / processing / done / failed / merged
    created_at = Column(DateTime, default=datetime.utcnow)


# OCR 배번 인식 결과 (관리자 수정 가능)
class DetectedBib(Base):
    __tablename__ = "detected_bibs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    clip_id = Column(Integer, ForeignKey("camera_clips.id"))
    raw_bib = Column(String)                        # OCR이 인식한 원본값 (예: "1Z34")
    assigned_bib = Column(String, nullable=True)    # 실제 배정된 배번 (관리자 수정 가능)
    confidence = Column(Float, nullable=True)        # OCR 신뢰도
    start_sec = Column(Float, nullable=True)         # 영상 내 등장 시작(초)
    end_sec = Column(Float, nullable=True)           # 영상 내 등장 종료(초)
    status = Column(String, default="pending")       # pending / matched / failed / corrected
    created_at = Column(DateTime, default=datetime.utcnow)


# 자세분석 영상 생성 작업
class PoseVideoJob(Base):
    __tablename__ = "pose_video_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    analysis_job_id = Column(Integer, ForeignKey("analysis_jobs.id"), nullable=True)
    status = Column(String, default="pending")          # pending / processing / done / failed
    output_filename = Column(String, nullable=True)     # 생성된 영상 S3 URL
    created_at = Column(DateTime, default=datetime.utcnow)


# 코칭 영상 생성 작업
class CoachingJob(Base):
    __tablename__ = "coaching_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    coaching_text = Column(Text, nullable=True)         # 코칭 텍스트 (Gemini 리포트 등)
    status = Column(String, default="pending")          # pending / processing / done / failed
    output_filename = Column(String, nullable=True)     # 생성된 코칭 영상 파일명
    created_at = Column(DateTime, default=datetime.utcnow)


# 인증영상 생성 작업 (Nike 스타일)
class CertJob(Base):
    __tablename__ = "cert_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(Integer, ForeignKey("videos.id"))
    event_config_json = Column(Text, nullable=True)     # 이벤트 설정 JSON (title, distance_km 등)
    mode = Column(String, default="simple")             # simple / full
    status = Column(String, default="pending")          # pending / processing / done / failed
    output_filename = Column(String, nullable=True)     # 생성된 인증영상 S3 URL
    created_at = Column(DateTime, default=datetime.utcnow)


