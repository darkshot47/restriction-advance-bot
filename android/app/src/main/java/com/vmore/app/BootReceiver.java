package com.vmore.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Comes back after a restart or an update.
 *
 * Two things do not survive a reboot on their own: the repeating auto-copy
 * alarm (alarms are cleared) and a queue that was half way through a batch.  The
 * queue is only restarted when the user left it running, so a job somebody
 * paused stays paused.
 */
public class BootReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (context == null) {
            return;
        }
        String action = intent == null ? "" : intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        Context app = context.getApplicationContext();
        try {
            Mirror.refresh(app);
        } catch (Throwable ignored) {
        }
        try {
            Jobs jobs = Jobs.get(app);
            if (jobs.hasWork() && !jobs.pausedAll()) {
                Log.step(app, "restarting the queue after a reboot");
                QueueService.run(app);
            }
        } catch (Throwable ignored) {
        }
    }
}
