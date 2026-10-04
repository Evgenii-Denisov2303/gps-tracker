from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func

from app.db import get_db, utcnow
from app.main import app
from app.models import Device, LocationPoint


def payload(**changes):
    return dict(app_version="1.0.2", battery_level=82, charging=True,
                gps_enabled=True, location_permission=True, background_permission=True,
                battery_optimization_exempt=True, gps_age_seconds=None, queue_count=0, **changes)


def beat(c, d, data=None):
    return c.post('/api/v1/heartbeat', json=data or payload(), headers={'Authorization': 'Bearer '+d['token']})


def test_heartbeat_without_gps_does_not_invent_position(tracker):
    c, v, d = tracker
    assert beat(c, d).status_code == 200
    latest = c.get(f'/api/v1/vehicles/{v}/latest').json()
    assert latest['connection_status'] == 'fresh'
    assert latest['status'] == 'offline' and latest['point'] is None
    assert latest['device_health']['battery_level'] == 82
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(LocationPoint)) == 0


def test_heartbeat_does_not_refresh_old_gps(tracker):
    c, v, d = tracker
    p = dict(event_id=str(uuid4()), latitude=55.79, longitude=49.12, accuracy=10,
             gps_timestamp=(utcnow()-timedelta(hours=2)).isoformat(), speed=20)
    assert c.post('/api/v1/locations',json={'points':[p]},headers={'Authorization':'Bearer '+d['token']}).status_code == 200
    beat(c,d)
    latest=c.get(f'/api/v1/vehicles/{v}/latest').json()
    assert latest['status']=='offline' and latest['age_seconds']>=7190
    assert latest['connection_status']=='fresh'
    assert latest['point']['gps_timestamp']==p['gps_timestamp']


def test_heartbeat_snapshot_expires_and_old_client_still_works(tracker):
    c,v,d=tracker
    beat(c,d)
    with next(app.dependency_overrides[get_db]()) as db:
        row=db.get(Device,d['id']); row.last_seen=row.heartbeat_at=utcnow()-timedelta(minutes=11); db.commit()
    latest=c.get(f'/api/v1/vehicles/{v}/latest').json()
    assert latest['connection_status']=='offline'
    assert latest['device_health']['age_seconds']>=660
    p=dict(event_id=str(uuid4()),latitude=55.79,longitude=49.12,accuracy=10,gps_timestamp=utcnow().isoformat())
    assert c.post('/api/v1/locations',json={'points':[p]},headers={'Authorization':'Bearer '+d['token']}).status_code==200
    latest=c.get(f'/api/v1/vehicles/{v}/latest').json()
    assert latest['connection_status']=='fresh' and latest['status']=='fresh'
    assert latest['device_health']['age_seconds']>=660


def test_heartbeat_requires_active_device_not_website_session(tracker):
    c,v,d=tracker
    assert c.post('/api/v1/heartbeat',json=payload()).status_code==401
    assert c.post('/api/v1/heartbeat',json=payload(),headers={'Authorization':'Bearer bad'}).status_code==401
    c.delete(f'/api/v1/devices/{d["id"]}')
    assert beat(c,d).status_code==401


@pytest.mark.parametrize('field,value',[('battery_level',101),('queue_count',-1),('gps_age_seconds',-1),('app_version','<script>'),('vehicle_id',999),('latitude',55)])
def test_invalid_heartbeat_rejected(tracker,field,value):
    c,v,d=tracker
    data=payload(); data[field]=value
    assert beat(c,d,data).status_code==422
    assert c.get(f'/api/v1/vehicles/{v}/latest').json()['last_contact'] is None


def test_heartbeat_binding_and_revoked_health_not_used(tracker):
    c,v,d=tracker
    second=c.post('/api/v1/vehicles',json={'name':'Second'}).json()['id']
    beat(c,d)
    assert c.get(f'/api/v1/vehicles/{second}/latest').json()['device_health'] is None
    c.delete(f'/api/v1/devices/{d["id"]}')
    latest=c.get(f'/api/v1/vehicles/{v}/latest').json()
    assert latest['device_health'] is None and latest['last_contact'] is None
