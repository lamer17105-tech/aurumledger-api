from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from passlib.context import CryptContext
from .db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd.verify(plain, hashed)
    except Exception:
        return False

def _user_count(db: Session) -> int:
    return db.execute(text("SELECT COUNT(*) AS c FROM users")).mappings().first()["c"]

# 受保護依賴
def login_required(request: Request):
    if not request.session.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登入")
    return True

@router.get("/has-user")
def has_user(db: Session = Depends(get_db)):
    return {"has_user": _user_count(db) > 0}

@router.post("/setup")
def setup_first_user(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if _user_count(db) > 0:
        raise HTTPException(400, "已存在使用者，請改用登入")
    db.execute(text("INSERT INTO users(username, password_hash) VALUES(:u, :p)"), {"u": username, "p": hash_password(password)})
    db.commit()
    return {"ok": True}

@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    row = db.execute(text("SELECT id, username, password_hash FROM users WHERE username = :u"), {"u": username}).mappings().first()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤")
    request.session["uid"] = int(row["id"])
    request.session["uname"] = row["username"]
    return {"ok": True}

@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@router.get("/me")
def me(request: Request, _=Depends(login_required)):
    return {"id": request.session.get("uid"), "username": request.session.get("uname")}

@router.post("/change-credentials")
def change_credentials(
    request: Request,
    current_password: str = Form(...),
    new_username: str = Form(None),
    new_password: str = Form(None),
    db: Session = Depends(get_db),
    _=Depends(login_required),
):
    uid = int(request.session["uid"]) if request.session.get("uid") else None
    row = db.execute(text("SELECT id, username, password_hash FROM users WHERE id = :i"), {"i": uid}).mappings().first()
    if not row or not verify_password(current_password, row["password_hash"]):
        raise HTTPException(400, "目前密碼不正確")

    updates = {}
    if new_username and new_username != row["username"]:
        dup = db.execute(text("SELECT 1 FROM users WHERE username = :u AND id != :i"), {"u": new_username, "i": uid}).first()
        if dup:
            raise HTTPException(400, "此帳號已被使用")
        updates["username"] = new_username
    if new_password:
        updates["password_hash"] = hash_password(new_password)

    if updates:
        sets = ", ".join([f"{k} = :{k}" for k in updates.keys()])
        updates["id"] = uid
        db.execute(text(f"UPDATE users SET {sets} WHERE id = :id"), updates)
        db.commit()
        if "username" in updates:
            request.session["uname"] = updates["username"]

    return {"ok": True}