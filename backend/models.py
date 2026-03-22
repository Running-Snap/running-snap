from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Boolean
from datetime import datetime
from database import Base, engine


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)      # 생성시점



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


# 아이폰 GPS 위치 기록
class UserLocation(Base):
    __tablename__ = "user_locations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lat = Column(Float)                          # 위도
    lng = Column(Float)                          # 경도
    recorded_at = Column(DateTime)               # 클라이언트 기록 시각 (UTC)
    created_at = Column(DateTime, default=datetime.utcnow)


# 갤럭시 카메라 30초 클립
class CameraClip(Base):
    __tablename__ = "camera_clips"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, unique=True)        # 저장된 파일명
    camera_lat = Column(Float)                   # 카메라 위도
    camera_lng = Column(Float)                   # 카메라 경도
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


