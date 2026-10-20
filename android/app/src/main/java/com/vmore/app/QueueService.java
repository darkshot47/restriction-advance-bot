package com.vmore.app;

import android.app.Notification;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Foreground transfer engine for Vmore.
 *
 * Every queued link attempts a zero-data server copy (`tryNativeCopy` /
 * `native_cpy`) first whenever a destination chat is set. When Telegram accepts
 * the direct copy, the job finishes immediately without touching mobile data.
 * When Telegram refuses (protected/restricted content or caption rules that
 * require re-upload), the engine automatically falls back to downloading into
 * cache storage (`context.getCacheDir()`), uploading via mobile data, and
 * cleaning up temporary cache files.
 *
 * Removing or stopping a job immediately cancels all active TDLib downloads and
 * uploads and deletes every partial or cached file written so far.
 */
public class QueueService extends Service {

    public static final String ACTION_RUN = "com.vmore.app.RUN";
    public static final String ACTION_PAUSE_ALL = "com.vmore.app.PAUSE_ALL";
    public static final String ACTION_RESUME_ALL = "com.vmore.app.RESUME_ALL";
    public static final String ACTION_STOP_JOB = "com.vmore.app.STOP_JOB";
    public static final String ACTION_REMOVE_JOB = "com.vmore.app.REMOVE_JOB";
    public static final String ACTION_SKIP_JOB = "com.vmore.app.SKIP_JOB";
    public static final String EXTRA_JOB_ID = "job_id";

    /** How long a freshly woken queue waits for the Telegram session. */
    private static final long WAIT_FOR_SESSION_MS = 90_000L;
    /** Attempts per job, and the pause between them (it grows a little). */
    private static final int MAX_ATTEMPTS = 4;
    /** Room kept free on top of the file itself, for the upload copy. */
    private static final long FREE_MARGIN = 64L * 1024L * 1024L;
    private static final long RETRY_WAIT_MS = 6_000L;
    /** How often a queue waiting for Wi-Fi or the charger looks again. */
    private static final long HOLD_POLL_MS = 5_000L;
    /** How long the queue waits for a session that is still coming up. */
    private static final long ENGINE_WAIT_MAX = 180_000L;

    /** Live numbers for whichever job is running — read by every screen. */
    public static final class Live {
        public static volatile String JOB_ID = "";
        public static volatile String NAME = "";
        public static volatile String STAGE = "";
        public static volatile String ERROR = "";
        public static volatile long STARTED_AT = 0L;
        public static final AtomicLong DONE = new AtomicLong();
        public static final AtomicLong TOTAL = new AtomicLong();
        public static final AtomicBoolean RUNNING = new AtomicBoolean(false);
        public static volatile double SPEED;      // bytes per second
        public static volatile long ETA_MS;

        public static void reset() {
            JOB_ID = "";
            NAME = "";
            STAGE = "";
            ERROR = "";
            SPEED = 0;
            ETA_MS = 0;
            DONE.set(0);
            TOTAL.set(0);
            STARTED_AT = 0L;
        }
    }

    private static volatile QueueService current;

    private PowerManager.WakeLock wakeLock;
    private Thread worker;
    private volatile QJob currentRunningJob;
    private volatile boolean shuttingDown;
    /** The exception the last attempt died of — read by the retry rule. */
    private volatile Exception lastFailure;
    /** The reason the queue last waited, so the log gets it once, not 700 times. */
    private volatile String lastHold = "";
    private final AtomicBoolean cancelled = new AtomicBoolean(false);
    private final AtomicBoolean skipCurrent = new AtomicBoolean(false);
    private final AtomicBoolean removingCurrent = new AtomicBoolean(false);
    private long postedAt;
    private int completedJobs;
    private int skippedJobs;
    private String lastName = "";
    private String lastWhere = "";

    // -------------------------------------------------------------- control //

    public static boolean running() {
        return current != null;
    }

    public static void run(Context context) {
        Prefs.setStartNow(context, true);
        dispatch(context, ACTION_RUN, null);
    }

    public static void pauseAll(Context context) {
        dispatch(context, ACTION_PAUSE_ALL, null);
    }

    public static void resumeAll(Context context) {
        dispatch(context, ACTION_RESUME_ALL, null);
    }

    public static void stopJob(Context context, String jobId) {
        dispatch(context, ACTION_STOP_JOB, jobId);
    }

    /**
     * Immediately removes one job from the queue, stops any running TDLib
     * background download or upload for it on the spot, and deletes all partial
     * or cached bytes written so far.
     */
    public static void removeJob(Context context, String jobId) {
        if (context == null || jobId == null || jobId.isEmpty()) {
            return;
        }
        Context app = context.getApplicationContext();
        Jobs jobs = Jobs.get(app);
        QJob removed = jobs.removeAndGet(jobId);
        QueueService service = current;
        if (removed == null && service != null && service.currentRunningJob != null
                && jobId.equals(service.currentRunningJob.id)) {
            removed = service.currentRunningJob;
        }
        if (service != null
                && (jobId.equals(Live.JOB_ID)
                || (service.currentRunningJob != null
                && jobId.equals(service.currentRunningJob.id)))) {
            service.removingCurrent.set(true);
            service.cancelled.set(true);
            Thread activeWorker = service.worker;
            if (activeWorker != null) {
                activeWorker.interrupt();
            }
            Live.reset();
        }
        if (removed != null) {
            removed.stage = QJob.CANCELLED;
            purgeJobFiles(app, removed);
            History.get(app).record(removed.title(), removed.kind, removed.size,
                    removed.destChatId, removed.destTitle, History.STATUS_FAILED,
                    removed.raw, "cancelled and deleted", "");
        }
        if (service != null) {
            dispatch(app, ACTION_REMOVE_JOB, jobId);
        }
    }

    public static void skipJob(Context context, String jobId) {
        dispatch(context, ACTION_SKIP_JOB, jobId);
    }

    /**
     * Cancels active TDLib file transfers and deletes every partial or staged
     * file associated with {@code job} across all cache folders.
     */
    public static void purgeJobFiles(Context context, QJob job) {
        if (context == null || job == null) {
            return;
        }
        Context app = context.getApplicationContext();
        try {
            Tg.get(app).abortJobTransfers(job);
        } catch (Throwable ignored) {
        }
        if (job.path != null && !job.path.isEmpty()) {
            //noinspection ResultOfMethodCallIgnored
            new File(job.path).delete();
            History.get(app).markLocalGone(job.path);
            job.path = "";
        }
        if (job.name != null && !job.name.isEmpty()) {
            File staged = new File(LocalFiles.downloadsDir(app), job.name);
            if (staged.isFile()) {
                //noinspection ResultOfMethodCallIgnored
                staged.delete();
                History.get(app).markLocalGone(staged.getAbsolutePath());
            }
        }
        job.done = 0;
    }

    private static void dispatch(Context context, String action, String jobId) {
        Intent intent = new Intent(context, QueueService.class);
        intent.setAction(action);
        if (jobId != null) {
            intent.putExtra(EXTRA_JOB_ID, jobId);
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception ignored) {
        }
    }

    // -------------------------------------------------------------- service //

    @Override
    public void onCreate() {
        super.onCreate();
        current = this;
        Notifications.ensureChannels(this);
        PowerManager power = getSystemService(PowerManager.class);
        if (power != null) {
            wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "vmore:queue");
            wakeLock.setReferenceCounted(false);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_RUN : intent.getAction();
        if (action == null) {
            action = ACTION_RUN;
        }
        Jobs jobs = Jobs.get(this);
        postProgress(false);
        switch (action) {
            case ACTION_PAUSE_ALL:
                jobs.setPausedAll(true);
                Live.RUNNING.set(false);
                cancelled.set(true);
                QJob runningNow = currentRunningJob != null ? currentRunningJob : jobs.active();
                if (runningNow != null && runningNow.fileId != 0) {
                    Tg.get(this).cancelDownload(runningNow.fileId);
                }
                postProgress(true);
                if (worker == null || !worker.isAlive()) {
                    stopForegroundCompat(STOP_FOREGROUND_DETACH);
                    stopSelf();
                }
                return START_STICKY;
            case ACTION_RESUME_ALL:
                jobs.setPausedAll(false);
                Live.ERROR = "";
                startWorker();
                return START_STICKY;
            case ACTION_REMOVE_JOB:
                if (!jobs.hasWork() && (worker == null || !worker.isAlive())) {
                    Notifications.cancelProgress(this);
                    stopForegroundCompat(STOP_FOREGROUND_REMOVE);
                    stopSelf();
                    return START_NOT_STICKY;
                }
                postProgress(false);
                return START_STICKY;
            case ACTION_STOP_JOB:
                cancelled.set(true);
                String jobId = intent == null ? null : intent.getStringExtra(EXTRA_JOB_ID);
                if (jobId == null) {
                    stopEverything(jobs);
                    return START_NOT_STICKY;
                }
                markCancelled(jobId);
                return START_STICKY;
            case ACTION_SKIP_JOB:
                skipCurrent.set(true);
                cancelled.set(true);
                if (currentRunningJob != null) {
                    purgeJobFiles(this, currentRunningJob);
                }
                return START_STICKY;
            default:
                startWorker();
                return START_STICKY;
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        shuttingDown = true;
        cancelled.set(true);
        current = null;
        releaseWakeLock();
        super.onDestroy();
    }

    // --------------------------------------------------------------- worker //

    private void startWorker() {
        if (worker != null && worker.isAlive()) {
            return;
        }
        if (Jobs.get(this).pausedAll()) {
            showNotification(true);
            return;
        }
        acquireWakeLock();
        completedJobs = 0;
        skippedJobs = 0;
        Live.RUNNING.set(true);
        Live.STAGE = "";
        worker = new Thread(this::loop, "vmore-queue");
        worker.start();
    }

    private void loop() {
        Jobs jobs = Jobs.get(this);
        try {
            boolean engineReady = Tg.get(this).awaitReady(WAIT_FOR_SESSION_MS);
            long engineWaited = 0L;
            while (!shuttingDown) {
                if (jobs.pausedAll()) {
                    break;
                }
                if (!Tg.get(this).isReady()) {
                    engineReady = Tg.get(this).awaitReady(WAIT_FOR_SESSION_MS);
                }
                String hold = holdReason();
                if (!hold.isEmpty()) {
                    hold(hold);
                    continue;
                }
                QJob job = jobs.nextQueued();
                if (job == null) {
                    break;
                }
                if (!engineReady) {
                    if (Tg.get(this).starting() && engineWaited < ENGINE_WAIT_MAX) {
                        engineWaited += HOLD_POLL_MS;
                        hold("waiting for the Telegram session");
                        continue;
                    }
                    failJob(jobs, job, Tg.get(this).blockedReason());
                    continue;
                }
                lastHold = "";
                cancelled.set(false);
                skipCurrent.set(false);
                removingCurrent.set(false);
                currentRunningJob = job;
                try {
                    process(jobs, job);
                    if (!jobs.wasRemoved(job.id)) {
                        jobs.update(job);
                    }
                } finally {
                    currentRunningJob = null;
                    // Clear thread interrupt status if removeJob interrupted sleep/wait
                    Thread.interrupted();
                }
            }
        } catch (Throwable error) {
            Live.ERROR = String.valueOf(error.getMessage());
        } finally {
            Live.RUNNING.set(false);
            if (!shuttingDown) {
                finishUp(jobs);
            }
        }
    }

    private void finishUp(Jobs jobs) {
        QJob active = jobs.active();
        Live.reset();
        if (jobs.pausedAll()) {
            postProgress(true);
            stopForegroundCompat(STOP_FOREGROUND_DETACH);
            stopSelf();
            return;
        }
        if (active != null || jobs.hasWork()) {
            showNotification(false);
            return;
        }
        if (completedJobs > 0 || skippedJobs > 0) {
            String extra = skippedJobs == 0 ? lastName
                    : lastName + " (" + skippedJobs + " left out by the filters)";
            Notifications.finished(this, extra, lastWhere);
        }
        Notifications.cancelProgress(this);
        stopForegroundCompat(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private void process(Jobs jobs, QJob job) {
        int attempt = 0;
        while (!shuttingDown && !jobs.wasRemoved(job.id)) {
            attempt++;
            job.attempts = attempt;
            lastFailure = null;
            processOnce(jobs, job);
            if (jobs.wasRemoved(job.id) || removingCurrent.get()) {
                purgeJobFiles(this, job);
                return;
            }
            if (!QJob.FAILED.equals(job.stage)) {
                return;
            }
            boolean staleReference = job.fileId != 0;
            boolean again = attempt < MAX_ATTEMPTS && !cancelled.get() && !jobs.pausedAll()
                    && worthRetrying(lastFailure, job.error, staleReference);
            Log.step(this, "job " + job.id + " attempt " + attempt + " failed: "
                    + job.error + (again ? " (trying again with a fresh link)" : ""));
            if (!again) {
                recordFailure(jobs, job);
                return;
            }
            if (staleReference) {
                job.fileId = 0;
            }
            job.stage = QJob.QUEUED;
            job.error = "";
            jobs.update(job);
            Live.reset();
            Live.RUNNING.set(true);
            Live.JOB_ID = job.id;
            Live.NAME = job.title();
            Live.STAGE = QJob.QUEUED;
            postProgress(false);
            sleep(RETRY_WAIT_MS * attempt);
        }
    }

    private void hold(String reason) {
        Live.STAGE = "";
        Live.NAME = reason;
        Live.RUNNING.set(true);
        if (!reason.equals(lastHold)) {
            lastHold = reason;
            Log.step(this, "holding: " + reason);
        }
        postProgress(false);
        sleep(HOLD_POLL_MS);
    }

    private String holdReason() {
        String schedule = Net.scheduleBlocker(this);
        if (!schedule.isEmpty()) {
            return schedule;
        }
        return Net.blocker(this);
    }

    private static boolean worthRetrying(Exception failure, String message, boolean stale) {
        if (failure instanceof Tg.Failure) {
            return ((Tg.Failure) failure).retryable;
        }
        if (Retry.fatal(message)) {
            return false;
        }
        if (stale) {
            return true;
        }
        return Retry.recoverable(message);
    }

    private void sleep(long millis) {
        try {
            Thread.sleep(Math.max(0L, millis));
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    private void recordFailure(Jobs jobs, QJob job) {
        if (jobs.wasRemoved(job.id)) {
            return;
        }
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_FAILED, job.raw, job.error, job.path);
        jobs.update(job);
    }

    private void failJob(Jobs jobs, QJob job, String reason) {
        if (jobs.wasRemoved(job.id)) {
            return;
        }
        job.stage = QJob.FAILED;
        job.error = reason;
        Live.STAGE = QJob.FAILED;
        Live.ERROR = reason;
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_FAILED, job.raw, reason, job.path);
        jobs.update(job);
    }

    private void processOnce(Jobs jobs, QJob job) {
        Live.reset();
        Live.JOB_ID = job.id;
        Live.NAME = job.title();
        Live.TOTAL.set(job.size);
        Live.DONE.set(job.done);
        Log.step(this, "job " + job.id + " " + job.method + " " + shortText(job.raw, 120));
        try {
            if (QJob.METHOD_SCAN.equals(job.method)) {
                scanIntoQueue(jobs, job);
                return;
            }
            if (job.chatId == 0L || job.messageId == 0L
                    || (job.fileId == 0 && !"text".equals(job.kind))) {
                resolveJob(jobs, job);
                if (abortIfInterrupted(jobs, job)) {
                    return;
                }
            }

            String skip = skipReason(job);
            if (!skip.isEmpty()) {
                skippedJobs++;
                Log.step(this, "job " + job.id + " " + skip);
                job.skipped = true;
                job.note = skip;
                job.stage = QJob.DONE;
                Live.STAGE = QJob.DONE;
                Live.ERROR = "";
                jobs.update(job);
                jobs.remove(job.id);
                Tg.get(this).releaseDownload(job.fileId);
                return;
            }

            //: Step 1 (`native_cpy`): ALWAYS attempt direct server-side copy
            //: first whenever a destination chat is set. If Telegram copies the
            //: message on its servers, finish immediately with zero mobile data
            //: downloaded or uploaded. If refused (protected/restricted source),
            //: seamlessly fall back to cache download + mobile-data upload below.
            if (job.uploadAfter && job.destChatId != 0L) {
                if (tryNativeCopy(jobs, job)) {
                    return;
                }
                if (abortIfInterrupted(jobs, job)) {
                    return;
                }
            }

            //: Step 2 (Data fallback): protected text messages have no file to
            //: download, so send their text body directly; media files download
            //: into cache storage (`getCacheDir()`) and upload from cache.
            if ("text".equals(job.kind) && job.fileId == 0) {
                if (job.destChatId != 0L) {
                    job.stage = QJob.UPLOADING;
                    Live.STAGE = QJob.UPLOADING;
                    jobs.update(job);
                    showNotification(false);
                    long sentId = Tg.get(this).sendTextBlocking(
                            job.destChatId, job.caption, cancelled);
                    History.get(this).record(job.title(), job.kind, job.size,
                            job.destChatId, job.destTitle, History.STATUS_UPLOADED,
                            job.raw, "", "");
                    job.note = "sent as message " + sentId;
                    markFinished(job);
                }
                job.stage = QJob.DONE;
                Live.STAGE = QJob.DONE;
                jobs.remove(job.id);
                return;
            }

            String space = spaceProblem(job.size);
            if (!space.isEmpty()) {
                Log.step(this, "job " + job.id + " " + space);
                job.stage = QJob.FAILED;
                job.error = space;
                Live.STAGE = QJob.FAILED;
                Live.ERROR = space;
                jobs.update(job);
                return;
            }

            job.stage = QJob.DOWNLOADING;
            Live.STAGE = QJob.DOWNLOADING;
            Live.TOTAL.set(job.size);
            jobs.update(job);
            showNotification(false);

            String rawDownloadedPath = download(job);
            if (abortIfInterrupted(jobs, job) || rawDownloadedPath == null) {
                return;
            }
            Log.step(this, "job " + job.id + " cached download "
                    + shortText(rawDownloadedPath, 80) + " (" + Format.size(job.size) + ")");

            String stagedPath = stageIntoCacheDownloads(rawDownloadedPath, job);
            job.path = stagedPath;
            job.size = job.size > 0 ? job.size : new File(stagedPath).length();
            job.done = job.size;
            Live.DONE.set(job.done);

            if (job.uploadAfter && job.destChatId != 0L) {
                job.stage = QJob.UPLOADING;
                Live.STAGE = QJob.UPLOADING;
                Live.DONE.set(0);
                jobs.update(job);
                showNotification(false);
                long sentId = Tg.get(this).sendBlocking(job, (done, total) -> {
                    Live.DONE.set(done);
                    Live.TOTAL.set(total);
                    jobs.ping();
                }, cancelled);
                if (abortIfInterrupted(jobs, job)) {
                    return;
                }
                job.uploaded = job.size;
                job.note = "";
                Stats.rememberUploaded(this, String.valueOf(job.fileId), job.size);

                if (job.deleteLocal) {
                    deleteLocalCopy(job);
                    History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                            job.destTitle, History.STATUS_UPLOADED, job.raw, "", "");
                } else {
                    if (!stagedPath.equals(rawDownloadedPath)) {
                        Tg.get(this).forgetFile(job.fileId);
                    }
                    History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                            job.destTitle, History.STATUS_UPLOADED, job.raw, "", job.path);
                }
                job.note = "sent as message " + sentId;
                Log.step(this, "job " + job.id + " uploaded to " + shortText(job.destTitle, 40)
                        + " as message " + sentId);
                markFinished(job);
            } else {
                if (!stagedPath.equals(rawDownloadedPath)) {
                    Tg.get(this).forgetFile(job.fileId);
                }
                History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                        job.destTitle, History.STATUS_DOWNLOADED, job.raw, "", job.path);
                markFinished(job);
            }

            job.stage = QJob.DONE;
            Live.STAGE = QJob.DONE;
            jobs.remove(job.id);
            Tg.get(this).releaseDownload(job.fileId);
        } catch (Exception error) {
            lastFailure = error;
            if (abortIfInterrupted(jobs, job)) {
                return;
            }
            String message = error.getMessage() == null ? "the job failed" : error.getMessage();
            Log.step(this, "job " + job.id + " " + job.stage + ": " + message);
            if (message.contains("original thread")) {
                Log.step(this, "job " + job.id + " hit a screen error, not a transfer one");
                job.stage = QJob.QUEUED;
                job.error = "";
                jobs.update(job);
                return;
            }
            job.stage = QJob.FAILED;
            job.error = message;
            Live.STAGE = QJob.FAILED;
            Live.ERROR = message;
            jobs.update(job);
        }
    }

    /**
     * Attempts zero-data server-side `native_cpy` first. Returns {@code true}
     * if Telegram completed the copy directly on its servers so no download is
     * needed; returns {@code false} when fallback to mobile data is required.
     */
    private boolean tryNativeCopy(Jobs jobs, QJob job) {
        if (job.chatId == 0L || job.messageId == 0L || job.destChatId == 0L) {
            return false;
        }
        job.stage = QJob.COPYING;
        Live.STAGE = QJob.COPYING;
        Live.NAME = job.title();
        jobs.update(job);
        showNotification(false);
        try {
            boolean keepForwardHeader = QJob.METHOD_FORWARD.equals(job.method);
            long sentId = Tg.get(this).nativeCopyBlocking(
                    job, job.caption, keepForwardHeader, cancelled);
            if (jobs.wasRemoved(job.id) || removingCurrent.get()) {
                return false;
            }
            if (job.fileId != 0) {
                Stats.rememberUploaded(this, String.valueOf(job.fileId), job.size);
            }
            History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                    job.destTitle, History.STATUS_UPLOADED, job.raw, "", "");
            job.note = "copied directly without using mobile data (message " + sentId + ")";
            Log.step(this, "job " + job.id + " native_cpy succeeded to "
                    + shortText(job.destTitle, 40) + " as message " + sentId);
            markFinished(job);
            job.stage = QJob.DONE;
            Live.STAGE = QJob.DONE;
            jobs.remove(job.id);
            return true;
        } catch (Exception copyRefused) {
            if (cancelled.get() || jobs.wasRemoved(job.id) || removingCurrent.get()) {
                return false;
            }
            String why = copyRefused.getMessage() == null
                    ? "direct copy refused" : copyRefused.getMessage();
            Log.step(this, "job " + job.id + " native_cpy refused (" + why
                    + "); falling back to cache download and data upload");
            job.method = QJob.METHOD_DOWNLOAD;
            job.uploadAfter = true;
            job.error = "";
            job.note = "direct copy refused; downloading via data";
            jobs.update(job);
            return false;
        }
    }

    private boolean abortIfInterrupted(Jobs jobs, QJob job) {
        if (jobs.wasRemoved(job.id) || removingCurrent.get()) {
            purgeJobFiles(this, job);
            return true;
        }
        if (cancelled.get()) {
            if (skipCurrent.get()) {
                dropJob(jobs, job);
            } else {
                Tg.get(this).cancelDownload(job.fileId);
                markPaused(jobs, job);
            }
            return true;
        }
        return false;
    }

    /**
     * Stages a downloaded file inside {@code <cacheDir>/downloads/} so all
     * Vmore files stay 100% under Android Cache storage (`Clear Cache`), never
     * inflating User Data storage.
     */
    private String stageIntoCacheDownloads(String rawPath, QJob job) {
        if (job.uploadAfter && job.destChatId != 0L && job.deleteLocal) {
            return rawPath;
        }
        File target = new File(downloadsDir(),
                Format.safeName(job.name, "vmore_" + job.messageId));
        if (target.getAbsolutePath().equals(rawPath)) {
            return rawPath;
        }
        File copied = LocalFiles.copy(rawPath, target);
        return copied != null ? copied.getAbsolutePath() : rawPath;
    }

    private void scanIntoQueue(Jobs jobs, QJob job) throws Exception {
        job.stage = QJob.RESOLVING;
        Live.STAGE = QJob.RESOLVING;
        Live.NAME = shortText(job.raw, 60);
        Live.TOTAL.set(0);
        jobs.update(job);
        showNotification(false);

        TgLink link = new TgLink();
        link.raw = job.raw;
        link.chatId = job.chatId;
        link.username = job.username;
        link.inviteHash = job.inviteHash;
        link.privateLink = job.privateLink;
        link.internalId = job.internalId;
        link.valid = true;

        long chatId = Tg.get(this).chatForBlocking(link, cancelled);
        List<Tg.Media> media = Tg.get(this).scanBlocking(chatId, Vmore.SCAN_LIMIT);
        if (media.isEmpty()) {
            job.stage = QJob.DONE;
            job.note = "nothing to move in that chat";
            Log.step(this, "job " + job.id + " " + job.note);
            Live.STAGE = QJob.DONE;
            jobs.remove(job.id);
            return;
        }
        List<QJob> children = new ArrayList<>();
        for (Tg.Media item : media) {
            QJob child = new QJob();
            child.batchId = job.batchId;
            child.batchLabel = job.batchLabel;
            child.raw = item.chatTitle.isEmpty() ? job.raw : item.chatTitle;
            child.chatId = item.chatId;
            child.messageId = item.messageId;
            child.privateLink = item.chatId < -1000000000000L;
            child.internalId = TgLink.internalFromChatId(item.chatId);
            child.method = QJob.METHOD_FORWARD.equals(job.method)
                    ? QJob.METHOD_FORWARD : QJob.METHOD_DOWNLOAD;
            child.destChatId = job.destChatId;
            child.destTitle = job.destTitle;
            child.sendAs = job.sendAs;
            child.uploadAfter = job.uploadAfter;
            child.deleteLocal = job.deleteLocal;
            child.onlyKinds = job.onlyKinds;
            child.minSize = job.minSize;
            child.maxSize = job.maxSize;
            child.skipDuplicates = job.skipDuplicates;
            child.protectedContent = item.protectedContent;
            child.stage = QJob.QUEUED;
            children.add(child);
        }
        jobs.addBatch(children);
        job.stage = QJob.DONE;
        job.note = children.size() + " files queued from this chat";
        Live.STAGE = QJob.DONE;
        Log.step(this, "job " + job.id + " " + job.note);
        jobs.remove(job.id);
    }

    /** Step one: ask Telegram what is behind the link. */
    private void resolveJob(Jobs jobs, QJob job) throws Exception {
        job.stage = QJob.RESOLVING;
        Live.STAGE = QJob.RESOLVING;
        Live.NAME = job.raw.isEmpty() ? "Link" : job.raw;
        jobs.update(job);
        showNotification(false);

        TgLink link = new TgLink();
        link.raw = job.raw;
        link.chatId = job.chatId;
        link.messageId = job.messageId;
        link.username = job.username;
        link.inviteHash = job.inviteHash;
        link.privateLink = job.privateLink;
        link.internalId = job.internalId;
        link.valid = true;

        Tg.Media media = Tg.get(this).resolveBlocking(link, cancelled);
        if (media.protectedContent) {
            Log.step(this, "job " + job.id + " the chat protects its content; "
                    + "direct copy will fall back to fresh upload if refused");
        }
        job.chatId = media.chatId;
        job.messageId = media.messageId;
        job.fileId = media.fileId;
        job.size = media.size;
        job.name = media.name;
        job.kind = media.kind;
        job.caption = captionFor(job, media);
        job.durationSec = media.durationSec;
        job.width = media.width;
        job.height = media.height;
        job.protectedContent = media.protectedContent;
        if (job.destTitle.isEmpty() && job.destChatId != 0L) {
            try {
                Tg.Chat chat = Tg.get(this).chatBlocking(job.destChatId);
                job.destTitle = chat.title;
            } catch (Exception ignored) {
                job.destTitle = "";
            }
        }
        Live.NAME = job.name;
        Live.TOTAL.set(job.size);
        jobs.update(job);
    }

    private String skipReason(QJob job) {
        if (!"text".equals(job.kind) && !job.allows(job.kind, job.size)) {
            return "left out: the batch filter does not keep this kind of media";
        }
        if (job.skipDuplicates && job.fileId != 0 && job.uploadAfter
                && Stats.alreadyUploaded(this, String.valueOf(job.fileId), job.size)) {
            return "left out: this file was already uploaded once";
        }
        return "";
    }

    private String captionFor(QJob job, Tg.Media media) {
        String template = Prefs.captionTemplate(this);
        if (template != null && !template.isEmpty()) {
            if (template.contains("{name}")) {
                return template.replace("{name}", Format.withoutExtension(media.name));
            }
            return template;
        }
        if (job.caption != null && !job.caption.isEmpty()) {
            return job.caption;
        }
        return media.caption == null ? "" : media.caption;
    }

    private String download(QJob job) throws Exception {
        final long started = System.currentTimeMillis();
        Live.STARTED_AT = started;
        return Tg.get(this).downloadBlocking(job.fileId, (done, total) -> {
            job.done = done;
            if (total > 0) {
                job.size = total;
            }
            Live.DONE.set(done);
            Live.TOTAL.set(total > 0 ? total : job.size);
            long elapsed = Math.max(1, System.currentTimeMillis() - started);
            Live.SPEED = done * 1000.0 / elapsed;
            Live.ETA_MS = Live.SPEED > 0 && job.size > 0
                    ? (long) ((job.size - done) / Live.SPEED * 1000) : 0L;
            jobs().ping();
        }, cancelled);
    }

    private Jobs jobs() {
        return Jobs.get(this);
    }

    private void deleteLocalCopy(QJob job) {
        try {
            File file = job.path == null || job.path.isEmpty() ? null : new File(job.path);
            if (file != null && file.exists()) {
                //noinspection ResultOfMethodCallIgnored
                file.delete();
            }
            File parent = file == null ? null : file.getParentFile();
            if (parent != null && parent.exists() && parent.list() != null
                    && parent.list().length == 0 && !parent.equals(downloadsDir())) {
                //noinspection ResultOfMethodCallIgnored
                parent.delete();
            }
            History.get(this).markLocalGone(job.path);
        } catch (Exception ignored) {
        }
        Tg.get(this).forgetFile(job.fileId);
        job.path = "";
        job.done = 0;
    }

    private File downloadsDir() {
        return LocalFiles.downloadsDir(this);
    }

    private String spaceProblem(long size) {
        if (size <= 0) {
            return "";
        }
        try {
            File dir = downloadsDir();
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
            android.os.StatFs stat = new android.os.StatFs(dir.getAbsolutePath());
            long free = stat.getAvailableBytes();
            if (free < size + FREE_MARGIN) {
                return "not enough space on this phone: this file needs "
                        + Format.size(size) + " and only " + Format.size(free)
                        + " is free";
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    private static String shortText(String text, int max) {
        String value = Format.oneLine(text == null ? "" : text);
        return value.length() <= max ? value : value.substring(0, max) + "...";
    }

    private void markPaused(Jobs jobs, QJob job) {
        if (jobs.wasRemoved(job.id)) {
            return;
        }
        job.stage = QJob.PAUSED;
        Live.STAGE = QJob.PAUSED;
        Live.ERROR = "";
        jobs.update(job);
    }

    private void markCancelled(String jobId) {
        Jobs jobs = Jobs.get(this);
        QJob job = jobId == null
                ? (currentRunningJob != null ? currentRunningJob : jobs.active())
                : jobs.byId(jobId);
        if (job != null) {
            job.stage = QJob.CANCELLED;
            purgeJobFiles(this, job);
            History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                    job.destTitle, History.STATUS_FAILED, job.raw, "stopped", "");
            jobs.remove(job.id);
        }
    }

    private void dropJob(Jobs jobs, QJob job) {
        job.stage = QJob.CANCELLED;
        purgeJobFiles(this, job);
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_FAILED, job.raw, "skipped", "");
        jobs.remove(job.id);
    }

    private void markFinished(QJob job) {
        completedJobs++;
        lastName = job.title();
        lastWhere = job.destTitle == null ? "" : job.destTitle;
    }

    private void stopEverything(Jobs jobs) {
        for (QJob job : jobs.all()) {
            if (QJob.QUEUED.equals(job.stage) || QJob.RESOLVING.equals(job.stage)
                    || QJob.PAUSED.equals(job.stage) || job.isActive()) {
                job.stage = QJob.CANCELLED;
                purgeJobFiles(this, job);
                History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                        job.destTitle, History.STATUS_FAILED, job.raw, "stopped", "");
                jobs.remove(job.id);
            }
        }
        markCancelled(null);
        jobs.setPausedAll(false);
        Live.RUNNING.set(false);
        Live.reset();
        Notifications.cancelProgress(this);
        stopForegroundCompat(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    // -------------------------------------------------------------- helpers //

    private void postProgress(boolean paused) {
        Widget.touch(this);
        Notification notification = Notifications.progress(this, Live.NAME, Live.STAGE,
                Live.DONE.get(), Live.TOTAL.get(), paused);
        try {
            startForeground(Notifications.ID_PROGRESS, notification);
            postedAt = System.currentTimeMillis();
        } catch (Exception ignored) {
        }
    }

    private void showNotification(boolean paused) {
        if (!paused && System.currentTimeMillis() - postedAt < 500) {
            return;
        }
        postProgress(paused);
    }

    private void acquireWakeLock() {
        if (wakeLock != null && !wakeLock.isHeld()) {
            wakeLock.acquire(6 * 60 * 60 * 1000L);
        }
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
    }

    private void stopForegroundCompat(int mode) {
        try {
            stopForeground(mode);
        } catch (Exception ignored) {
        }
    }
}
