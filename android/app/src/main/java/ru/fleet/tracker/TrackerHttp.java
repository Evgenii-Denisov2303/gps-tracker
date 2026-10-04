package ru.fleet.tracker;

import android.content.Context;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

final class TrackerHttp {
    static final class Rejected extends java.io.IOException {
        final int code;
        Rejected(int code) { super("HTTP " + code); this.code=code; }
    }
    static JSONObject post(Context context, String path, JSONObject body) throws Exception {
        URL url=new URL(Config.prefs(context).getString("url","")+path);
        if(!"https".equals(url.getProtocol()))throw new IllegalStateException("HTTPS required");
        HttpsURLConnection connection=(HttpsURLConnection)url.openConnection();
        try {
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(10_000);connection.setReadTimeout(15_000);
            connection.setRequestMethod("POST");connection.setDoOutput(true);
            connection.setRequestProperty("Authorization","Bearer "+Config.token(context));
            connection.setRequestProperty("Content-Type","application/json");
            byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try(java.io.OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int code=connection.getResponseCode();
            if(code!=200)throw new Rejected(code);
            try(java.io.InputStream in=connection.getInputStream();java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
                byte[] buf=new byte[4096];int count;
                while((count=in.read(buf))!=-1){out.write(buf,0,count);if(out.size()>131072)throw new java.io.IOException("Response too large");}
                return new JSONObject(out.toString("UTF-8"));
            }
        } finally {connection.disconnect();}
    }
    static String error(Exception error, boolean heartbeat) {
        if(error instanceof Rejected) {
            int code=((Rejected)error).code;
            if(code==401)return "Токен отклонён. Обратитесь к владельцу.";
            if(code==422)return heartbeat?"Сервер отклонил диагностику. Обновите сервер.":"Сервер отклонил точки. Проверьте дату телефона; очередь сохранена.";
            if(code==404 && heartbeat)return "На сервере ещё нет проверки связи. Обновите сервер.";
            return "Ошибка сервера: "+code+". Повторим автоматически.";
        }
        return "Нет соединения с сервером. Проверьте интернет и HTTPS; повторим автоматически.";
    }
}
