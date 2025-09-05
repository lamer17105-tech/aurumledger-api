# models.py
import os
import enum
from sqlalchemy import create_engine, Column, Integer, String, Date, Enum, Numeric, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.getenv("RESTO_DB", "resto.db")
engine = create_engine(f"sqlite:///{DB_PATH}", future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

class Shift(str, enum.Enum):
    MORNING = "早班"
    EVENING = "晚班"

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)            # 訂單日期
    shift = Column(Enum(Shift), nullable=False)    # 早班/晚班
    order_no = Column(String(32), nullable=False)  # 單號（如 10037 或 37）
    amount = Column(Numeric(14,2), nullable=False) # 金額（如 2568）
    memo = Column(Text, nullable=True)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)            # 支出日期
    category = Column(String(50), nullable=False)  # 分類
    amount = Column(Numeric(14,2), nullable=False) # 金額
    note = Column(Text, nullable=True)

def init_db():
    Base.metadata.create_all(engine)
