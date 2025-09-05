# -*- coding: utf-8 -*-
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import asc, and_, or_
from ..utils.db import SessionLocal
from ..models import Order, Shift
from ..security import get_current_token

router = APIRouter(prefix="/orders", tags=["orders"])

class OrderIn(BaseModel):
    date: date
    shift: str
    order_no: str
    amount: Decimal
    memo: str | None = None

@router.get("")
def list_orders(d: date, q: str | None = None, _tok: dict = Depends(get_current_token)):
    with SessionLocal() as s:
        if not q:
            rs = s.query(Order).filter(Order.date==d).order_by(asc(Order.id)).all()
        else:
            like = f"%{q}%"
            cond = [Order.date==d, Order.order_no.like(like)]
            try:
                v = float(q.replace(",", ""))
                cond = [Order.date==d, or_(Order.order_no.like(like), Order.amount==v)]
            except:
                pass
            rs = s.query(Order).filter(and_(*cond)).order_by(asc(Order.id)).all()
        return [
            {"id": o.id, "date": o.date.isoformat(), "shift": o.shift.value,
             "order_no": o.order_no, "amount": float(o.amount), "memo": o.memo}
            for o in rs
        ]

@router.post("")
def add_order(d: OrderIn, _tok: dict = Depends(get_current_token)):
    if d.shift not in (Shift.MORNING.value, Shift.EVENING.value):
        raise HTTPException(400, "shift 無效")
    with SessionLocal() as s:
        o = Order(date=d.date, shift=Shift(d.shift), order_no=d.order_no, amount=d.amount, memo=d.memo)
        s.add(o); s.commit()
        return {"id": o.id}

class OrderPatch(BaseModel):
    order_no: str | None = None
    amount: Decimal | None = None
    memo: str | None = None

@router.patch("/{oid}")
def patch_order(oid: int, d: OrderPatch, _tok: dict = Depends(get_current_token)):
    with SessionLocal() as s:
        o = s.get(Order, oid)
        if not o: raise HTTPException(404, "not found")
        if d.order_no is not None: o.order_no = d.order_no
        if d.amount is not None: o.amount = d.amount
        if d.memo is not None: o.memo = d.memo
        s.commit()
    return {"ok": True}

@router.delete("/{oid}")
def delete_order(oid: int, _tok: dict = Depends(get_current_token)):
    with SessionLocal() as s:
        o = s.get(Order, oid)
        if not o: return {"ok": True}
        s.delete(o); s.commit()
    return {"ok": True}
