# -*- coding: utf-8 -*-
import enum
from sqlalchemy import Column, Integer, String, Date, Enum as SAEnum, Numeric, Text
from .utils.db import Base

class Shift(str, enum.Enum):
    MORNING = "早班"
    EVENING = "晚班"

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    shift = Column(SAEnum(Shift), nullable=False, index=True)
    order_no = Column(String(32), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    memo = Column(Text)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String(50), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    note = Column(Text)
