"""JWT authentication for GEO Analyzer — extracted from EntityOS."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from fastapi import HTTPException, Request

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, PLAN_LIMITS
from db import get_db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    payload = decode_token(auth[7:])
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    db.close()
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)


def check_usage_limit(user: dict) -> bool:
    """Check if user has remaining analyses for today."""
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = db.execute(
        "SELECT COUNT(*) FROM usage_log WHERE user_id = ? AND created_at >= ?",
        (user["id"], today),
    ).fetchone()[0]
    db.close()
    limit = PLAN_LIMITS.get(user.get("plan", "free"), 3)
    return count < limit


def log_usage(user_id: int, action: str, url: str = ""):
    db = get_db()
    db.execute(
        "INSERT INTO usage_log (user_id, action, url) VALUES (?, ?, ?)",
        (user_id, action, url),
    )
    db.commit()
    db.close()
