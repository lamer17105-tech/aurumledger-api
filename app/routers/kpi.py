# -*- coding: utf-8 -*-
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import func, and_
from ..utils.db import SessionLocal
from ..models import Order, Expense, Shift
from ..security import require_revenue_token

router = APIRouter(prefix="/kpi", tags=["kpi"])

@router.get("/day")
def kpi_day(d: date, _rev: dict = Depends(require_revenue_token)):
    with SessionLocal() as s:
        mm = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.date==d, Order.shift==Shift.MORNING).scalar() or 0
        me = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.date==d, Order.shift==Shift.EVENING).scalar() or 0
        mx = s.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.date==d).scalar() or 0
    total = float(mm) + float(me)
    net = total - float(mx)
    return {"morning": float(mm), "evening": float(me), "expense": float(mx), "total": total, "net": net}

def _month_first_last(y: int, m: int):
    from datetime import date, timedelta
    first = date(y, m, 1)
    if m == 12:
        last = date(y+1, 1, 1) - timedelta(days=1)
    else:
        last = date(y, m+1, 1) - timedelta(days=1)
    return first, last

@router.get("/month")
def kpi_month(y: int, m: int, _rev: dict = Depends(require_revenue_token)):
    first, last = _month_first_last(y, m)
    with SessionLocal() as s:
        mm = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date>=first, Order.date<=last, Order.shift==Shift.MORNING)).scalar() or 0
        me = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date>=first, Order.date<=last, Order.shift==Shift.EVENING)).scalar() or 0
        mx = s.query(func.coalesce(func.sum(Expense.amount), 0)).filter(and_(Expense.date>=first, Expense.date<=last)).scalar() or 0
    total = float(mm) + float(me)
    net = total - float(mx)
    return {"morning": float(mm), "evening": float(me), "expense": float(mx), "total": total, "net": net}

@router.get("/year")
def kpi_year(y: int, _rev: dict = Depends(require_revenue_token)):
    first, last = date(y,1,1), date(y,12,31)
    with SessionLocal() as s:
        mm = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date>=first, Order.date<=last, Order.shift==Shift.MORNING)).scalar() or 0
        me = s.query(func.coalesce(func.sum(Order.amount), 0)).filter(and_(Order.date>=first, Order.date<=last, Order.shift==Shift.EVENING)).scalar() or 0
        mx = s.query(func.coalesce(func.sum(Expense.amount), 0)).filter(and_(Expense.date>=first, Expense.date<=last)).scalar() or 0
    total = float(mm) + float(me)
    net = total - float(mx)
    return {"morning": float(mm), "evening": float(me), "expense": float(mx), "total": total, "net": net}
