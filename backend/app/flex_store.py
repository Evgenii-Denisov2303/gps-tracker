"""Commit telemetry before acknowledging it. Archive upload is not live GPS."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import SessionLocal, utcnow
from .flex import ProtocolError
from .models import Device, HardwareRecord, LocationPoint, Vehicle


class Store:
    def __init__(self, factory=SessionLocal):
        self.factory = factory

    @staticmethod
    def device(db, imei):
        device = db.scalar(select(Device).join(Vehicle, Vehicle.id == Device.vehicle_id).where(
            Device.imei == imei, Device.kind == 'navtelecom', Device.active.is_(True), Vehicle.active.is_(True)))
        if device is None:
            raise ProtocolError('Device unavailable')
        return device

    def authorize(self, imei):
        with self.factory() as db:
            self.device(db, imei)

    def save(self, imei, records):
        now = utcnow()
        with self.factory() as db:
            device = self.device(db, imei)  # Recheck revocation on EVERY packet.
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            for fields in records:
                if any(isinstance(v, float) and not math.isfinite(v) for v in fields.values()):
                    raise ProtocolError('Nonfinite telemetry')
                event_time = datetime.fromtimestamp(fields[3], timezone.utc)
                if event_time.year < 2020 or event_time > now + timedelta(minutes=2):
                    raise ProtocolError('Invalid event clock')
                gps_time = datetime.fromtimestamp(fields.get(9, 0), timezone.utc)
                nav = fields.get(8, 0)
                lat, lon = fields.get(10, 0)/600000, fields.get(11, 0)/600000
                reason = None
                if not {8, 9, 10, 11, 13, 14}.issubset(fields):
                    reason = 'missing_navigation_fields'
                elif not nav & 2 or nav >> 2 < 3:
                    reason = 'invalid_navigation'
                elif gps_time.year < 2020 or gps_time > event_time + timedelta(seconds=2) or event_time - gps_time > timedelta(seconds=120):
                    reason = 'stale_navigation'
                elif not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= fields[13] <= 400 and 0 <= fields[14] <= 360):
                    reason = 'invalid_navigation_values'
                # Persist rejected navigation as diagnostics too. A valid protocol
                # record is not silently discarded when the black box gets its ACK.
                raw = json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False)
                key = hashlib.sha256(raw.encode()).hexdigest()
                db.execute(insert(HardwareRecord).values(device_id=device.id, record_hash=key,
                    event_at=event_time, received_at=now, fields=json.loads(raw), rejection=reason
                ).on_conflict_do_nothing(index_elements=['device_id', 'record_hash']))
                if reason is None:
                    # Archive/current/priority retransmissions of a fix collapse to
                    # one point even when the enclosing event index differs.
                    event_id = str(uuid5(NAMESPACE_URL, f'flex:{device.id}:{fields[9]}'))
                    db.execute(insert(LocationPoint).values(event_id=event_id,
                        device_id=device.id, vehicle_id=device.vehicle_id, latitude=lat, longitude=lon,
                        accuracy=None, speed=fields[13], heading=fields[14] % 360,
                        gps_timestamp=gps_time, received_at=now
                    ).on_conflict_do_nothing(index_elements=['device_id', 'event_id']))
                # Never present an old black-box event as current power/navigation.
                if (abs((now-event_time).total_seconds()) <= 120 and
                        (not device.health or event_time.timestamp() >= device.health.get('event_timestamp', 0))):
                    device.heartbeat_at = event_time
                    device.health = dict(kind='navtelecom', event_timestamp=fields[3],
                        gps_enabled=bool(nav & 1), navigation_valid=reason is None,
                        satellites=nav >> 2, gsm_level=fields.get(7),
                        main_voltage=fields[19]/1000 if 19 in fields else None,
                        backup_voltage=fields[20]/1000 if 20 in fields else None,
                        navigation_problem=reason)
            device.last_seen = now
            db.commit()
