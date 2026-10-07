package com.vmore.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Turns the notification's Pause / Resume / Stop buttons into service calls. */
public class NotificationActionReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (Notifications.ACTION_PAUSE.equals(action)) {
            DownloadService.command(context, DownloadService.ACTION_PAUSE);
        } else if (Notifications.ACTION_RESUME.equals(action)) {
            DownloadService.command(context, DownloadService.ACTION_RESUME);
        } else if (Notifications.ACTION_STOP.equals(action)) {
            DownloadService.command(context, DownloadService.ACTION_STOP);
        }
    }
}
