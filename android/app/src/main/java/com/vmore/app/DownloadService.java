package com.vmore.app;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * The download itself — a foreground service, so it keeps running (with the
 * notification progress the owner asked for) while the app is in the background
 * or closed.
 *
 * Flow: start a job on the server → stream it into the spool file → keep the
 * notification in sync → remember the file locally → offer the editor.
 */
public class DownloadService extends Service {

    public static final String ACTION_START = "com.vmore.app.DOWNLOAD_START";
    public static final String ACTION_PAUSE = "com.vmore.app.DOWNLOAD_PAUSE";
    public static final String ACTION_RESUME = "com.vmore.app.DOWNLOAD_RESUME";
    public static final String ACTION_STOP = "com.vmore.app.DOWNLOAD_STOP";
    public static final String EXTRA_LINK = "link";
    public static final String EXTRA_NAME = "name";
    public static final String EXTRA_JOB = "job";

    /** The screen watches these two so it can draw the same progress bar. */
    public static final class Live {
        public static final AtomicLong WRITTEN = new AtomicLong();
        public static final AtomicLong TOTAL = new AtomicLong();
        public static final AtomicBoolean PAUSED = new AtomicBoolean(false);
        public static volatile String NAME = "";
        public static volatile String STATUS = "idle";
        public static volatile String ERROR = null;
        public static volatile String PATH = null;
    }

    private static volatile DownloadService current;

    private PowerManager.WakeLock wakeLock;
    private volatile boolean stopped = false;
    private volatile boolean paused = false;
    private volatile long lastPostAt = 0L;
    private Thread worker;
    private String jobId;
    private String link;
    private File target;
    /** Direct mode (TDLib on the phone): the file key and the origin message. */
    private volatile int tdFileId;
    private volatile long tdChatId;
    private volatile long tdMessageId;
    private final AtomicBoolean tdCancelled = new AtomicBoolean(false);

    public static boolean running() {
        return current != null;
    }

    public static void start(Context context, String link, String name) {
        Intent intent = new Intent(context, DownloadService.class);
        intent.setAction(ACTION_START);
        intent.putExtra(EXTRA_LINK, link);
        intent.putExtra(EXTRA_NAME, name);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception exc) {
            //: Some OEM builds refuse a foreground start from the background —
            //: the screen then shows the message instead of crashing.
            Live.STATUS = "error";
            Live.ERROR = "the phone blocked the background download (" + exc.getMessage() + ")";
        }
    }

    /**
     * Drive a running download (pause / resume / stop).
     *
     * ``startForegroundService`` on Android 8+: a plain ``startService`` from the
     * background throws, which would have made the screen buttons work but the
     * notification buttons silently do nothing.
     */
    public static void command(Context context, String action) {
        Intent intent = new Intent(context, DownloadService.class);
        intent.setAction(action);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        current = this;
        Notifications.ensureChannels(this);
        PowerManager power = getSystemService(PowerManager.class);
        if (power != null) {
            wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "vmore:download");
            wakeLock.setReferenceCounted(false);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_RESUME : intent.getAction();
        if (action == null) {
            action = ACTION_RESUME;
        }
        if (ACTION_PAUSE.equals(action)) {
            paused = true;
            Live.PAUSED.set(true);
            Live.STATUS = "paused";
            //: Android may have started this service looking for a foreground
            //: service (the notification's Pause button) — satisfy that in the
            //: same breath as the state change.
            keepForeground();
            post("paused");
            postJob("pause");
            if (tdFileId != 0) {
                tdCancelled.set(true);
                TdDirect.get(this).cancelDownload(tdFileId);
            }
            return START_STICKY;
        }
        if (ACTION_RESUME.equals(action)) {
            paused = false;
            stopped = false;
            tdCancelled.set(false);
            Live.PAUSED.set(false);
            Live.STATUS = "downloading";
            keepForeground();
            postJob("resume");
            //: Pausing closed the socket (server mode) or cancelled TDLib's feed
            //: (direct mode).  Either way, resuming asks for the rest — the
            //: server answers with a Range, TDLib continues from its prefix.
            if (worker == null && jobId != null && target != null) {
                final long total = Live.TOTAL.get();
                if (jobId.startsWith("td:")) {
                    worker = new Thread(() -> streamDirect(total), "vmore-td-download");
                } else {
                    final String id = jobId;
                    worker = new Thread(() -> stream(id, target.getName(), total), "vmore-download");
                }
                worker.start();
            }
            return START_STICKY;
        }
        if (ACTION_STOP.equals(action)) {
            stopped = true;
            postJob("cancel");
            if (tdFileId != 0) {
                tdCancelled.set(true);
                TdDirect.get(this).cancelDownload(tdFileId);
            }
            finish("stopped", null, null);
            return START_NOT_STICKY;
        }
        if (ACTION_START.equals(action) && intent != null && worker == null) {
            link = intent.getStringExtra(EXTRA_LINK);
            begin(intent.getStringExtra(EXTRA_NAME));
        }
        return START_STICKY;
    }

    private void begin(String name) {
        String display = name == null || name.isEmpty() ? "Vmore download" : name;
        Live.NAME = display;
        Live.STATUS = "preparing";
        Live.ERROR = null;
        startForeground(Notifications.ID_PROGRESS,
                Notifications.progress(this, display, 0, 0, false));
        if (wakeLock != null) {
            wakeLock.acquire(60 * 60 * 1000L);
        }
        tdCancelled.set(false);
        if (TdDirect.get(this).isReady()) {
            //: Direct mode: the phone pulls straight from Telegram; the server
            //: learns nothing about this download and spends nothing on it.
            worker = new Thread(this::resolveAndDownloadDirect, "vmore-td-download");
        } else {
            worker = new Thread(this::resolveAndDownload, "vmore-download");
        }
        worker.start();
    }

    /** Direct mode: resolve with the phone's own session, then stream. */
    private void resolveAndDownloadDirect() {
        try {
            TdDirect direct = TdDirect.get(this);
            TdDirect.Resolved resolved = direct.resolveBlocking(link);
            tdFileId = resolved.fileId;
            tdChatId = resolved.chatId;
            tdMessageId = resolved.messageId;
            jobId = "td:" + resolved.chatId + ":" + resolved.messageId;
            String fileName = resolved.fileName == null || resolved.fileName.isEmpty()
                    ? "Vmore.bin" : resolved.fileName;
            target = new File(LocalStore.downloadsDir(this), fileName);
            Live.PATH = target.getAbsolutePath();
            Live.STATUS = "downloading";
            streamDirect(resolved.fileSize);
        } catch (Exception exc) {
            if (stopped) {
                finish("stopped", null, null);
                return;
            }
            if (paused) {
                post("paused");
                worker = null;
                return;
            }
            finish("error", exc.getMessage(), null);
        }
    }

    private void streamDirect(long total) {
        Live.TOTAL.set(total);
        try {
            String path = TdDirect.get(this).downloadBlocking(tdFileId,
                    (done, full) -> {
                        Live.WRITTEN.set(done);
                        if (full > 0) {
                            Live.TOTAL.set(full);
                        }
                        post("download");
                    }, tdCancelled);
            if (stopped) {
                finish("stopped", null, null);
                return;
            }
            if (paused) {
                post("paused");
                worker = null;
                return;
            }
            moveIntoPlace(new File(path), target);
            finish("done", null, null);
        } catch (Exception exc) {
            if (stopped) {
                finish("stopped", null, null);
                return;
            }
            if (paused) {
                //: TDLib keeps the partial prefix, so a later resume continues.
                post("paused");
                worker = null;
                return;
            }
            finish("error", exc.getMessage(), null);
        }
    }

    /** The completed file lives in TDLib's directory; the app's flow wants it
     *  named like every other download inside the Vmore folder. */
    private void moveIntoPlace(File source, File destination) throws IOException {
        if (source.equals(destination)) {
            return;
        }
        if (destination.exists()) {
            //noinspection ResultOfMethodCallIgnored
            destination.delete();
        }
        if (source.renameTo(destination)) {
            return;
        }
        try (FileInputStream in = new FileInputStream(source);
             FileOutputStream out = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            out.flush();
        }
        //noinspection ResultOfMethodCallIgnored
        source.delete();
    }

    /** Ask the server what is behind the link, then start streaming it. */
    private void resolveAndDownload() {
        String base = Prefs.baseUrl(this);
        String token = Prefs.token(this);
        try {
            JSONObject body = new JSONObject().put("link", link);
            JSONObject created = post(base, token, "/job", body);
            if (created == null || !created.optBoolean("ok", false)) {
                finish("error", created == null ? "the server did not start the download"
                        : created.optString("error", "could not start"), null);
                return;
            }
            JSONObject job = created.getJSONObject("job");
            jobId = job.optString("id");
            String fileName = job.optString("file_name", "Vmore.bin");
            long total = job.optLong("total", 0L);
            target = new File(LocalStore.downloadsDir(this), fileName);
            Live.PATH = target.getAbsolutePath();
            Live.STATUS = "downloading";
            stream(jobId, fileName, total);
        } catch (Exception exc) {
            finish("error", exc.getMessage(), null);
        }
    }

    private void stream(String id, String fileName, long total) {
        String url = Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this))
                + "/job/" + id + "/file";
        Live.TOTAL.set(total);
        try {
            Api.download(url, target, (written, reported) -> {
                //: Returning false closes the socket at once.  That is what makes
                //: Pause instant (and Stop immediate); Resume asks the server for
                //: the remaining bytes with a Range request.
                if (stopped || paused) {
                    Live.WRITTEN.set(written);
                    return false;
                }
                Live.WRITTEN.set(written);
                if (reported > 0) {
                    Live.TOTAL.set(reported);
                }
                post("download");
                return true;
            });
        } catch (Api.Stopped exc) {
            if (stopped) {
                finish("stopped", null, null);
                return;
            }
            paused = true;
            keepForeground();
            post("paused");
            worker = null;
            return;
        } catch (Exception exc) {
            finish("error", exc.getMessage(), null);
            return;
        }
        if (stopped) {
            finish("stopped", null, null);
            return;
        }
        if (paused) {
            //: The socket was closed; keep the notification and resume later.
            post("paused");
            worker = null;
            return;
        }
        finish("done", null, null);
    }

    private void finish(String status, String error, String ignored) {
        Live.STATUS = status;
        Live.ERROR = error;
        if (worker == Thread.currentThread()) {
            worker = null;
        }
        if ("done".equals(status) && target != null && target.exists() && target.length() > 0) {
            LocalStore.Item item = new LocalStore.Item();
            item.name = target.getName();
            item.path = target.getAbsolutePath();
            item.link = link;
            //: Server downloads carry the job id (the commit endpoint replays the
            //: spool); direct downloads carry "td:<chat>:<message>" (the editor's
            //: zero-byte forward target).
            item.kind = jobId;
            item.status = "done";
            item.size = target.length();
            item.date = System.currentTimeMillis();
            LocalStore.add(this, item);
            String where = target.getParentFile() == null ? null : "Vmore";
            android.app.NotificationManager manager =
                    getSystemService(android.app.NotificationManager.class);
            if (manager != null) {
                manager.notify(Notifications.ID_DONE,
                        Notifications.finished(this, target.getName(), where));
            }
        } else if ("error".equals(status) && target != null) {
            android.app.NotificationManager manager =
                    getSystemService(android.app.NotificationManager.class);
            if (manager != null) {
                manager.notify(Notifications.ID_DONE,
                        Notifications.failed(this, target.getName(), String.valueOf(error)));
            }
        }
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        stopForeground(true);
        stopSelf();
    }

    /**
     * Re-assert the foreground notification.
     *
     * Cheap and idempotent, but it is also the contract Android enforces: a
     * service started with {@code startForegroundService()} (which is how the
     * notification's Pause / Resume buttons reach us) must call
     * {@code startForeground()} promptly.
     */
    private void keepForeground() {
        if (target == null) {
            stopSelf();
            return;
        }
        startForeground(Notifications.ID_PROGRESS, Notifications.progress(
                this, Live.NAME, Live.WRITTEN.get(), Live.TOTAL.get(), paused));
    }

    private void post(String state) {
        android.app.NotificationManager manager =
                getSystemService(android.app.NotificationManager.class);
        if (manager == null || target == null) {
            return;
        }
        long now = System.currentTimeMillis();
        if ("download".equals(state) && now - lastPostAt < 400) {
            return;                       // not 16 notifications per megabyte
        }
        lastPostAt = now;
        manager.notify(Notifications.ID_PROGRESS, Notifications.progress(
                this, Live.NAME, Live.WRITTEN.get(), Live.TOTAL.get(), paused));
    }

    /** Tell the server about pause / resume / cancel (best effort, never blocking). */
    private void postJob(String suffix) {
        if (jobId == null || jobId.startsWith("td:")) {
            //: Direct-mode downloads have no server job to inform about.
            return;
        }
        final String id = jobId;
        final String base = Prefs.baseUrl(this);
        final String token = Prefs.token(this);
        new Thread(() -> {
            try {
                Api.post(Api.tokenUrl(base, token) + "/job/" + id + "/" + suffix,
                        new JSONObject(), result -> {
                        });
            } catch (Exception ignored) {
            }
        }).start();
    }

    private JSONObject post(String base, String token, String path, JSONObject body) {
        Api.Result[] holder = new Api.Result[1];
        Object lock = new Object();
        Api.post(Api.tokenUrl(base, token) + path, body, result -> {
            synchronized (lock) {
                holder[0] = result;
                lock.notifyAll();
            }
        });
        synchronized (lock) {
            long deadline = System.currentTimeMillis() + 30_000;
            while (holder[0] == null && System.currentTimeMillis() < deadline) {
                try {
                    lock.wait(200);
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        return holder[0] == null ? null : holder[0].json;
    }

    @Override
    public void onDestroy() {
        current = null;
        stopped = true;
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
