'use strict';
function trackerState(latest, elapsed = 0) {
  elapsed = Math.max(0, elapsed);
  const age = latest.age_seconds == null ? null : latest.age_seconds + elapsed;
  const contactAge = latest.contact_age_seconds == null ? null : latest.contact_age_seconds + elapsed;
  const connection = contactAge == null || contactAge >= latest.offline_seconds ? 'offline' : contactAge >= latest.stale_seconds ? 'stale' : 'fresh';
  const health = latest.device_health;
  const healthFresh = Boolean(health && health.age_seconds + elapsed < latest.stale_seconds);
  const gpsFresh = age != null && age < latest.stale_seconds &&
    (!healthFresh || (health.gps_enabled !== false && health.location_permission !== false));
  const siteFresh = elapsed <= 45;
  const point = latest.point;
  const useHealthBattery = health?.battery_level != null && (!point || Date.parse(health.received_at) >= Date.parse(point.gps_timestamp));
  const battery = useHealthBattery ? health : point;
  return {age, contactAge, connection, healthFresh, gpsFresh, siteFresh,
    state: !siteFresh ? 'stale' : connection !== 'fresh' ? connection : gpsFresh ? 'fresh' : 'stale',
    speed: siteFresh && connection === 'fresh' && gpsFresh ? point?.speed ?? null : null,
    battery, batteryFresh: siteFresh && (useHealthBattery ? healthFresh : gpsFresh)};
}
if (typeof module !== 'undefined') module.exports = {trackerState};
