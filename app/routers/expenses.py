# -*- coding: utf-8 -*-
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import asc, and_, or_
from ..utils.db import SessionLocal
from ..models import Expense
from ..security import get_current_token

router = APIRouter(prefix="/expenses", tags=["expenses"])

class ExpenseIn(BaseModel):
    date: date
    category: str
    amount: Decimal
    note: str | None = None

@router.get("")
def list_expenses(d1: date, d2: date, q: str | None = None, _tok: dict = Depends(get_current_token)):
    if d1 > d2: d1, d2 = d2, d1
    with SessionLocal() as s:
        if not q:
            rs = s.query(Expense).filter(and_(Expense.date>=d1, Expense.date<=d2)).order_by(asc(Expense.date), asc(Expense.id)).all()
        else:
            like = f"%{q}%"
            cond = [and_(Expense.date>=d1, Expense.date<=d2),
                    or_(Expense.category.like(like), Expense.note.like(like))]
            try:
                v = float(q.replace(",",""))
                cond = [and_(Expense.date>=d1, Expense.date<=d2),
                        or_(Expense.category.like(like), Expense.note.like(like), Expense.amount==v)]
            except:
                pass
            rs = s.query(Expense).filter(and_(*cond)).order_by(asc(Expense.date), asc(Expense.id)).all()
        return [
            {"id": e.id, "date": e.date.isoformat(), "category": e.category,
             "amount": float(e.amount), "note": e.note}
            for e in rs
        ]

@router.post("")
def add_expense(d: ExpenseIn, _tok: dict = Depends(get_current_token)):
    with SessionLocal() as s:
        x = Expense(date=d.date, category=d.category, amount=d.amount, note=d.note)
        s.add(x); s.commit()
        return {"id": x.id}

@router.delete("/{eid}")
def delete_expense(eid: int, _tok: dict = Depends(get_current_token)):
    with SessionLocal() as s:
        x = s.get(Expense, eid)
        if not x: return {"ok": True}
        s.delete(x); s.commit()
    return {"ok": True}
