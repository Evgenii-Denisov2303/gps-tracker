"""Conservative GPS estimates: gaps are unknown, never inferred parking/driving."""
from datetime import datetime
from math import asin, cos, radians, sin, sqrt


def distance(a, b):
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    dlat, dlon = lat2 - lat1, radians(b.longitude - a.longitude)
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(min(1, sqrt(h)))


def serialize(p):
    return {k: getattr(p, k) for k in (
        "id", "latitude", "longitude", "speed", "accuracy", "heading",
        "battery_level", "charging", "gps_timestamp", "received_at")}


def analyze(rows, cfg, start: datetime, end: datetime):
    candidates = [p for p in rows if (p.accuracy is None or p.accuracy <= cfg.max_accuracy_m)
                  and (p.speed is None or p.speed <= cfg.max_speed_kmh)]
    accepted = []
    rejected = len(rows) - len(candidates)
    for i, p in enumerate(candidates):
        # An isolated leading outlier must not poison the subsequent track.
        if not accepted and i + 2 < len(candidates):
            b, c = candidates[i + 1:i + 3]
            dt = (b.gps_timestamp - p.gps_timestamp).total_seconds()
            dt2 = (c.gps_timestamp - b.gps_timestamp).total_seconds()
            if (0 < dt <= cfg.max_gap_seconds and 0 < dt2 <= cfg.max_gap_seconds
                    and distance(p, b) / dt * 3.6 > cfg.max_speed_kmh
                    and distance(b, c) / dt2 * 3.6 <= cfg.max_speed_kmh):
                rejected += 1
                continue
        if accepted:
            prev = accepted[-1]
            dt = (p.gps_timestamp - prev.gps_timestamp).total_seconds()
            if dt <= 0:
                rejected += 1
                continue
            if (prev.device_id == p.device_id and dt <= cfg.max_gap_seconds
                    and distance(prev, p) / dt * 3.6 > cfg.max_speed_kmh):
                rejected += 1
                continue
        accepted.append(p)

    stops, segments, current_segment, cluster = [], [], [], []
    meters = moving = unknown = 0.0
    travel_intervals = []

    def overlap(a, b):
        return max(0, (min(b, end) - max(a, start)).total_seconds())

    def finish_stop():
        if len(cluster) < 2:
            return
        first, last = cluster[0], cluster[-1]
        if (last.gps_timestamp - first.gps_timestamp).total_seconds() < cfg.stop_seconds:
            return
        duration = overlap(first.gps_timestamp, last.gps_timestamp)
        if duration:
            stops.append({
                "latitude": sum(p.latitude for p in cluster) / len(cluster),
                "longitude": sum(p.longitude for p in cluster) / len(cluster),
                "start": max(first.gps_timestamp, start),
                "end": min(last.gps_timestamp, end),
                "duration_seconds": round(duration),
                "ongoing": last is accepted[-1],
            })

    for i, p in enumerate(accepted):
        in_day = start <= p.gps_timestamp < end
        prev = accepted[i - 1] if i else None
        dt = (p.gps_timestamp - prev.gps_timestamp).total_seconds() if prev else 0
        gap = prev and (dt > cfg.max_gap_seconds or p.device_id != prev.device_id)
        if gap:
            unknown += overlap(prev.gps_timestamp, p.gps_timestamp)
            if current_segment:
                segments.append(current_segment)
            current_segment = []
            finish_stop()
            cluster = []
        if in_day:
            current_segment.append(serialize(p))
        slow = p.speed is None or p.speed <= 3
        if cluster and (not slow or distance(cluster[0], p) > cfg.stop_radius_m):
            finish_stop()
            cluster = []
        if slow:
            cluster.append(p)
        if prev and not gap:
            d = distance(prev, p)
            both_slow = slow and (prev.speed is None or prev.speed <= 3)
            # Suppress parking jitter; slow travel beyond the noise floor still counts.
            jitter = both_slow and d <= min(cfg.stop_radius_m, max(10, prev.accuracy or 0, p.accuracy or 0))
            if not jitter:
                travel_intervals.append((prev.gps_timestamp, p.gps_timestamp, d, dt))
    finish_stop()
    # A confirmed stationary cluster must not also add low-speed jitter to driving.
    for a, b, d, dt in travel_intervals:
        seconds = overlap(a, b)
        seconds -= sum(max(0, (min(b, s["end"]) - max(a, s["start"])).total_seconds()) for s in stops)
        seconds = max(0, seconds)
        meters += d * seconds / dt
        moving += seconds
    if current_segment:
        segments.append(current_segment)
    points = [p for p in accepted if start <= p.gps_timestamp < end]
    return {
        "segments": segments, "stops": stops,
        "summary": {
            "distance_km": round(meters / 1000, 2),
            "first_point": points[0].gps_timestamp if points else None,
            "last_point": points[-1].gps_timestamp if points else None,
            "max_speed_kmh": max((p.speed or 0 for p in points), default=0),
            "moving_seconds": round(moving),
            "stopped_seconds": sum(s["duration_seconds"] for s in stops),
            "unknown_seconds": round(unknown),
            "stop_count": len(stops), "point_count": len(points),
            "filtered_points": rejected,
        },
    }
