import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import LoginIn, UserOut
from app.db import get_db
from app.models import User
from app.security import current_user, verify_password, verify_totp

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Simple per-process brute-force limiter: 5 failures per 15 minutes per username+IP.
_FAILS: dict[str, deque[float]] = defaultdict(deque)
WINDOW, MAX_FAILS = 900, 5


def _key(req: Request, username: str) -> str:
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "?").split(",")[0].strip()
    return f"{username.lower()}|{ip}"


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key, now = _key(request, body.username), time.monotonic()
    fails = _FAILS[key]
    while fails and now - fails[0] > WINDOW:
        fails.popleft()
    if len(fails) >= MAX_FAILS:
        raise HTTPException(429, "too many attempts, try later")
    user = db.scalar(select(User).where(User.username == body.username))
    if not (user and verify_password(user.password_hash, body.password) and verify_totp(user.totp_secret, body.code)):
        fails.append(now)
        raise HTTPException(401, "invalid credentials")
    fails.clear()
    request.session.clear()
    request.session["uid"] = user.id
    return user


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
