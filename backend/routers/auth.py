from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User
from core.schemas import UserCreate, UserResponse, Token
from core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from core.security import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str

# ✅ 새로 추가: 배번호 로그인 요청 스키마
class BibLoginRequest(BaseModel):
    bib_number: str  # 숫자 문자열 (예: "1042")

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # username 중복 확인
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다")
    # email 중복 확인 (입력한 경우에만)
    if user.email and db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다")
    db_user = User(
        username=user.username,
        email=user.email or None,
        hashed_password=get_password_hash(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/login-json", response_model=Token)
async def login_json(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter((User.username == req.email) | (User.email == req.email)).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="잘못된 아이디 또는 비밀번호")
    token = create_access_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter((User.username == form_data.username) | (User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 아이디 또는 비밀번호",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# ─── ✅ 새로 추가: 배번호 로그인 ────────────────────────────

@router.post("/bib-login", response_model=Token)
async def bib_login(req: BibLoginRequest, db: Session = Depends(get_db)):
    # 입력값 검증: 숫자만 허용
    if not req.bib_number.strip().isdigit():
        raise HTTPException(status_code=400, detail="배번호는 숫자만 입력해주세요")

    bib = req.bib_number.strip()

    # 배번호로 기존 유저 조회
    user = db.query(User).filter(User.bib_number == bib).first()

    # 등록된 배번호만 허용
    if not user:
        raise HTTPException(
            status_code=404,
            detail="등록되지 않은 배번호입니다. 대회 운영진에게 문의해주세요."
        )

    token = create_access_token(
        {"sub": user.username},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer"}
