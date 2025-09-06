# app/main.py
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent       # == app/
TEMPLATES_DIR = BASE_DIR / "templates"           # == app/templates
STATIC_DIR = BASE_DIR / "static"                 # == app/static

app = FastAPI(title="AurumLedger 企業版")

# 正確掛載 /static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 指定模板資料夾
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---- 頁面路由（登入 + 首頁示意）----
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, msg: str | None = None):
    # 登入頁使用置中版型（在 login.html 透過 body_class block 處理）
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})

@app.post("/login")
async def do_login(username: str = Form(...), password: str = Form(...)):
    # TODO: 放你的驗證邏輯；先導回首頁
    return RedirectResponse("/", status_code=302)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # 你已有 ui_home.html；沒有就改成 dashboard.html
    page = "ui_home.html" if (TEMPLATES_DIR / "ui_home.html").exists() else "dashboard.html"
    return templates.TemplateResponse(page, {"request": request})

# ---- 既有 API / 頁面 router 掛載（有就用，沒有就略過，不影響樣式）----
try:
    from .routers import orders, expenses, items, kpi, biz, init as init_router
    app.include_router(orders.router)
    app.include_router(expenses.router)
    app.include_router(items.router)
    app.include_router(kpi.router)
    app.include_router(biz.router)
    app.include_router(init_router.router)
except Exception:
    pass
