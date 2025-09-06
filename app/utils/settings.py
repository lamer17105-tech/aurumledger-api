import os, secrets

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
SESSION_SAMESITE = os.getenv("SESSION_SAMESITE", "lax")   # lax/strict/none
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "0") in ("1", "true", "True")