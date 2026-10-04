package ru.fleet.tracker;
import org.junit.Test;
import static org.junit.Assert.*;

public class RetryPolicyTest {
    @Test public void retriesBackOffAndCapAtFiveMinutes() {
        RetryPolicy p=new RetryPolicy(); long now=0;
        for(long wait:new long[]{20000,40000,80000,160000,300000,300000}) {
            p.failed(now); assertFalse(p.ready(now+wait-1)); assertTrue(p.ready(now+wait)); now+=wait;
        }
    }
    @Test public void restoredNetworkRetriesImmediatelyAndSuccessResetsFailures() {
        RetryPolicy p=new RetryPolicy();p.failed(100);p.networkAvailable();assertTrue(p.ready(200));
        p.succeeded();p.failed(300);assertTrue(p.ready(20300));
    }
    @Test public void brokenPointUploadsDoNotBlockHeartbeat() {
        RetryPolicy locations=new RetryPolicy(),heartbeat=new RetryPolicy();
        locations.failed(0);assertFalse(locations.ready(1));assertTrue(heartbeat.ready(1));
        heartbeat.succeeded();assertFalse(locations.ready(1));
    }
}
