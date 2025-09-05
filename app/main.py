# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .utils.config import APP_NAME, APP_VERSION, CORS_ORIGINS
from .utils.db import init_db
from .routers import auth, items
from .routers import biz  # ← 新增

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# API
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(biz.router)  # ← 新增

@app.get("/healthz")
def healthz():
    return {"ok": True}

# 前端（靜態檔）
app.mount("/ui", StaticFiles(directory="web", html=True), name="ui")
