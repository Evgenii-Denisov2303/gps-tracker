const {test}=require('node:test');
const assert=require('node:assert/strict');
const {trackerState}=require('./tracker-status.js');
const base={age_seconds:5,contact_age_seconds:2,stale_seconds:180,offline_seconds:600,
  point:{speed:25,battery_level:90,charging:false,gps_timestamp:'2026-10-04T12:00:00Z'}};
const health={age_seconds:1,received_at:'2026-10-04T12:05:00Z',battery_level:85,charging:true};
test('phone online does not make old GPS or speed current',()=>{
  const s=trackerState({...base,age_seconds:3600,device_health:health});
  assert.equal(s.connection,'fresh');assert.equal(s.gpsFresh,false);assert.equal(s.speed,null);assert.equal(s.state,'stale');
  assert.equal(s.battery.battery_level,85);assert.equal(s.batteryFresh,true);
});
test('heartbeat without any position still shows phone battery',()=>{
  const s=trackerState({...base,age_seconds:null,point:null,device_health:health});
  assert.equal(s.connection,'fresh');assert.equal(s.speed,null);assert.equal(s.battery.charging,true);
});
test('cached heartbeat and website response expire',()=>{
  const s=trackerState({...base,device_health:health},700);
  assert.equal(s.connection,'offline');assert.equal(s.healthFresh,false);assert.equal(s.siteFresh,false);assert.equal(s.speed,null);assert.equal(s.batteryFresh,false);
});
test('old client still shows valid position without heartbeat',()=>{
  const s=trackerState(base);assert.equal(s.speed,25);assert.equal(s.battery.battery_level,90);assert.equal(s.state,'fresh');
});
test('older health never overrides newer point battery',()=>{
  const s=trackerState({...base,device_health:{...health,received_at:'2026-10-04T11:59:00Z'}});
  assert.equal(s.battery.battery_level,90);
});
test('no contact is offline even if GPS timestamp was fresh',()=>{
  const s=trackerState({...base,contact_age_seconds:null});assert.equal(s.state,'offline');assert.equal(s.speed,null);
});
test('stale and offline boundaries are exact',()=>{
  assert.equal(trackerState({...base,contact_age_seconds:180}).connection,'stale');
  assert.equal(trackerState({...base,contact_age_seconds:600}).connection,'offline');
  assert.equal(trackerState({...base,age_seconds:180}).gpsFresh,false);
});
test('disabled GPS or revoked permission hides speed even with a recent point',()=>{
  for(const diagnostic of [{gps_enabled:false},{location_permission:false}]) {
    const s=trackerState({...base,device_health:{...health,...diagnostic}});
    assert.equal(s.speed,null);assert.equal(s.state,'stale');
  }
});

test('hardware navigation failure hides recent speed without Android permissions',()=>{
  const valid=trackerState({...base,device_kind:'navtelecom',device_health:{age_seconds:1,gps_enabled:true,navigation_valid:true}});
  assert.equal(valid.gpsFresh,true);
  const invalid=trackerState({...base,device_kind:'navtelecom',device_health:{age_seconds:1,gps_enabled:true,navigation_valid:false}});
  assert.equal(invalid.gpsFresh,false);assert.equal(invalid.speed,null);
});
