import io, csv
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from .db import get_db
from .auth import login_required

router = APIRouter(prefix="/data", tags=["data"])

ALLOWED_TABLES = {"orders", "expenses"}

def _validate_table(inspector, name: str):
    tables = {t.lower() for t in inspector.get_table_names()}
    if name.lower() not in tables or name.lower() not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"不支援的資料表：{name}")

@router.get("/export/{table}")
def export_csv(table: str, db: Session = Depends(get_db), _=Depends(login_required)):
    insp = inspect(db.bind)
    _validate_table(insp, table)
    cols = [c["name"] for c in insp.get_columns(table)]
    q = db.execute(text(f"SELECT {', '.join([f'\"{c}\"' for c in cols])} FROM \"{table}\""))
    rows = q.mappings().all()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r[k] for k in cols})
    buf.seek(0)
    filename = f"{table}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(iter([buf.read()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.post("/import/{table}")
async def import_csv(table: str, file: UploadFile, db: Session = Depends(get_db), _=Depends(login_required)):
    insp = inspect(db.bind)
    _validate_table(insp, table)
    cols = [c["name"] for c in insp.get_columns(table)]

    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    missing = [c for c in cols if c not in reader.fieldnames]
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV 欄位缺少：{missing}")

    records = [{c: row.get(c) for c in cols} for row in reader]
    if not records:
        return {"inserted": 0}

    col_list = ", ".join([f'"{c}"' for c in cols])
    val_list = ", ".join([f':{c}' for c in cols])
    db.execute(text(f'INSERT INTO "{table}" ({col_list}) VALUES ({val_list})'), records)
    db.commit()
    return {"inserted": len(records)}