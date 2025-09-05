# api.py — AurumLedger API（支援 DATABASE_URL / 首頁導向 / pydantic v2 / WAL 等）
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Literal, Tuple, Annotated
from contextlib import asynccontextmanager
import calendar
import enum, json, os, base64, hashlib, hmac, logging

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from starlette.requests import Request

from pydantic import BaseModel, Field, field_validator, field_serializer

from sqlalchemy import (
    create_engine, Column, Integer, String, Date, Enum as SAEnum, Numeric, Text,
    func, and_, or_, asc
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy import event

# ================= DB & ORM（支援 DATABASE_URL，否則用 SQLite+WAL） =================
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # 例如：postgresql+psycopg://user:pass@host:5432/dbname
    engine = create_engine(
        DATABASE_URL,
        future=True,
        echo=False,
        pool_pre_ping=True,
    )
else:
    DB_PATH = os.getenv("RESTO_DB", "resto.db")
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        future=True,
        echo=False,
        connect_args={"check_same_thread": False},  # 多執行緒安全
        pool_pre_ping=True,
    )
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.close()

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

def init_db():
    Base.metadata.create_all(engine)

# ================= Auth（沿用 auth.json） =================
AUTH_FILE = os.getenv("AUTH_FILE", "/data/auth.json" if DATABASE_URL=="" else "auth.json")
PEPPER    = os.getenv("AL_PEPPER", "")  # 部署時請設置

def _safe_read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _verify_password(pw: str, salt_b64: str, hash_b64: str) -> bool:
    try:
        salt   = base64.b64decode(salt_b64.encode())
        target = base64.b64decode(hash_b64.encode())
    except Exception:
        return False
    raw = (pw + PEPPER).encode()
    dk  = hashlib.pbkdf2_hmac("sha256", raw, salt, 200_000)
    return hmac.compare_digest(dk, target)

def verify_account(code: str, pw: str) -> bool:
    d=_safe_read_json(AUTH_FILE) or {}
    u=d.get("user",{})
    return (u.get("code")== (code or "").strip()) and _verify_password(pw or "", u.get("salt",""), u.get("hash",""))

# ================= Util =================
def month_first_last(y:int,m:int):
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last_day)

def year_first_last(y:int):
    return date(y,1,1), date(y,12,31)

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================= Schemas（pydantic v2） =================
class OrderIn(BaseModel):
    date: date
    shift: Literal["早班","晚班"]
    order_no: str = Field(min_length=1, max_length=32)
    amount: Decimal
    memo: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def pos_amount(cls, v: Decimal):
        if v is None or v <= 0:
            raise ValueError("amount must be > 0")
        return v

class OrderOut(BaseModel):
    id: int
    date: date
    shift: str
    order_no: str
    amount: Decimal
    memo: Optional[str] = None
    class Config:
        from_attributes = True

    @field_serializer("amount")
    def ser_amount(self, v: Decimal):
        return float(v)

class ExpenseIn(BaseModel):
    date: date
    category: str
    amount: Decimal
    note: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def pos_amount(cls, v: Decimal):
        if v is None or v <= 0:
            raise ValueError("amount must be > 0")
        return v

class ExpenseOut(BaseModel):
    id: int
    date: date
    category: str
    amount: Decimal
    note: Optional[str] = None
    class Config:
        from_attributes = True

    @field_serializer("amount")
    def ser_amount(self, v: Decimal):
        return float(v)

class KPIOut(BaseModel):
    morning: float
    evening: float
    expense: float
    total: float
    net: float
    period_label: str

# ================= FastAPI（lifespan） =================
security = HTTPBasic()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="AurumLedger API", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 上線請改為你的網域清單
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
    allow_headers=["Authorization","Content-Type"],
)

def require_auth(cred: HTTPBasicCredentials = Depends(security)):
    if not verify_account(cred.username, cred.password):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return cred.username

# ================= 全域錯誤處理 =================
log = logging.getLogger("uvicorn.error")

@app.exception_handler(Exception)
async def unhandled_exc(request: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

# ================= 首頁導向 /docs =================
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

# ================= Routes =================
@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(func.count().select())
        return {"ok": True, "db": "up", "driver": "postgres" if DATABASE_URL else "sqlite"}
    except Exception:
        return {"ok": False, "db": "down"}

@app.get("/me")
def whoami(user=Depends(require_auth)):
    return {"code": user}

# ---- Orders ----
@app.get("/orders", response_model=List[OrderOut])
def list_orders(
    on: Optional[date] = Query(None, description="若給定，只取該日"),
    q: Optional[str] = Query(None, description="模糊搜尋 order_no 或金額"),
    sort: Literal["date","id","amount","order_no"] = "date",
    order: Literal["asc","desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db), user=Depends(require_auth)
):
    query = db.query(Order)
    if on:
        query = query.filter(Order.date == on)
    if q:
        like = f"%{q}%"
        cond = [Order.order_no.like(like)]
        try:
            v = float(str(q).replace(",",""))
            cond.append(Order.amount == v)
        except:
            pass
        query = query.filter(or_(*cond))
    colmap = {"date": Order.date, "id": Order.id, "amount": Order.amount, "order_no": Order.order_no}
    col = colmap[sort]
    query = query.order_by(asc(col) if order=="asc" else col.desc()).limit(limit).offset(offset)
    return query.all()

@app.post("/orders", response_model=OrderOut, status_code=201)
def add_order(data: OrderIn, db: Session = Depends(get_db), user=Depends(require_auth)):
    obj = Order(date=data.date, shift=Shift(data.shift), order_no=data.order_no, amount=data.amount, memo=data.memo)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.put("/orders/{oid}", response_model=OrderOut)
def update_order(oid: int, data: OrderIn, db: Session = Depends(get_db), user=Depends(require_auth)):
    obj = db.get(Order, oid)
    if not obj: raise HTTPException(404, "order not found")
    obj.date = data.date
    obj.shift = Shift(data.shift)
    obj.order_no = data.order_no
    obj.amount = data.amount
    obj.memo = data.memo
    db.commit(); db.refresh(obj)
    return obj

@app.delete("/orders/{oid}", status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), user=Depends(require_auth)):
    obj = db.get(Order, oid)
    if obj:
        db.delete(obj); db.commit()
    return

# ---- Expenses ----
@app.get("/expenses", response_model=List[ExpenseOut])
def list_expenses(
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    q: Optional[str] = Query(None, description="模糊搜尋 category/note 或金額"),
    sort: Literal["date","id","amount","category"] = "date",
    order: Literal["asc","desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db), user=Depends(require_auth)
):
    query = db.query(Expense)
    if start and end:
        d1, d2 = (start, end) if start <= end else (end, start)
        query = query.filter(and_(Expense.date>=d1, Expense.date<=d2))
    if q:
        like = f"%{q}%"
        cond = [Expense.category.like(like), Expense.note.like(like)]
        try:
            v = float(str(q).replace(",",""))
            cond.append(Expense.amount == v)
        except:
            pass
        query = query.filter(or_(*cond))
    colmap = {"date": Expense.date, "id": Expense.id, "amount": Expense.amount, "category": Expense.category}
    col = colmap[sort]
    query = query.order_by(asc(col) if order=="asc" else col.desc()).limit(limit).offset(offset)
    return query.all()

@app.post("/expenses", response_model=ExpenseOut, status_code=201)
def add_expense(data: ExpenseIn, db: Session = Depends(get_db), user=Depends(require_auth)):
    obj = Expense(date=data.date, category=data.category, amount=data.amount, note=data.note)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.delete("/expenses/{eid}", status_code=204)
def delete_expense(eid: int, db: Session = Depends(get_db), user=Depends(require_auth)):
    obj = db.get(Expense, eid)
    if obj:
        db.delete(obj); db.commit()
    return

# ---- KPI / 報表 ----
def _parse_range(mode: Optional[str], ref: Optional[str]) -> Tuple[date,date,str]:
    today = date.today()
    m = (mode or "day").lower()
    if m == "day":
        d = datetime.strptime(ref, "%Y-%m-%d").date() if ref else today
        return d, d, d.strftime("%Y-%m-%d")
    if m == "month":
        if ref:
            y, mm = [int(x) for x in ref.split("-")]
        else:
            y, mm = today.year, today.month
        f,l = month_first_last(y,mm)
        return f,l, f.strftime("%Y-%m")
    if m == "year":
        y = int(ref) if ref else today.year
        f,l = year_first_last(y)
        return f,l, f"{y} 年"
    raise HTTPException(400, "mode must be one of: day, month, year")

class KPIOut(BaseModel):
    morning: float
    evening: float
    expense: float
    total: float
    net: float
    period_label: str

@app.get("/kpi", response_model=KPIOut)
def kpi(
    mode: Literal["day","month","year"] = Query("day"),
    ref: Optional[str] = Query(None, description="day=YYYY-MM-DD, month=YYYY-MM, year=YYYY"),
    db: Session = Depends(get_db), user=Depends(require_auth)
):
    d1, d2, label = _parse_range(mode, ref)
    mm = db.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=d1, Order.date<=d2, Order.shift==Shift.MORNING)).scalar() or 0
    me = db.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=d1, Order.date<=d2, Order.shift==Shift.EVENING)).scalar() or 0
    ex = db.query(func.coalesce(func.sum(Expense.amount),0)).filter(and_(Expense.date>=d1, Expense.date<=d2)).scalar() or 0
    total = float(mm) + float(me)
    net = total - float(ex)
    return KPIOut(
        morning=float(mm), evening=float(me), expense=float(ex),
        total=total, net=net, period_label=label
    )

@app.get("/reports/revenue")
def revenue_report(
    start: date = Query(...), end: date = Query(...),
    db: Session = Depends(get_db), user=Depends(require_auth)
):
    d1, d2 = (start, end) if start <= end else (end, start)
    ords = db.query(Order.date, Order.shift, func.sum(Order.amount)).filter(and_(Order.date>=d1, Order.date<=d2)).group_by(Order.date, Order.shift).all()
    exps = db.query(Expense.date, func.sum(Expense.amount)).filter(and_(Expense.date>=d1, Expense.date<=d2)).group_by(Expense.date).all()
    o_map, x_map, dates = {}, {}, set()
    for d,sh,sumv in ords:
        dates.add(d)
        o_map.setdefault(d, {Shift.MORNING:0.0, Shift.EVENING:0.0})[sh] = float(sumv or 0)
    for d,sv in exps:
        dates.add(d); x_map[d] = float(sv or 0)
    out = []
    for d in sorted(dates):
        mm = o_map.get(d,{}).get(Shift.MORNING,0.0)
        me = o_map.get(d,{}).get(Shift.EVENING,0.0)
        tot = mm + me
        x = x_map.get(d, 0.0)
        out.append({
            "date": d.isoformat(),
            "morning": round(mm,2),
            "evening": round(me,2),
            "total": round(tot,2),
            "expense": round(x,2),
            "profit": round(tot - x,2),
        })
    return out
