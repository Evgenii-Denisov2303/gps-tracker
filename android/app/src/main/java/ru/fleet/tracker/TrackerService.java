package ru.fleet.tracker;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.location.*;
import android.net.*;
import android.os.*;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.*;
import org.json.*;

public class TrackerService extends Service implements LocationListener {
    static final String CHANNEL="tracking";
    static volatile boolean finishing=false, active=false;
    private final Handler main=new Handler(Looper.getMainLooper());
    private LocationManager manager;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback networkCallback;
    private PointQueue queue;
    private ScheduledExecutorService worker, healthWorker;
    private PowerManager.WakeLock wakeLock;
    private Location anchor;
    private final SamplingPolicy sampling=new SamplingPolicy();
    private final RetryPolicy uploadRetry=new RetryPolicy(), healthRetry=new RetryPolicy();
    private volatile long lastFixElapsed=-1, lastCallbackElapsed=-1;
    private long lastGpsRequest=-1, lastHeartbeatAttempt=-1;
    private volatile boolean stopped=false;
    private boolean subscribed=false;
    private final Runnable gpsCheck=new Runnable(){public void run(){
        if(stopped)return;
        ensureGps();
        main.postDelayed(this,60_000);
    }};

    static void channel(Context c) {
        c.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL,"GPS-мониторинг",NotificationManager.IMPORTANCE_LOW));
    }
    static Notification notification(Context c,String text) {
        channel(c);
        PendingIntent open=PendingIntent.getActivity(c,0,new Intent(c,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(c,CHANNEL).setSmallIcon(R.drawable.ic_tracker).setContentTitle("Маршрут — служебный автомобиль")
            .setContentText(text).setContentIntent(open).setOngoing(true).build();
    }
    private boolean permission() {return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED;}
    private boolean gpsEnabled() {
        try{return manager!=null && manager.isProviderEnabled(LocationManager.GPS_PROVIDER);}
        catch(RuntimeException e){return false;}
    }
    private void gpsStatus(String value){Config.prefs(this).edit().putString("gps_status",value).apply();}

    @Override public void onCreate() {
        super.onCreate();
        try{startForeground(1,notification(this,"GPS-мониторинг включён"));}
        catch(RuntimeException e){gpsStatus("Android запретил запуск. Откройте приложение и проверьте разрешения.");stopSelf();return;}
        if(!permission()){gpsStatus("Нет разрешения точной геолокации");stopSelf();return;}
        queue=new PointQueue(this);
        worker=Executors.newSingleThreadScheduledExecutor();
        healthWorker=Executors.newSingleThreadScheduledExecutor();
        manager=getSystemService(LocationManager.class);
        wakeLock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"FleetTracker:GPS");
        wakeLock.setReferenceCounted(false);wakeLock.acquire(600_000);
        // Independent scheduler: a slow/rejected GPS batch cannot stop heartbeat or lock renewal.
        healthWorker.scheduleWithFixedDelay(()->{
            if(stopped)return;
            try{wakeLock.acquire(600_000);heartbeat();}
            catch(Exception e){Config.prefs(this).edit().putString("heartbeat_status","Не удалось проверить связь. Повторим автоматически.").apply();}
        },0,30,TimeUnit.SECONDS);
        worker.scheduleWithFixedDelay(this::flush,0,30,TimeUnit.SECONDS);
        active=true;
        Config.prefs(this).edit().putBoolean("running",true).putString("gps_status","Ожидание GPS-точки").apply();
        main.post(gpsCheck);
        connectivity=getSystemService(ConnectivityManager.class);
        networkCallback=new ConnectivityManager.NetworkCallback(){
            private boolean validated;
            @Override public void onCapabilitiesChanged(Network network,NetworkCapabilities caps){
                boolean available=caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
                if(available && !validated && !stopped){
                    enqueue(worker,()->{uploadRetry.networkAvailable();flush();});
                    enqueue(healthWorker,()->{healthRetry.networkAvailable();lastHeartbeatAttempt=-1;heartbeat();});
                }
                validated=available;
            }
            @Override public void onLost(Network network){validated=false;}
        };
        try{connectivity.registerDefaultNetworkCallback(networkCallback);}
        catch(RuntimeException e){networkCallback=null;} // Periodic retries remain available.
    }
    private void enqueue(ScheduledExecutorService executor,Runnable action){
        if(stopped || executor==null || executor.isShutdown())return;
        try{executor.execute(action);}catch(RejectedExecutionException ignored){}
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(!Config.prefs(this).getBoolean("enabled",false)){stopSelf();return START_NOT_STICKY;}
        return START_STICKY;
    }
    private void ensureGps(){
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED){gpsStatus("Нет разрешения точной геолокации");return;}
        if(!gpsEnabled()){gpsStatus("GPS выключен. Включите геолокацию.");return;}
        long now=SystemClock.elapsedRealtime();
        long reference=Math.max(lastCallbackElapsed,lastGpsRequest);
        if(subscribed && now-reference<300_000)return;
        try{
            // Re-register the same listener if Android has stopped delivering callbacks.
            // Poor accuracy alone does not restart acquisition.
            manager.requestLocationUpdates(LocationManager.GPS_PROVIDER,20_000,0,this,Looper.getMainLooper());
            lastGpsRequest=now;subscribed=true;
            if(lastFixElapsed<0 || now-lastFixElapsed>=180_000)gpsStatus("Поиск спутников. Нужен открытый обзор неба.");
        }catch(SecurityException e){subscribed=false;lastGpsRequest=now;gpsStatus("Доступ к GPS отозван. Разрешите точную геолокацию.");}
        catch(RuntimeException e){lastGpsRequest=now;gpsStatus("GPS недоступен. Проверьте разрешения.");}
    }
    @Override public void onLocationChanged(Location location) {
        if(stopped || worker==null || worker.isShutdown())return;
        lastCallbackElapsed=SystemClock.elapsedRealtime();
        Location loc=new Location(location);
        if(!loc.hasAccuracy() || !Float.isFinite(loc.getAccuracy()) || loc.getAccuracy()<=0 || loc.getAccuracy()>80){
            gpsStatus("Слабый GPS: точность хуже 80 м. Подойдите к окну или выйдите на улицу.");return;
        }
        long fixTime=FixTime.timestampMillis(System.currentTimeMillis(),SystemClock.elapsedRealtimeNanos(),loc.getElapsedRealtimeNanos());
        if(fixTime<0){gpsStatus("Устаревшее измерение GPS или неверные часы телефона");return;}
        lastFixElapsed=loc.getElapsedRealtimeNanos()/1_000_000L;
        Config.prefs(this).edit().putLong("gps_time",fixTime).putString("gps_status","GPS работает").apply();
        boolean moving=(loc.hasSpeed() && loc.getSpeed()>0.84f)||(anchor!=null && anchor.distanceTo(loc)>50);
        if(anchor==null || moving)anchor=new Location(loc);
        if(!sampling.shouldSave(SystemClock.elapsedRealtime(),moving))return;
        Intent battery=registerReceiver(null,new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        enqueue(worker,()->{
            try{
                JSONObject p=new JSONObject().put("event_id",UUID.randomUUID().toString())
                    .put("latitude",loc.getLatitude()).put("longitude",loc.getLongitude()).put("accuracy",loc.getAccuracy())
                    .put("gps_timestamp",Instant.ofEpochMilli(fixTime).toString());
                if(loc.hasSpeed() && Float.isFinite(loc.getSpeed()) && loc.getSpeed()>=0 && loc.getSpeed()*3.6<=400)p.put("speed",loc.getSpeed()*3.6);
                if(loc.hasBearing() && Float.isFinite(loc.getBearing()))p.put("heading",((loc.getBearing()%360)+360)%360);
                batteryFields(p,battery);
                queue.add(p);
                Config.prefs(this).edit().putLong("queue_count",queue.count()).apply();
                flush();
            }catch(Exception e){sampling.saveFailed();Config.prefs(this).edit().putString("upload_status","Не удалось сохранить точку. Проверьте свободное место.").apply();}
        });
    }
    private void batteryFields(JSONObject body,Intent battery)throws JSONException{
        if(battery==null)return;
        int level=battery.getIntExtra(BatteryManager.EXTRA_LEVEL,-1),scale=battery.getIntExtra(BatteryManager.EXTRA_SCALE,100);
        if(level>=0 && scale>0)body.put("battery_level",Math.min(100,level*100/scale));
        body.put("charging",battery.getIntExtra(BatteryManager.EXTRA_PLUGGED,0)!=0);
    }
    private void heartbeat(){
        long now=SystemClock.elapsedRealtime();
        if(stopped || !healthRetry.ready(now) || (lastHeartbeatAttempt>=0 && now-lastHeartbeatAttempt<60_000))return;
        lastHeartbeatAttempt=now;
        try{
            long count=queue.count(),fix=lastFixElapsed;
            JSONObject body=new JSONObject().put("app_version",BuildConfig.VERSION_NAME)
                .put("gps_enabled",gpsEnabled()).put("location_permission",permission())
                .put("background_permission",Build.VERSION.SDK_INT<29 || checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION)==PackageManager.PERMISSION_GRANTED)
                .put("battery_optimization_exempt",getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName()))
                .put("queue_count",Math.min(Integer.MAX_VALUE,count))
                .put("gps_age_seconds",fix<0?JSONObject.NULL:Math.min(Integer.MAX_VALUE,Math.max(0,(now-fix)/1000)));
            batteryFields(body,registerReceiver(null,new IntentFilter(Intent.ACTION_BATTERY_CHANGED)));
            TrackerHttp.post(this,"/api/v1/heartbeat",body);
            healthRetry.succeeded();
            Config.prefs(this).edit().putLong("last_heartbeat",System.currentTimeMillis())
                .putString("heartbeat_status","Телефон на связи с сервером").apply();
        }catch(Exception e){
            healthRetry.failed(SystemClock.elapsedRealtime());
            Config.prefs(this).edit().putString("heartbeat_status",TrackerHttp.error(e,true)).apply();
        }
    }
    private void flush(){
        if(stopped || queue==null || !uploadRetry.ready(SystemClock.elapsedRealtime()))return;
        try{
            JSONArray batch=queue.batch();
            Config.prefs(this).edit().putLong("queue_count",queue.count()).apply();
            if(batch.length()==0)return;
            JSONObject result=TrackerHttp.post(this,"/api/v1/locations",new JSONObject().put("points",batch));
            queue.acknowledge(result.getJSONArray("acknowledged"),batch);uploadRetry.succeeded();
            Config.prefs(this).edit().putLong("last_upload",System.currentTimeMillis()).putLong("queue_count",queue.count())
                .putString("upload_status","Точки переданы на сервер").apply();
        }catch(Exception e){
            uploadRetry.failed(SystemClock.elapsedRealtime());
            Config.prefs(this).edit().putString("upload_status",TrackerHttp.error(e,false)).apply();
        }
    }
    @Override public void onProviderDisabled(String provider){gpsStatus("GPS выключен. Включите геолокацию.");}
    @Override public void onProviderEnabled(String provider){subscribed=false;ensureGps();}
    @Override public void onStatusChanged(String provider,int status,Bundle extras){}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public void onDestroy(){
        stopped=true;active=false;main.removeCallbacks(gpsCheck);
        if(networkCallback!=null)try{connectivity.unregisterNetworkCallback(networkCallback);}catch(RuntimeException ignored){}
        if(manager!=null)try{manager.removeUpdates(this);}catch(RuntimeException ignored){}
        if(worker!=null)worker.shutdown();
        if(healthWorker!=null)healthWorker.shutdown();
        finishing=true;
        // Wait for in-flight requests outside the main thread before closing their shared queue.
        new Thread(()->{
            try{
                if(worker!=null)worker.awaitTermination(60,TimeUnit.SECONDS);
                if(healthWorker!=null)healthWorker.awaitTermination(60,TimeUnit.SECONDS);
                if(queue!=null)queue.close();
            }catch(InterruptedException e){Thread.currentThread().interrupt();}
            finally{
                if(wakeLock!=null && wakeLock.isHeld())wakeLock.release();
                finishing=false;
            }
        },"tracker-stop").start();
        Config.prefs(this).edit().putBoolean("running",false).apply();super.onDestroy();
    }
}
