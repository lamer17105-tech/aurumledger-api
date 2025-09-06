from sqlalchemy import Column, Integer, String, Date, Numeric, Text, Index
from .db import Base, engine

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_no = Column(String(64), index=True, nullable=False)
    date = Column(Date, nullable=False)
    customer = Column(String(128))
    total = Column(Numeric(12, 2), nullable=False)
    status = Column(String(16), default="open")
    notes = Column(Text)
    __table_args__ = (Index("ix_orders_no_date", "order_no", "date"),)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    category = Column(String(64), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    owner = Column(String(64))
    note = Column(Text)
    __table_args__ = (Index("ix_expenses_date_cat", "date", "category"),)

# 啟動時確保表存在
def ensure_tables(_engine=engine):
    Base.metadata.create_all(bind=_engine)