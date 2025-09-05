from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db import get_db
from .models import User
from .utils.security import decode_token

auth_scheme = HTTPBearer()

def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(cred.credentials)
        username = payload.get("sub")
        if not username:
            raise ValueError("no sub")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError("no user")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
