package ru.fleet.tracker;

/** UTC from the phone clock, adjusted by the fix's monotonic age. */
final class FixTime {
    private static final long MIN_TIME_MS = 1577836800000L;
    private static final long MAX_AGE_NS = 120_000_000_000L;

    private FixTime() {}

    static long timestampMillis(long wallTimeMs, long elapsedNowNs, long fixElapsedNs) {
        if (wallTimeMs < MIN_TIME_MS || fixElapsedNs < 0 || elapsedNowNs < fixElapsedNs) return -1;
        long ageNs = elapsedNowNs - fixElapsedNs;
        if (ageNs > MAX_AGE_NS) return -1;
        long timestamp = wallTimeMs - ageNs / 1_000_000L;
        return timestamp >= MIN_TIME_MS ? timestamp : -1;
    }
}
