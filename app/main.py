# app/main.py
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from .auth import router as auth_router
from .import_export import router as data_router
from .deps import login_required
from .settings import SECRET_KEY  # 放一個穩定隨機字串；Render 以環境變數注入

app = FastAPI(title="AurumLedger Web")

app.add_middleware(SessionMiddleware,
                   secret_key=SECRET_KEY,
                   same_site="lax",
                   https_only=False)  # 上雲後設 True

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ===== 頁面（一律走 base.html，受保護）=====
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "登入"})

@app.get("/")
@app.get("/orders")
def orders_page(request: Request, _=Depends(login_required)):
    return templates.TemplateResponse("orders.html", {"request": request, "title": "訂單"})

@app.get("/expenses")
def expenses_page(request: Request, _=Depends(login_required)):
    return templates.TemplateResponse("expenses.html", {"request": request, "title": "支出"})

# ===== API 路由 =====
app.include_router(auth_router)
app.include_router(data_router)
