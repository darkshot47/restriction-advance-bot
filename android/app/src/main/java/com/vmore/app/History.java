package com.vmore.app;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The record of everything the app ever moved: what it was, how big it was,
 * where it went and whether it worked.
 *
 * Auto-deleting a phone copy never touches this list — the owner asked for the
 * storage to be freed while the history keeps showing what happened.
 */
public final class History {

    public interface Listener {
        void onHistoryChanged();
    }

    private static final String FILE_NAME = "history.json";
    private static final int MAX_ENTRIES = 1000;

    public static final String STATUS_DONE = "done";
    public static final String STATUS_UPLOADED = "uploaded";
    public static final String STATUS_FAILED = "failed";
    public static final String STATUS_DOWNLOADED = "downloaded";

    public static final class Entry {
        public String id = "";
        public String name = "";
        public String kind = "document";
        public long size;
        public String destTitle = "";
        public long destChatId;
        public String status = STATUS_DONE;
        public long when;
        public String link = "";
        public String error = "";
        /** The file is still on the phone (false once it was auto-deleted). */
        public boolean local;
        public String path = "";

        public JSONObject toJson() {
            JSONObject json = new JSONObject();
            try {
                json.put("id", id);
                json.put("name", name);
                json.put("kind", kind);
                json.put("size", size);
                json.put("dest_title", destTitle);
                json.put("dest_chat_id", destChatId);
                json.put("status", status);
                json.put("when", when);
                json.put("link", link);
                json.put("error", error);
                json.put("local", local);
                json.put("path", path);
            } catch (Exception ignored) {
            }
            return json;
        }

        public static Entry from(JSONObject json) {
            Entry entry = new Entry();
            entry.id = json.optString("id", "");
            entry.name = json.optString("name", "");
            entry.kind = json.optString("kind", "document");
            entry.size = json.optLong("size", 0L);
            entry.destTitle = json.optString("dest_title", "");
            entry.destChatId = json.optLong("dest_chat_id", 0L);
            entry.status = json.optString("status", STATUS_DONE);
            entry.when = json.optLong("when", 0L);
            entry.link = json.optString("link", "");
            entry.error = json.optString("error", "");
            entry.local = json.optBoolean("local", false);
            entry.path = json.optString("path", "");
            return entry;
        }
    }

    private static volatile History instance;

    public static History get(Context context) {
        History value = instance;
        if (value == null) {
            synchronized (History.class) {
                value = instance;
                if (value == null) {
                    value = new History(context.getApplicationContext());
                    instance = value;
                }
            }
        }
        return value;
    }

    private final Context app;
    private final List<Entry> entries = new ArrayList<>();
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    private final ExecutorService writer = Executors.newSingleThreadExecutor();

    private History(Context context) {
        app = context;
        load();
    }

    public synchronized List<Entry> all() {
        return new ArrayList<>(entries);
    }

    public synchronized List<Entry> byStatus(String status) {
        if (status == null || status.isEmpty() || "all".equals(status)) {
            return all();
        }
        List<Entry> result = new ArrayList<>();
        for (Entry entry : entries) {
            if (entry.status.equals(status)) {
                result.add(entry);
            }
        }
        return result;
    }

    public synchronized void record(String name, String kind, long size, long destChatId,
                                    String destTitle, String status, String link,
                                    String error, String path) {
        Entry entry = new Entry();
        entry.id = UUID.randomUUID().toString();
        entry.name = name == null ? "" : name;
        entry.kind = kind == null ? "document" : kind;
        entry.size = size;
        entry.destChatId = destChatId;
        entry.destTitle = destTitle == null ? "" : destTitle;
        entry.status = status;
        entry.when = System.currentTimeMillis();
        entry.link = link == null ? "" : link;
        entry.error = error == null ? "" : error;
        entry.path = path == null ? "" : path;
        entry.local = path != null && !path.isEmpty() && new File(path).exists();
        entries.add(0, entry);
        while (entries.size() > MAX_ENTRIES) {
            entries.remove(entries.size() - 1);
        }
        persist();
        notifyListeners();
    }

    /** The auto-delete step: the file is gone, the record stays. */
    public synchronized void markLocalGone(String path) {
        if (path == null || path.isEmpty()) {
            return;
        }
        for (Entry entry : entries) {
            if (path.equals(entry.path)) {
                entry.local = false;
            }
        }
        persist();
        notifyListeners();
    }

    /**
     * Clears the "on the phone" mark of every record whose file is gone.
     *
     * Called after the downloaded files are deleted from Settings: the record
     * itself stays, which is the point of the history — it says what happened,
     * not what is still on disk.
     */
    public synchronized void forgetMissingFiles() {
        boolean changed = false;
        for (Entry entry : entries) {
            if (!entry.local) {
                continue;
            }
            if (entry.path == null || entry.path.isEmpty() || !new File(entry.path).exists()) {
                entry.local = false;
                changed = true;
            }
        }
        if (changed) {
            persist();
            notifyListeners();
        }
    }

    public synchronized void remove(String id) {
        entries.removeIf(entry -> entry.id.equals(id));
        persist();
        notifyListeners();
    }

    public synchronized void clear() {
        entries.clear();
        persist();
        notifyListeners();
    }

    public void addListener(Listener listener) {
        if (listener != null && !listeners.contains(listener)) {
            listeners.add(listener);
        }
    }

    public void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    private void notifyListeners() {
        //: History rows are written from the queue thread; the screens that
        //: show them are built here, on the main thread.
        UiThread.safe(() -> {
            for (Listener listener : listeners) {
                try {
                    listener.onHistoryChanged();
                } catch (Throwable ignored) {
                }
            }
        });
    }

    private File file() {
        return new File(app.getFilesDir(), FILE_NAME);
    }

    private void load() {
        File file = file();
        if (!file.exists()) {
            return;
        }
        try {
            String text = Jobs.readAll(file);
            if (text.isEmpty()) {
                return;
            }
            JSONArray array = new JSONArray(text);
            synchronized (this) {
                entries.clear();
                for (int index = 0; index < array.length(); index++) {
                    JSONObject json = array.optJSONObject(index);
                    if (json != null) {
                        entries.add(Entry.from(json));
                    }
                }
            }
        } catch (Exception ignored) {
        }
    }

    private void persist() {
        final JSONArray array = new JSONArray();
        for (Entry entry : new ArrayList<>(entries)) {
            array.put(entry.toJson());
        }
        final String payload = array.toString();
        writer.execute(() -> Jobs.writeAll(file(), payload));
    }
}
