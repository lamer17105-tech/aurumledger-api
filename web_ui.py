# app/web_ui.py
from __future__ import annotations
import os
from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

APP_NAME = os.getenv("APP_NAME", "AurumLedger 企業版")
STATIC_DIR = "app/static"
TEMPLATE_DIR = "app/templates"

app = FastAPI(title=APP_NAME, default_response_class=HTMLResponse)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me-please"))

# 掛上 /static
if not any(getattr(r, "path", None) == "/static" for r in app.routes):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals.update(now=lambda: datetime.utcnow(), APP_NAME=APP_NAME)

# ---- 可選載入既有 routers（存在才會掛） ----
def _include_router(module_path: str, attr: str = "router"):
    try:
        mod = __import__(module_path, fromlist=[attr])
        router = getattr(mod, attr)
        app.include_router(router)
    except Exception:
        pass

_include_router("app.routers.orders")
_include_router("app.routers.expenses")
_include_router("app.routers.kpi")
_include_router("app.import_export")

# ---- 小工具 ----
def render_first_exist(request: Request, names: list[str], ctx: dict | None = None, status_code: int = 200):
    ctx = dict(ctx or {}); ctx.setdefault("request", request)
    for name in names:
        if os.path.exists(os.path.join(TEMPLATE_DIR, name)):
            return templates.TemplateResponse(name, ctx, status_code=status_code)
    return HTMLResponse("<h3>Template not found.</h3>", status_code=200)

def current_user(request: Request):
    return request.session.get("user")

def login_required(user=Depends(current_user)):
    if not user:
        raise RedirectResponse("/login")
    return user

# ---- 基本路由 ----
@app.get("/", include_in_schema=False)
def root(): return RedirectResponse("/ui", status_code=302)

@app.get("/healthz", include_in_schema=False)
def healthz(): return JSONResponse({"ok": True, "ts": datetime.utcnow().isoformat()})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    p = os.path.join(STATIC_DIR, "img", "favicon.ico")
    return FileResponse(p) if os.path.exists(p) else PlainTextResponse("", status_code=204)

@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return render_first_exist(request, ["login.html", "account.html", "ui_home.html", "dashboard.html"], {"title": "登入"})

@app.post("/login", include_in_schema=False)
def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    # 若你有 app.auth.validate 可自動接上（沒有就直接通過）
    try:
        validate = __import__("app.auth", fromlist=["validate"]).validate  # type: ignore
        if not bool(validate(username, password)):
            return render_first_exist(request, ["login.html", "account.html"], {"title": "登入", "error": "帳號或密碼錯誤"}, 401)
    except Exception:
        pass
    request.session["user"] = {"name": username, "ts": datetime.utcnow().isoformat()}
    return RedirectResponse("/ui", status_code=302)

@app.get("/logout", include_in_schema=False)
def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/ui", include_in_schema=False)
def ui_home(request: Request, user=Depends(login_required)):
    return render_first_exist(request, ["ui_home.html", "dashboard.html", "base.html"], {"user": user, "title": "首頁"})

@app.get("/orders", include_in_schema=False)
def ui_orders(request: Request, user=Depends(login_required)):
    return render_first_exist(request, ["orders.html", "ui_table.html", "base.html"], {"user": user, "title": "訂單"})

@app.get("/expenses", include_in_schema=False)
def ui_expenses(request: Request, user=Depends(login_required)):
    return render_first_exist(request, ["expenses.html", "ui_table.html", "base.html"], {"user": user, "title": "支出"})

@app.get("/kpi", include_in_schema=False)
def ui_kpi(request: Request, user=Depends(login_required)):
    return render_first_exist(request, ["kpi.html", "kpi_pin.html", "verify_kpi.html", "base.html"], {"user": user, "title": "KPI"})

@app.get("/import-export", include_in_schema=False)
def ui_io(request: Request, user=Depends(login_required)):
    return render_first_exist(request, ["import_export.html", "backup.html", "settings_io.html", "base.html"], {"user": user, "title": "匯入/匯出"})

@app.exception_handler(404)
async def not_found(req: Request, _exc):
    if not req.session.get("user"):
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/ui", status_code=302)
