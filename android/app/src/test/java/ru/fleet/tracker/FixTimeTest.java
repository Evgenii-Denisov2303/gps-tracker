package ru.fleet.tracker;

import org.junit.Test;
import static org.junit.Assert.*;

public class FixTimeTest {
    private static final long OCTOBER_4_2026 = 1791122700000L;
    private static final long NOW_NS = 900_000_000_000L;

    @Test public void freshFixUsesPhoneCalendarInsteadOfGpsCalendar() {
        assertEquals(OCTOBER_4_2026, FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, NOW_NS));
    }
    @Test public void delayedFixKeepsMeasurementTime() {
        assertEquals(OCTOBER_4_2026 - 45_000,
            FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, NOW_NS - 45_000_000_000L));
    }
    @Test public void twoMinuteBoundaryIsAccepted() {
        assertEquals(OCTOBER_4_2026 - 120_000,
            FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, NOW_NS - 120_000_000_000L));
    }
    @Test public void oldFixIsRejected() {
        assertEquals(-1, FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, NOW_NS - 120_000_000_001L));
    }
    @Test public void futureOrInvalidMonotonicTimeIsRejected() {
        assertEquals(-1, FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, NOW_NS + 1));
        assertEquals(-1, FixTime.timestampMillis(OCTOBER_4_2026, NOW_NS, -1));
        assertEquals(-1, FixTime.timestampMillis(OCTOBER_4_2026, -1, 0));
    }
    @Test public void InvalidPhoneClockIsRejected() {
        assertEquals(-1, FixTime.timestampMillis(0, NOW_NS, NOW_NS));
        assertEquals(-1, FixTime.timestampMillis(1577836800000L, NOW_NS, NOW_NS - 1_000_000L));
    }
}
