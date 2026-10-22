package com.vmore.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Auto-copy: new posts of one source chat, copied into one destination chat.
 *
 * The source is a chat the signed-in account can read (picked from the account's
 * own chat list, never guessed from the screen), the destination is a chat it may
 * post in, and every run only looks at messages newer than the last one copied —
 * so the same post can never be sent twice and switching the feature on never
 * floods the destination with the source's back catalogue.
 *
 * The scan runs on an inexact repeating alarm, which is why it keeps working
 * after a reboot, after the app is swiped away, and while the phone is idle.
 */
final class Mirror {

    static final String ACTION_CHECK = "com.vmore.app.MIRROR_CHECK";
    /** How many source messages one scan looks at. */
    private static final int PAGE = 20;
    /** how often the alarm looks: twice an hour is plenty for a channel. */
    private static final long PERIOD_MS = AlarmManager.INTERVAL_HALF_HOUR;
    private static final int REQUEST_CODE = 4201;

    private Mirror() {
    }

    // ---------------------------------------------------------- scheduling //

    /** Starts (or moves forward) the repeating scan for this account. */
    static void arm(Context context) {
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (manager == null) {
            return;
        }
        try {
            manager.setInexactRepeating(
                    AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    SystemClock.elapsedRealtime() + 60_000L,
                    PERIOD_MS,
                    pending(context));
        } catch (Throwable ignored) {
            //: A phone that refuses the alarm still mirrors whenever the app runs.
        }
    }

    static void disarm(Context context) {
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (manager == null) {
            return;
        }
        try {
            manager.cancel(pending(context));
        } catch (Throwable ignored) {
        }
    }

    /** Re-arms or drops the alarm to match the switch the user just touched. */
    static void refresh(Context context) {
        if (Prefs.mirrorEnabled(context)) {
            arm(context);
        } else {
            disarm(context);
        }
    }

    private static PendingIntent pending(Context context) {
        Intent intent = new Intent(context, MirrorReceiver.class);
        intent.setAction(ACTION_CHECK);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getBroadcast(context, REQUEST_CODE, intent, flags);
    }

    // -------------------------------------------------------------- scanning //

    /** True when every ingredient of a mirror is actually there. */
    static boolean ready(Context context) {
        return Prefs.mirrorEnabled(context)
                && Prefs.mirrorSourceId(context) != 0L
                && Prefs.mirrorDestId(context) != 0L;
    }

    /**
     * One scan: everything in the source newer than the last copied message is
     * turned into a normal queue job, exactly as if the links had been pasted.
     */
    static void check(Context context) {
        final Context app = context.getApplicationContext();
        if (!ready(app)) {
            return;
        }
        Tg tg = Tg.get(app);
        if (!tg.isReady()) {
            //: The alarm can wake the app with no session in memory.  Starting
            //: it here is what makes auto-copy work with the app closed.
            tg.start(null);
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                if (Tg.get(app).isReady()) {
                    check(app);
                }
            }, 9000L);
            return;
        }
        final long source = Prefs.mirrorSourceId(app);
        final long last = Prefs.mirrorLastId(app);
        Tg.get(app).listChatMedia(source, 0L, PAGE, false, new Tg.Cb<Tg.MediaPage>() {
            @Override
            public void ok(Tg.MediaPage page) {
                if (page == null || page.items.isEmpty()) {
                    return;
                }
                long newest = 0L;
                for (Tg.Media media : page.items) {
                    newest = Math.max(newest, media.messageId);
                }
                if (last <= 0L) {
                    //: First run: the channel's newest post is the starting
                    //: line, so turning auto-copy on never re-sends old posts.
                    Prefs.setMirrorStart(app, newest);
                    return;
                }
                List<Tg.Media> fresh = new ArrayList<>();
                for (Tg.Media media : page.items) {
                    if (media.messageId > last) {
                        fresh.add(media);
                    }
                }
                if (fresh.isEmpty()) {
                    return;
                }
                //: Oldest first, so the destination reads in the right order.
                fresh.sort((a, b) -> Long.compare(a.messageId, b.messageId));
                enqueue(app, fresh);
                Prefs.setMirrorLastId(app, newest);
            }

            @Override
            public void fail(String message) {
                Log.step(app, "mirror scan failed: " + message);
            }
        });
    }

    private static void enqueue(Context app, List<Tg.Media> items) {
        long dest = Prefs.mirrorDestId(app);
        String destTitle = Prefs.mirrorDestTitle(app);
        String kinds = Prefs.filterKinds(app);
        long min = Prefs.filterMinSize(app);
        long max = Prefs.filterMaxSize(app);
        String batchId = UUID.randomUUID().toString();
        List<QJob> batch = new ArrayList<>();
        for (Tg.Media media : items) {
            QJob probe = new QJob();
            probe.onlyKinds = kinds;
            probe.minSize = min;
            probe.maxSize = max;
            if (!probe.allows(media.kind, media.size)) {
                continue;
            }
            QJob job = new QJob();
            job.id = UUID.randomUUID().toString();
            job.batchId = batchId;
            job.batchLabel = "Auto-copy";
            job.raw = (media.chatTitle == null || media.chatTitle.isEmpty()
                    ? "auto-copy" : media.chatTitle) + " / " + media.name;
            job.chatId = media.chatId;
            job.internalId = TgLink.internalFromChatId(media.chatId);
            job.messageId = media.messageId;
            job.fileId = media.fileId;
            job.remoteFileId = media.remoteFileId;
            job.name = media.name;
            job.kind = media.kind;
            job.size = media.size;
            job.caption = media.caption;
            job.durationSec = media.durationSec;
            job.width = media.width;
            job.height = media.height;
            job.protectedContent = media.protectedContent;
            job.destChatId = dest;
            job.destTitle = destTitle;
            job.method = QJob.METHOD_DOWNLOAD;
            job.sendAs = Prefs.sendAs(app);
            job.uploadAfter = true;
            job.deleteLocal = Prefs.autoDeleteLocal(app);
            job.onlyKinds = kinds;
            job.minSize = min;
            job.maxSize = max;
            job.stage = QJob.QUEUED;
            job.created = System.currentTimeMillis();
            batch.add(job);
        }
        if (batch.isEmpty()) {
            return;
        }
        Jobs.get(app).addBatch(batch);
        Log.step(app, "mirror queued " + batch.size() + " new post(s)");
        QueueService.run(app);
    }
}
