# -*- coding: utf-8 -*-
# AurumLedger Web API（與桌機版共用 DB 與 auth.json）
# - 資料庫：沿用 RESTO_DB=resto.db
# - 登入：沿用 auth.json（PBKDF2），成功後給 JWT
# - 端點：/api/v1/orders, /api/v1/expenses, /api/v1/reports/*
# - 文件：/docs

import os, json, base64, hashlib, hmac, enum
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt  # PyJWT

# SQLAlchemy 2.x（相容 declarative_base）
try:
    from sqlalchemy.orm import declarative_base
except Exception:
    from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy import (
    create_engine, Column, Integer, String, Date, Enum as SAEnum, Numeric, Text,
    func, and_, or_, select
)
from sqlalchemy.orm import sessionmaker, Session

# ------------------------------
# 設定
# ------------------------------
APP_NAME = "AurumLedger Web API"
APP_VERSION = "1.0.0"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
DB_PATH = os.getenv("RESTO_DB", "resto.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")  # 上線請改強隨機字串
JWT_ALG = "HS256"
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))

# ------------------------------
# FastAPI
# ------------------------------
app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if CORS_ORIGINS == ["*"] else CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# 資料庫
# ------------------------------
engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

class Shift(str, enum.Enum):
    MORNING = "早班"
    EVENING = "晚班"

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    shift = Column(SAEnum(Shift), nullable=False, index=True)
    order_no = Column(String(32), nullable=False, index=True)
    amount = Column(Numeric(14,2), nullable=False)
    memo = Column(Text)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String(50), nullable=False)
    amount = Column(Numeric(14,2), nullable=False)
    note = Column(Text)

# 啟動時確保資料表存在（與桌機版共存）
@app.on_event("startup")
def _create_tables():
    Base.metadata.create_all(bind=engine)

# ------------------------------
# auth.json 相容驗證
# ------------------------------
AUTH_FILE = "auth.json"

def _safe_read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _verify_password(pw: str, salt_b64: str, hash_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64.encode())
        target = base64.b64decode(hash_b64.encode())
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return hmac.compare_digest(dk, target)

def verify_user(code: str, pw: str) -> bool:
    d = _safe_read_json(AUTH_FILE)
    if not d:
        return False
    u = d.get("user", {})
    return (u.get("code") == code.strip()) and _verify_password(pw or "", u.get("salt", ""), u.get("hash", ""))

# ------------------------------
# JWT
# ------------------------------
auth_scheme = HTTPBearer()

def create_token(sub: str) -> str:
    payload = {
        "sub": sub,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def require_user(cred: HTTPAuthorizationCredentials = Security(auth_scheme)) -> str:
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        sub = payload.get("sub")
        if not sub:
            raise ValueError("no sub")
        return sub
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ------------------------------
# Pydantic（v2）
# ------------------------------
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class LoginIn(BaseModel):
    code: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OrderIn(BaseModel):
    date: date
    shift: Literal["早班", "晚班"]
    order_no: str = Field(..., min_length=1, max_length=32)
    amount: float = Field(..., gt=0)
    memo: Optional[str] = None

class OrderOut(OrderIn):
    id: int

class ExpenseIn(BaseModel):
    date: date
    category: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., gt=0)
    note: Optional[str] = None

class ExpenseOut(ExpenseIn):
    id: int

class PageOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]

class KPIOut(BaseModel):
    morning: float
    evening: float
    expense: float
    total: float
    net: float
    period_label: str

# ------------------------------
# 依賴：DB session
# ------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# 健康 / 根 / 登入
# ------------------------------
@app.get("/healthz")
def healthz():
    return {"ok": True, "version": APP_VERSION, "db": DB_PATH}

@app.get("/")
def root():
    return {"service": APP_NAME, "docs": "/docs", "health": "/healthz"}

@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(payload: LoginIn):
    if verify_user(payload.code, payload.password):
        return {"access_token": create_token(payload.code)}
    raise HTTPException(401, "bad credentials")

# ------------------------------
# Orders
# ------------------------------
@app.get("/api/v1/orders", response_model=PageOut)
def list_orders(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    shift: Optional[Literal["早班", "晚班"]] = Query(None),
    q: Optional[str] = Query(None, description="單號或金額（精確）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    stmt = select(Order)
    if date_from:
        stmt = stmt.where(Order.date >= date_from)
    if date_to:
        stmt = stmt.where(Order.date <= date_to)
    if shift:
        stmt = stmt.where(Order.shift == Shift(shift))
    if q:
        like = f"%{q}%"
        cond = [Order.order_no.like(like)]
        try:
            val = float(q.replace(",", ""))
            # 金額精確比對
            cond.append(Order.amount == Decimal(str(val)))
        except Exception:
            pass
        stmt = stmt.where(or_(*cond))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Order.id.desc()).offset((page-1)*page_size).limit(page_size)).scalars().all()
    items = [{
        "id": o.id,
        "date": o.date,
        "shift": o.shift.value,
        "order_no": o.order_no,
        "amount": float(o.amount),
        "memo": o.memo,
    } for o in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}

@app.post("/api/v1/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderIn, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    o = Order(
        date=payload.date,
        shift=Shift(payload.shift),
        order_no=payload.order_no,
        amount=Decimal(str(payload.amount)),
        memo=payload.memo or None,
    )
    db.add(o); db.commit(); db.refresh(o)
    return {
        "id": o.id, "date": o.date, "shift": o.shift.value,
        "order_no": o.order_no, "amount": float(o.amount), "memo": o.memo
    }

@app.put("/api/v1/orders/{oid}", response_model=OrderOut)
def update_order(oid: int, payload: OrderIn, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "order not found")
    o.date = payload.date
    o.shift = Shift(payload.shift)
    o.order_no = payload.order_no
    o.amount = Decimal(str(payload.amount))
    o.memo = payload.memo or None
    db.commit(); db.refresh(o)
    return {
        "id": o.id, "date": o.date, "shift": o.shift.value,
        "order_no": o.order_no, "amount": float(o.amount), "memo": o.memo
    }

@app.delete("/api/v1/orders/{oid}", status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "order not found")
    db.delete(o); db.commit()
    return

# ------------------------------
# Expenses
# ------------------------------
@app.get("/api/v1/expenses", response_model=PageOut)
def list_expenses(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None, description="分類/備註或金額（精確）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    stmt = select(Expense)
    if date_from:
        stmt = stmt.where(Expense.date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.date <= date_to)
    if q:
        like = f"%{q}%"
        cond = [Expense.category.like(like), Expense.note.like(like)]
        try:
            val = float(q.replace(",", ""))
            cond.append(Expense.amount == Decimal(str(val)))
        except Exception:
            pass
        stmt = stmt.where(or_(*cond))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Expense.id.desc()).offset((page-1)*page_size).limit(page_size)).scalars().all()
    items = [{
        "id": x.id,
        "date": x.date,
        "category": x.category,
        "amount": float(x.amount),
        "note": x.note,
    } for x in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}

@app.post("/api/v1/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseIn, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    x = Expense(
        date=payload.date,
        category=payload.category,
        amount=Decimal(str(payload.amount)),
        note=payload.note or None,
    )
    db.add(x); db.commit(); db.refresh(x)
    return {
        "id": x.id, "date": x.date, "category": x.category,
        "amount": float(x.amount), "note": x.note
    }

@app.put("/api/v1/expenses/{eid}", response_model=ExpenseOut)
def update_expense(eid: int, payload: ExpenseIn, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    x = db.get(Expense, eid)
    if not x: raise HTTPException(404, "expense not found")
    x.date = payload.date
    x.category = payload.category
    x.amount = Decimal(str(payload.amount))
    x.note = payload.note or None
    db.commit(); db.refresh(x)
    return {
        "id": x.id, "date": x.date, "category": x.category,
        "amount": float(x.amount), "note": x.note
    }

@app.delete("/api/v1/expenses/{eid}", status_code=204)
def delete_expense(eid: int, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    x = db.get(Expense, eid)
    if not x: raise HTTPException(404, "expense not found")
    db.delete(x); db.commit()
    return

# ------------------------------
# 報表 / KPI
# ------------------------------
def _month_first_last(y: int, m: int):
    first = date(y, m, 1)
    if m == 12:
        last = date(y, 12, 31)
    else:
        last = date(y, m+1, 1) - timedelta(days=1)
    return first, last

def _year_first_last(y: int):
    return date(y,1,1), date(y,12,31)

@app.get("/api/v1/reports/kpi", response_model=KPIOut)
def kpi(
    mode: str = Query("day", pattern="^(day|month|year)$"),
    ref_date: date = Query(default_factory=lambda: date.today()),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    if mode == "day":
        d1 = d2 = ref_date
        label = f"期間：{ref_date:%Y-%m-%d}"
    elif mode == "month":
        d1, d2 = _month_first_last(ref_date.year, ref_date.month)
        label = f"期間：{d1:%Y-%m}"
    else:
        d1, d2 = _year_first_last(ref_date.year)
        label = f"期間：{ref_date.year} 年"

    mm = float(db.scalar(select(func.coalesce(func.sum(Order.amount),0)).where(
        and_(Order.date>=d1, Order.date<=d2, Order.shift==Shift.MORNING)
    )) or 0)
    me = float(db.scalar(select(func.coalesce(func.sum(Order.amount),0)).where(
        and_(Order.date>=d1, Order.date<=d2, Order.shift==Shift.EVENING)
    )) or 0)
    mx = float(db.scalar(select(func.coalesce(func.sum(Expense.amount),0)).where(
        and_(Expense.date>=d1, Expense.date<=d2)
    )) or 0)
    total = mm + me
    net = total - mx
    return {"morning": mm, "evening": me, "expense": mx, "total": total, "net": net, "period_label": label}

# ------------------------------
# 本機啟動
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
