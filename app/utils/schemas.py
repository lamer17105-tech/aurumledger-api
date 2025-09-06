from pydantic import BaseModel, Field
from typing import Optional, List

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserLoginIn(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str

class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., ge=0)
    note: Optional[str] = None

class ItemOut(ItemIn):
    id: int

class PageOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ItemOut]
