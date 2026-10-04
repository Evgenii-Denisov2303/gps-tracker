from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.analytics import analyze
from app.config import Settings

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
CFG = Settings(cookie_secure=False)


def p(seconds, lat=55, lon=49, speed=0, accuracy=5, device_id=1):
    return SimpleNamespace(id=seconds, latitude=lat, longitude=lon, speed=speed,
                           accuracy=accuracy, heading=None, battery_level=80, charging=True,
                           device_id=device_id, gps_timestamp=START + timedelta(seconds=seconds), received_at=START)


def report(points, start=START, end=START + timedelta(days=1)):
    return analyze(points, CFG, start, end)


def test_parking_jitter():
    data = report([p(t, lat=55 + (t % 40) * 0.000001) for t in range(0, 601, 20)])
    assert len(data["stops"]) == 1
    assert data["stops"][0]["duration_seconds"] == 600
    assert data["summary"]["distance_km"] == 0


def test_short_stop_not_counted():
    assert report([p(0), p(100), p(200)])["stops"] == []


def test_gap_does_not_become_stop_or_distance():
    data = report([p(0), p(1200, lat=56)])
    assert data["summary"]["distance_km"] == 0
    assert data["summary"]["unknown_seconds"] == 1200
    assert data["stops"] == [] and len(data["segments"]) == 2


def test_jump_and_bad_accuracy():
    data = report([p(0), p(20, lat=60, speed=60), p(40, lat=55.00001), p(60, accuracy=500)])
    assert data["summary"]["point_count"] == 2
    assert data["summary"]["distance_km"] == 0


def test_initial_outlier():
    data = report([p(0, lat=60), p(20), p(40)])
    assert data["summary"]["point_count"] == 2


def test_motion_and_stops():
    data = report([p(t) for t in range(0, 361, 20)] + [p(380, lat=55.001, speed=20), p(400, lat=55.002, speed=20)])
    assert data["summary"]["stop_count"] == 1
    assert 0.20 < data["summary"]["distance_km"] < 0.24
    assert data["summary"]["moving_seconds"] == 40


def test_cross_midnight_clipping():
    data = report([p(t) for t in range(-300, 301, 20)])
    assert data["stops"][0]["duration_seconds"] == 300
    assert data["stops"][0]["start"] == START


def test_device_change_splits_track():
    data = report([p(0), p(20, lat=56, device_id=2)])
    assert data["summary"]["distance_km"] == 0
    assert len(data["segments"]) == 2


def test_confirmed_parking_cannot_count_as_driving():
    data = report([p(t, lat=55 + (0.0002 if t % 40 else 0), speed=1) for t in range(0, 601, 20)])
    assert data["summary"]["stop_count"] == 1
    assert data["summary"]["distance_km"] == 0
    assert data["summary"]["moving_seconds"] == 0
