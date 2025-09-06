# app/auth.py
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .deps import get_db
from .deps import login_required

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 你專案應該已經有 User 模型；名稱略有不同請對應
# 範例：
# class User(Base):
#     _tablename_ = "users"
#     id = Column(Integer, primary_key=True)
#     username = Column(String, unique=True, index=True)
#     password_hash = Column(String)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

@router.post("/login")
async def login(request: Request,
                username: str = Form(...),
                password: str = Form(...),
                db: Session = Depends(get_db)):
    user = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = :u",
        {"u": username}
    ).mappings().first()
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤")

    # 建立 Session
    request.session["uid"] = int(user["id"])
    request.session["uname"] = user["username"]
    return {"ok": True}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@router.get("/me")
async def me(request: Request, _=Depends(login_required)):
    return {"id": request.session.get("uid"), "username": request.session.get("uname")}