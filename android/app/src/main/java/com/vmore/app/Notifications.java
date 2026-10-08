package com.vmore.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Notification plumbing: the live download progress (with Pause / Stop) and the
 * "download finished" note the owner asked for — both stay in the shade even
 * when the app is closed.
 */
final class Notifications {

    static final String CHANNEL_PROGRESS = "vmore_downloads";
    static final String CHANNEL_DONE = "vmore_done";
    static final int ID_PROGRESS = 4101;
    static final int ID_DONE = 4102;

    //: One source of truth for the actions: the service handles these intents
    //: directly, so the notification buttons and the on-screen buttons are the
    //: same code path.
    static final String ACTION_PAUSE = DownloadService.ACTION_PAUSE;
    static final String ACTION_RESUME = DownloadService.ACTION_RESUME;
    static final String ACTION_STOP = DownloadService.ACTION_STOP;

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
        NotificationChannel progress = new NotificationChannel(
                CHANNEL_PROGRESS, "Downloads", NotificationManager.IMPORTANCE_LOW);
        progress.setDescription("Download progress with pause and stop");
        progress.setShowBadge(false);
        manager.createNotificationChannel(progress);

        NotificationChannel done = new NotificationChannel(
                CHANNEL_DONE, "Finished downloads", NotificationManager.IMPORTANCE_DEFAULT);
        done.setDescription("Tells you when a download finished");
        manager.createNotificationChannel(done);
    }

    /** The service itself, so Android knows these actions may wake it up. */
    private static PendingIntent action(Context context, String action, int requestCode) {
        Intent intent = new Intent(context, DownloadService.class);
        intent.setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return PendingIntent.getForegroundService(context, requestCode, intent, flags);
        }
        return PendingIntent.getService(context, requestCode, intent, flags);
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

    static Notification progress(Context context, String name, long written, long total,
                                 boolean paused) {
        int percent = total > 0 ? (int) Math.min(100, written * 100 / total) : 0;
        String size = total > 0
                ? human(written) + " / " + human(total)
                : human(written);
        Notification.Builder builder = base(context, CHANNEL_PROGRESS);
        builder.setContentTitle((paused ? "⏸ Paused — " : "⬇️ Downloading — ") + name)
                .setContentText(paused ? size + " • tap Resume to continue" : size)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentIntent(openApp(context))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setProgress(100, percent, total <= 0);
        if (paused) {
            builder.addAction(new Notification.Action.Builder(
                    android.R.drawable.ic_media_play, "Resume",
                    action(context, ACTION_RESUME, 21)).build());
        } else {
            builder.addAction(new Notification.Action.Builder(
                    android.R.drawable.ic_media_pause, "Pause",
                    action(context, ACTION_PAUSE, 22)).build());
        }
        builder.addAction(new Notification.Action.Builder(
                android.R.drawable.ic_menu_close_clear_cancel, "Stop",
                action(context, ACTION_STOP, 23)).build());
        return builder.build();
    }

    static Notification finished(Context context, String name, String where) {
        Notification.Builder builder = base(context, CHANNEL_DONE);
        builder.setContentTitle("✅ Download complete")
                .setContentText(name + (where == null ? "" : " • saved in " + where))
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentIntent(openApp(context))
                .setAutoCancel(true)
                .setStyle(new Notification.BigTextStyle().bigText(
                        name + (where == null ? "" : "\nSaved in " + where)))
                .setWhen(System.currentTimeMillis());
        return builder.build();
    }

    static Notification failed(Context context, String name, String error) {
        Notification.Builder builder = base(context, CHANNEL_DONE);
        builder.setContentTitle("⚠️ Download failed")
                .setContentText(name + " — " + error)
                .setSmallIcon(android.R.drawable.stat_notify_error)
                .setContentIntent(openApp(context))
                .setAutoCancel(true);
        return builder.build();
    }

    private static Notification.Builder base(Context context, String channel) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return new Notification.Builder(context, channel);
        }
        //noinspection deprecation
        return new Notification.Builder(context);
    }

    static String human(long bytes) {
        if (bytes <= 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        double value = bytes;
        int unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit++;
        }
        return (value >= 100 || unit == 0
                ? String.format(java.util.Locale.US, "%.0f %s", value, units[unit])
                : String.format(java.util.Locale.US, "%.1f %s", value, units[unit]));
    }
}
