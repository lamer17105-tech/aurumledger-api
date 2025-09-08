# app/web_ui.py
from __future__ import annotations
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Optional, Dict, List, Tuple
import json, os, base64, hashlib, hmac, sqlite3, re, io, zipfile
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse, StreamingResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "aurum.db"
AUTH_PATH = APP_DIR / "auth.json"

# app/web_ui.py（只改這 3 行）
import os  # ← 已經有就略過
app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))  # ← 原本是 app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_ME_32+CHARS")


templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.filters["money"] = lambda v: f"{float(v):,.0f}" if v not in (None, "", "None") else "0"
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# ---------------- DB ----------------
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def _init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift TEXT NOT NULL,
            order_no TEXT NOT NULL,
            amount INTEGER NOT NULL,
            odt TEXT NOT NULL,
            ctime TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat TEXT NOT NULL,
            amount INTEGER NOT NULL,
            odt TEXT NOT NULL,
            memo TEXT DEFAULT '',
            ctime TEXT NOT NULL
        )""")
        # 索引（提升搜尋/篩選/排序穩定度）
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_odt_shift_id ON orders(odt, shift, id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_amount   ON orders(amount)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_expenses_odt    ON expenses(odt)")
        c.commit()
_init_db()

# -------------- Auth helpers --------------
def _hash_pbkdf2(pw: str, salt: bytes | None = None) -> str:
    if salt is None: salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 120_000)
    return "pbkdf2$120000$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(dk).decode())

def _verify_pbkdf2(pw: str, stored: str) -> bool:
    try:
        _, rounds, b64salt, b64hash = stored.split("$")
        salt = base64.b64decode(b64salt); expect = base64.b64decode(b64hash)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(dk, expect)
    except Exception:
        return False

def _load_auth() -> Optional[Dict[str,str]]:
    if AUTH_PATH.exists():
        with open(AUTH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def _save_auth(username: str, pw_hash: str, kpi_pin_hash: Optional[str] = None) -> None:
    old = _load_auth() or {}
    data = {
        "username": username,
        "pw_hash": pw_hash,
        "kpi_pin_hash": kpi_pin_hash or old.get("kpi_pin_hash")
    }
    with open(AUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -------------- helpers --------------
def _today() -> str:
    return date.today().isoformat()

def _parse_dt(s: Optional[str]) -> date:
    try: return datetime.strptime(s or "", "%Y-%m-%d").date()
    except Exception: return date.today()

def _to_int(s: Optional[str]) -> Optional[int]:
    try: return int(str(s).replace(",", "").strip())
    except Exception: return None

def _ctx(request: Request, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base = {"request": request, "user": request.session.get("user")}
    if extra: base.update(extra)
    return base

def _need_login(request: Request) -> bool:
    return not bool(request.session.get("user"))

def _add_months(d: date, n: int) -> date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    from calendar import monthrange
    return date(y, m, min(d.day, monthrange(y, m)[1]))

def _add_years(d: date, n: int) -> date:
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(month=2, day=28, year=d.year + n)

def _range(mode: str, dt: Optional[str]) -> tuple[str,str,date]:
    base = _parse_dt(dt)
    if mode == "day":
        return base.isoformat(), base.isoformat(), base
    if mode == "month":
        from calendar import monthrange
        start = base.replace(day=1); end = base.replace(day=monthrange(base.year, base.month)[1])
        return start.isoformat(), end.isoformat(), base
    if mode == "year":
        return date(base.year,1,1).isoformat(), date(base.year,12,31).isoformat(), base
    return "0001-01-01", "9999-12-31", base

def _nav(mode: str, dt: Optional[str]) -> Dict[str,str]:
    base = _parse_dt(dt)
    if mode == "day":
        return {"prev": (base - timedelta(days=1)).isoformat(),
                "next": (base + timedelta(days=1)).isoformat(),
                "today": _today()}
    if mode == "month":
        return {"prev": _add_months(base, -1).isoformat(),
                "next": _add_months(base, 1).isoformat(),
                "today": _today()}
    if mode == "year":
        return {"prev": _add_years(base, -1).isoformat(),
                "next": _add_years(base, 1).isoformat(),
                "today": _today()}
    return {"prev": _today(), "next": _today(), "today": _today()}

# -------------- routes --------------
@app.get("/")
def root():
    return RedirectResponse("/orders")

# ---------- Auth ----------
@app.get("/login")
def login_page(request: Request):
    first_setup = _load_auth() is None
    remembered = request.cookies.get("remember_user","")
    return templates.TemplateResponse("login.html",
        _ctx(request, {"first_setup": first_setup, "auth_only": True, "remembered": remembered}))

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...),
                 remember: Optional[str] = Form(None), mode: str = Form("login")):
    auth = _load_auth()
    if auth is None or mode == "setup":
        if not username or not password:
            return RedirectResponse("/login", status_code=303)
        _save_auth(username, _hash_pbkdf2(password), None)
        resp = RedirectResponse("/orders", status_code=303)
        if remember: resp.set_cookie("remember_user", username, max_age=30*86400)
        else: resp.delete_cookie("remember_user")
        request.session.clear(); request.session["user"] = username
        return resp
    if username == auth.get("username") and _verify_pbkdf2(password, auth.get("pw_hash","")):
        resp = RedirectResponse("/orders", status_code=303)
        if remember: resp.set_cookie("remember_user", username, max_age=30*86400)
        else: resp.delete_cookie("remember_user")
        request.session.clear(); request.session["user"] = username
        return resp
    return templates.TemplateResponse("login.html",
        _ctx(request, {"error":"帳號或密碼錯誤。","first_setup":False,"auth_only":True,"remembered":username}))

@app.get("/logout")
def logout(request: Request):
    # 登出時保留「記住帳號」cookie 讓登入頁自動帶入
    uname = request.session.get("user","")
    resp = RedirectResponse("/login", status_code=303)
    if uname:
        resp.set_cookie("remember_user", uname, max_age=30*86400)
    request.session.clear()
    return resp

@app.get("/account")
def account_page(request: Request):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    auth = _load_auth() or {}
    return templates.TemplateResponse("account.html", _ctx(request, {"username": auth.get("username","")}))

@app.post("/account/update")
def account_update(request: Request, current_password: str = Form(...),
                   new_username: str = Form(""), new_password: str = Form(""), new_kpi_pin: str = Form("")):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    auth = _load_auth() or {}
    if not _verify_pbkdf2(current_password, auth.get("pw_hash","")):
        return templates.TemplateResponse("account.html", _ctx(request, {"username":auth.get("username",""), "error":"目前密碼不正確。"}))
    uname = new_username.strip() or auth.get("username","")
    pwh  = _hash_pbkdf2(new_password.strip()) if new_password.strip() else auth.get("pw_hash","")
    kpin = _hash_pbkdf2(new_kpi_pin.strip()) if new_kpi_pin.strip() else auth.get("kpi_pin_hash")
    _save_auth(uname, pwh, kpin); request.session["user"] = uname; request.session.pop("kpi_ok", None)
    return templates.TemplateResponse("account.html", _ctx(request, {"username":uname, "ok":"已更新。"}))

# ---------- KPI guard ----------
@app.get("/kpi/guard")
def kpi_guard(request: Request):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("kpi_pin.html", _ctx(request, {}))

@app.post("/kpi/guard")
def kpi_guard_go(request: Request, pin: str = Form(...)):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    auth = _load_auth() or {}
    if auth.get("kpi_pin_hash") and _verify_pbkdf2(pin, auth["kpi_pin_hash"]):
        request.session["kpi_ok"] = True
        return RedirectResponse("/kpi", status_code=303)
    return templates.TemplateResponse("kpi_pin.html", _ctx(request, {"error":"二次密碼錯誤。"}))

# ---------- Orders ----------
@app.get("/orders")
def orders_page(request: Request, q: Optional[str] = None,
                from_: Optional[str] = None, to: Optional[str] = None):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    sql = "SELECT id,shift,order_no,amount,odt FROM orders"
    where, params = [], []
    if q and q.strip():
        qi = _to_int(q)
        if qi is not None:
            where.append("(order_no LIKE ? OR amount=?)"); params += [f"%{q.strip()}%", qi]
        else:
            where.append("(order_no LIKE ?)"); params += [f"%{q.strip()}%"]
    if from_: where.append("odt>=?"); params.append(from_)
    if to:    where.append("odt<=?"); params.append(to)
    if where: sql += " WHERE " + " AND ".join(where)
    # 依日期新→舊；同日先早班後晚班；同班別以 id 由小到大（越新的在該班別最下方）
    sql += " ORDER BY odt DESC, CASE WHEN shift='早班' THEN 0 ELSE 1 END, id ASC"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, params)]
        for i, r in enumerate(rows): r["idx"] = i
    return templates.TemplateResponse("orders.html", _ctx(request, {
        "orders": rows, "today": _today(), "q": q or "", "from_": from_ or "", "to": to or ""
    }))

@app.post("/orders/create")
def orders_create(request: Request, odt: str = Form(...), shift: str = Form(...),
                  order_no: str = Form(...), amount: str = Form(...)):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    try: datetime.strptime(odt, "%Y-%m-%d")
    except: odt = _today()
    shift = "早班" if shift == "早班" else "晚班"
    order_no = (order_no or "").strip()
    amt = _to_int(amount) or 0
    if not order_no: return RedirectResponse("/orders", status_code=303)
    with _conn() as c:
        c.execute("INSERT INTO orders (shift,order_no,amount,odt,ctime) VALUES(?,?,?,?,?)",
                  (shift, order_no, amt, odt, datetime.utcnow().isoformat()))
        c.commit()
    # 與前端統一：回 orders 並帶 #create，前端會自動聚焦「單號」
    return RedirectResponse("/orders#create", status_code=303)

@app.post("/orders/update-json")
async def orders_update_json(request: Request):
    if _need_login(request): return JSONResponse({"ok": False, "msg": "auth"}, status_code=403)
    data = await request.json()
    oid, field, value = int(data.get("id")), data.get("field"), (data.get("value") or "").strip()
    if field not in {"shift","order_no","amount","odt"}:
        return JSONResponse({"ok": False, "msg": "field"})
    if field == "shift":
        value = "早班" if value == "早班" else "晚班"
    elif field == "amount":
        value = str(_to_int(value) or 0)
    elif field == "odt":
        try: datetime.strptime(value, "%Y-%m-%d")
        except: value = _today()
    with _conn() as c:
        c.execute(f"UPDATE orders SET {field}=? WHERE id=?", (value, oid)); c.commit()
    return JSONResponse({"ok": True, "value": value})

@app.post("/orders/delete")
async def orders_delete(request: Request):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    form = await request.form()
    ids: List[int] = []
    for v in form.getlist("selected"):
        try: ids.append(int(v))
        except: pass
    if ids:
        with _conn() as c:
            c.execute(f"DELETE FROM orders WHERE id IN ({','.join(['?']*len(ids))})", ids)
            c.commit()
    return RedirectResponse("/orders", status_code=303)

# ---------- Expenses ----------
@app.get("/expenses")
def expenses_page(request: Request, mode: str = "day", dt: Optional[str] = None,
                  q: str = "", start: str = "", end: str = ""):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    frm, to, base = _range(mode, dt)
    if start: frm = start
    if end:   to = end
    where = ["odt BETWEEN ? AND ?"]; params = [frm, to]
    if q.strip():
        where.append("(cat LIKE ? OR memo LIKE ?)")
        params += [f"%{q.strip()}%", f"%{q.strip()}%"]
    sql = "SELECT id,cat,amount,odt,memo FROM expenses WHERE " + " AND ".join(where) + " ORDER BY odt DESC, id DESC"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, params)]
    return templates.TemplateResponse("expenses.html", _ctx(request, {
        "items": rows, "mode": mode, "dt": base.isoformat(), "nav": _nav(mode, dt),
        "q": q, "start": frm, "end": to
    }))

@app.post("/expenses/create")
def expenses_create(request: Request, odt: str = Form(...), cat: str = Form(...),
                    amount: str = Form(...), memo: str = Form("")):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    try: datetime.strptime(odt, "%Y-%m-%d")
    except: odt = _today()
    amt = _to_int(amount) or 0
    with _conn() as c:
        c.execute("INSERT INTO expenses (cat,amount,odt,memo,ctime) VALUES(?,?,?,?,?)",
                  (cat.strip() or "未分類", amt, odt, memo.strip(), datetime.utcnow().isoformat()))
        c.commit()
    return RedirectResponse("/expenses", status_code=303)

@app.post("/expenses/delete")
async def expenses_delete(request: Request):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    form = await request.form()
    ids: List[int] = []
    for v in form.getlist("selected"):
        try: ids.append(int(v))
        except: pass
    if ids:
        with _conn() as c:
            c.execute(f"DELETE FROM expenses WHERE id IN ({','.join(['?']*len(ids))})", ids)
            c.commit()
    return RedirectResponse("/expenses", status_code=303)

# 表內即時更新（分類/金額/日期/備註）
@app.post("/expenses/update-json")
async def expenses_update_json(request: Request):
    if _need_login(request):
        return JSONResponse({"ok": False, "msg": "auth"}, status_code=403)
    data = await request.json()
    eid   = int(data.get("id"))
    field = data.get("field")
    value = (data.get("value") or "").strip()
    if field not in {"cat", "amount", "odt", "memo"}:
        return JSONResponse({"ok": False, "msg": "field"})
    if field == "amount":
        value = str(_to_int(value) or 0)
    elif field == "odt":
        try: datetime.strptime(value, "%Y-%m-%d")
        except Exception: value = _today()
    with _conn() as c:
        c.execute(f"UPDATE expenses SET {field}=? WHERE id=?", (value, eid))
        c.commit()
    return JSONResponse({"ok": True, "value": value})

# ---------- KPI ----------
@app.get("/kpi")
def kpi_page(request: Request, mode: str = "day", dt: Optional[str] = None):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    if not request.session.get("kpi_ok"): return RedirectResponse("/kpi/guard", status_code=303)
    frm, to, base = _range(mode, dt); nav = _nav(mode, dt)
    with _conn() as c:
        early = c.execute("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE odt BETWEEN ? AND ? AND shift='早班'", (frm,to)).fetchone()["v"]
        late  = c.execute("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE odt BETWEEN ? AND ? AND shift='晚班'", (frm,to)).fetchone()["v"]
        total = early + late
        exp   = c.execute("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE odt BETWEEN ? AND ?", (frm,to)).fetchone()["v"]
    net = total - exp
    return templates.TemplateResponse("kpi.html", _ctx(request, {
        "mode": mode, "dt": base.isoformat(), "nav": nav,
        "k_early": early, "k_late": late, "k_total": total, "k_exp": exp, "k_net": net,
        "period": f"{frm} ~ {to}"
    }))

# ---------- Reports（export only, ASCII filename + UTF-8 BOM + CRLF） ----------
def _csv_response(filename_ascii: str, lines: List[str]):
    headers = {
        "Content-Disposition": f"attachment; filename={filename_ascii}; filename*=UTF-8''{quote(filename_ascii)}"
    }
    def gen():
        yield "\ufeff"  # BOM
        for ln in lines:
            if not ln.endswith("\r\n"): ln = ln.rstrip("\n") + "\r\n"
            yield ln
    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8", headers=headers)

@app.get("/reports")
def reports_page(request: Request, mode: str = "day", dt: Optional[str] = None):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    _, _, base = _range(mode, dt); nav = _nav(mode, dt)
    return templates.TemplateResponse("reports.html", _ctx(request, {"mode": mode, "dt": base.isoformat(), "nav": nav}))

@app.get("/export/orders.csv")
def export_orders_csv(scope: str = "day", base: Optional[str] = None):
    frm, to, d = _range(scope, base)
    lines = ["id,班別,單號,金額,日期,建立時間"]
    with _conn() as c:
        for r in c.execute("SELECT id,shift,order_no,amount,odt,ctime FROM orders WHERE odt BETWEEN ? AND ? ORDER BY odt,id", (frm,to)):
            lines.append(f'{r["id"]},{r["shift"]},{r["order_no"]},{r["amount"]},{r["odt"]},{r["ctime"]}')
    return _csv_response(f"orders_{scope}_{d}.csv", lines)

@app.get("/export/expenses.csv")
def export_expenses_csv(scope: str = "day", base: Optional[str] = None):
    frm, to, d = _range(scope, base)
    lines = ["id,類別,金額,日期,備註,建立時間"]
    with _conn() as c:
        for r in c.execute("SELECT id,cat,amount,odt,memo,ctime FROM expenses WHERE odt BETWEEN ? AND ? ORDER BY odt,id", (frm,to)):
            memo = (r["memo"] or "").replace(",", "，")
            lines.append(f'{r["id"]},{r["cat"]},{r["amount"]},{r["odt"]},{memo},{r["ctime"]}')
    return _csv_response(f"expenses_{scope}_{d}.csv", lines)

@app.get("/export/sales.csv")
def export_sales_csv(scope: str = "day", base: Optional[str] = None):
    frm, to, d = _range(scope, base)
    with _conn() as c:
        s = c.execute("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE odt BETWEEN ? AND ?", (frm,to)).fetchone()["v"]
        e = c.execute("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE odt BETWEEN ? AND ?", (frm,to)).fetchone()["v"]
    lines = ["期間,營業額,支出,淨利", f"{frm}~{to},{s},{e},{s-e}"]
    return _csv_response(f"sales_{scope}_{d}.csv", lines)

# ---------- AI Assistant ----------
@app.get("/ai")
def ai_page(request: Request):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("ai.html", _ctx(request, {}))

@app.post("/ai/analyze")
def ai_analyze(request: Request, q: str = Form(""), mode: str = Form("auto"),
               start: str = Form(""), end: str = Form("")):
    if _need_login(request): return RedirectResponse("/login", status_code=303)

    def period_for(m: str, s: str, e: str) -> Tuple[str,str,str]:
        if m == "day":
            d0 = _today(); return d0, d0, "當日"
        if m == "month":
            d = _parse_dt(_today()); frm = d.replace(day=1).isoformat()
            from calendar import monthrange
            ed = d.replace(day=monthrange(d.year,d.month)[1]).isoformat()
            return frm, ed, "本月"
        if m == "year":
            d = _parse_dt(_today()); return f"{d.year}-01-01", f"{d.year}-12-31", "今年"
        if s and e:
            return s, e, f"{s}~{e}"
        # auto from text
        text = q
        if "本月" in text: return period_for("month","","")
        if "今年" in text: return period_for("year","","")
        if "昨天" in text:
            d = _parse_dt(_today()) - timedelta(days=1)
            return d.isoformat(), d.isoformat(), "昨天"
        return period_for("day","","")

    frm, to, tag = period_for(mode, start, end)

    def fetch(sql: str, args=()):
        with _conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    # 單號查詢
    txt = q.strip()
    m = re.search(r"單號\s*(\d+)", txt)
    if m:
        num = m.group(1)
        rows = fetch("SELECT shift,order_no,amount,odt FROM orders WHERE order_no LIKE ? AND odt BETWEEN ? AND ? ORDER BY odt, id",
                     (f"%{num}%", frm, to))
        html = ["<h3>查詢單號結果</h3><table class='table'><thead><tr><th>班別</th><th>單號</th><th>金額</th><th>日期</th></tr></thead><tbody>"]
        for r in rows:
            html.append(f"<tr><td class='center'>{r['shift']}</td><td class='center'>{r['order_no']}</td><td class='center'>{r['amount']:,}</td><td class='center'>{r['odt']}</td></tr>")
        if not rows: html.append("<tr><td colspan='4' class='center muted'>沒有資料</td></tr>")
        html.append("</tbody></table>")
        return templates.TemplateResponse("ai.html", _ctx(request, {"answer_html": "".join(html), "q": q}))

    # 聚合
    early = fetch("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE odt BETWEEN ? AND ? AND shift='早班'", (frm,to))[0]["v"]
    late  = fetch("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE odt BETWEEN ? AND ? AND shift='晚班'", (frm,to))[0]["v"]
    total = early + late
    exp   = fetch("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE odt BETWEEN ? AND ?", (frm,to))[0]["v"]
    net   = total - exp

    if any(k in txt for k in ["top","TOP","Top","TOP3","前三","top3","分類"]):
        rows = fetch("""SELECT cat, SUM(amount) s FROM expenses
                        WHERE odt BETWEEN ? AND ? GROUP BY cat ORDER BY s DESC LIMIT 3""", (frm,to))
        html = [f"<h3>{tag}TOP3 支出分類</h3><table class='table'><thead><tr><th>分類</th><th>金額</th></tr></thead><tbody>"]
        for r in rows:
            html.append(f"<tr><td class='center'>{r['cat']}</td><td class='center'>{r['s']:,}</td></tr>")
        if not rows: html.append("<tr><td colspan='2' class='center muted'>沒有資料</td></tr>")
        html.append("</tbody></table>")
    else:
        html = [f"""
        <div class='card'>
          <div class='export-strip'>
            <div class='tile gold'>早班{tag}：<b>NT${early:,}</b></div>
            <div class='tile blue'>晚班{tag}：<b>NT${late:,}</b></div>
            <div class='tile' style='background:#ffe4e4'>支出{tag}：<b>NT${exp:,}</b></div>
          </div>
          <div class='kpi-figure' style='margin-top:12px'>總額：NT${total:,}　｜　扣支出後：<b>NT${net:,}</b></div>
        </div>"""]
    return templates.TemplateResponse("ai.html", _ctx(request, {"answer_html": "".join(html), "q": q}))

# ===================== 備份 / 還原 =====================
@app.get("/backup")
def backup_page(request: Request, ok: str | None = None, err: str | None = None):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("backup.html", _ctx(request, {"ok": ok, "error": err}))

@app.get("/backup/download")
def backup_download(request: Request, inc_db: int = 1, inc_auth: int = 1):
    if _need_login(request): return RedirectResponse("/login", status_code=303)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # templates
        tpl_dir = APP_DIR / "templates"
        for f in sorted(tpl_dir.glob("*.html")):
            z.write(f, arcname=f"templates/{f.name}")
        # static css
        css = APP_DIR / "static" / "css" / "style.css"
        if css.exists(): z.write(css, arcname="static/css/style.css")
        # main app file
        z.write(APP_DIR / "web_ui.py", arcname="web_ui.py")
        # db / auth（依選項）
        if inc_db and DB_PATH.exists(): z.write(DB_PATH, arcname="aurum.db")
        if inc_auth and AUTH_PATH.exists(): z.write(AUTH_PATH, arcname="auth.json")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"aurum_backup_{ts}.zip"
    headers = {
        "Content-Disposition": f"attachment; filename={fname}; filename*=UTF-8''{quote(fname)}"
    }
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers=headers)

@app.post("/backup/restore")
async def backup_restore(request: Request, file: UploadFile = File(...)):
    if _need_login(request): return RedirectResponse("/login", status_code=303)
    try:
        data = await file.read()
        with zipfile.ZipFile(io.BytesIO(data), "r") as z:
            def _extract_member(name: str, target: Path):
                target.parent.mkdir(parents=True, exist_ok=True)
                content = z.read(name)
                # path safety（限制在 APP_DIR 下）
                p = target.resolve()
                if APP_DIR not in p.parents and p != APP_DIR:
                    raise RuntimeError("非法路徑")
                with open(p, "wb") as f: f.write(content)

            for name in z.namelist():
                if name.endswith("/"):
                    continue
                if name == "web_ui.py":
                    _extract_member(name, APP_DIR / "web_ui.py")
                elif name.startswith("templates/"):
                    rel = name.split("/",1)[1]
                    _extract_member(name, APP_DIR / "templates" / rel)
                elif name == "static/css/style.css":
                    _extract_member(name, APP_DIR / "static" / "css" / "style.css")
                elif name == "aurum.db":
                    _extract_member(name, DB_PATH)
                elif name == "auth.json":
                    _extract_member(name, AUTH_PATH)
                else:
                    pass
        return RedirectResponse("/backup?ok=已還原，請重啟服務使變更生效。", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/backup?err=還原失敗：{quote(str(e))}", status_code=303)
