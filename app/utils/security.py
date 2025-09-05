# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .utils.config import JWT_SECRET, JWT_ALG

bearer = HTTPBearer(auto_error=False)

def create_token(sub: str, claims: Dict, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        **claims
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已過期")
    except Exception:
        raise HTTPException(status_code=401, detail="Token 無效")

def get_current_token(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="缺少憑證")
    return decode_token(creds.credentials)

def require_revenue_token(tok: dict = Depends(get_current_token)) -> dict:
    if not tok.get("rev", False):
        raise HTTPException(status_code=403, detail="尚未通過營業額二次驗證")
    return tok
