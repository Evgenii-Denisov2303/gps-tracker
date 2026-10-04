package ru.fleet.tracker;

/** One independent retry budget per transport channel; times are monotonic. */
final class RetryPolicy {
    private int failures;
    private long retryAt;
    boolean ready(long now) { return now >= retryAt; }
    void succeeded() { failures = 0; retryAt = 0; }
    void failed(long now) {
        failures = Math.min(5, failures + 1);
        retryAt = now + Math.min(300_000, 10_000L * (1L << failures));
    }
    void networkAvailable() { retryAt = 0; }
}
