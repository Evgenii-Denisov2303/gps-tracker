package ru.fleet.tracker;
import org.junit.Test;
import static org.junit.Assert.*;

public class SamplingPolicyTest {
    @Test public void motionEveryTwentySeconds(){SamplingPolicy p=new SamplingPolicy();assertTrue(p.shouldSave(0,true));assertFalse(p.shouldSave(19000,true));assertTrue(p.shouldSave(20000,true));}
    @Test public void parkingSlowsAfterFiveMinutes(){SamplingPolicy p=new SamplingPolicy();assertTrue(p.shouldSave(0,false));assertTrue(p.shouldSave(280000,false));assertFalse(p.shouldSave(300000,false));assertTrue(p.shouldSave(400000,false));}
    @Test public void movementRestoresFrequency(){SamplingPolicy p=new SamplingPolicy();p.shouldSave(0,false);p.shouldSave(300000,false);assertTrue(p.shouldSave(320000,true));}
    @Test public void failedPersistenceRetries(){SamplingPolicy p=new SamplingPolicy();p.shouldSave(0,true);p.saveFailed();assertTrue(p.shouldSave(1000,true));}
}
