# app/utils/settings.py
import os, secrets

# DB 連線字串
# 例：sqlite:///./data.db  或  postgresql+psycopg://user:pass@host:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")

# Session 用的密鑰：上雲請用環境變數固定；本機沒設就臨時給一組
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))

# 這兩個給 SessionMiddleware 用；也可直接寫死
SESSION_SAMESITE = os.getenv("SESSION_SAMESITE", "lax")  # "lax" / "strict" / "none"
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "0") in ("1", "true", "True")
