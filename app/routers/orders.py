from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import or_, func, select, and_
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import login_required
from ..models import Order

router = APIRouter(prefix="/api/orders", tags=["orders"], dependencies=[Depends(login_required)])

def _to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "date": o.date.isoformat() if o.date else None,
        "customer": o.customer,
        "total": float(o.total) if o.total is not None else 0.0,
        "status": o.status,
        "notes": o.notes or "",
    }

@router.get("", response_model=List[dict])
def list_orders(
    q: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default="desc"),  # desc|asc by date
    db: Session = Depends(get_db),
):
    stmt = select(Order)
    conds = []
    if q:
        qs = q.strip().lower()
        conds.append(or_(func.lower(Order.order_no).contains(qs), func.lower(Order.customer).contains(qs)))
    if date_from:
        try:
            conds.append(Order.date >= date.fromisoformat(date_from))
        except Exception:
            pass
    if date_to:
        try:
            conds.append(Order.date <= date.fromisoformat(date_to))
        except Exception:
            pass
    if status:
        conds.append(func.lower(Order.status) == status.lower())
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(Order.date.desc() if sort != "asc" else Order.date.asc(), Order.id.desc())
    rows = db.execute(stmt).scalars().all()
    return [_to_dict(o) for o in rows]

@router.post("", response_model=dict)
def create_order(payload: dict = Body(...), db: Session = Depends(get_db)):
    required = ["order_no", "date", "total"]
    miss = [k for k in required if not payload.get(k)]
    if miss:
        raise HTTPException(400, f"缺少欄位：{miss}")
    try:
        total = Decimal(str(payload.get("total", "0")))
    except (InvalidOperation, TypeError):
        raise HTTPException(400, "金額格式錯誤")
    o = Order(
        order_no=str(payload["order_no"]),
        date=date.fromisoformat(payload["date"]),
        customer=payload.get("customer"),
        total=total,
        status=payload.get("status") or "open",
        notes=payload.get("notes"),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_dict(o)

@router.put("/{oid}", response_model=dict)
def update_order(oid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "找不到訂單")
    if "order_no" in payload and payload["order_no"]:
        o.order_no = str(payload["order_no"])
    if "date" in payload and payload["date"]:
        o.date = date.fromisoformat(payload["date"])
    if "customer" in payload:
        o.customer = payload["customer"]
    if "total" in payload:
        try:
            o.total = Decimal(str(payload["total"]))
        except (InvalidOperation, TypeError):
            raise HTTPException(400, "金額格式錯誤")
    if "status" in payload:
        o.status = payload["status"]
    if "notes" in payload:
        o.notes = payload["notes"]
    db.commit()
    db.refresh(o)
    return _to_dict(o)

@router.delete("/{oid}", response_model=dict)
def delete_order(oid: int, db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "找不到訂單")
    db.delete(o)
    db.commit()
    return {"ok": True}

@router.delete("", response_model=dict)
def delete_orders_batch(ids: List[int] = Body(..., embed=True), db: Session = Depends(get_db)):
    if not ids:
        return {"deleted": 0}
    q = db.query(Order).filter(Order.id.in_(ids))
    count = q.count()
    q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}