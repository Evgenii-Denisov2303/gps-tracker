package ru.fleet.tracker;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;

final class PointQueue extends SQLiteOpenHelper {
    PointQueue(Context context) { super(context, "queue.db", null, 1); setWriteAheadLoggingEnabled(true); }
    @Override public void onCreate(SQLiteDatabase db) { db.execSQL("CREATE TABLE points (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)"); }
    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) { throw new IllegalStateException("Queue migration required"); }
    synchronized void add(JSONObject point) throws Exception {
        ContentValues values = new ContentValues(); values.put("event_id", point.getString("event_id")); values.put("payload", point.toString());
        getWritableDatabase().insertOrThrow("points", null, values);
    }
    synchronized JSONArray batch() throws Exception {
        JSONArray array = new JSONArray();
        // Send the newest sample first even when several days of backlog exist.
        try (Cursor c = getReadableDatabase().rawQuery("SELECT payload FROM points WHERE seq = (SELECT MAX(seq) FROM points) OR seq IN (SELECT seq FROM points ORDER BY seq LIMIT 99) ORDER BY seq DESC", null)) {
            while(c.moveToNext()) array.put(new JSONObject(c.getString(0)));
        }
        return array;
    }
    synchronized void acknowledge(JSONArray ids, JSONArray sent) throws Exception {
        java.util.HashSet<String> allowed = new java.util.HashSet<>();
        for(int i=0;i<sent.length();i++) allowed.add(sent.getJSONObject(i).getString("event_id"));
        SQLiteDatabase db = getWritableDatabase(); db.beginTransaction();
        try { for(int i=0;i<ids.length();i++) {String id=ids.getString(i); if(allowed.contains(id)) db.delete("points", "event_id=?", new String[]{id});} db.setTransactionSuccessful(); }
        finally { db.endTransaction(); }
    }
    synchronized long count() {
        try(Cursor c=getReadableDatabase().rawQuery("SELECT COUNT(*) FROM points",null)){c.moveToFirst();return c.getLong(0);}
    }
}
