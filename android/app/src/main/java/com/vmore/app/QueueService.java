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
 * The engine: it walks the queue, downloads each job with the user's own
 * Telegram session, uploads it to the chosen chat and then removes the phone
 * copy when the user asked for that.
 *
 * It is a foreground service, so a long batch keeps running with the screen off
 * — which is exactly why the "delete the local copy" setting can be trusted:
 * the file only disappears after the upload really finished.
 */
public class QueueService extends Service {

    public static final String ACTION_RUN = "com.vmore.app.RUN";
    public static final String ACTION_PAUSE_ALL = "com.vmore.app.PAUSE_ALL";
    public static final String ACTION_RESUME_ALL = "com.vmore.app.RESUME_ALL";
    public static final String ACTION_STOP_JOB = "com.vmore.app.STOP_JOB";
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
    private volatile boolean shuttingDown;
    /** The exception the last attempt died of — read by the retry rule. */
    private volatile Exception lastFailure;
    /** The reason the queue last waited, so the log gets it once, not 700 times. */
    private volatile String lastHold = "";
    private final AtomicBoolean cancelled = new AtomicBoolean(false);
    private final AtomicBoolean skipCurrent = new AtomicBoolean(false);
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
        //: Anything that asks the queue to go right now (Start, Resume, the
        //: notification, the widget) also says "do not wait for the start time".
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

    public static void skipJob(Context context, String jobId) {
        dispatch(context, ACTION_SKIP_JOB, jobId);
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
            //: Some phones refuse a background start; the next launch of the app
            //: (or the notification) starts the queue again.
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
        //: Android gives a service started with startForegroundService five
        //: seconds to show its notification, so it goes up before any work.
        postProgress(false);
        switch (action) {
            case ACTION_PAUSE_ALL:
                jobs.setPausedAll(true);
                Live.RUNNING.set(false);
                cancelled.set(true);
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
            case ACTION_STOP_JOB:
                cancelled.set(true);
                String jobId = intent == null ? null : intent.getStringExtra(EXTRA_JOB_ID);
                if (jobId == null) {
                    //: No id means the user tapped the stop button: the running
                    //: job and everything still waiting leaves the queue.
                    stopEverything(jobs);
                    return START_NOT_STICKY;
                }
                markCancelled(jobId);
                return START_STICKY;
            case ACTION_SKIP_JOB:
                skipCurrent.set(true);
                cancelled.set(true);
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
        //: A queue woken by the system lives in a fresh process where the
        //: Telegram session has not been built yet; the worker waits for it.
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
                //: Re-checked every turn: switching accounts closes the session
                //: the queue was using, and a worker that trusted its first
                //: answer would fail every remaining job on the spot.
                if (!Tg.get(this).isReady()) {
                    engineReady = Tg.get(this).awaitReady(WAIT_FOR_SESSION_MS);
                }
                //: "only on Wi-Fi", "only while charging" and a start time are
                //: rules the queue obeys for every job, not just the first one.
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
                        //: The session is coming up.  Waiting here is the whole
                        //: point: failing now would throw away a loaded queue
                        //: over a few seconds of sign-in.
                        engineWaited += HOLD_POLL_MS;
                        hold("waiting for the Telegram session");
                        continue;
                    }
                    //: No sign-in in this process: say so once, plainly, and
                    //: leave the queue alone for the next launch of the app.
                    failJob(jobs, job, Tg.get(this).blockedReason());
                    continue;
                }
                lastHold = "";
                cancelled.set(false);
                skipCurrent.set(false);
                process(jobs, job);
                jobs.update(job);
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
        stopForegroundCompat(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    /**
     * Runs one job, and gives a job that only hit a flood wait or a slow
     * network a few more tries before it is called failed.
     */
    private void process(Jobs jobs, QJob job) {
        int attempt = 0;
        while (!shuttingDown) {
            attempt++;
            job.attempts = attempt;
            lastFailure = null;
            processOnce(jobs, job);
            if (!QJob.FAILED.equals(job.stage)) {
                return;
            }
            //: A job that already knows which file it wants is holding a file
            //: reference Telegram handed out earlier.  Those go stale, and the
            //: old code retried with the very same stale id, which is how one
            //: hiccup turned into "download failed" on the first try.  Clearing
            //: the id makes the retry ask Telegram for the link again.
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

    /**
     * The queue stays where it is and says why, on the home screen, in the
     * notification and — once per reason — in the log.
     */
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

    /** The rule that makes the queue wait right now, or an empty string. */
    private String holdReason() {
        String schedule = Net.scheduleBlocker(this);
        if (!schedule.isEmpty()) {
            return schedule;
        }
        return Net.blocker(this);
    }

    /**
     * Whether another attempt is worth the data.
     *
     * The step itself is asked first (a {@link Tg.Failure} knows whether it was
     * a lost connection or a file that will never be allowed), then a stale file
     * reference counts as replaceable, and finally the older keyword rules cover
     * the rest.
     */
    private static boolean worthRetrying(Exception failure, String message, boolean stale) {
        if (failure instanceof Tg.Failure) {
            //: The step itself knows best: it has Telegram's own words.
            return ((Tg.Failure) failure).retryable;
        }
        if (Retry.fatal(message)) {
            return false;
        }
        if (stale) {
            //: Nothing is known about this failure, but the next attempt asks
            //: Telegram for the link again, which is a genuinely new try.
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

    /** One failed job, written down once, in the user's words. */
    private void recordFailure(Jobs jobs, QJob job) {
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_FAILED, job.raw, job.error, job.path);
        jobs.update(job);
    }

    /** A job that never started: same shape, no history noise. */
    private void failJob(Jobs jobs, QJob job, String reason) {
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
            if (QJob.METHOD_FORWARD.equals(job.method)) {
                try {
                    forwardOnly(jobs, job);
                    return;
                } catch (Exception forwardRefused) {
                    String why = forwardRefused.getMessage() == null
                            ? "" : forwardRefused.getMessage();
                    //: A chat that protects its content forbids the forward but
                    //: still lets the file down for viewing, so the job carries
                    //: on down the download path.  This is what the bot did,
                    //: and it is the only way the file reaches the destination.
                    if (job.destChatId == 0L || !Retry.forwardBlocked(why)) {
                        throw forwardRefused;
                    }
                    Log.step(this, "job " + job.id + " Telegram refused the forward ("
                            + why + "); moving a copy instead");
                    job.method = QJob.METHOD_DOWNLOAD;
                    job.uploadAfter = true;
                    job.stage = QJob.QUEUED;
                    job.error = "";
                    job.note = "forward refused; sent a copy instead";
                    jobs.update(job);
                }
            }
            if (QJob.METHOD_SCAN.equals(job.method)) {
                scanIntoQueue(jobs, job);
                return;
            }
            if (job.fileId == 0 || job.chatId == 0L) {
                resolveJob(jobs, job);
                if (cancelled.get()) {
                    if (skipCurrent.get()) {
                        dropJob(jobs, job);
                    } else {
                        markPaused(jobs, job);
                    }
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

            String space = spaceProblem(job.size);
            if (!space.isEmpty()) {
                //: Said here, in plain words, instead of surfacing as a strange
                //: Telegram error half way through.
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

            String path = download(job);
            Log.step(this, "job " + job.id + " downloaded " + shortText(path, 80)
                    + " (" + Format.size(job.size) + ")");
            if (path == null) {
                if (skipCurrent.get()) {
                    dropJob(jobs, job);
                } else {
                    markPaused(jobs, job);
                }
                return;
            }
            job.path = path;
            job.size = job.size > 0 ? job.size : new File(path).length();
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
                job.uploaded = job.size;
                job.note = "";
                Stats.rememberUploaded(this, String.valueOf(job.fileId), job.size);

                if (job.deleteLocal) {
                    deleteLocalCopy(job);
                    History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                            job.destTitle, History.STATUS_UPLOADED, job.raw, "", "");
                } else {
                    History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                            job.destTitle, History.STATUS_UPLOADED, job.raw, "", job.path);
                }
                job.note = (job.note.isEmpty() ? "" : job.note + " \u2022 ")
                        + "sent as message " + sentId;
                Log.step(this, "job " + job.id + " uploaded to " + shortText(job.destTitle, 40)
                        + " as message " + sentId);
                markFinished(job);
            } else {
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
            String message = error.getMessage() == null ? "the job failed" : error.getMessage();
            Log.step(this, "job " + job.id + " " + job.stage + ": " + message);
            if (message.contains("original thread")) {
                //: A repaint mistake is not a transfer problem: say so in the
                //: log, leave the job in the queue, and let the next turn of the
                //: loop pick it up.
                Log.step(this, "job " + job.id + " hit a screen error, not a transfer one");
                job.stage = QJob.QUEUED;
                job.error = "";
                jobs.update(job);
                return;
            }
            if (cancelled.get() && skipCurrent.get()) {
                dropJob(jobs, job);
                return;
            }
            if (cancelled.get()) {
                markPaused(jobs, job);
                return;
            }
            job.stage = QJob.FAILED;
            job.error = message;
            Live.STAGE = QJob.FAILED;
            Live.ERROR = message;
            //: History gets the failure once, after the last retry (see above).
            jobs.update(job);
        }
    }

    /**
     * A link that names a chat but no message — "https://t.me/channel",
     * "@channel", an invite link — means that chat's recent files.  They become
     * one job each inside the same batch, with the same rules and the same
     * destination, and the link itself leaves the queue.
     */
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
            //: Worth saying once in the log: the download works, and the upload
            //: goes up as a new file because the chat forbids forwarding.
            Log.step(this, "job " + job.id + " the chat protects its content; "
                    + "the copy goes up as a new file");
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
        //: Telegram's own verdict on the message.  The upload uses it to send
        //: the bytes as a new file instead of pointing at protected content.
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

    /** Why this job is not worth downloading, or an empty string. */
    private String skipReason(QJob job) {
        if (!job.allows(job.kind, job.size)) {
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
        return media.caption == null ? "" : media.caption;
    }

    private void forwardOnly(Jobs jobs, QJob job) throws Exception {
        Live.STAGE = QJob.UPLOADING;
        Live.NAME = job.title();
        jobs.update(job);
        showNotification(false);
        if (job.destChatId == 0L) {
            throw new Exception("no destination chat was chosen");
        }
        if (job.chatId == 0L || job.messageId == 0L) {
            resolveJob(jobs, job);
        }
        Tg.get(this).forwardBlocking(job, cancelled);
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_UPLOADED, job.raw, "", "");
        job.stage = QJob.DONE;
        Live.STAGE = QJob.DONE;
        markFinished(job);
        jobs.remove(job.id);
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

    /**
     * The reason this file must not be downloaded right now, or an empty
     * string: a phone that is full should say so before the transfer starts.
     */
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

    /** One line of text, never longer than a log line should be. */
    private static String shortText(String text, int max) {
        String value = Format.oneLine(text == null ? "" : text);
        return value.length() <= max ? value : value.substring(0, max) + "...";
    }

    private void markPaused(Jobs jobs, QJob job) {
        job.stage = QJob.PAUSED;
        Live.STAGE = QJob.PAUSED;
        Live.ERROR = "";
        jobs.update(job);
    }

    private void markCancelled(String jobId) {
        Jobs jobs = Jobs.get(this);
        QJob job = jobId == null ? jobs.active() : jobs.byId(jobId);
        if (job != null) {
            job.stage = QJob.CANCELLED;
            History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                    job.destTitle, History.STATUS_FAILED, job.raw, "stopped", job.path);
            jobs.remove(job.id);
        }
    }

    /** Skipped: the job leaves the queue without touching the rest of it. */
    private void dropJob(Jobs jobs, QJob job) {
        job.stage = QJob.CANCELLED;
        History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                job.destTitle, History.STATUS_FAILED, job.raw, "skipped", job.path);
        jobs.remove(job.id);
    }

    /** A job reached its destination; remembered for the finish note. */
    private void markFinished(QJob job) {
        completedJobs++;
        lastName = job.title();
        lastWhere = job.destTitle == null ? "" : job.destTitle;
    }

    /**
     * The stop button: the running job is cancelled and every job that is still
     * waiting is taken out of the queue, each with its own history line.
     */
    private void stopEverything(Jobs jobs) {
        for (QJob job : jobs.all()) {
            if (QJob.QUEUED.equals(job.stage) || QJob.RESOLVING.equals(job.stage)
                    || QJob.PAUSED.equals(job.stage)) {
                job.stage = QJob.CANCELLED;
                History.get(this).record(job.title(), job.kind, job.size, job.destChatId,
                        job.destTitle, History.STATUS_FAILED, job.raw, "stopped", job.path);
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

    /** Puts the live row up as a real foreground notification. */
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

    /** Same row, but progress ticks are batched so the manager is not spammed. */
    private void showNotification(boolean paused) {
        if (!paused && System.currentTimeMillis() - postedAt < 500) {
            return;
        }
        postProgress(paused);
    }

    /** A long batch has to keep running with the screen off. */
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
