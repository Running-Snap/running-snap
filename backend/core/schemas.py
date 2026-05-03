from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# User 스키마
class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None   # 선택 항목 (마라톤 자동 생성 계정은 email 없음)
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    bib_number: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# 영상 분석 작업 스키마
class AnalysisJobCreate(BaseModel):
    video_id: int


class AnalysisJobResponse(BaseModel):
    id: int
    video_id: Optional[int] = None
    status: str
    result_json: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 숏폼 생성 작업 스키마
class ShortformJobCreate(BaseModel):
    video_ids: List[int]        # 영상 ID 목록 (최소 2개, 프론트에서 업로드 후 받은 video_id들)
    style: str = "action"       # action / instagram / tiktok / humor / documentary
    duration_sec: float = 30.0  # 목표 길이 (초)


class ShortformJobResponse(BaseModel):
    id: int
    video_id: Optional[int] = None
    video_ids_json: Optional[str] = None
    style: str
    duration_sec: float
    status: str
    output_filename: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 베스트 컷 추출 작업 스키마
class BestCutJobCreate(BaseModel):
    video_ids: List[int]        # 영상 ID 목록 (최소 1개, 프론트에서 업로드 후 받은 video_id들)
    photo_count: int = 5
    # 포스터 설정 (선택)
    poster_title:       Optional[str] = "2026\nMIRACLE MARATHON"
    poster_location:    Optional[str] = "Daejeon, Republic of Korea"
    poster_sublocation: Optional[str] = "Gapcheon"
    poster_distance_km: Optional[float] = 10.0
    poster_run_time:    Optional[str] = ""
    poster_pace:        Optional[str] = ""
    poster_color_scheme:Optional[str] = "warm"   # warm / cool / neutral


class BestCutJobResponse(BaseModel):
    id: int
    video_id: Optional[int] = None
    video_ids_json: Optional[str] = None
    photo_count: int
    status: str
    result_json: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 자세분석 영상 생성 작업 스키마
class PoseVideoJobCreate(BaseModel):
    video_id: int
    analysis_job_id: int  # 분석 결과에서 feedback_data 자동 추출


class PoseVideoJobResponse(BaseModel):
    id: int
    video_id: int
    analysis_job_id: Optional[int] = None
    status: str
    output_filename: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 인증영상 생성 작업 스키마 (Nike 스타일)
class CertJobCreate(BaseModel):
    video_id: int
    mode: str = "simple"                        # simple / full
    # 이벤트 정보
    title:          Optional[str] = "RUNNING\nDIARY"
    location:       Optional[str] = "Running Diary"
    date:           Optional[str] = ""           # e.g. "2026.04.19" (비어있으면 오늘 날짜 자동)
    distance_km:    Optional[float] = 0.0
    run_time:       Optional[str] = ""           # e.g. "34'18\""
    pace:           Optional[str] = ""           # e.g. "6'35\"/km"
    calories:       Optional[str] = ""           # e.g. "312 kcal"
    elevation_gain: Optional[str] = ""           # e.g. "48 m"
    avg_heart_rate: Optional[str] = ""           # e.g. "152 bpm"
    cadence:        Optional[str] = ""           # e.g. "163 spm"
    color_scheme:   Optional[str] = "warm"       # warm / cool / neutral


class CertJobResponse(BaseModel):
    id: int
    video_id: int
    mode: str
    status: str
    output_filename: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 코칭 영상 생성 작업 스키마
class CoachingJobCreate(BaseModel):
    video_id: int               # 원본 영상 ID
    coaching_text: str = ""     # 코칭 텍스트 (비어있으면 analysis_job_id에서 자동 추출)
    analysis_job_id: Optional[int] = None  # 분석 결과에서 coaching_report 자동 사용


class CoachingJobResponse(BaseModel):
    id: int
    video_id: int
    coaching_text: Optional[str] = None
    status: str
    output_filename: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
