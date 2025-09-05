# app/routers/biz.py
from datetime import datetime, date
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, asc

from ..utils.db import get_db, Order, Expense, Shift

router = APIRouter(prefix="/api", tags=["biz"])

# Pydantic 輸入/輸出
class OrderOut(BaseModel):
    id: int
    date: date
    shift: str
    order_no: str
    amount: float
    memo: Optional[str] = None

class OrderIn(BaseModel):
    date: date
    shift: Literal["早班", "晚班"]
    order_no: str = Field(min_length=1)
    amount: float = Field(gt=0)
    memo: Optional[str] = None

def _parse_day(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="date 需為 YYYY-MM-DD")

@router.get("/orders", response_model=List[OrderOut])
def list_orders(
    date_str: str = Query(..., alias="date"),
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    d = _parse_day(date_str)
    qset = db.query(Order).filter(Order.date == d)
    if q:
        like = f"%{q}%"
        # 金額搜尋（純數字時）
        cond = [Order.order_no.like(like)]
        try:
            val = float(q.replace(",", ""))
            cond.append(Order.amount == val)
        except Exception:
            pass
        qset = qset.filter(or_(*cond))
    rows = qset.order_by(asc(Order.id)).all()
    return [
        OrderOut(
            id=o.id, date=o.date, shift=o.shift.value, order_no=o.order_no,
            amount=float(o.amount), memo=o.memo
        )
        for o in rows
    ]

@router.post("/orders", response_model=OrderOut)
def create_order(payload: OrderIn, db: Session = Depends(get_db)):
    obj = Order(
        date=payload.date,
        shift=Shift.MORNING if payload.shift == "早班" else Shift.EVENING,
        order_no=payload.order_no,
        amount=payload.amount,
        memo=payload.memo,
    )
    db.add(obj); db.commit(); db.refresh(obj)
    return OrderOut(
        id=obj.id, date=obj.date, shift=obj.shift.value,
        order_no=obj.order_no, amount=float(obj.amount), memo=obj.memo
    )

@router.delete("/orders/{oid}")
def delete_order(oid: int, db: Session = Depends(get_db)):
    obj = db.get(Order, oid)
    if not obj:
        raise HTTPException(status_code=404, detail="訂單不存在")
    db.delete(obj); db.commit()
    return {"ok": True}

@router.get("/kpi/day")
def kpi_day(date_str: str = Query(..., alias="date"), db: Session = Depends(get_db)):
    d = _parse_day(date_str)
    mm = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date == d, Order.shift == Shift.MORNING)).scalar() or 0
    me = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date == d, Order.shift == Shift.EVENING)).scalar() or 0
    mx = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.date == d).scalar() or 0
    total = float(mm) + float(me)
    return {
        "morning": float(mm),
        "evening": float(me),
        "expense": float(mx),
        "total": total,
        "net": total - float(mx),
    }
