# -*- coding: utf-8 -*-
import os

APP_NAME = "AurumLedger Web"
APP_VERSION = "0.1.0"
# 內網本機開發就全開
CORS_ORIGINS = ["*"]



# SQLite 路徑（沿用你桌面版的環境變數 RESTO_DB，沒有就用 resto.db）
DB_PATH = os.getenv("RESTO_DB", "resto.db")

# CORS（如需限制可改成你的網域）
CORS_ORIGINS = ["*"]

# auth.json 與 GUI 相容
AUTH_FILE = "auth.json"

# JWT 設定（正式環境請改為強隨機字串＋用 .env）
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = 8 * 60  # 登入 token（分鐘）
JWT_REV_EXPIRE_MIN = 60  # 營業額解鎖 token（分鐘）
