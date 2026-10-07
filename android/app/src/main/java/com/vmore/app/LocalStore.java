package com.vmore.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * The phone's own list of downloads — what the app downloaded, where it is and
 * how big it is.  The History screen shows this plus the server's history.
 */
final class LocalStore {

    private static final String FILE = "vmore_downloads";
    private static final String KEY_ITEMS = "items";
    private static final int MAX_ITEMS = 100;

    private LocalStore() {
    }

    static class Item {
        String name;
        String path;
        String link;
        String kind;
        String status;
        long size;
        long date;

        JSONObject toJson() {
            JSONObject json = new JSONObject();
            try {
                json.put("name", name);
                json.put("path", path);
                json.put("link", link);
                json.put("kind", kind);
                json.put("status", status);
                json.put("size", size);
                json.put("date", date);
            } catch (Exception ignored) {
            }
            return json;
        }

        static Item from(JSONObject json) {
            Item item = new Item();
            item.name = json.optString("name", "");
            item.path = json.optString("path", "");
            item.link = json.optString("link", "");
            item.kind = json.optString("kind", "");
            item.status = json.optString("status", "done");
            item.size = json.optLong("size", 0L);
            item.date = json.optLong("date", 0L);
            return item;
        }
    }

    static synchronized void add(Context context, Item item) {
        List<Item> items = all(context);
        items.removeIf(existing -> existing.path != null && existing.path.equals(item.path));
        items.add(0, item);
        while (items.size() > MAX_ITEMS) {
            items.remove(items.size() - 1);
        }
        save(context, items);
    }

    static synchronized List<Item> all(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
        List<Item> items = new ArrayList<>();
        try {
            JSONArray array = new JSONArray(prefs.getString(KEY_ITEMS, "[]"));
            for (int index = 0; index < array.length(); index++) {
                items.add(Item.from(array.getJSONObject(index)));
            }
        } catch (Exception ignored) {
        }
        return items;
    }

    private static void save(Context context, List<Item> items) {
        JSONArray array = new JSONArray();
        for (Item item : items) {
            array.put(item.toJson());
        }
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
                .edit().putString(KEY_ITEMS, array.toString()).apply();
    }

    static synchronized void forget(Context context, String path) {
        List<Item> items = all(context);
        items.removeIf(item -> item.path != null && item.path.equals(path));
        save(context, items);
    }

    static File downloadsDir(Context context) {
        File dir = new File(context.getExternalFilesDir(null), "Vmore");
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }
}
