import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

ph = PasswordHasher()


def hash_password(p: str) -> str:
    return ph.hash(p)


def verify_password(h: str, p: str) -> bool:
    try:
        return ph.verify(h, p)
    except VerifyMismatchError:
        return False


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(user: User, issuer: str = "Family Budget") -> str:
    return pyotp.TOTP(user.totp_secret or "").provisioning_uri(name=user.username, issuer_name=issuer)


def verify_totp(secret: str | None, code: str) -> bool:
    return bool(secret) and pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.scalar(select(User).where(User.id == uid)) if uid else None
    if not user:
        raise HTTPException(401, "not authenticated")
    return user
