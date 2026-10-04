import secrets
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .analytics import analyze
from .config import settings
from .db import get_db, utcnow
from .models import Admin, AdminSession, Device, LocationPoint, Vehicle
from .schemas import BatchIn, DeviceIn, HeartbeatIn, Login, VehicleIn
from .security import DUMMY_HASH, admin_session, owner_session, device_auth, digest, login_limit, origin_check, verify

app = FastAPI(title="Fleet GPS", docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not echo credentials or non-JSON floats from malformed input.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]})


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            size += len(msg.get("body", b""))
            if size > 512 * 1024:
                return await Response(status_code=413)(scope, receive, send)
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


app.add_middleware(BodyLimit)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    origin_check(request)
    login_limit(db, request, body.username)
    user = db.scalar(select(Admin).where(Admin.username == body.username))
    valid = verify(user.password_hash if user else DUMMY_HASH, body.password)
    if not user or not valid:
        raise HTTPException(401, "Invalid credentials")
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    old = request.cookies.get("gps_session")
    if old:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == digest(old)))
    db.execute(delete(AdminSession).where(AdminSession.expires_at <= utcnow()))
    db.add(AdminSession(token_hash=digest(raw), csrf_token=csrf, admin_id=user.id,
                        expires_at=utcnow() + timedelta(hours=settings().session_hours)))
    db.commit()
    response.set_cookie("gps_session", raw, httponly=True, secure=settings().cookie_secure,
                        samesite="strict", max_age=settings().session_hours * 3600, path="/")
    return {"username": user.username, "role": "viewer" if user.read_only else "owner",
            "csrf_token": csrf, "timezone": settings().timezone}


@app.get("/api/v1/auth/me")
def me(session=Depends(admin_session), db=Depends(get_db)):
    user = db.get(Admin, session.admin_id)
    return {"username": user.username, "role": "viewer" if user.read_only else "owner",
            "csrf_token": session.csrf_token, "timezone": settings().timezone}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(response: Response, session=Depends(admin_session), db=Depends(get_db)):
    db.delete(session)
    db.commit()
    response.delete_cookie("gps_session", path="/", secure=settings().cookie_secure,
                           httponly=True, samesite="strict")


def vehicle_or_404(db, vehicle_id):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    return vehicle


@app.get("/api/v1/vehicles", dependencies=[Depends(admin_session)])
def vehicles(db=Depends(get_db)):
    return [{"id": v.id, "name": v.name, "plate": v.plate, "description": v.description,
             "active": v.active} for v in db.scalars(select(Vehicle).order_by(Vehicle.id))]


@app.post("/api/v1/vehicles", status_code=201, dependencies=[Depends(owner_session)])
def create_vehicle(body: VehicleIn, db=Depends(get_db)):
    v = Vehicle(**body.model_dump())
    db.add(v)
    db.commit()
    return {"id": v.id, "name": v.name}


@app.get("/api/v1/vehicles/{vehicle_id}/devices", dependencies=[Depends(owner_session)])
def devices(vehicle_id: int, db=Depends(get_db)):
    vehicle_or_404(db, vehicle_id)
    return [{"id": d.id, "name": d.name, "active": d.active, "last_seen": d.last_seen}
            for d in db.scalars(select(Device).where(Device.vehicle_id == vehicle_id).order_by(Device.id))]


@app.post("/api/v1/vehicles/{vehicle_id}/devices", status_code=201, dependencies=[Depends(owner_session)])
def create_device(vehicle_id: int, body: DeviceIn, db=Depends(get_db)):
    vehicle_or_404(db, vehicle_id)
    raw = secrets.token_urlsafe(32)
    d = Device(vehicle_id=vehicle_id, name=body.name, token_hash=digest(raw))
    db.add(d)
    db.commit()
    return {"id": d.id, "token": raw, "message": "Token is shown only once"}


@app.delete("/api/v1/devices/{device_id}", status_code=204, dependencies=[Depends(owner_session)])
def revoke_device(device_id: int, db=Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    device.active = False
    db.commit()


@app.post("/api/v1/locations")
def locations(body: BatchIn, device=Depends(device_auth), db=Depends(get_db)):
    now = utcnow()
    if any(p.gps_timestamp > now + timedelta(minutes=2) for p in body.points):
        raise HTTPException(422, "GPS time is in the future; correct device clock")
    rows = [dict(p.model_dump(), event_id=str(p.event_id), device_id=device.id,
                 vehicle_id=device.vehicle_id, received_at=now) for p in body.points]
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(LocationPoint).values(rows).on_conflict_do_nothing(
        index_elements=[LocationPoint.device_id, LocationPoint.event_id]).returning(LocationPoint.id)
    accepted = len(db.execute(stmt).all())
    device.last_seen = now
    db.commit()
    return {"accepted": accepted, "acknowledged": [str(p.event_id) for p in body.points],
            "server_time": now}


@app.get("/api/v1/vehicles/{vehicle_id}/latest", dependencies=[Depends(admin_session)])
def latest(vehicle_id: int, db=Depends(get_db)):
    vehicle_or_404(db, vehicle_id)
    cfg = settings()
    recent = list(reversed(list(db.scalars(select(LocationPoint).where(LocationPoint.vehicle_id == vehicle_id).order_by(
                       LocationPoint.gps_timestamp.desc(), LocationPoint.id.desc()).limit(64)))))
    segments = analyze(recent, cfg, recent[0].gps_timestamp,
                       recent[-1].gps_timestamp + timedelta(microseconds=1))["segments"] if recent else []
    point = segments[-1][-1] if segments else None
    device = db.scalar(select(Device).where(Device.vehicle_id == vehicle_id,
                        Device.active.is_(True), Device.last_seen.is_not(None)).order_by(Device.last_seen.desc(), Device.id.desc()).limit(1))
    contact = device.last_seen if device else None
    contact_age = max(0, int((utcnow() - contact).total_seconds())) if contact else None
    connection = "offline" if contact_age is None or contact_age >= cfg.offline_seconds else "stale" if contact_age >= cfg.stale_seconds else "fresh"
    health = dict(device.health, received_at=device.heartbeat_at,
                  age_seconds=max(0, int((utcnow() - device.heartbeat_at).total_seconds()))) if device and device.health and device.heartbeat_at else None
    age = max(0, int((utcnow() - point["gps_timestamp"]).total_seconds())) if point else None
    status = "offline" if age is None or age >= cfg.offline_seconds else "stale" if age >= cfg.stale_seconds else "fresh"
    return {"point": point, "status": status,
            "age_seconds": age, "last_contact": contact,
            "stale_seconds": cfg.stale_seconds, "offline_seconds": cfg.offline_seconds,
            "connection_status": connection, "contact_age_seconds": contact_age, "device_health": health}


@app.post("/api/v1/heartbeat")
def heartbeat(body: HeartbeatIn, device=Depends(device_auth), db=Depends(get_db)):
    # Receipt time is authoritative. Heartbeats are snapshots, never queued GPS history.
    now = utcnow()
    device.last_seen = now
    device.heartbeat_at = now
    device.health = body.model_dump()
    db.commit()
    return {"server_time": now}


def day_report(db, vehicle_id, day):
    vehicle_or_404(db, vehicle_id)
    cfg = settings()
    zone = ZoneInfo(cfg.timezone)
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    context = timedelta(seconds=cfg.stop_seconds + cfg.max_gap_seconds)
    rows = list(db.scalars(select(LocationPoint).where(LocationPoint.vehicle_id == vehicle_id,
                          LocationPoint.gps_timestamp >= start - context,
                          LocationPoint.gps_timestamp < end + context).order_by(LocationPoint.gps_timestamp, LocationPoint.id)))
    return dict(analyze(rows, cfg, start, end), date=day, timezone=cfg.timezone)


@app.get("/api/v1/vehicles/{vehicle_id}/route", dependencies=[Depends(admin_session)])
def route(vehicle_id: int, date: date = Query(ge=date(2020, 1, 1), le=date(2100, 1, 1)), db=Depends(get_db)):
    return day_report(db, vehicle_id, date)


@app.get("/api/v1/vehicles/{vehicle_id}/stops", dependencies=[Depends(admin_session)])
def stops(vehicle_id: int, date: date = Query(ge=date(2020, 1, 1), le=date(2100, 1, 1)), db=Depends(get_db)):
    return day_report(db, vehicle_id, date)["stops"]


web = Path(settings().web_dir)
if web.is_dir():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
