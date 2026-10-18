package com.vmore.app;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;

/**
 * The application object.
 *
 * It pushes the saved skin into the process before any screen exists, and it
 * watches how many screens are open: when the last one stops, the app really is
 * in the background, which is the moment the optional PIN lock arms itself.
 */
public class VmoreApp extends Application implements Application.ActivityLifecycleCallbacks {

    private int started;

    @Override
    public void onCreate() {
        super.onCreate();
        Skin.apply(this);
        registerActivityLifecycleCallbacks(this);
        //: A session folder that a reset could not delete (it was still open,
        //: the phone was shutting down) is taken here, once the process is new.
        Thread tidy = new Thread(() -> Tg.get(this).tidySessions(), "vmore-session-tidy");
        tidy.setDaemon(true);
        tidy.start();
    }

    @Override
    public void onActivityStarted(Activity activity) {
        started++;
    }

    @Override
    public void onActivityStopped(Activity activity) {
        started = Math.max(0, started - 1);
        if (started == 0) {
            Lock.appLeft();
        }
    }

    @Override
    public void onActivityCreated(Activity activity, Bundle state) {
    }

    @Override
    public void onActivityResumed(Activity activity) {
    }

    @Override
    public void onActivityPaused(Activity activity) {
    }

    @Override
    public void onActivitySaveInstanceState(Activity activity, Bundle state) {
    }

    @Override
    public void onActivityDestroyed(Activity activity) {
    }
}
