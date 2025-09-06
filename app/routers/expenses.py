from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import or_, func, select, and_
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import login_required
from ..models import Expense

router = APIRouter(prefix="/api/expenses", tags=["expenses"], dependencies=[Depends(login_required)])

def _to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "date": e.date.isoformat() if e.date else None,
        "category": e.category,
        "amount": float(e.amount) if e.amount is not None else 0.0,
        "owner": e.owner,
        "note": e.note or "",
    }

@router.get("", response_model=List[dict])
def list_expenses(
    q: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default="desc"),
    db: Session = Depends(get_db),
):
    stmt = select(Expense)
    conds = []
    if q:
        qs = q.strip().lower()
        conds.append(or_(func.lower(Expense.category).contains(qs), func.lower(func.coalesce(Expense.owner, "")).contains(qs), func.lower(func.coalesce(Expense.note, "")).contains(qs)))
    if date_from:
        try: conds.append(Expense.date >= date.fromisoformat(date_from))
        except Exception: pass
    if date_to:
        try: conds.append(Expense.date <= date.fromisoformat(date_to))
        except Exception: pass
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(Expense.date.desc() if sort != "asc" else Expense.date.asc(), Expense.id.desc())
    rows = db.execute(stmt).scalars().all()
    return [_to_dict(e) for e in rows]

@router.post("", response_model=dict)
def create_expense(payload: dict = Body(...), db: Session = Depends(get_db)):
    required = ["date", "category", "amount"]
    miss = [k for k in required if not payload.get(k)]
    if miss:
        raise HTTPException(400, f"缺少欄位：{miss}")
    try:
        amount = Decimal(str(payload.get("amount", "0")))
    except (InvalidOperation, TypeError):
        raise HTTPException(400, "金額格式錯誤")
    e = Expense(
        date=date.fromisoformat(payload["date"]),
        category=payload["category"],
        amount=amount,
        owner=payload.get("owner"),
        note=payload.get("note"),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _to_dict(e)

@router.put("/{eid}", response_model=dict)
def update_expense(eid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    e = db.get(Expense, eid)
    if not e:
        raise HTTPException(404, "找不到支出")
    if "date" in payload and payload["date"]:
        e.date = date.fromisoformat(payload["date"])
    if "category" in payload:
        e.category = payload["category"]
    if "amount" in payload:
        try: e.amount = Decimal(str(payload["amount"]))
        except (InvalidOperation, TypeError): raise HTTPException(400, "金額格式錯誤")
    if "owner" in payload:
        e.owner = payload["owner"]
    if "note" in payload:
        e.note = payload["note"]
    db.commit(); db.refresh(e)
    return _to_dict(e)

@router.delete("/{eid}", response_model=dict)
def delete_expense(eid: int, db: Session = Depends(get_db)):
    e = db.get(Expense, eid)
    if not e:
        raise HTTPException(404, "找不到支出")
    db.delete(e); db.commit()
    return {"ok": True}

@router.delete("", response_model=dict)
def delete_expenses_batch(ids: List[int] = Body(..., embed=True), db: Session = Depends(get_db)):
    if not ids:
        return {"deleted": 0}
    q = db.query(Expense).filter(Expense.id.in_(ids))
    count = q.count()
    q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}