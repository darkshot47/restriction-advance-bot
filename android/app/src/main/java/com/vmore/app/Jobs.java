package com.vmore.app;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The queue: every job that is waiting, running, paused or failed.
 *
 * It is written to {@code filesDir/queue.json} after each change, so reopening
 * the app — or the phone restarting — shows exactly the same list and the engine
 * simply carries on.
 */
public final class Jobs {

    public interface Listener {
        /** Any change in the list (jobs added, removed or updated). */
        void onJobsChanged();
    }

    private static final String FILE_NAME = "queue.json";
    private static final int MAX_JOBS = 3000;

    private static volatile Jobs instance;

    public static Jobs get(Context context) {
        Jobs value = instance;
        if (value == null) {
            synchronized (Jobs.class) {
                value = instance;
                if (value == null) {
                    value = new Jobs(context.getApplicationContext());
                    instance = value;
                }
            }
        }
        return value;
    }

    private final Context app;
    private final List<QJob> jobs = new ArrayList<>();
    private final List<String> removedIds = new ArrayList<>();
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    private final ExecutorService writer = Executors.newSingleThreadExecutor();
    private volatile boolean pausedAll;

    private Jobs(Context context) {
        app = context;
        load();
    }

    // ------------------------------------------------------------- reading //

    public synchronized List<QJob> all() {
        return new ArrayList<>(jobs);
    }

    public synchronized int size() {
        return jobs.size();
    }

    public synchronized QJob byId(String id) {
        for (QJob job : jobs) {
            if (job.id.equals(id)) {
                return job;
            }
        }
        return null;
    }

    /** The job the engine should run now: the oldest queued one. */
    public synchronized QJob nextQueued() {
        for (QJob job : jobs) {
            if (QJob.QUEUED.equals(job.stage)) {
                return job;
            }
        }
        return null;
    }

    public synchronized QJob active() {
        for (QJob job : jobs) {
            if (job.isActive()) {
                return job;
            }
        }
        return null;
    }

    public synchronized List<QJob> batch(String batchId) {
        List<QJob> result = new ArrayList<>();
        for (QJob job : jobs) {
            if (job.batchId.equals(batchId)) {
                result.add(job);
            }
        }
        return result;
    }

    /**
     * Moves a job up or down the waiting list: the engine always takes the
     * first queued job, so the list order is the priority.
     */
    public synchronized boolean move(String id, int delta) {
        int from = -1;
        for (int index = 0; index < jobs.size(); index++) {
            if (jobs.get(index).id.equals(id)) {
                from = index;
                break;
            }
        }
        if (from < 0) {
            return false;
        }
        int to = from + delta;
        if (to < 0 || to >= jobs.size()) {
            return false;
        }
        QJob moved = jobs.remove(from);
        jobs.add(to, moved);
        persist();
        notifyListeners();
        return true;
    }

    /** Puts every failed job back in line; returns how many were woken. */
    public synchronized int retryFailed() {
        int woken = 0;
        for (QJob job : jobs) {
            if (QJob.FAILED.equals(job.stage)) {
                job.stage = QJob.QUEUED;
                job.error = "";
                job.attempts = 0;
                job.skipped = false;
                //: The retry asks Telegram for the link again: a file id from
                //: the failed attempt may be exactly what Telegram refuses.
                job.fileId = 0;
                woken++;
            }
        }
        if (woken > 0) {
            persist();
            notifyListeners();
        }
        return woken;
    }

    public synchronized int countInStage(String stage) {
        int total = 0;
        for (QJob job : jobs) {
            if (job.stage.equals(stage)) {
                total++;
            }
        }
        return total;
    }

    public synchronized boolean hasWork() {
        for (QJob job : jobs) {
            if (QJob.QUEUED.equals(job.stage) || job.isActive()) {
                return true;
            }
        }
        return false;
    }

    public boolean pausedAll() {
        return pausedAll;
    }

    public void setPausedAll(boolean value) {
        pausedAll = value;
        notifyListeners();
    }

    // ------------------------------------------------------------- writing //

    public synchronized QJob add(QJob job) {
        if (job.id == null || job.id.isEmpty()) {
            job.id = UUID.randomUUID().toString();
        }
        removedIds.remove(job.id);
        long now = System.currentTimeMillis();
        if (job.created == 0L) {
            job.created = now;
        }
        job.updated = now;
        jobs.add(job);
        trim();
        persist();
        notifyListeners();
        return job;
    }

    public synchronized void addBatch(List<QJob> batch) {
        for (QJob job : batch) {
            add(job);
        }
    }

    public synchronized boolean wasRemoved(String id) {
        return id != null && removedIds.contains(id);
    }

    public synchronized void update(QJob job) {
        if (job == null || removedIds.contains(job.id)) {
            return;
        }
        job.updated = System.currentTimeMillis();
        persist();
        notifyListeners();
    }

    /** Progress ticks: the screens refresh, but nothing is written to disk. */
    public void ping() {
        notifyListeners();
    }

    public synchronized QJob removeAndGet(String id) {
        QJob found = null;
        for (int index = 0; index < jobs.size(); index++) {
            if (jobs.get(index).id.equals(id)) {
                found = jobs.remove(index);
                break;
            }
        }
        if (id != null && !id.isEmpty()) {
            removedIds.add(id);
            while (removedIds.size() > 500) {
                removedIds.remove(0);
            }
        }
        persist();
        notifyListeners();
        return found;
    }

    public synchronized void remove(String id) {
        removeAndGet(id);
    }

    /** Finished and cancelled jobs leave the queue; their record is in History. */
    public synchronized void removeFinished() {
        jobs.removeIf(job -> job.isFinished() || QJob.CANCELLED.equals(job.stage));
        persist();
        notifyListeners();
    }

    public synchronized void removeDone() {
        jobs.removeIf(QJob::isFinished);
        persist();
        notifyListeners();
    }

    public synchronized void clear() {
        jobs.clear();
        pausedAll = false;
        persist();
        notifyListeners();
    }

    private void trim() {
        while (jobs.size() > MAX_JOBS) {
            jobs.remove(0);
        }
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
        //: The queue is served on its own thread, but every listener is a
        //: screen: the callbacks go to the main thread, and a listener that
        //: throws is swallowed while the queue carries on.  Before this, a
        //: repaint from the worker thread threw "Only the original thread that
        //: created a view hierarchy can touch its views" and the running job was
        //: marked failed with that sentence as its reason.
        UiThread.safe(() -> {
            for (Listener listener : listeners) {
                try {
                    listener.onJobsChanged();
                } catch (Throwable ignored) {
                }
            }
            //: The home screen and the Quick Settings panel see the same queue.
            Widget.touch(app);
        });
    }

    // --------------------------------------------------------- persistence //

    private File file() {
        return new File(app.getFilesDir(), FILE_NAME);
    }

    private void load() {
        File file = file();
        if (!file.exists()) {
            return;
        }
        try {
            String text = readAll(file);
            if (text.isEmpty()) {
                return;
            }
            JSONArray array = new JSONArray(text);
            synchronized (this) {
                jobs.clear();
                for (int index = 0; index < array.length(); index++) {
                    JSONObject json = array.optJSONObject(index);
                    if (json != null) {
                        jobs.add(QJob.from(json));
                    }
                }
            }
        } catch (Exception ignored) {
            //: A damaged queue file must never stop the app from starting.
        }
    }

    private void persist() {
        final JSONArray array = new JSONArray();
        for (QJob job : new ArrayList<>(jobs)) {
            array.put(job.toJson());
        }
        final String payload = array.toString();
        writer.execute(() -> writeAll(file(), payload));
    }

    static String readAll(File file) throws Exception {
        try (RandomAccessFile reader = new RandomAccessFile(file, "r")) {
            byte[] bytes = new byte[(int) reader.length()];
            reader.readFully(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }

    /** Atomic write: a half-written file would lose the whole queue. */
    static void writeAll(File file, String payload) {
        try {
            File temp = new File(file.getParentFile(), file.getName() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(temp)) {
                out.write(payload.getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
            if (file.exists() && !file.delete()) {
                //: Fall through: writing over it is still better than nothing.
            }
            //noinspection ResultOfMethodCallIgnored
            temp.renameTo(file);
        } catch (Exception ignored) {
        }
    }

    public static List<QJob> emptyList() {
        return Collections.emptyList();
    }
}
