# -*- coding: utf-8 -*-
import os, json, base64, hashlib, hmac
from .config import AUTH_FILE

def _safe_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        try:
            os.rename(path, path + ".broken")
        except Exception:
            pass
        return None

def _hash_password(pw: str):
    import os
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return base64.b64encode(salt).decode(), base64.b64encode(dk).decode()

def _verify_password(pw: str, salt_b64: str, hash_b64: str):
    try:
        salt = base64.b64decode(salt_b64.encode())
        target = base64.b64decode(hash_b64.encode())
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return hmac.compare_digest(dk, target)

class AuthManager:
    @staticmethod
    def is_initialized():
        if not os.path.exists(AUTH_FILE): return False
        d = _safe_read_json(AUTH_FILE)
        if not d: return False
        u = d.get("user", {})
        return bool(u.get("code") and u.get("salt") and u.get("hash"))

    @staticmethod
    def setup_account(code: str, pw: str):
        if not code or not pw: raise ValueError("請輸入帳號與密碼")
        salt, h = _hash_password(pw)
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "user": {"code": code.strip(), "salt": salt, "hash": h}},
                      f, ensure_ascii=False, indent=2)

    @staticmethod
    def verify(code: str, pw: str) -> bool:
        if not os.path.exists(AUTH_FILE): return False
        d = _safe_read_json(AUTH_FILE)
        if not d: return False
        u = d.get("user", {})
        return (u.get("code") == code.strip()) and _verify_password(pw or "", u.get("salt", ""), u.get("hash", ""))
