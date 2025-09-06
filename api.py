# api.py  — always ensure /ui/orders exists

from __future__ import annotations
import os
import logging
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, PlainTextResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from fastapi import APIRouter

logging.basicConfig(level=logging.INFO, format="[api] %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="AurumLedger API", version="1.0.0")

# ── static/ ─────────────────────────────────────────────────────────
for candidate in ("static", os.path.join("web", "static")):
    if os.path.isdir(candidate):
        app.mount("app/static", StaticFiles(directory=candidate), name="static")
        log.info(f"Mounted static from: {candidate}")
        break

# ── helpers ─────────────────────────────────────────────────────────
def _route_exists(routes: Iterable, path: str, method: str = "GET") -> bool:
    m = method.upper()
    for r in routes:
        if isinstance(r, APIRoute) and r.path == path and (m in r.methods):
            return True
    return False

def _add_fallback_orders_ui() -> None:
    fallback = APIRouter()

    @fallback.get("/ui/orders", response_class=HTMLResponse)
    @fallback.get("/ui/orders/", response_class=HTMLResponse)
    async def _orders():
        return (
            "<h2>Orders UI (fallback)</h2>"
            "<p>未載入 <code>web_ui.py</code> 或其中沒有 <code>/ui/orders</code>。</p>"
            "<p>請確認：</p>"
            "<ul>"
            "<li>專案根目錄存在 <code>web_ui.py</code> 且內含 <code>router = APIRouter()</code></li>"
            "<li>有 <code>@router.get('/ui/orders')</code> 端點</li>"
            "<li>若使用樣板，<code>templates/orders.html</code> 或 <code>web/templates/orders.html</code> 存在</li>"
            "</ul>"
        )

    app.include_router(fallback, prefix="")
    log.info("Fallback /ui/orders mounted")

# ── 尝试加载 web_ui.router ─────────────────────────────────────────
loaded_ui = False
try:
    from web_ui import router as web_router
    app.include_router(web_router, prefix="")
    loaded_ui = True
    log.info("UI router loaded from web_ui.py")
except Exception as e:  # noqa: BLE001
    log.warning(f"UI router not available: {e!r}")

# 沒有 /ui/orders 就補上一個保底 UI
if not _route_exists(app.routes, "/ui/orders", "GET"):
    _add_fallback_orders_ui()

# ── health & root ───────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/")
async def root():
    return RedirectResponse(url="/docs", status_code=302)

# 列出目前載入的路由，方便你檢查
@app.get("/_routes", response_class=PlainTextResponse)
async def _routes():
    lines = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            lines.append(f"{sorted(r.methods)}  {r.path}")
    return "\n".join(lines)

# 讓樣板遺失時顯示可讀訊息（避免只看到 500）
try:
    from jinja2 import TemplateNotFound  # type: ignore
except Exception:  # noqa: BLE001
    TemplateNotFound = None

if TemplateNotFound:
    @app.exception_handler(TemplateNotFound)
    async def _template_missing(_: Request, exc: TemplateNotFound):
        msg = (
            f"Template not found: {exc.name}\n\n"
            "請確認樣板路徑：\n"
            "- templates/orders.html  或\n"
            "- web/templates/orders.html\n"
        )
        return PlainTextResponse(msg, status_code=500)

# ── 後端 API routers（能載就載，載不到不影響 UI） ───────────────────
def _safe_include(module: str, prefix: str = "") -> None:
    try:
        mod = __import__(module, fromlist=["router"])
        app.include_router(getattr(mod, "router"), prefix=prefix)
        log.info(f"Included router from {module} as {prefix or '/'}")
    except Exception as e:  # noqa: BLE001
        log.warning(f"Skip {module}: {e}")

_safe_include("app.routers.auth", "/auth")
_safe_include("app.routers.items", "/items")
_safe_include("app.routers.orders", "/orders")
_safe_include("app.routers.expenses", "/expenses")
_safe_include("app.routers.kpi", "/kpi")
