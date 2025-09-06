# app/deps.py
from typing import Generator
from fastapi import Request, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# 你的 DB URL（沿用現有設定）
# 例：DATABASE_URL = "sqlite:///./data.db" 或 "postgresql+psycopg://..."
from app.utils.settings import DATABASE_URL  # 若沒有 settings.py，就把常數寫在這支

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def login_required(request: Request):
    if not request.session.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登入")
    return True
