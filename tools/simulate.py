"""Send clearly synthetic GPS data to a dedicated demo vehicle; no direct DB writes."""
import argparse
import getpass
import json
import math
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()
    token = os.environ.get("GPS_DEVICE_TOKEN") or getpass.getpass("Device token for DEMO vehicle: ")
    start = datetime.now(timezone.utc) - timedelta(minutes=45)
    points = []
    # A fictional route near Kazan. Two stationary groups; no real person's movement.
    for i in range(136):
        if i < 35:
            fraction = i / 35
        elif i < 65:
            fraction = 1
        elif i < 105:
            fraction = 1 + (i - 65) / 40
        else:
            fraction = 2
        moving = i < 35 or 65 <= i < 105
        lat = 55.790 + .009 * fraction
        lon = 49.115 + .018 * fraction + .002 * math.sin(fraction * math.pi)
        points.append({"event_id": str(uuid4()), "latitude": lat, "longitude": lon,
                       "accuracy": 6, "speed": 16 if moving else 0, "battery_level": 82,
                       "charging": True, "gps_timestamp": (start + timedelta(seconds=i * 20)).isoformat()})
    request = urllib.request.Request(args.url.rstrip("/") + "/api/v1/locations",
                                     data=json.dumps({"points": points}).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    print(f"Sent {len(points)} fictional points; inserted {result['accepted']}. Select today in the website.")


if __name__ == "__main__":
    main()
