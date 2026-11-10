package com.vmore.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The alarm behind auto-copy: one scan, then the queue takes over. */
public class MirrorReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (context == null) {
            return;
        }
        Context app = context.getApplicationContext();
        if (!Mirror.ready(app)) {
            Mirror.disarm(app);
            return;
        }
        Mirror.check(app);
    }
}
