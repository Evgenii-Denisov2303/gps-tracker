package ru.fleet.tracker;

/** Uses elapsed realtime, never wall clock, for cadence and parking decisions. */
final class SamplingPolicy {
    private long stillSince = -1, lastSaved = -1;
    synchronized boolean shouldSave(long elapsed, boolean moving) {
        if(moving) stillSince = -1;
        else if(stillSince < 0) stillSince = elapsed;
        long interval = stillSince >= 0 && elapsed - stillSince >= 300_000 ? 120_000 : 20_000;
        if(lastSaved < 0 || elapsed - lastSaved >= interval) { lastSaved = elapsed; return true; }
        return false;
    }
    synchronized void saveFailed() {lastSaved = -1;}
}
