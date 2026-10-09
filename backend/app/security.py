import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import settings
from .db import get_db, utcnow
from .models import Admin, AdminSession, Device, LoginLimit, Vehicle

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def origin_check(request):
    if request.headers.get("origin") != settings().public_origin.rstrip("/"):
        raise HTTPException(403, "Untrusted origin")


def admin_session(request: Request, db=Depends(get_db)):
    token = request.cookies.get("gps_session", "")
    session = db.get(AdminSession, digest(token)) if token else None
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "Login required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin_check(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
            raise HTTPException(403, "Invalid CSRF token")
    return session


def device_auth(request: Request, db=Depends(get_db)):
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    device = db.scalar(select(Device).where(Device.token_hash == digest(token), Device.active.is_(True))) if token else None
    if not device or device.kind != "android" or not db.get(Vehicle, device.vehicle_id).active:
        raise HTTPException(401, "Invalid device token")
    return device


def owner_session(session=Depends(admin_session), db=Depends(get_db)):
    user = db.get(Admin, session.admin_id)
    if not user or user.read_only:
        raise HTTPException(403, "Owner access required")
    return session


def login_limit(db, request, username):
    # Persistent and atomic across API workers; proxy headers are not trusted.
    # Account key protects passwords even with many source addresses.
    for raw_key, limit in (("ip:" + (request.client.host if request.client else "unknown"), 60),
                           ("user:" + username, 10)):
        key = digest(raw_key)
        now = utcnow()
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = insert(LoginLimit).values(key=key, count=1, reset_at=now + timedelta(minutes=15))
        from sqlalchemy import case
        stmt = stmt.on_conflict_do_update(index_elements=[LoginLimit.key], set_={
            "count": case((LoginLimit.reset_at <= now, 1), else_=LoginLimit.count + 1),
            "reset_at": case((LoginLimit.reset_at <= now, now + timedelta(minutes=15)), else_=LoginLimit.reset_at),
        }).returning(LoginLimit.count)
        count = db.execute(stmt).scalar_one()
        db.commit()
        if count > limit:
            raise HTTPException(429, "Too many attempts; retry in 15 minutes", headers={"Retry-After": "900"})
