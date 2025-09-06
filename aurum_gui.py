# -*- coding: utf-8 -*-
# AurumLedger 企業版｜餐飲作帳系統（修正版：Shift 以代碼 MORNING/EVENING 存DB；開機自動正規化）
# 強化點：
# 1) 啟動時備份並把 DB 內「早班/晚班/AM/PM…」自動轉為 MORNING/EVENING（避免 Enum 炸掉）
# 2) 模型改為嚴格 Enum（validate_strings=True），並在寫入前自動把中文轉代碼
# 3) 介面顯示中文；DB 一律存代碼；查詢用 Enum

import os, sys, json, base64, hashlib, hmac, enum, csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

# ====== 啟動旗標 ======
USE_MARBLE = False     # 先關掉大理石背景；確認可正常運作後可改 True
SAFE_THEME  = True     # 簡潔高對比主題
LOG_FILE    = "error.log"

# --- 全域例外攔截：視窗提示 + 寫入 error.log ---
def _exception_hook(exctype, value, tb):
    import traceback, io
    buf = io.StringIO()
    traceback.print_exception(exctype, value, tb, file=buf)
    msg = buf.getvalue()
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "未預期錯誤", (msg[:2000] + ("\n...（更完整內容見 error.log）" if len(msg)>2000 else "")))
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)

import sys as _sys
_sys.excepthook = _exception_hook

# ====== 相容性：SQLAlchemy declarative_base 新/舊版相容 ======
try:
    from sqlalchemy.orm import declarative_base
except Exception:
    from sqlalchemy.ext.declarative import declarative_base

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
    QAbstractItemView, QHeaderView, QDialog, QFormLayout, QDialogButtonBox, QSpacerItem,
    QSizePolicy, QFileDialog, QCheckBox, QFrame, QListWidget, QTextEdit,
    QStackedWidget, QButtonGroup
)
from PySide6.QtGui import QPalette, QColor, QBrush, QPixmap, QTransform, QFont
from PySide6.QtCore import Qt, QDate, Signal, QTimer

from sqlalchemy import (
    create_engine, Column, Integer, String, Date, Enum as SAEnum, Numeric, Text,
    func, asc, and_, or_, event, MetaData, text, update
)
from sqlalchemy.orm import sessionmaker

# ====================== 啟動健檢 ======================
def preflight_checks():
    msgs = []
    msgs.append(f"Python: {sys.version.split()[0]}  | 平台: {sys.platform}")
    try:
        with open("_write_test.tmp", "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove("_write_test.tmp")
        msgs.append("寫入權限：OK")
    except Exception as e:
        msgs.append(f"寫入權限：失敗 ({e})")
    try:
        import PySide6
        msgs.append(f"PySide6：{getattr(PySide6,'__version__','unknown')}")
    except Exception as e:
        msgs.append(f"PySide6 載入失敗：{e}")
    try:
        import sqlalchemy
        msgs.append(f"SQLAlchemy：{getattr(sqlalchemy,'__version__','unknown')}")
    except Exception as e:
        msgs.append(f"SQLAlchemy 載入失敗：{e}")
    return "\n".join(msgs)

# ====================== 資料庫（啟動修復） ======================
DB_PATH = os.getenv("RESTO_DB", "resto.db")
DB_PATH = os.path.abspath(DB_PATH)

def _backup_sqlite(db_path: str):
    import shutil, datetime
    if not os.path.exists(db_path):
        return
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db_path + f".bak.{ts}"
    try:
        shutil.copy2(db_path, bak)
        for ext in (db_path + "-wal", db_path + "-shm"):
            if os.path.exists(ext):
                shutil.copy2(ext, ext + f".bak.{ts}")
        print(f"[BOOT] DB 已備份 → {bak}")
    except Exception as e:
        print(f"[BOOT] 備份失敗：{e}")

def _normalize_shift_values(db_path: str):
    """把 早班/晚班/AM/PM… 轉為 MORNING/EVENING；在 ORM 建立前執行"""
    if not os.path.exists(db_path):
        return
    tmp_engine = create_engine(f"sqlite:///{db_path}", future=True)
    meta = MetaData()
    meta.reflect(bind=tmp_engine)
    FIX = {
        "早班":"MORNING","上午":"MORNING","am":"MORNING","AM":"MORNING","morning":"MORNING",
        "晚班":"EVENING","夜班":"EVENING","下午":"EVENING","pm":"EVENING","PM":"EVENING","evening":"EVENING",
    }
    with tmp_engine.begin() as conn:
        for tbl in meta.tables.values():
            cols = {c.name.lower() for c in tbl.columns}
            if "shift" not in cols:
                continue
            conn.execute(text(f"UPDATE {tbl.name} SET shift=UPPER(TRIM(shift)) WHERE shift IS NOT NULL"))
            for k, v in FIX.items():
                conn.execute(text(f"UPDATE {tbl.name} SET shift=:v WHERE shift=:k"),
                             {"v": v, "k": k.upper()})
            rows = conn.execute(text(f"SELECT shift, COUNT(*) FROM {tbl.name} GROUP BY shift")).all()
            print(f"[BOOT] {tbl.name} shift 分布：{dict(rows)}")
    tmp_engine.dispose()

# 執行一次性資料修復
if os.path.exists(DB_PATH):
    _backup_sqlite(DB_PATH)
    _normalize_shift_values(DB_PATH)
else:
    print(f"[BOOT] 尚未找到資料庫，稍後 create_all() 會建立：{DB_PATH}")

# 建立正式 engine / Session
try:
    engine = create_engine(f"sqlite:///{DB_PATH}", future=True, echo=False)
except Exception as e:
    raise RuntimeError(f"資料庫引擎建立失敗：{e}")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

# ===== Shift 代碼/標籤對照（DB 存代碼、UI 顯示中文）=====
class ShiftEnum(str, enum.Enum):
    MORNING = "MORNING"
    EVENING = "EVENING"

SHIFT_CODE_LABEL = {"MORNING": "早班", "EVENING": "晚班"}
LABEL2CODE = {
    "早班":"MORNING","上午":"MORNING","am":"MORNING","AM":"MORNING","morning":"MORNING",
    "晚班":"EVENING","夜班":"EVENING","下午":"EVENING","pm":"EVENING","PM":"EVENING","evening":"EVENING"
}
def shift_label(code:str) -> str:
    return SHIFT_CODE_LABEL.get(str(code), str(code))
def shift_code(label:str) -> str:
    if label is None: return "MORNING"
    s = str(label).strip()
    return LABEL2CODE.get(s, s).upper()

# ====== ORM 模型 ======
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    # 嚴格 Enum，存字串；不存中文
    shift = Column(SAEnum(ShiftEnum, name="shift", native_enum=False, validate_strings=True),
                   nullable=False, index=True, default=ShiftEnum.MORNING)
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

# 寫入/更新時自動把中文/別名轉為代碼
@event.listens_for(Order, "before_insert")
@event.listens_for(Order, "before_update")
def _coerce_shift(mapper, connection, target):
    val = getattr(target, "shift", None)
    if isinstance(val, ShiftEnum):
        return
    code = shift_code(val)
    try:
        target.shift = ShiftEnum(code)
    except Exception:
        target.shift = ShiftEnum.MORNING

def init_db():
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        raise RuntimeError(f"建立資料表失敗：{e}")

# ====================== 帳號/設定 ======================
AUTH_FILE="auth.json"
SET_FILE="settings.json"

def _safe_read_json(path):
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        try:
            os.rename(path, path+".broken")
        except Exception:
            pass
        return None

class Settings:
    def __init__(self):
        self.remember_code = False
        self.last_code = ""
        self.search_history = []        # 訂單搜尋歷史
        self.exp_search_history = []    # 支出搜尋歷史

    @staticmethod
    def load():
        s = Settings()
        if os.path.exists(SET_FILE):
            d=_safe_read_json(SET_FILE)
            if d:
                s.remember_code = bool(d.get("remember_code",False))
                s.last_code = str(d.get("last_code","") or "")
                s.search_history = list(d.get("search_history",[]))[:8]
                s.exp_search_history = list(d.get("exp_search_history",[]))[:8]
        return s

    def save(self):
        with open(SET_FILE,"w",encoding="utf-8") as f:
            json.dump({
                "remember_code": self.remember_code,
                "last_code": self.last_code,
                "search_history": self.search_history,
                "exp_search_history": self.exp_search_history
            }, f, ensure_ascii=False, indent=2)

def _hash_password(pw:str):
    salt=os.urandom(16)
    dk=hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return base64.b64encode(salt).decode(), base64.b64encode(dk).decode()

def _verify_password(pw:str, salt_b64:str, hash_b64:str):
    try:
        salt=base64.b64decode(salt_b64.encode())
        target=base64.b64decode(hash_b64.encode())
    except Exception:
        return False
    dk=hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return hmac.compare_digest(dk, target)

class AuthManager:
    @staticmethod
    def is_initialized():
        if not os.path.exists(AUTH_FILE): return False
        d=_safe_read_json(AUTH_FILE)
        if not d: return False
        u=d.get("user",{})
        return bool(u.get("code") and u.get("salt") and u.get("hash"))

    @staticmethod
    def setup_account(code:str, pw:str):
        if not code or not pw: raise ValueError("請輸入帳號代號與密碼")
        salt,h=_hash_password(pw)
        with open(AUTH_FILE,"w",encoding="utf-8") as f:
            json.dump({"version":1,"user":{"code":code.strip(),"salt":salt,"hash":h}}, f, ensure_ascii=False, indent=2)

    @staticmethod
    def verify(code:str, pw:str)->bool:
        if not os.path.exists(AUTH_FILE): return False
        d=_safe_read_json(AUTH_FILE)
        if not d: return False
        u=d.get("user",{})
        return (u.get("code")==code.strip()) and _verify_password(pw or "", u.get("salt",""), u.get("hash",""))

    @staticmethod
    def change_account(current_code:str, current_pw:str, new_code:str="", new_pw:str=""):
        if not AuthManager.verify(current_code, current_pw):
            raise ValueError("目前帳號或密碼不正確")
        d=_safe_read_json(AUTH_FILE) or {"user":{}}
        u=d.get("user",{})
        if new_code.strip(): u["code"]=new_code.strip()
        if new_pw.strip():
            salt,h=_hash_password(new_pw.strip())
            u["salt"],u["hash"]=salt,h
        d["user"]=u
        with open(AUTH_FILE,"w",encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

# ====================== 小工具 ======================
def dec(txt:str)->Decimal:
    t=(txt or "").strip().replace(",","")
    if t=="": return Decimal("0")
    try: return Decimal(t)
    except InvalidOperation:
        raise ValueError("金額格式錯誤，請輸入數字（如 2568 或 2568.00）")

def month_first_last(y:int,m:int):
    first = date(y,m,1)
    last = (date(y+(m//12),(m%12)+1,1) - timedelta(days=1))
    return first,last

def year_first_last(y:int):
    return date(y,1,1), date(y,12,31)

class SearchLine(QLineEdit):
    arrow = Signal(int)   # 1=Down, -1=Up
    decide = Signal()     # Enter
    focused_in = Signal()
    focused_out = Signal()
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Down, Qt.Key_Up):
            self.arrow.emit(1 if e.key()==Qt.Key_Down else -1); return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.decide.emit(); return
        super().keyPressEvent(e)
    def focusInEvent(self, e):
        self.focused_in.emit(); super().focusInEvent(e)
    def focusOutEvent(self, e):
        self.focused_out.emit(); super().focusOutEvent(e)

# ====================== KPI 卡片 ======================
class KpiCard(QWidget):
    def __init__(self, title, icon, grad, show_sub=False):
        super().__init__()
        lay=QVBoxLayout(self); lay.setContentsMargins(16,14,16,16); lay.setSpacing(6)
        self.t=QLabel(f"{icon} {title}"); self.t.setAlignment(Qt.AlignCenter)
        self.t.setStyleSheet("font-size:18px;font-weight:900;color:#0b1320;")
        self.v=QLabel("NT$0"); self.v.setAlignment(Qt.AlignCenter)
        self.v.setStyleSheet("font-size:30px;font-weight:900;color:#0b1320;")
        self.s=QLabel(""); self.s.setAlignment(Qt.AlignCenter)
        self.s.setStyleSheet("font-size:16px;font-weight:800;color:#334155;")
        self.s.setVisible(show_sub)
        lay.addWidget(self.t); lay.addWidget(self.v); lay.addWidget(self.s)
        self.setStyleSheet(f"QWidget{{background:{grad};border:1px solid #e5d7a8;border-radius:14px;}}")
    def title(self, t): self.t.setText(t)
    def value(self, t): self.v.setText(t)
    def set_sub(self, txt:str): self.s.setText(txt); self.s.setVisible(True)
    def hide_sub(self): self.s.setVisible(False)

class KpiBoard(QWidget):
    def __init__(self):
        super().__init__()
        row=QHBoxLayout(self); row.setSpacing(14)
        g1="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #fff7ed, stop:1 #fde68a)"  # 早班
        g2="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #eef2ff, stop:1 #c7d2fe)"  # 晚班
        g3="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #fff1f2, stop:1 #fecdd3)"  # 支出
        g4="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ecfeff, stop:1 #a7f3d0)"  # 總額
        self.c1=KpiCard("早班當日","🌅",g1)
        self.c2=KpiCard("晚班當日","🌙",g2)
        self.c3=KpiCard("當日支出","💸",g3)
        self.c4=KpiCard("當日總額","📊",g4, show_sub=True)
        for w in (self.c1,self.c2,self.c3,self.c4): row.addWidget(w)
    def set_mode(self,mode):
        if mode=="day":
            self.c1.title("🌅 早班當日"); self.c2.title("🌙 晚班當日"); self.c3.title("💸 當日支出"); self.c4.title("📊 當日總額")
        elif mode=="month":
            self.c1.title("🌅 早班當月"); self.c2.title("🌙 晚班當月"); self.c3.title("💸 月總支出"); self.c4.title("📊 當月總額")
        else:
            self.c1.title("🌅 早班當年"); self.c2.title("🌙 晚班當年"); self.c3.title("💸 年總支出"); self.c4.title("📊 當年總額")
    def update(self, morning, evening, expense, total, net_text):
        self.c1.value(morning); self.c2.value(evening); self.c3.value(expense)
        self.c4.value(total);   self.c4.set_sub(net_text)

# ====================== 訂單（歷史清單） ======================
class OrdersTab(QWidget):
    updated = Signal()
    def __init__(self, settings):
        super().__init__(); self._loading=False; self.settings=settings
        root=QVBoxLayout(self)

        # 搜尋列
        searchBox=QFrame(); searchBox.setObjectName("glassBox")
        sLay=QVBoxLayout(searchBox); sLay.setContentsMargins(10,10,10,10); sLay.setSpacing(6)
        srow=QHBoxLayout()
        self.search=SearchLine(); self.search.setPlaceholderText("搜尋單號或金額（清空回全部）"); self.search.setClearButtonEnabled(True)
        self.btnSearch=QPushButton("🔎 搜尋"); self.btnSearch.clicked.connect(self._enter_search)
        srow.addWidget(self._flabel("搜尋")); srow.addWidget(self.search); srow.addWidget(self.btnSearch)
        sLay.addLayout(srow)
        self.hist=QListWidget(); self.hist.setVisible(False); self.hist.setMaximumHeight(160)
        self.hist.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hist.setStyleSheet("""
            QListWidget{border:1px solid #e5e7eb;border-radius:8px;background:#fff;}
            QListWidget::item{padding:6px 10px;}
            QListWidget::item:selected{background:#2563EB;color:#fff;}
        """)
        self.hist.itemClicked.connect(lambda it: self._apply_query(it.text()))
        sLay.addWidget(self.hist)
        root.addWidget(searchBox)

        # 新增列
        addBox=QFrame(); addBox.setObjectName("glassBox")
        rowLay=QHBoxLayout(addBox); rowLay.setContentsMargins(10,10,10,10); rowLay.setSpacing(8)
        rowLay.addWidget(self._flabel("日期")); self.d=QDateEdit(QDate.currentDate()); self.d.setCalendarPopup(True); self.d.dateChanged.connect(lambda:self.load()); rowLay.addWidget(self.d)
        rowLay.addWidget(self._flabel("班別")); self.shift=QComboBox(); self.shift.addItems([shift_label("MORNING"), shift_label("EVENING")]); rowLay.addWidget(self.shift)
        rowLay.addWidget(self._flabel("單號")); self.no=QLineEdit(); self.no.setPlaceholderText("如 10037 或 37"); rowLay.addWidget(self.no)
        rowLay.addWidget(self._flabel("金額")); self.amt=QLineEdit(); self.amt.setPlaceholderText("如 2568"); rowLay.addWidget(self.amt)
        add=QPushButton("新增"); add.clicked.connect(self.add); rowLay.addWidget(add)
        self.no.returnPressed.connect(lambda:self.amt.setFocus()); self.amt.returnPressed.connect(self.add)
        root.addWidget(addBox)

        # 表格
        self.t=QTableWidget(0,5); self.t.setHorizontalHeaderLabels(["班別","單號","金額","日期","ID(隱藏)"])
        h=self.t.horizontalHeader(); [h.setSectionResizeMode(i,QHeaderView.Stretch) for i in range(4)]
        self.t.setColumnHidden(4,True); self.t.verticalHeader().setVisible(False)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.SelectedClicked|QAbstractItemView.EditKeyPressed)
        self.t.setSortingEnabled(True); self.t.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.t)

        row2=QHBoxLayout()
        delb=QPushButton("刪除選中"); delb.setObjectName("btnDanger"); delb.clicked.connect(self.delete)
        row2.addWidget(delb); row2.addStretch(); root.addLayout(row2)

        # 搜尋互動
        self.search.focused_in.connect(lambda: self._show_hist(self.search.text()))
        self.search.focused_out.connect(lambda: QTimer.singleShot(120,self._maybe_hide_hist))
        self.search.textChanged.connect(self._on_search_change)
        self.search.arrow.connect(self._on_arrow)
        self.search.decide.connect(self._enter_search)
        self._refresh_history(); self.load()

    def _flabel(self, text):
        lb=QLabel(text); lb.setObjectName("fieldLabel"); return lb

    def _maybe_hide_hist(self):
        if not (self.hist.underMouse() or self.search.hasFocus()): self.hist.hide()

    def _show_hist(self, keyword:str=""):
        self._refresh_history(keyword)
        self.hist.setVisible(self.hist.count()>0)

    def _refresh_history(self, keyword:str=""):
        self.hist.clear()
        items=[q for q in self.settings.search_history if keyword.strip() in q] if keyword else self.settings.search_history
        for q in items: self.hist.addItem(q)
        if self.hist.count()>0: self.hist.setCurrentRow(0)

    def _add_history(self, q:str):
        q=q.strip()
        if not q: return
        if q in self.settings.search_history: self.settings.search_history.remove(q)
        self.settings.search_history.insert(0,q)
        self.settings.search_history=self.settings.search_history[:8]
        self.settings.save()
        self._refresh_history(self.search.text())

    def _on_search_change(self, txt:str):
        if txt.strip()=="":
            self.load(None)
            if self.search.hasFocus(): self._show_hist("")
            else: self.hist.hide()
        else:
            self._show_hist(txt)

    def _on_arrow(self, step:int):
        if not self.hist.isVisible() or self.hist.count()==0: return
        r=self.hist.currentRow()
        r = 0 if r<0 else r+step
        r = max(0, min(self.hist.count()-1, r))
        self.hist.setCurrentRow(r)

    def _enter_search(self):
        if self.hist.isVisible() and self.hist.currentItem():
            q=self.hist.currentItem().text()
        else:
            q=self.search.text().strip()
        self._add_history(q); self.hist.hide(); self.load(q)

    def _apply_query(self,q:str):
        self.search.setText(q); self.hist.hide(); self.load(q)

    def _set_item(self,row,col,text,editable=False,center=True,brush=None):
        it=QTableWidgetItem(text)
        if center: it.setTextAlignment(Qt.AlignCenter)
        if brush: it.setBackground(brush)
        it.setFlags((it.flags()|Qt.ItemIsEditable) if editable else (it.flags() & ~Qt.ItemIsEditable))
        self.t.setItem(row,col,it)

    def _color_for_shift(self, code:str):
        return QBrush(QColor("#e0f2fe")) if code=="MORNING" else QBrush(QColor("#ede9fe"))

    def load(self, query:str|None=None):
        self._loading=True
        d=self.d.date().toPython()
        with SessionLocal() as s:
            if not query:
                rs=s.query(Order).filter(Order.date==d).order_by(asc(Order.id)).all()
            else:
                like=f"%{query}%"
                cond=[Order.date==d, Order.order_no.like(like)]
                try:
                    v=float(query.replace(",",""))
                    cond=[Order.date==d, or_(Order.order_no.like(like), Order.amount==v)]
                except: pass
                rs=s.query(Order).filter(and_(*cond)).order_by(asc(Order.id)).all()
        self.t.setSortingEnabled(False); self.t.setRowCount(len(rs))
        for i,o in enumerate(rs):
            code = o.shift.value  # 'MORNING' / 'EVENING'
            br=self._color_for_shift(code)
            self._set_item(i,0,shift_label(code),brush=br)
            self._set_item(i,1,o.order_no,editable=True)
            self._set_item(i,2,f"{float(o.amount):,.0f}",editable=True)
            self._set_item(i,3,o.date.strftime("%Y-%m-%d"))
            self._set_item(i,4,str(o.id),editable=False,center=False)
        self.t.setSortingEnabled(True); self.t.sortByColumn(1,Qt.AscendingOrder)
        self._loading=False

    def _on_item_changed(self,item:QTableWidgetItem):
        if self._loading or item.column() not in (1,2): return
        id_item=self.t.item(item.row(),4)
        if not id_item: return
        try: oid=int(id_item.text())
        except: return
        val=item.text().strip()
        with SessionLocal() as s:
            obj=s.get(Order,oid)
            if not obj: return
            if item.column()==1:
                if not val:
                    QMessageBox.warning(self,"錯誤","單號不可空白。")
                    self._loading=True; item.setText(obj.order_no); self._loading=False; return
                obj.order_no=val
            else:
                try:
                    v=dec(val); assert v>0; obj.amount=v
                except:
                    QMessageBox.warning(self,"錯誤","金額格式錯誤。")
                    self._loading=True; item.setText(f"{float(obj.amount):,.0f}"); self._loading=False; return
            s.commit()
        if item.column()==2:
            self._loading=True; item.setText(f"{float(obj.amount):,.0f}"); self._loading=False
        self.updated.emit()

    def add(self):
        try:
            d=self.d.date().toPython()
            code = shift_code(self.shift.currentText())      # 'MORNING' / 'EVENING'
            no=self.no.text().strip(); amt=dec(self.amt.text())
            if not no or amt<=0:
                QMessageBox.warning(self,"錯誤","請輸入單號與正確金額。"); return
            with SessionLocal() as s:
                s.add(Order(date=d, shift=ShiftEnum(code), order_no=no, amount=amt)); s.commit()
            self.no.clear(); self.amt.clear(); self.load(None); self.updated.emit(); self.no.setFocus(); self.no.selectAll()
        except ValueError as e:
            QMessageBox.warning(self,"錯誤", str(e))

    def delete(self):
        rows=sorted({i.row() for i in self.t.selectedIndexes()},reverse=True); ids=[]
        for r in rows:
            it=self.t.item(r,4)
            if it:
                try: ids.append(int(it.text()))
                except: pass
        if not ids: return
        with SessionLocal() as s:
            for _id in ids:
                o=s.get(Order, _id)
                if o: s.delete(o)
            s.commit()
        self.load(None); self.updated.emit()

# ====================== 支出（時間搜尋＋歷史） ======================
class ExpensesTab(QWidget):
    updated=Signal()
    def __init__(self, settings):
        super().__init__(); self.settings=settings
        root=QVBoxLayout(self)

        # --- 搜尋區 ---
        searchBox=QFrame(); searchBox.setObjectName("glassBox")
        sLay=QVBoxLayout(searchBox); sLay.setContentsMargins(10,10,10,10); sLay.setSpacing(6)

        srow=QHBoxLayout()
        self.search=SearchLine(); self.search.setPlaceholderText("搜尋分類/備註或金額（清空回全部）"); self.search.setClearButtonEnabled(True)
        btn=QPushButton("🔎 搜尋")
        srow.addWidget(self._flabel("搜尋")); srow.addWidget(self.search); srow.addWidget(btn)
        sLay.addLayout(srow)

        trow=QHBoxLayout()
        self.time_mode=QComboBox(); self.time_mode.addItems(["當日","當月","當年","區間"])
        self.d_ref=QDateEdit(QDate.currentDate()); self.d_ref.setCalendarPopup(True); self.d_ref.setDisplayFormat("yyyy-MM-dd")
        self.fd=QDateEdit(QDate.currentDate()); self.fd.setCalendarPopup(True); self.fd.setDisplayFormat("yyyy-MM-dd")
        self.td=QDateEdit(QDate.currentDate()); self.td.setCalendarPopup(True); self.td.setDisplayFormat("yyyy-MM-dd")
        trow.addWidget(self._flabel("時間")); trow.addWidget(self.time_mode)
        trow.addWidget(self._flabel("基準")); trow.addWidget(self.d_ref)
        trow.addWidget(self._flabel("起")); trow.addWidget(self.fd)
        trow.addWidget(self._flabel("迄")); trow.addWidget(self.td)
        sLay.addLayout(trow)
        root.addWidget(searchBox)

        def on_mode_change():
            is_range = (self.time_mode.currentText()=="區間")
            self.d_ref.setVisible(not is_range)
            for w in (self.fd,self.td): w.setVisible(is_range)
            self._reload_current(self.search.text().strip() or None)
        self._on_mode_change = on_mode_change

        self.time_mode.currentIndexChanged.connect(self._on_mode_change)
        self.d_ref.dateChanged.connect(lambda *_: self._reload_current(self.search.text().strip() or None))
        self.fd.dateChanged.connect(lambda *_: self._reload_current(self.search.text().strip() or None))
        self.td.dateChanged.connect(lambda *_: self._reload_current(self.search.text().strip() or None))
        btn.clicked.connect(self._enter_search)

        # --- 新增列 ---
        addBox=QFrame(); addBox.setObjectName("glassBox")
        row=QHBoxLayout(addBox); row.setContentsMargins(10,10,10,10); row.setSpacing(8)
        self.d_add=QDateEdit(QDate.currentDate()); self.d_add.setCalendarPopup(True)
        row.addWidget(self._flabel("日期")); row.addWidget(self.d_add)
        self.cat=QComboBox(); self.cat.addItems(["原物料","人事","租金水電","行銷","雜支","其他"])
        row.addWidget(self._flabel("分類")); row.addWidget(self.cat)
        self.amt=QLineEdit(); row.addWidget(self._flabel("金額")); row.addWidget(self.amt)
        self.note=QLineEdit(); row.addWidget(self._flabel("備註")); row.addWidget(self.note)
        add=QPushButton("新增"); add.clicked.connect(self.add); row.addWidget(add)
        self.amt.returnPressed.connect(lambda:self.note.setFocus()); self.note.returnPressed.connect(self.add)
        root.addWidget(addBox)

        # --- 表格 ---
        self.t=QTableWidget(0,5); self.t.setHorizontalHeaderLabels(["分類","金額","日期","備註","ID(隱藏)"])
        h=self.t.horizontalHeader(); [h.setSectionResizeMode(i,QHeaderView.Stretch) for i in range(4)]
        self.t.setColumnHidden(4,True); self.t.verticalHeader().setVisible(False)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.setSortingEnabled(True)
        root.addWidget(self.t)

        row2=QHBoxLayout()
        delb=QPushButton("刪除選中"); delb.setObjectName("btnDanger"); delb.clicked.connect(self.delete)
        row2.addWidget(delb); row2.addStretch(); root.addLayout(row2)

        self.hist=QListWidget(); self.hist.setVisible(False); self.hist.setMaximumHeight(160)
        self.hist.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hist.setStyleSheet("""
            QListWidget{border:1px solid #e5e7eb;border-radius:8px;background:#fff;}
            QListWidget::item{padding:6px 10px;}
            QListWidget::item:selected{background:#2563EB;color:#fff;}
        """)
        self.hist.itemClicked.connect(lambda it: self._apply_query(it.text()))
        root.addWidget(self.hist)

        self.search.focused_in.connect(lambda: self._show_hist(self.search.text()))
        self.search.focused_out.connect(lambda: QTimer.singleShot(120,self._maybe_hide_hist))
        self.search.textChanged.connect(self._on_search_change)
        self.search.arrow.connect(self._on_arrow)
        self.search.decide.connect(self._enter_search)

        self._refresh_history()
        self._on_mode_change()

    def _flabel(self, text):
        lb=QLabel(text); lb.setObjectName("fieldLabel"); return lb

    def _range(self):
        mode=self.time_mode.currentText()
        if mode=="區間":
            d1=self.fd.date().toPython(); d2=self.td.date().toPython()
            if d1>d2: d1,d2=d2,d1
            return d1,d2
        ref=self.d_ref.date().toPython()
        if mode=="當日": return ref,ref
        if mode=="當月":
            f,l=month_first_last(ref.year, ref.month); return f,l
        return year_first_last(ref.year)

    def _maybe_hide_hist(self):
        if not (self.hist.underMouse() or self.search.hasFocus()):
            self.hist.hide()

    def _show_hist(self, keyword:str=""):
        self._refresh_history(keyword)
        self.hist.setVisible(self.hist.count()>0)

    def _refresh_history(self, keyword:str=""):
        self.hist.clear()
        items=[q for q in self.settings.exp_search_history if keyword.strip() in q] if keyword else self.settings.exp_search_history
        for q in items: self.hist.addItem(q)
        if self.hist.count()>0: self.hist.setCurrentRow(0)

    def _add_history(self, q:str):
        q=q.strip()
        if not q: return
        if q in self.settings.exp_search_history: self.settings.exp_search_history.remove(q)
        self.settings.exp_search_history.insert(0,q)
        self.settings.exp_search_history=self.settings.exp_search_history[:8]
        self.settings.save()
        self._refresh_history(self.search.text())

    def _on_search_change(self, txt:str):
        if txt.strip()=="":
            self._reload_current(None)
            if self.search.hasFocus(): self._show_hist("")
            else: self.hist.hide()
        else:
            self._show_hist(txt)

    def _on_arrow(self, step:int):
        if not self.hist.isVisible() or self.hist.count()==0: return
        r=self.hist.currentRow()
        r = 0 if r<0 else r+step
        r = max(0, min(self.hist.count()-1, r))
        self.hist.setCurrentRow(r)

    def _enter_search(self):
        if self.hist.isVisible() and self.hist.currentItem():
            q=self.hist.currentItem().text()
        else:
            q=self.search.text().strip()
        self._add_history(q); self.hist.hide(); self._reload_current(q)

    def _apply_query(self,q:str):
        self.search.setText(q); self.hist.hide(); self._reload_current(q)

    def _reload_current(self, query:str|None=None):
        if not hasattr(self, "t"):
            return
        d1,d2=self._range()
        with SessionLocal() as s:
            if not query:
                q=s.query(Expense).filter(and_(Expense.date>=d1,Expense.date<=d2)).order_by(asc(Expense.date),asc(Expense.id)).all()
            else:
                like=f"%{query}%"
                cond=[and_(Expense.date>=d1,Expense.date<=d2),
                      or_(Expense.category.like(like), Expense.note.like(like))]
                try:
                    v=float(query.replace(",",""))
                    cond=[and_(Expense.date>=d1,Expense.date<=d2),
                          or_(Expense.category.like(like), Expense.note.like(like), Expense.amount==v)]
                except: pass
                q=s.query(Expense).filter(and_(*cond)).order_by(asc(Expense.date),asc(Expense.id)).all()
        self.t.setSortingEnabled(False); self.t.setRowCount(len(q))
        for i,e in enumerate(q):
            def c(x): it=QTableWidgetItem(x); it.setTextAlignment(Qt.AlignCenter); return it
            self.t.setItem(i,0,c(e.category))
            self.t.setItem(i,1,c(f"{float(e.amount):,.0f}"))
            self.t.setItem(i,2,c(e.date.strftime("%Y-%m-%d")))
            self.t.setItem(i,3,QTableWidgetItem(e.note or ""))
            self.t.setItem(i,4,QTableWidgetItem(str(e.id)))
        self.t.setSortingEnabled(True); self.t.sortByColumn(1,Qt.AscendingOrder)

    def add(self):
        try:
            d=self.d_add.date().toPython()
            cat=self.cat.currentText()
            amt=dec(self.amt.text())
            note=self.note.text().strip()
            if amt<=0: QMessageBox.warning(self,"錯誤","請輸入正確金額。"); return
            with SessionLocal() as s:
                s.add(Expense(date=d, category=cat, amount=amt, note=note or None)); s.commit()
            self.amt.clear(); self.note.clear(); self._reload_current(); self.updated.emit()
        except ValueError as e:
            QMessageBox.warning(self,"錯誤", str(e))

    def delete(self):
        rows=sorted({i.row() for i in self.t.selectedIndexes()},reverse=True); ids=[]
        for r in rows:
            it=self.t.item(r,4)
            if it:
                try: ids.append(int(it.text()))
                except: pass
        if not ids: return
        with SessionLocal() as s:
            for _id in ids:
                x=s.get(Expense,_id)
                if x: s.delete(x)
            s.commit()
        self._reload_current(); self.updated.emit()

# ====================== 營業額（KPI） ======================
class DashboardTab(QWidget):
    def __init__(self):
        super().__init__(); self._ui(); self._mode_changed()

    def _ui(self):
        root=QVBoxLayout(self)

        ctr_frame=QFrame(); ctr_frame.setObjectName("periodFrame")
        ctr=QHBoxLayout(ctr_frame); ctr.setContentsMargins(8,8,8,8); ctr.setSpacing(6); ctr.setAlignment(Qt.AlignCenter)

        self.mode=QComboBox(); self.mode.addItems(["當日","當月","當年"]); self.mode.currentIndexChanged.connect(self._mode_changed)
        self.d=QDateEdit(QDate.currentDate()); self.d.setCalendarPopup(True); self.d.setDisplayFormat("yyyy-MM-dd"); self.d.dateChanged.connect(self.refresh)
        self.btn_prev=QPushButton("← 前一天"); self.btn_today=QPushButton("今日"); self.btn_next=QPushButton("後一天 →")
        self.btn_prev.clicked.connect(lambda:self._set_day(self.d.date().addDays(-1)))
        self.btn_today.clicked.connect(lambda:self._set_day(QDate.currentDate()))
        self.btn_next.clicked.connect(lambda:self._set_day(self.d.date().addDays(1)))

        self.m=QDateEdit(QDate.currentDate()); self.m.setCalendarPopup(True); self.m.setDisplayFormat("yyyy-MM"); self.m.dateChanged.connect(self.refresh)
        self.btn_m_prev=QPushButton("← 上一月"); self.btn_m_this=QPushButton("本月"); self.btn_m_next=QPushButton("下一月 →")
        self.btn_m_prev.clicked.connect(lambda:self._set_month(self.m.date().addMonths(-1)))
        self.btn_m_this.clicked.connect(lambda:self._set_month(self.m.date().addMonths(1)))
        self.btn_m_next.clicked.connect(lambda:self._set_month(self.m.date().addMonths(1)))

        self.y=QDateEdit(QDate.currentDate()); self.y.setCalendarPopup(True); self.y.setDisplayFormat("yyyy"); self.y.dateChanged.connect(self.refresh)
        self.btn_y_prev=QPushButton("← 前一年"); self.btn_y_this=QPushButton("今年"); self.btn_y_next=QPushButton("後一年 →")
        self.btn_y_prev.clicked.connect(lambda:self._set_year(self.y.date().addYears(-1)))
        self.btn_y_this.clicked.connect(lambda:self._set_year(self.y.date().addYears(1)))
        self.btn_y_next.clicked.connect(lambda:self._set_year(self.y.date().addYears(1)))

        self.period=QLabel(""); self.period.setAlignment(Qt.AlignCenter)
        self.period.setStyleSheet("color:#334155;font-weight:800;")

        for w in (QLabel("模式"), self.mode,
                  self.d,self.btn_prev,self.btn_today,self.btn_next,
                  self.m,self.btn_m_prev,self.btn_m_this,self.btn_m_next,
                  self.y,self.btn_y_prev,self.btn_y_this,self.btn_y_next,
                  self.period):
            ctr.addWidget(w)
        root.addWidget(ctr_frame)

        self.kpi=KpiBoard()
        root.addWidget(self.kpi)

    def _set_day(self,qd): self.d.setDate(qd); self.refresh()
    def _set_month(self,qd): self.m.setDate(QDate(qd.year(),qd.month(),1)); self.refresh()
    def _set_year(self,qd): self.y.setDate(QDate(qd.year(),1,1)); self.refresh()

    def _mode_changed(self):
        m=self.mode.currentText()
        self.kpi.set_mode("day" if m=="當日" else ("month" if m=="當月" else "year"))
        for w,vis in (
            ((self.d,self.btn_prev,self.btn_today,self.btn_next), m=="當日"),
            ((self.m,self.btn_m_prev,self.btn_m_this,self.btn_m_next), m=="當月"),
            ((self.y,self.btn_y_prev,self.btn_y_this,self.btn_y_next), m=="當年"),
        ):
            for x in w: x.setVisible(vis)
        self.refresh()

    def refresh(self):
        m=self.mode.currentText()
        if m=="當日":
            d=self.d.date().toPython()
            with SessionLocal() as s:
                mm=s.query(func.coalesce(func.sum(Order.amount),0)).filter(Order.date==d,Order.shift==ShiftEnum.MORNING).scalar() or 0
                me=s.query(func.coalesce(func.sum(Order.amount),0)).filter(Order.date==d,Order.shift==ShiftEnum.EVENING).scalar() or 0
                mx=s.query(func.coalesce(func.sum(Expense.amount),0)).filter(Expense.date==d).scalar() or 0
            total=float(mm)+float(me); net=total-float(mx)
            self.kpi.update(f"NT${float(mm):,.0f}", f"NT${float(me):,.0f}", f"NT${float(mx):,.0f}",
                            f"NT${total:,.0f}", f"扣支出後 NT${net:,.0f}")
            self.period.setText(f"期間：{d.strftime('%Y-%m-%d')}")
        elif m=="當月":
            q=self.m.date().toPython(); y,mn=q.year,q.month; first,last=month_first_last(y,mn)
            with SessionLocal() as s:
                mm=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=first,Order.date<=last,Order.shift==ShiftEnum.MORNING)).scalar() or 0
                me=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=first,Order.date<=last,Order.shift==ShiftEnum.EVENING)).scalar() or 0
                mx=s.query(func.coalesce(func.sum(Expense.amount),0)).filter(and_(Expense.date>=first,Expense.date<=last)).scalar() or 0
            total=float(mm)+float(me); net=total-float(mx)
            self.kpi.update(f"NT${float(mm):,.0f}", f"NT${float(me):,.0f}", f"NT${float(mx):,.0f}",
                            f"NT${total:,.0f}", f"扣支出後 NT${net:,.0f}")
            self.period.setText(f"期間：{first.strftime('%Y-%m')}")
        else:
            yv=self.y.date().year(); first,last=year_first_last(yv)
            with SessionLocal() as s:
                mm=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=first,Order.date<=last,Order.shift==ShiftEnum.MORNING)).scalar() or 0
                me=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=first,Order.date<=last,Order.shift==ShiftEnum.EVENING)).scalar() or 0
                mx=s.query(func.coalesce(func.sum(Expense.amount),0)).filter(and_(Expense.date>=first,Expense.date<=last)).scalar() or 0
            total=float(mm)+float(me); net=total-float(mx)
            self.kpi.update(f"NT${float(mm):,.0f}", f"NT${float(me):,.0f}", f"NT${float(mx):,.0f}",
                            f"NT${total:,.0f}", f"扣支出後 NT${net:,.0f}")
            self.period.setText(f"期間：{yv} 年")

# ====================== 報表（日期控制＋三大匯出） ======================
class ReportsTab(QWidget):
    def __init__(self):
        super().__init__(); root=QVBoxLayout(self)

        box=QFrame(); box.setObjectName("periodBox")
        ctr=QHBoxLayout(box); ctr.setContentsMargins(8,8,8,8); ctr.setSpacing(6); ctr.setAlignment(Qt.AlignCenter)

        self.mode=QComboBox(); self.mode.addItems(["當日","當月","當年"]); self.mode.currentIndexChanged.connect(self._mode_changed)
        self.d=QDateEdit(QDate.currentDate()); self.d.setCalendarPopup(True); self.d.setDisplayFormat("yyyy-MM-dd")
        self.btn_prev=QPushButton("← 前一天"); self.btn_today=QPushButton("今日"); self.btn_next=QPushButton("後一天 →")
        self.btn_prev.clicked.connect(lambda:self._set_day(self.d.date().addDays(-1)))
        self.btn_today.clicked.connect(lambda:self._set_day(QDate.currentDate()))
        self.btn_next.clicked.connect(lambda:self._set_day(self.d.date().addDays(1)))

        self.m=QDateEdit(QDate.currentDate()); self.m.setCalendarPopup(True); self.m.setDisplayFormat("yyyy-MM")
        self.btn_m_prev=QPushButton("← 上一月"); self.btn_m_this=QPushButton("本月"); self.btn_m_next=QPushButton("下一月 →")
        self.btn_m_prev.clicked.connect(lambda:self._set_month(self.m.date().addMonths(-1)))
        self.btn_m_this.clicked.connect(lambda:self._set_month(self.m.date().addMonths(1)))
        self.btn_m_next.clicked.connect(lambda:self._set_month(self.m.date().addMonths(1)))

        self.y=QDateEdit(QDate.currentDate()); self.y.setCalendarPopup(True); self.y.setDisplayFormat("yyyy")
        self.btn_y_prev=QPushButton("← 前一年"); self.btn_y_this=QPushButton("今年"); self.btn_y_next=QPushButton("後一年 →")
        self.btn_y_prev.clicked.connect(lambda:self._set_year(self.y.date().addYears(-1)))
        self.btn_y_this.clicked.connect(lambda:self._set_year(self.y.date().addYears(1)))
        self.btn_y_next.clicked.connect(lambda:self._set_year(self.y.date().addYears(1)))

        for w in (QLabel("模式"), self.mode,
                  self.d, self.btn_prev, self.btn_today, self.btn_next,
                  self.m, self.btn_m_prev, self.btn_m_this, self.btn_m_next,
                  self.y, self.btn_y_prev, self.btn_y_this, self.btn_y_next):
            ctr.addWidget(w)

        root.addWidget(box)

        btns=QHBoxLayout()
        self.b1=QPushButton("📤 匯出訂單 CSV"); self.b1.setObjectName("btnOrders")
        self.b2=QPushButton("🧾 匯出支出 CSV"); self.b2.setObjectName("btnExpenses")
        self.b3=QPushButton("💹 匯出營業額 CSV"); self.b3.setObjectName("btnRevenue")
        for b in (self.b1,self.b2,self.b3):
            b.setMinimumHeight(56)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btns.addWidget(b)
        root.addLayout(btns)

        self.b1.clicked.connect(self.exp_orders); self.b2.clicked.connect(self.exp_expenses); self.b3.clicked.connect(self.exp_revenue)
        self._mode_changed()

    def _mode_changed(self):
        m=self.mode.currentText()
        for w,vis in (
            ((self.d,self.btn_prev,self.btn_today,self.btn_next), m=="當日"),
            ((self.m,self.btn_m_prev,self.btn_m_this,self.btn_m_next), m=="當月"),
            ((self.y,self.btn_y_prev,self.btn_y_this,self.btn_y_next), m=="當年"),
        ):
            for x in w: x.setVisible(vis)

    def _set_day(self,qd): self.d.setDate(qd)
    def _set_month(self,qd): self.m.setDate(QDate(qd.year(),qd.month(),1))
    def _set_year(self,qd): self.y.setDate(QDate(qd.year(),1,1))

    def _range(self):
        m=self.mode.currentText()
        if m=="當日":
            d=self.d.date().toPython(); return d,d
        if m=="當月":
            q=self.m.date().toPython(); first,last=month_first_last(q.year,q.month); return first,last
        yv=self.y.date().year(); return year_first_last(yv)

    def _pick(self,name):
        p,_=QFileDialog.getSaveFileName(self,"儲存為...",name,"CSV 檔 (*.csv)")
        return p

    def exp_orders(self):
        d1,d2=self._range()
        path=self._pick(f"訂單_{d1.strftime('%Y%m%d')}_{d2.strftime('%Y%m%d')}.csv")
        if not path: return
        with SessionLocal() as s, open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["日期","班別","單號","金額","備註"])
            q=s.query(Order).filter(and_(Order.date>=d1,Order.date<=d2)).order_by(asc(Order.date),asc(Order.id)).all()
            for o in q:
                w.writerow([o.date.strftime("%Y-%m-%d"), shift_label(o.shift.value), o.order_no, f"{float(o.amount):.0f}", o.memo or ""])
        QMessageBox.information(self,"完成",f"已匯出：\n{path}")

    def exp_expenses(self):
        d1,d2=self._range()
        path=self._pick(f"支出_{d1.strftime('%Y%m%d')}_{d2.strftime('%Y%m%d')}.csv")
        if not path: return
        with SessionLocal() as s, open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["日期","分類","金額","備註"])
            q=s.query(Expense).filter(and_(Expense.date>=d1,Expense.date<=d2)).order_by(asc(Expense.date),asc(Expense.id)).all()
            for e in q: w.writerow([e.date.strftime("%Y-%m-%d"),e.category,f"{float(e.amount):,.0f}",e.note or ""])
        QMessageBox.information(self,"完成",f"已匯出：\n{path}")

    def exp_revenue(self):
        d1,d2=self._range()
        path=self._pick(f"營業額_{d1.strftime('%Y%m%d')}_{d2.strftime('%Y%m%d')}.csv")
        if not path: return
        with SessionLocal() as s, open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["日期","早班營業額","晚班營業額","總營業額","支出","利潤"])
            ords=s.query(Order.date,Order.shift,func.sum(Order.amount)).filter(and_(Order.date>=d1,Order.date<=d2)).group_by(Order.date,Order.shift).all()
            exps=s.query(Expense.date,func.sum(Expense.amount)).filter(and_(Expense.date>=d1,Expense.date<=d2)).group_by(Expense.date).all()
            o_map={}; dates=set()
            for d,sh,sumv in ords:
                dates.add(d); o_map.setdefault(d,{ShiftEnum.MORNING:0.0,ShiftEnum.EVENING:0.0})[sh]=float(sumv or 0)
            x_map={d:float(v or 0) for d,v in exps}; dates.update(x_map.keys())
            for d in sorted(dates):
                m=o_map.get(d,{ShiftEnum.MORNING:0.0,ShiftEnum.EVENING:0.0})
                mm,me=float(m.get(ShiftEnum.MORNING,0)),float(m.get(ShiftEnum.EVENING,0))
                total=mm+me; x=float(x_map.get(d,0)); profit=total-x
                w.writerow([d.strftime("%Y-%m-%d"),f"{mm:.0f}",f"{me:.0f}",f"{total:.0f}",f"{x:.0f}",f"{profit:.0f}"])
        QMessageBox.information(self,"完成",f"已匯出：\n{path}")

# ====================== AI 智能助手 ======================
class AiTab(QWidget):
    def __init__(self):
        super().__init__(); root=QVBoxLayout(self)

        glass=QFrame(); glass.setObjectName("glassBox")
        gl=QVBoxLayout(glass); gl.setContentsMargins(10,10,10,10); gl.setSpacing(6)

        tip=QLabel("輸入問題（例：本月利潤？ / 今天早班營業額 / 今年支出 / 本月TOP3支出分類 / 單號 37）")
        tip.setStyleSheet("color:#334155;font-weight:700;")
        gl.addWidget(tip)

        prow=QHBoxLayout()
        self.mode=QComboBox(); self.mode.addItems(["自動","今日","本月","今年","區間"])
        self.fd=QDateEdit(QDate.currentDate()); self.fd.setCalendarPopup(True); self.fd.setDisplayFormat("yyyy-MM-dd")
        self.td=QDateEdit(QDate.currentDate()); self.td.setCalendarPopup(True); self.td.setDisplayFormat("yyyy-MM-dd")
        prow.addWidget(QLabel("期間")); prow.addWidget(self.mode)
        prow.addWidget(QLabel("起")); prow.addWidget(self.fd)
        prow.addWidget(QLabel("迄")); prow.addWidget(self.td)
        gl.addLayout(prow)

        def on_mode():
            rng = (self.mode.currentText()=="區間")
            self.fd.setVisible(rng); self.td.setVisible(rng)
        self.mode.currentIndexChanged.connect(on_mode); on_mode()

        row=QHBoxLayout()
        self.q=QLineEdit(); self.q.setPlaceholderText("在此輸入問題…"); self.q.returnPressed.connect(self.ask)
        askb=QPushButton("▶ 解析"); askb.clicked.connect(self.ask)
        row.addWidget(self.q); row.addWidget(askb); gl.addLayout(row)

        root.addWidget(glass)

        self.out=QTextEdit(); self.out.setReadOnly(True); root.addWidget(self.out)

        chips=QHBoxLayout()
        for txt in ["今日利潤","本月支出","今年總營業額","今天早班營業額","今天晚班營業額","本月TOP3支出分類"]:
            b=QPushButton(txt); b.clicked.connect(lambda _,t=txt:self._fill(t)); chips.addWidget(b)
        chips.addStretch(); root.addLayout(chips)

    def _fill(self,t): self.q.setText(t); self.ask()

    def _period_from_ui_or_text(self, qtext:str):
        today=date.today()
        m=self.mode.currentText()
        if m=="今日": return (today,today)
        if m=="本月":
            f,l=month_first_last(today.year, today.month); return (f,l)
        if m=="今年": return year_first_last(today.year)
        if m=="區間":
            d1=self.fd.date().toPython(); d2=self.td.date().toPython()
            if d1>d2: d1,d2=d2,d1
            return (d1,d2)
        if ("今日" in qtext) or ("今天" in qtext): return (today,today)
        if "本月" in qtext:
            f,l=month_first_last(today.year, today.month); return (f,l)
        if "今年" in qtext: return year_first_last(today.year)
        return (today,today)

    def ask(self):
        q=self.q.text().strip()
        if not q: return
        d1,d2=self._period_from_ui_or_text(q)
        want_profit=("利潤" in q)
        want_rev=("營業額" in q) or ("收入" in q)
        want_exp=("支出" in q)
        want_m=("早班" in q); want_e=("晚班" in q)
        want_top=("TOP" in q) or ("Top" in q) or ("排行" in q) or ("前三" in q)
        digits="".join([c for c in q if c.isdigit()])

        with SessionLocal() as s:
            msg=[]
            if ("單號" in q) or (digits and not (want_profit or want_rev or want_exp or want_top)):
                like=f"%{digits or q}%"
                rs=s.query(Order).filter(Order.order_no.like(like)).order_by(asc(Order.date),asc(Order.id)).all()
                if not rs: msg.append("找不到相符單號。")
                else:
                    msg.append(f"🔎 單號查詢，共 {len(rs)} 筆（顯示前20）：")
                    for o in rs[:20]:
                        msg.append(f"- {o.date.strftime('%Y-%m-%d')} {shift_label(o.shift.value)} 單號 {o.order_no} 金額 NT${float(o.amount):,.0f}")
                self.out.setText("\n".join(msg)); return

            rev_m=rev_e=exp=0.0
            if want_rev or want_profit or want_m or want_e:
                if want_m or not (want_m or want_e):
                    v=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=d1,Order.date<=d2,Order.shift==ShiftEnum.MORNING)).scalar() or 0
                    rev_m=float(v)
                if want_e or not (want_m or want_e):
                    v=s.query(func.coalesce(func.sum(Order.amount),0)).filter(and_(Order.date>=d1,Order.date<=d2,Order.shift==ShiftEnum.EVENING)).scalar() or 0
                    rev_e=float(v)
            if want_exp or want_profit:
                v=s.query(func.coalesce(func.sum(Expense.amount),0)).filter(and_(Expense.date>=d1,Expense.date<=d2)).scalar() or 0
                exp=float(v)

            if want_top and want_exp:
                rows=s.query(Expense.category, func.sum(Expense.amount)).filter(and_(Expense.date>=d1,Expense.date<=d2)).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()
                msg.append(f"📊 {d1} ~ {d2} 支出分類排行（TOP 3）：")
                for i,(cat,sumv) in enumerate(rows[:3],1):
                    msg.append(f"  {i}. {cat} NT${float(sumv):,.0f}")

            if want_rev and not (want_m or want_e):
                msg.append(f"📈 營業額合計（{d1} ~ {d2}）：NT${(rev_m+rev_e):,.0f}")
            if want_m: msg.append(f"🌅 早班營業額（{d1} ~ {d2}）：NT${rev_m:,.0f}")
            if want_e: msg.append(f"🌙 晚班營業額（{d1} ~ {d2}）：NT${rev_e:,.0f}")
            if want_exp: msg.append(f"💸 支出（{d1} ~ {d2}）：NT${exp:,.0f}")
            if want_profit: msg.append(f"💰 利潤（營業額-支出，{d1} ~ {d2}）：NT${(rev_m+rev_e-exp):,.0f}")
            if not msg:
                msg.append("可問我：今日/本月/今年 + 營業額、支出、利潤；或「單號 37」。")
            self.out.setText("\n".join(msg))

# ====================== 外觀 ======================
def apply_marble(widget:QWidget, crop_ratio:float=0.12, scale_ratio:float=0.6):
    for name in ("marble.jpg","marble.png","Marble.jpg","Marble.png"):
        if os.path.exists(name):
            pm=QPixmap(name)
            if not pm.isNull():
                cw=max(50, int(pm.width()*(1.0-crop_ratio)))
                ch=max(50, int(pm.height()*(1.0-crop_ratio)))
                if cw>0 and ch>0:
                    pm=pm.copy(0,0,cw,ch)
                pal=widget.palette()
                br=QBrush(pm)
                br.setTransform(QTransform().scale(scale_ratio,scale_ratio))
                pal.setBrush(QPalette.Window, br)
                widget.setAutoFillBackground(True)
                widget.setPalette(pal)
            break

def apply_light_theme(app:QApplication):
    pal=app.palette()
    pal.setColor(QPalette.WindowText,QColor("#0b1320"))
    pal.setColor(QPalette.Base,QColor("#ffffff"))
    pal.setColor(QPalette.Text,QColor("#0b1320"))
    pal.setColor(QPalette.Button,QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText,QColor("#0b1320"))
    pal.setColor(QPalette.Highlight,QColor("#2563EB"))
    pal.setColor(QPalette.HighlightedText,QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase,QColor("#f6f8fb"))
    app.setPalette(pal)

    font = QFont("Microsoft JhengHei UI", 10)
    app.setFont(font)

    app.setStyleSheet("""
        QWidget{font-size:15px;}
        #glassBox{
            background: rgba(255,255,255,0.92);
            border:1px solid #e5e7eb;
            border-radius:14px;
        }
        QLabel#fieldLabel{
            background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;
            padding:4px 8px;font-weight:900;color:#0b1320;
        }
        #sideMenu{background:rgba(255,255,255,0.92);border:1px solid #e5e7eb;border-radius:14px;}
        #sideMenu #menuBtn{
            text-align:left;padding:10px 14px;border:0;color:#0b1320;font-weight:800;border-radius:10px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e0f2fe, stop:1 #bae6fd);
        }
        #sideMenu #menuBtn:hover{ filter: brightness(0.96); }
        #sideMenu #menuBtn:checked{
            color:#ffffff;background:#1e40af;border-left:4px solid #0b3ea8;
        }
        QTableWidget{background:#fff;color:#0b1320;gridline-color:#e5d7a8;selection-background-color:#2563EB;selection-color:#fff;alternate-background-color:#fafafa;border:1px solid #e5d7a8;border-radius:12px;}
        QHeaderView::section{background:#f8fafc;color:#0b1320;padding:10px 12px;border:1px solid #e5d7a8;font-weight:800;}
        QLabel{color:#0b1320;}
        QLineEdit,QComboBox,QDateEdit{
            border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;background:#fff;color:#0b1320;
            selection-background-color:#2563EB;selection-color:#fff;
        }
        QLineEdit:focus,QComboBox:focus,QDateEdit:focus{border:1px solid #2563EB;}
        QPushButton{border:1px solid #2563EB;border-radius:10px;padding:9px 16px;background:#2563EB;color:#fff;font-weight:800;}
        QPushButton:hover{background:#1e40af;border-color:#1e40af;} QPushButton:pressed{background:#172554;}
        QPushButton#btnDanger{border:1px solid #ef4444;background:#ef4444;color:#fff;}
        QPushButton#btnDanger:hover{background:#dc2626;border-color:#dc2626;}
        QPushButton#btnLogout{border:1px solid #ef4444;background:#ef4444;color:#fff;}
        QPushButton#btnLogout:hover{background:#dc2626;border-color:#dc2626;}
        QFrame#periodFrame, QFrame#periodBox{
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #eef7ff, stop:1 #e0f2fe);
            border:1px solid #cfe3ff; border-radius:12px;
        }
        QPushButton#btnOrders{border:1px solid #38bdf8;color:#0b1320;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #e0f2fe,stop:1 #bae6fd);border-radius:12px;padding:12px 20px;font-weight:900;font-size:16px;}
        QPushButton#btnOrders:hover{background:#bae6fd;}
        QPushButton#btnExpenses{border:1px solid #f59e0b;color:#0b1320;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fff7ed,stop:1 #fde68a);border-radius:12px;padding:12px 20px;font-weight:900;font-size:16px;}
        QPushButton#btnExpenses:hover{background:#fde68a;}
        QPushButton#btnRevenue{border:1px solid #34d399;color:#0b1320;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ecfeff,stop:1 #a7f3d0);border-radius:12px;padding:12px 20px;font-weight:900;font-size:16px;}
        QPushButton#btnRevenue:hover{background:#a7f3d0;}
        QToolTip{color:#0b1320;background:#fff;border:1px solid #e5e7eb;}
    """)

# ====================== 營業額二次驗證視窗 ======================
class RevenuePasswordDialog(QDialog):
    def __init__(self, code:str):
        super().__init__(); self.setWindowTitle("營業額存取驗證"); self.ok=False; self.code=code
        lay=QVBoxLayout(self); form=QFormLayout()
        self.pw=QLineEdit(); self.pw.setEchoMode(QLineEdit.Password); self.pw.setPlaceholderText("請輸入管理者密碼")
        form.addRow("管理者密碼", self.pw); lay.addLayout(form)
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)
    def _ok(self):
        if AuthManager.verify(self.code, self.pw.text()):
            self.ok=True; self.accept()
        else:
            QMessageBox.warning(self,"錯誤","密碼不正確。")

# ====================== 主視窗 ======================
class MainWindow(QMainWindow):
    def __init__(self, current_code:str, settings):
        super().__init__(); self.current_code=current_code; self.settings=settings
        self.setWindowTitle("AurumLedger 企業版｜餐飲作帳系統"); self.resize(1200,780)
        self.revenue_unlocked=False
        self.current_btn=None

        root=QWidget()
        if USE_MARBLE:
            try: apply_marble(root)
            except Exception: pass
        outer=QVBoxLayout(root)

        # 上方標題列
        top=QHBoxLayout()
        title_frame=QFrame(); title_frame.setObjectName("titleCapsule")
        title_frame.setStyleSheet("QFrame#titleCapsule{background:rgba(255,255,255,0.88);border-radius:14px;}")
        tlay=QHBoxLayout(title_frame); tlay.setContentsMargins(14,6,14,6)
        title=QLabel("AurumLedger 企業版｜餐飲作帳系統"); title.setStyleSheet("font-size:24px;font-weight:900;color:#0b1320;")
        tlay.addWidget(title)
        top.addWidget(title_frame); top.addStretch()

        self.btn_acc=QPushButton("帳號設定")
        self.btn_out=QPushButton("登出"); self.btn_out.setObjectName("btnLogout")
        self.btn_acc.clicked.connect(self.on_account); self.btn_out.clicked.connect(self.on_logout)
        top.addWidget(self.btn_acc); top.addWidget(self.btn_out)
        outer.addLayout(top)

        # 中段：左側目錄 + 右側內容
        mid=QHBoxLayout()

        side=QFrame(); side.setObjectName("sideMenu"); side.setFixedWidth(220)
        slyt=QVBoxLayout(side); slyt.setContentsMargins(12,12,12,12); slyt.setSpacing(8)
        def mkbtn(text):
            b=QPushButton(text); b.setObjectName("menuBtn"); b.setCheckable(True)
            b.setMinimumHeight(46); b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return b
        self.btn_orders = mkbtn("🧾  訂單")
        self.btn_exp    = mkbtn("💸  支出")
        self.btn_dash   = mkbtn("📈  營業額")
        self.btn_rep    = mkbtn("📤  報表")
        self.btn_ai     = mkbtn("🤖  AI 智能助手")

        self.grp=QButtonGroup(self); self.grp.setExclusive(True)
        for b in [self.btn_orders,self.btn_exp,self.btn_dash,self.btn_rep,self.btn_ai]:
            self.grp.addButton(b); slyt.addWidget(b)
        slyt.addStretch(1)

        self.stack=QStackedWidget()
        self.orders   = OrdersTab(settings=self.settings)
        self.expenses = ExpensesTab(settings=self.settings)
        self.dashboard= DashboardTab()
        self.reports  = ReportsTab()
        self.ai       = AiTab()
        for w in (self.orders,self.expenses,self.dashboard,self.reports,self.ai):
            self.stack.addWidget(w)

        self.btn_to_index = {
            self.btn_orders: 0,
            self.btn_exp:    1,
            self.btn_dash:   2,
            self.btn_rep:    3,
            self.btn_ai:     4,
        }

        self.btn_orders.setChecked(True)
        self.current_btn = self.btn_orders
        self.stack.setCurrentIndex(self.btn_to_index[self.btn_orders])

        self.grp.buttonClicked.connect(self.on_tab_clicked_btn)

        self.orders.updated.connect(self.dashboard.refresh)
        self.expenses.updated.connect(self.dashboard.refresh)

        mid.addWidget(side); mid.addWidget(self.stack, 1)
        outer.addLayout(mid)
        self.setCentralWidget(root)

    def on_tab_clicked_btn(self, btn:QPushButton):
        if btn is self.btn_dash and not self.revenue_unlocked:
            dlg=RevenuePasswordDialog(self.current_code)
            if dlg.exec()!=QDialog.Accepted or not dlg.ok:
                if self.current_btn: self.current_btn.setChecked(True)
                return
            self.revenue_unlocked=True
        idx=self.btn_to_index.get(btn,0)
        self.stack.setCurrentIndex(idx)
        self.current_btn = btn

    def on_account(self):
        dlg=ChangeAccountDialog(self.current_code)
        if dlg.exec()==QDialog.Accepted and dlg.result_new_code:
            self.current_code=dlg.result_new_code

    def on_logout(self):
        self.hide()
        settings=Settings.load()
        login=LoginDialog(settings)
        if login.exec()==QDialog.Accepted and login.ok:
            self.current_code=login.code.text()
            self.revenue_unlocked=False
            self.show()
        else:
            self.close()

# ===== 首次設定 / 登入 / 修改帳號 =====
class SetupDialog(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle("首次設定帳號"); self.setModal(True)
        lay=QVBoxLayout(self); form=QFormLayout()
        self.code=QLineEdit(); self.pw=QLineEdit(); self.pw.setEchoMode(QLineEdit.Password)
        self.code.setPlaceholderText("帳號代號（如 admin）"); self.pw.setPlaceholderText("設定密碼")
        form.addRow("帳號代號", self.code); form.addRow("密　　碼", self.pw); lay.addLayout(form)
        lay.addItem(QSpacerItem(20,10,QSizePolicy.Minimum,QSizePolicy.Expanding))
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject); lay.addWidget(btns)
    def _ok(self):
        try:
            AuthManager.setup_account(self.code.text(), self.pw.text())
            QMessageBox.information(self,"完成","管理者帳號已建立。"); self.accept()
        except Exception as e:
            QMessageBox.warning(self,"錯誤", str(e))

class LoginDialog(QDialog):
    def __init__(self, settings):
        super().__init__(); self.setWindowTitle("登入"); self.setModal(True); self.ok=False; self.settings=settings
        lay=QVBoxLayout(self); form=QFormLayout()
        self.code=QLineEdit(); self.pw=QLineEdit(); self.pw.setEchoMode(QLineEdit.Password)
        if settings.remember_code and settings.last_code: self.code.setText(settings.last_code)
        self.code.setPlaceholderText("帳號代號"); self.pw.setPlaceholderText("密碼")
        form.addRow("帳號代號", self.code); form.addRow("密　　碼", self.pw); lay.addLayout(form)
        self.rem=QCheckBox("記住帳號"); self.rem.setChecked(settings.remember_code); lay.addWidget(self.rem)
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject); lay.addWidget(btns)
    def _ok(self):
        if AuthManager.verify(self.code.text(), self.pw.text()):
            self.settings.remember_code=self.rem.isChecked()
            self.settings.last_code=self.code.text() if self.rem.isChecked() else ""
            self.settings.save(); self.ok=True; self.accept()
        else:
            QMessageBox.warning(self,"錯誤","帳號或密碼錯誤。")

class ChangeAccountDialog(QDialog):
    def __init__(self, current_code):
        super().__init__(); self.setWindowTitle("帳號設定"); self.setModal(True); self.result_new_code=None
        lay=QVBoxLayout(self); form=QFormLayout()
        self.cur_code=QLineEdit(current_code); self.cur_code.setReadOnly(True)
        self.cur_pw=QLineEdit(); self.cur_pw.setEchoMode(QLineEdit.Password)
        self.new_code=QLineEdit(); self.new_pw=QLineEdit(); self.new_pw.setEchoMode(QLineEdit.Password)
        self.new_pw2=QLineEdit(); self.new_pw2.setEchoMode(QLineEdit.Password)
        form.addRow("目前帳號代號", self.cur_code); form.addRow("目前密碼（必填）", self.cur_pw)
        form.addRow("新帳號代號", self.new_code); form.addRow("新密碼", self.new_pw); form.addRow("確認新密碼", self.new_pw2)
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addLayout(form); lay.addWidget(btns)
    def _ok(self):
        if (self.new_pw.text() or self.new_pw2.text()) and self.new_pw.text()!=self.new_pw2.text():
            QMessageBox.warning(self,"錯誤","新密碼與確認不一致。"); return
        try:
            AuthManager.change_account(self.cur_code.text(), self.cur_pw.text(), self.new_code.text(), self.new_pw.text())
            self.result_new_code=self.new_code.text().strip() or self.cur_code.text()
            QMessageBox.information(self,"完成","帳號設定已更新。"); self.accept()
        except Exception as e:
            QMessageBox.warning(self,"錯誤", str(e))

# ====================== 進入點 ======================
def main():
    info = preflight_checks()
    print("=== 啟動健檢 ===\n"+info+"\n================")

    init_db()
    app=QApplication(sys.argv)
    apply_light_theme(app)

    # 首次設定流程
    if not AuthManager.is_initialized():
        d=SetupDialog()
        if d.exec()!=QDialog.Accepted:
            QMessageBox.information(None,"離開","未設定帳號，系統關閉。")
            return

    settings=Settings.load()

    # 登入可重試
    while True:
        login=LoginDialog(settings)
        res=login.exec()
        if res==QDialog.Accepted and login.ok:
            current_code=login.code.text()
            break
        ask=QMessageBox.question(None,"未登入","尚未成功登入，是否再試一次？",
                                 QMessageBox.Yes|QMessageBox.No, QMessageBox.Yes)
        if ask==QMessageBox.No:
            return

    w=MainWindow(current_code=current_code, settings=settings)
    w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
