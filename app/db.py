from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite 檔案 (在專案根目錄生成)
DB_URL = "sqlite:///resto.db"

# SQLite 搭配多執行緒時要關閉同執行緒檢查
engine = create_engine(DB_URL, future=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    # 延遲載入，避免循環 import
    from .models import Base
    Base.metadata.create_all(bind=engine)
