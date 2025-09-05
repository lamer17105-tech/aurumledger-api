PythonProject10/
├─ app/
│  ├─ __init__.py
│  ├─ main.py                ← FastAPI 入口＋掛載 /ui
│  ├─ routers/
│  │  ├─ __init__.py
│  │  └─ biz.py              ← 訂單 API（CRUD + KPI 部分）
│  └─ utils/
│     ├─ __init__.py
│     ├─ config.py           ← APP_NAME / 版號 / CORS
│     ├─ db.py               ← SQLAlchemy 連線＋init_db
│     └─ models.py           ← Order / Expense / Shift
└─ web/
   └─ index.html             ← 前端單頁（/ui/）
