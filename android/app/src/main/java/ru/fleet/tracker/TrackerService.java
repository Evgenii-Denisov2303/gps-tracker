package ru.fleet.tracker;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.location.*;
import android.os.*;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.*;
import javax.net.ssl.HttpsURLConnection;
import org.json.*;

public class TrackerService extends Service implements LocationListener {
    static final String CHANNEL="tracking";
    static volatile boolean finishing = false;
    private LocationManager manager;
    private PointQueue queue;
    private ScheduledExecutorService worker;
    private PowerManager.WakeLock wakeLock;
    private Location anchor;
    private final SamplingPolicy sampling = new SamplingPolicy();
    private long lastUpload=0, retryAfter=0;
    private int failures=0;

    static void channel(Context c) {
        c.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL,"GPS-мониторинг",NotificationManager.IMPORTANCE_LOW));
    }
    static Notification notification(Context c, String text) {
        channel(c);
        PendingIntent open=PendingIntent.getActivity(c,0,new Intent(c,MainActivity.class),PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(c,CHANNEL).setSmallIcon(R.drawable.ic_tracker).setContentTitle("Маршрут — служебный автомобиль")
            .setContentText(text).setContentIntent(open).setOngoing(true).build();
    }
    private void status(String text) {Config.prefs(this).edit().putString("status",text).apply();}

    @Override public void onCreate() {
        super.onCreate();
        try {startForeground(1,notification(this,"GPS-мониторинг включён"));}
        catch(RuntimeException e){status("Android запретил запуск. Откройте приложение и проверьте разрешения.");stopSelf();return;}
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED) {status("Нет точной геолокации");stopSelf();return;}
        queue=new PointQueue(this); worker=Executors.newSingleThreadScheduledExecutor();
        manager=getSystemService(LocationManager.class);
        try {manager.requestLocationUpdates(LocationManager.GPS_PROVIDER,20_000,0,this,Looper.getMainLooper());}
        catch(RuntimeException e){status("GPS недоступен. Включите геолокацию и проверьте разрешения.");stopSelf();return;}
        wakeLock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"FleetTracker:GPS");
        wakeLock.setReferenceCounted(false); wakeLock.acquire(600_000);
        worker.scheduleWithFixedDelay(()->wakeLock.acquire(600_000),300,300,TimeUnit.SECONDS);
        worker.scheduleWithFixedDelay(this::flush,0,30,TimeUnit.SECONDS);
        Config.prefs(this).edit().putBoolean("running",true).apply();
        status("Ожидание GPS-точки");
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(!Config.prefs(this).getBoolean("enabled",false)) {stopSelf();return START_NOT_STICKY;}
        return START_STICKY;
    }
    @Override public void onLocationChanged(Location location) {
        if(worker==null || worker.isShutdown())return;
        Location loc=new Location(location);
        if(!loc.hasAccuracy() || !Float.isFinite(loc.getAccuracy()) || loc.getAccuracy()<=0 || loc.getAccuracy()>80)return;
        // Some GPS receivers report a wrong calendar date despite a correct phone clock.
        // Capture the actual fix time before queuing work; offline uploads retain it.
        long fixTime=FixTime.timestampMillis(System.currentTimeMillis(),SystemClock.elapsedRealtimeNanos(),loc.getElapsedRealtimeNanos());
        if(fixTime<0)return;
        Config.prefs(this).edit().putLong("gps_time",fixTime).apply();
        boolean moving=(loc.hasSpeed() && loc.getSpeed()>0.84f) || (anchor!=null && anchor.distanceTo(loc)>50);
        if(anchor==null || moving)anchor=new Location(loc);
        if(!sampling.shouldSave(SystemClock.elapsedRealtime(),moving))return;
        Intent battery=registerReceiver(null,new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        worker.execute(()->{
            try {
                JSONObject p=new JSONObject();p.put("event_id",UUID.randomUUID().toString());
                p.put("latitude",loc.getLatitude());p.put("longitude",loc.getLongitude());p.put("accuracy",loc.getAccuracy());
                p.put("gps_timestamp",Instant.ofEpochMilli(fixTime).toString());
                if(loc.hasSpeed() && Float.isFinite(loc.getSpeed()) && loc.getSpeed()>=0 && loc.getSpeed()*3.6<=400)p.put("speed",loc.getSpeed()*3.6);
                if(loc.hasBearing() && Float.isFinite(loc.getBearing()))p.put("heading",((loc.getBearing()%360)+360)%360);
                if(battery!=null){int level=battery.getIntExtra(BatteryManager.EXTRA_LEVEL,-1),scale=battery.getIntExtra(BatteryManager.EXTRA_SCALE,100);
                    if(level>=0 && scale>0)p.put("battery_level",Math.min(100,level*100/scale));p.put("charging",battery.getIntExtra(BatteryManager.EXTRA_PLUGGED,0)!=0);}
                queue.add(p);status("GPS работает");flush();
            }catch(Exception e){sampling.saveFailed();status("Не удалось сохранить точку. Проверьте свободное место.");}
        });
    }

    private void flush() {
        if(queue==null || SystemClock.elapsedRealtime()<retryAfter)return;
        HttpsURLConnection connection=null;
        try {
            JSONArray batch=queue.batch();Config.prefs(this).edit().putLong("queue_count",queue.count()).apply();
            if(batch.length()==0)return;
            String base=Config.prefs(this).getString("url","");
            URL url=new URL(base+"/api/v1/locations");
            if(!"https".equals(url.getProtocol()))throw new IllegalStateException("HTTPS required");
            connection=(HttpsURLConnection)url.openConnection();connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(15_000);connection.setReadTimeout(20_000);connection.setRequestMethod("POST");connection.setDoOutput(true);
            connection.setRequestProperty("Authorization","Bearer "+Config.token(this));connection.setRequestProperty("Content-Type","application/json");
            byte[] bytes=new JSONObject().put("points",batch).toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try(java.io.OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int code=connection.getResponseCode();
            if(code!=200){
                status(code==401?"Токен отклонён. Получите новый токен у владельца.":code==422?"Сервер отклонил точки. Проверьте дату и время телефона.":"Ошибка сервера: "+code);
                failed();return;
            }
            String result;
            try(java.io.InputStream in=connection.getInputStream();java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
                byte[] buf=new byte[4096];int count;while((count=in.read(buf))!=-1){out.write(buf,0,count);if(out.size()>131072)throw new java.io.IOException("Response too large");}result=out.toString("UTF-8");}
            JSONArray ack=new JSONObject(result).getJSONArray("acknowledged");
            queue.acknowledge(ack,batch);failures=0;retryAfter=0;lastUpload=System.currentTimeMillis();
            Config.prefs(this).edit().putLong("last_upload",lastUpload).putLong("queue_count",queue.count()).putString("status","Сервер доступен").apply();
        }catch(Exception e){status("Нет отправки: проверьте интернет, HTTPS и адрес сервера. Точки остаются в очереди.");failed();}
        finally{if(connection!=null)connection.disconnect();}
    }
    private void failed(){failures=Math.min(failures+1,5);retryAfter=SystemClock.elapsedRealtime()+Math.min(300_000,10_000L*(1L<<failures));}
    @Override public void onProviderDisabled(String provider){status("GPS выключен. Включите геолокацию.");}
    @Override public void onProviderEnabled(String provider){status("Поиск спутников");}
    @Override public void onStatusChanged(String provider,int status,Bundle extras){}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public void onDestroy(){
        if(manager!=null)manager.removeUpdates(this);
        if(worker!=null){finishing=true;worker.execute(()->{try{if(queue!=null)queue.close();}finally{finishing=false;}});worker.shutdown();}
        if(wakeLock!=null && wakeLock.isHeld())wakeLock.release();
        Config.prefs(this).edit().putBoolean("running",false).apply();super.onDestroy();
    }
}
