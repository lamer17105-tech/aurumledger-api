# -*- coding: utf-8 -*-
"""
fix_shift_enum.py
自動尋找 SQLite 資料庫 → 備份 → 將 shift 欄位的中文/別名轉成 MORNING/EVENING。
可直接在 PyCharm 右鍵執行，或 PowerShell 執行：
  python .\scripts\fix_shift_enum.py
也可手動指定：
  python .\scripts\fix_shift_enum.py --db "C:\path\to\resto.db"
"""
import argparse, os, shutil
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, MetaData, update, text

# ---------- 幫手：判斷專案根 ----------
LIKELY_ROOT_MARKERS = {"requirements.txt", "pyproject.toml", "Pipfile", ".git", ".venv"}

def guess_project_root(here: Path) -> Path:
    p = here
    for _ in range(6):  # 最多往上 6 層
        marks = {m for m in LIKELY_ROOT_MARKERS if (p / m).exists()}
        if marks:
            return p
        p = p.parent
    # 若找不到，就回到 scripts 上一層或上上層
    return here.parents[2] if len(here.parents) >= 3 else here.parent

# ---------- 找 DB ----------
def find_db(base: Path):
    exts = {".db", ".sqlite", ".sqlite3"}
    cands = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if ".venv" in str(p):
            continue
        if p.suffix.lower() in exts and not (p.name.endswith("-wal") or p.name.endswith("-shm")):
            cands.append(p.resolve())
    if not cands:
        return None, []
    # 盡量優先選叫起來像主 DB 的
    cands.sort(key=lambda x: (
        # 名稱權重：resto / data / main 比較像主 DB
        0 if any(k in x.name.lower() for k in ("resto", "data", "main")) else 1,
        -x.stat().st_mtime,  # 新→舊
        -x.stat().st_size    # 大→小
    ))
    return cands[0], cands

# ---------- 備份 ----------
def backup_db(db: Path):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db.with_suffix(db.suffix + f".bak.{ts}")
    shutil.copy2(db, bak)
    for ext in (db.name + "-wal", db.name + "-shm"):
        p = db.with_name(ext)
        if p.exists():
            shutil.copy2(p, p.with_name(p.name + f".bak.{ts}"))
    print(f"[i] 已備份 → {bak}")

# ---------- 正規化 shift ----------
def normalize(db: Path):
    engine = create_engine(f"sqlite:///{db.as_posix()}", future=True)
    meta = MetaData()
    meta.reflect(bind=engine)

    FIX = {
        "早班":"MORNING","上午":"MORNING","am":"MORNING","AM":"MORNING","morning":"MORNING",
        "晚班":"EVENING","夜班":"EVENING","下午":"EVENING","pm":"EVENING","PM":"EVENING","evening":"EVENING",
    }
    ALLOWED = {"MORNING","EVENING"}

    touched = []
    with engine.begin() as conn:
        for tbl in meta.tables.values():
            cols = [c.name for c in tbl.columns]
            if "shift" not in cols:
                continue
            # 先去空白、轉大寫
            conn.execute(text(f"UPDATE {tbl.name} SET shift=UPPER(TRIM(shift)) WHERE shift IS NOT NULL"))
            # 中文/別名 → 標準碼
            for k, v in FIX.items():
                conn.execute(update(tbl).where(text("shift = :k")).values(shift=v), {"k": k.upper()})
            stats = dict(conn.execute(text(f"SELECT shift, COUNT(*) FROM {tbl.name} GROUP BY shift")).all())
            print(f"[i] {tbl.name} 現況：{stats}")
            unknown = [k for k in stats.keys() if k and k not in ALLOWED]
            if unknown:
                print(f"[!] 非標準值仍存在：{unknown}")
            touched.append(tbl.name)
    print(f"[✓] 已處理表：{touched}")

# ---------- 入口 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="SQLite 檔完整路徑（可選）")
    args = ap.parse_args()

    here = Path(__file__).resolve()
    root = guess_project_root(here)
    print(f"[i] 專案根：{root}")

    if args.db:
        db = Path(args.db).resolve()
        if not db.exists():
            raise SystemExit(f"DB 不存在：{db}")
    else:
        db, allc = find_db(root)
        if not db:
            raise SystemExit("找不到任何 .db/.sqlite/.sqlite3；請用 --db 指定路徑。")
        print("[i] 候選 DB（前幾筆）：")
        for q in allc[:10]:
            try:
                print("   -", q, f"(mtime={datetime.fromtimestamp(q.stat().st_mtime)}, size={q.stat().st_size})")
            except Exception:
                print("   -", q)
    print(f"[i] 使用 DB：{db}")

    # 要求你先關掉 GUI，避免 DB 被鎖
    backup_db(db)
    normalize(db)
    print("[✓] 完成。請重新啟動 GUI 測試。")

if __name__ == "__main__":
    from datetime import datetime
    main()
