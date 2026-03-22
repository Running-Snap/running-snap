from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# User 스키마
class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
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
