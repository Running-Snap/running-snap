import os
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:@running-db.c12mg8uquxct.ap-northeast-2.rds.amazonaws.com:5432/postgres"
)

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,      # 연결 풀 미사용 - 백그라운드 스레드 안전
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
