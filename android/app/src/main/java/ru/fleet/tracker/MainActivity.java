package ru.fleet.tracker;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.location.LocationManager;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.net.URI;
import java.text.DateFormat;
import java.util.Date;

public class MainActivity extends Activity {
    private EditText server,token;
    private TextView info;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable update=new Runnable(){@Override public void run(){render();handler.postDelayed(this,2000);}};
    private int dp(int value){return (int)(value*getResources().getDisplayMetrics().density);}
    private void note(String message){new AlertDialog.Builder(this).setMessage(message).setPositiveButton("Понятно",null).show();}
    private Button button(LinearLayout root,String title,View.OnClickListener action){Button b=new Button(this);b.setText(title);b.setOnClickListener(action);root.addView(b,new LinearLayout.LayoutParams(-1,-2));return b;}
    private TextView label(LinearLayout root,String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setPadding(0,dp(12),0,dp(8));root.addView(t);return t;}

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        ScrollView scroll=new ScrollView(this);LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(24),dp(24),dp(24),dp(24));scroll.addView(root);setContentView(scroll);
        if(Build.VERSION.SDK_INT>=30) scroll.setOnApplyWindowInsetsListener((v,insets)->{android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);return insets;});
        label(root,"Маршрут — трекер · "+BuildConfig.VERSION_NAME,27);
        label(root,"Телефон служебного автомобиля. Во время работы виден постоянный значок GPS-мониторинга.",14);
        info=label(root,"Загрузка состояния…",15);
        label(root,"Адрес сервера (HTTPS)",14);server=new EditText(this);server.setSingleLine(true);server.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);server.setHint("https://gps.example.com");server.setText(Config.prefs(this).getString("url",""));root.addView(server);
        label(root,"Токен устройства",14);token=new EditText(this);token.setSingleLine(true);token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);token.setHint("Оставьте пустым, чтобы сохранить прежний");token.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);root.addView(token);
        button(root,"Сохранить настройки",v->save());
        button(root,"1. Разрешить точную геолокацию",v->requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},1));
        button(root,"2. Геолокация «Разрешать всегда»",v->{
            if(Build.VERSION.SDK_INT==29)requestPermissions(new String[]{Manifest.permission.ACCESS_BACKGROUND_LOCATION},2);
            else startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())));
        });
        button(root,"3. Настройки экономии батареи",v->startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)));
        button(root,"4. Разрешить уведомления",v->{if(Build.VERSION.SDK_INT>=33)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},3);else note("Для этой версии Android отдельное разрешение не требуется.");});
        button(root,"Запустить трекер",v->startTracking());
        button(root,"Остановить трекер",v->{Config.prefs(this).edit().putBoolean("enabled",false).apply();stopService(new Intent(this,TrackerService.class));render();});
        button(root,"Очистить неотправленную очередь…",v->{
            if(Config.prefs(this).getBoolean("enabled",false) || TrackerService.finishing){note("Сначала остановите трекер и дождитесь завершения отправки.");return;}
            new AlertDialog.Builder(this).setTitle("Удалить неотправленные точки?")
                .setMessage("Они будут потеряны. Используйте только при смене машины или сервера, если передать старые точки невозможно.")
                .setNegativeButton("Отмена",null).setPositiveButton("Удалить",(dialog,which)->{try(PointQueue q=new PointQueue(this)){q.getWritableDatabase().delete("points",null,null);Config.prefs(this).edit().putLong("queue_count",0).apply();}render();}).show();
        });
        label(root,"Для автозапуска: включите точное местоположение, доступ «Всегда», разрешите автозапуск в настройках производителя и отключите оптимизацию батареи. После перезагрузки разблокируйте телефон. Принудительная остановка приложения блокирует автозапуск до его ручного открытия.",13);
    }
    private void save(){
        if(Config.prefs(this).getBoolean("enabled",false) || TrackerService.finishing){note("Сначала остановите трекер и дождитесь завершения отправки, затем измените настройки.");return;}
        try{
            String url=server.getText().toString().trim().replaceAll("/+$","");URI uri=new URI(url);
            if(!"https".equals(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null || (uri.getPath()!=null && !uri.getPath().isEmpty()))throw new IllegalArgumentException("Укажите только HTTPS-адрес сервера без пути, логина и параметров.");
            String old=Config.token(this),value=token.getText().toString().trim();if(value.isEmpty())value=old;
            if(value.length()<32)throw new IllegalArgumentException("Введите токен устройства из кабинета владельца.");
            try(PointQueue q=new PointQueue(this)){if(q.count()>0 && (!url.equals(Config.prefs(this).getString("url","")) || !value.equals(old)))throw new IllegalArgumentException("В очереди есть старые точки. Передайте их со старыми настройками или явно очистите очередь перед сменой токена/сервера.");}
            Config.save(this,url,value);token.setText("");note("Настройки сохранены.");
        }catch(Exception e){note(e.getMessage()==null?"Не удалось сохранить токен. Проверьте настройки.":e.getMessage());}
    }
    private void startTracking(){
        if(TrackerService.finishing){note("Завершается предыдущая отправка. Попробуйте через несколько секунд.");return;}
        try{
            if(Config.token(this).isEmpty() || Config.prefs(this).getString("url","").isEmpty()){note("Сначала сохраните адрес сервера и токен.");return;}
            if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED){note("Сначала разрешите точную геолокацию.");return;}
            if(!getSystemService(LocationManager.class).isProviderEnabled(LocationManager.GPS_PROVIDER)){startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));return;}
            Config.prefs(this).edit().putBoolean("enabled",true).commit();
            startForegroundService(new Intent(this,TrackerService.class));render();
        }catch(Exception e){Config.prefs(this).edit().putBoolean("enabled",false).apply();note("Не удалось запустить трекер. Проверьте разрешения и сохранённый токен.");}
    }
    private String time(long value){return value==0?"ещё не было":DateFormat.getDateTimeInstance(DateFormat.SHORT,DateFormat.MEDIUM).format(new Date(value));}
    private void render(){
        if(info==null)return;SharedPreferences p=Config.prefs(this);long gps=p.getLong("gps_time",0);
        boolean fresh=gps>0 && System.currentTimeMillis()-gps<180_000;
        Intent battery=registerReceiver(null,new IntentFilter(Intent.ACTION_BATTERY_CHANGED));String batteryText="неизвестно";
        if(battery!=null){int level=battery.getIntExtra(BatteryManager.EXTRA_LEVEL,-1),scale=battery.getIntExtra(BatteryManager.EXTRA_SCALE,100);batteryText=(level>=0 && scale>0?level*100/scale+"%":"неизвестно")+(battery.getIntExtra(BatteryManager.EXTRA_PLUGGED,0)!=0?" · зарядка":" · от батареи");}
        String bg=Build.VERSION.SDK_INT<29 || checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION)==PackageManager.PERMISSION_GRANTED?"разрешена":"нужно разрешить «Всегда»";
        boolean enabled=p.getBoolean("enabled",false);
        String service=TrackerService.active?"Служба трекера работает":enabled?"Служба не запущена — нажмите «Запустить трекер»":"Мониторинг остановлен";
        boolean exempt=getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName());
        info.setText(service+"\nGPS: "+(fresh?"работает":"нет свежей точки")
            +"\nПоследняя точка: "+time(gps)+"\nОтправка координат: "+time(p.getLong("last_upload",0))
            +"\nПроверка связи: "+time(p.getLong("last_heartbeat",0))
            +"\nОчередь: "+p.getLong("queue_count",0)+" точек\nБатарея: "+batteryText+"\nГеолокация в фоне: "+bg
            +"\nЭкономия батареи для трекера: "+(exempt?"отключена":"включена — отключите кнопкой 3")
            +(TrackerService.active?"\n\n"+p.getString("gps_status","Ожидание GPS")+"\n"+p.getString("heartbeat_status","Ожидание проверки связи")+"\n"+p.getString("upload_status",""):""));
    }
    @Override protected void onResume(){super.onResume();handler.post(update);}
    @Override protected void onPause(){handler.removeCallbacks(update);super.onPause();}
}
