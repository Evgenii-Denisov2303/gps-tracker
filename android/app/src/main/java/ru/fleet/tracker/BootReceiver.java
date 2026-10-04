package ru.fleet.tracker;

import android.Manifest;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Build;
import android.app.NotificationManager;

public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent intent) {
        if(!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))return;
        if(!Config.prefs(c).getBoolean("enabled",false))return;
        boolean allowed=c.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED;
        if(Build.VERSION.SDK_INT>=29)allowed &= c.checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION)==PackageManager.PERMISSION_GRANTED;
        try {
            if(!allowed)throw new IllegalStateException("Location permission missing");
            c.startForegroundService(new Intent(c,TrackerService.class));
        }catch(RuntimeException e){
            Config.prefs(c).edit().putString("status","Автозапуск заблокирован. Откройте приложение и нажмите «Запустить».").apply();
            if(Build.VERSION.SDK_INT<33 || c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED)
                c.getSystemService(NotificationManager.class).notify(2,TrackerService.notification(c,"Откройте трекер для возобновления GPS"));
        }
    }
}
