package com.vmore.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Notification plumbing: the live progress of the queue (with Pause all and Stop
 * buttons), the floating Smart feature status row, and the finished job note.
 */
final class Notifications {

    static final String CHANNEL_PROGRESS = "vmore_queue";
    static final String CHANNEL_DONE = "vmore_done";
    static final String CHANNEL_SMART = "vmore_smart";
    static final int ID_PROGRESS = 4101;
    static final int ID_DONE = 4102;
    static final int ID_SMART = 4103;

    private Notifications() {
    }

    static void ensureChannels(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        NotificationChannel progress = new NotificationChannel(CHANNEL_PROGRESS,
                context.getString(R.string.common_notification_channel),
                NotificationManager.IMPORTANCE_LOW);
        progress.setDescription("Progress of downloads and uploads");
        progress.setShowBadge(false);
        manager.createNotificationChannel(progress);

        NotificationChannel done = new NotificationChannel(CHANNEL_DONE,
                context.getString(R.string.common_notification_channel_done),
                NotificationManager.IMPORTANCE_DEFAULT);
        done.setDescription("Tells you when a job finished");
        manager.createNotificationChannel(done);

        NotificationChannel smart = new NotificationChannel(CHANNEL_SMART,
                context.getString(R.string.common_notification_channel_smart),
                NotificationManager.IMPORTANCE_LOW);
        smart.setDescription(" Keeps the floating Smart feature active above other apps");
        smart.setShowBadge(false);
        manager.createNotificationChannel(smart);
    }

    private static PendingIntent foregroundAction(Context context, String action, int code) {
        Intent intent = new Intent(context, QueueService.class);
        intent.setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return PendingIntent.getForegroundService(context, code, intent, flags);
        }
        return PendingIntent.getService(context, code, intent, flags);
    }

    private static PendingIntent smartAction(Context context, String action, int code) {
        Intent intent = new Intent(context, SmartOverlayService.class);
        intent.setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getService(context, code, intent, flags);
    }

    private static PendingIntent openApp(Context context) {
        Intent intent = new Intent(context, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getActivity(context, 7, intent, flags);
    }

    private static Notification.Builder base(Context context, String channel) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return new Notification.Builder(context, channel);
        }
        //noinspection deprecation
        return new Notification.Builder(context);
    }

    /** Foreground notification for the floating Smart feature overlay. */
    static Notification smart(Context context, String detail) {
        ensureChannels(context);
        Notification.Builder builder = base(context, CHANNEL_SMART);
        builder.setContentTitle(context.getString(R.string.smart_service_label))
                .setContentText(detail == null || detail.isEmpty()
                        ? context.getString(R.string.smart_step_ready) : detail)
                .setSmallIcon(R.drawable.ic_smart)
                .setContentIntent(openApp(context))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .addAction(new Notification.Action.Builder(
                        R.drawable.ic_smart,
                        context.getString(R.string.smart_open_menu),
                        smartAction(context, SmartOverlayService.ACTION_SHOW_MENU, 31))
                        .build())
                .addAction(new Notification.Action.Builder(
                        R.drawable.ic_close,
                        context.getString(R.string.smart_stop),
                        smartAction(context, SmartOverlayService.ACTION_STOP, 32))
                        .build());
        return builder.build();
    }

    /** The live queue notification: one row per running job. */
    static Notification progress(Context context, String name, String stage, long done, long total,
                                 boolean paused) {
        int percent = Format.percent(done, total);
        String label = stageLabel(context, stage);
        String size = total > 0
                ? Format.size(done) + " / " + Format.size(total)
                : Format.size(done);
        String title = name == null || name.isEmpty() ? context.getString(R.string.app_name) : name;
        Notification.Builder builder = base(context, CHANNEL_PROGRESS);
        builder.setContentTitle(title)
                .setContentText(paused ? label + " • paused • " + size : label + " • " + size)
                .setSmallIcon(R.drawable.ic_download)
                .setContentIntent(openApp(context))
                .setOngoing(!paused)
                .setOnlyAlertOnce(true)
                .setProgress(100, percent, total <= 0);
        if (paused) {
            builder.addAction(new Notification.Action.Builder(
                            R.drawable.ic_play,
                            context.getString(R.string.queue_resume_all),
                            foregroundAction(context, QueueService.ACTION_RESUME_ALL, 21))
                    .build());
        } else {
            builder.addAction(new Notification.Action.Builder(
                            R.drawable.ic_pause,
                            context.getString(R.string.queue_pause_all),
                            foregroundAction(context, QueueService.ACTION_PAUSE_ALL, 22))
                    .build());
        }
        builder.addAction(new Notification.Action.Builder(
                        R.drawable.ic_stop,
                        context.getString(R.string.queue_remove),
                        foregroundAction(context, QueueService.ACTION_STOP_JOB, 23))
                .build());

        Notification notification = builder.build();
        NotificationManager manager =
                (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null && !QueueService.running()) {
            manager.notify(ID_PROGRESS, notification);
        }
        return notification;
    }

    /** Drops the live row when the whole queue was stopped by the user. */
    static void cancelProgress(Context context) {
        NotificationManager manager =
                (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.cancel(ID_PROGRESS);
        }
    }

    /** Clears the Smart feature foreground notification when turned off. */
    static void cancelSmart(Context context) {
        NotificationManager manager =
                (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.cancel(ID_SMART);
        }
    }

    static void finished(Context context, String name, String where) {
        NotificationManager manager =
                (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) {
            return;
        }
        Notification.Builder builder = base(context, CHANNEL_DONE);
        builder.setContentTitle(context.getString(R.string.common_done))
                .setContentText(name + (where == null || where.isEmpty() ? "" : " • " + where))
                .setSmallIcon(R.drawable.ic_check)
                .setContentIntent(openApp(context))
                .setAutoCancel(true)
                .setWhen(System.currentTimeMillis());
        manager.notify(ID_DONE, builder.build());
    }

    private static String stageLabel(Context context, String stage) {
        if (stage == null) {
            return "";
        }
        switch (stage) {
            case QJob.COPYING:
                return context.getString(R.string.common_copying);
            case QJob.UPLOADING:
                return context.getString(R.string.common_uploading);
            case QJob.RESOLVING:
                return context.getString(R.string.common_resolving);
            case QJob.PAUSED:
                return context.getString(R.string.common_paused);
            case QJob.FAILED:
                return context.getString(R.string.common_failed);
            case QJob.DONE:
                return context.getString(R.string.common_done);
            default:
                return context.getString(R.string.common_downloading);
        }
    }
}
