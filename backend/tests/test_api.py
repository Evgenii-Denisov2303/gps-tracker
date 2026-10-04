from datetime import timedelta
from uuid import uuid4

from app.db import utcnow


def point(**extra):
    return dict({"event_id": str(uuid4()), "latitude": 55.79, "longitude": 49.12,
                 "accuracy": 8, "speed": 0, "battery_level": 82, "charging": True,
                 "gps_timestamp": utcnow().isoformat()}, **extra)


def send(c, device, points):
    return c.post("/api/v1/locations", headers={"Authorization": "Bearer " + device["token"]}, json={"points": points})


def test_private_endpoints(client):
    for path in ("vehicles", "vehicles/1/latest", "vehicles/1/route?date=2026-10-03", "vehicles/1/stops?date=2026-10-03", "vehicles/1/devices"):
        assert client.get("/api/v1/" + path).status_code == 401
    assert client.post("/api/v1/locations", json={"points": [point()]}).status_code == 401


def test_csrf_logout(owner):
    assert owner.get("/api/v1/auth/me").status_code == 200
    assert owner.post("/api/v1/vehicles", headers={"X-CSRF-Token": "wrong"}, json={"name": "bad"}).status_code == 403
    assert owner.post("/api/v1/vehicles", headers={"Origin": "https://evil.test"}, json={"name": "bad"}).status_code == 403
    assert owner.post("/api/v1/auth/logout").status_code == 204
    assert owner.get("/api/v1/vehicles").status_code == 401


def test_duplicate_and_out_of_order(tracker):
    c, v, d = tracker
    newest = point()
    old = point(gps_timestamp=(utcnow() - timedelta(hours=1)).isoformat())
    assert send(c, d, [newest, newest]).json()["accepted"] == 1
    assert send(c, d, [newest, old]).json()["accepted"] == 1
    data = c.get(f"/api/v1/vehicles/{v}/latest").json()
    assert data["status"] == "fresh"
    assert data["point"]["gps_timestamp"] == newest["gps_timestamp"]


def test_old_upload_is_not_live(tracker):
    c, v, d = tracker
    assert send(c, d, [point(gps_timestamp=(utcnow() - timedelta(hours=2)).isoformat())]).status_code == 200
    data = c.get(f"/api/v1/vehicles/{v}/latest").json()
    assert data["status"] == "offline" and data["last_contact"]


def test_revocation(tracker):
    c, v, d = tracker
    assert c.delete(f'/api/v1/devices/{d["id"]}').status_code == 204
    assert send(c, d, [point()]).status_code == 401


def test_token_cannot_access_owner_api(client):
    client.headers["Authorization"] = "Bearer fake-device-token"
    assert client.get("/api/v1/vehicles").status_code == 401


def test_validation(tracker):
    c, v, d = tracker
    for p in (point(latitude=91), point(gps_timestamp="2026-01-01T12:00:00"),
              point(gps_timestamp=(utcnow() + timedelta(days=1)).isoformat()), point(vehicle_id=999)):
        assert send(c, d, [p]).status_code == 422
    assert send(c, d, [point()] * 501).status_code == 422
    assert c.post("/api/v1/locations", content=b"x" * (512 * 1024 + 1)).status_code == 413


def test_login_rate_limit(client):
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 429


def test_timezone_day_boundary(tracker):
    c, v, d = tracker
    points = [point(gps_timestamp="2026-01-01T20:59:00Z"), point(gps_timestamp="2026-01-01T21:01:00Z")]
    assert send(c, d, points).status_code == 200
    data = c.get(f"/api/v1/vehicles/{v}/route?date=2026-01-02").json()
    assert data["summary"]["point_count"] == 1
    assert data["timezone"] == "Europe/Moscow"


def test_device_vehicle_binding(tracker):
    c, v, d = tracker
    second = c.post("/api/v1/vehicles", json={"name": "Second"}).json()["id"]
    send(c, d, [point()])
    assert c.get(f"/api/v1/vehicles/{second}/latest").json()["point"] is None


def test_no_cache_on_private_api(owner):
    assert owner.get("/api/v1/vehicles").headers["cache-control"] == "no-store"


def test_login_cookie_security(client):
    response = client.post("/api/v1/auth/login", json={"username": "owner", "password": "test-password-123"})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_nonfinite_is_rejected(tracker):
    import json
    c, v, d = tracker
    data = json.dumps({"points": [point(latitude=float('nan'))]})
    response = c.post("/api/v1/locations", content=data, headers={"Content-Type": "application/json", "Authorization": "Bearer " + d["token"]})
    assert response.status_code == 422


def test_invalid_date_bounds(tracker):
    c, v, d = tracker
    for day in ('0001-01-01', '9999-12-31', 'not-a-date'):
        assert c.get(f"/api/v1/vehicles/{v}/route?date={day}").status_code == 422


def test_latest_ignores_jump(tracker):
    c, v, d = tracker
    now = utcnow()
    send(c, d, [point(gps_timestamp=(now - timedelta(seconds=40)).isoformat()),
                point(gps_timestamp=(now - timedelta(seconds=20)).isoformat()),
                point(latitude=70)])
    assert c.get(f"/api/v1/vehicles/{v}/latest").json()["point"]["latitude"] == 55.79
