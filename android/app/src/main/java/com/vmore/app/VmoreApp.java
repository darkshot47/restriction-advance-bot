package com.vmore.app;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;

/**
 * The application object.
 *
 * Applies the active theme skin, sweeps unused session directories and legacy
 * user-data media into cache storage at startup, arms the optional PIN lock
 * when the app leaves the screen, and tracks whether the opening splash intro
 * should play when the user opens Vmore.
 */
public class VmoreApp extends Application implements Application.ActivityLifecycleCallbacks {

    private static volatile boolean launchIntroPending = true;
    private static volatile long backgroundedAt = 0L;
    private static final long REARM_INTRO_AFTER_MS = 12_000L;

    private int started;

    public static boolean consumeLaunchIntro() {
        if (launchIntroPending) {
            launchIntroPending = false;
            return true;
        }
        return false;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        launchIntroPending = true;
        Skin.apply(this);
        registerActivityLifecycleCallbacks(this);
        Thread tidy = new Thread(() -> Tg.get(this).tidySessions(), "vmore-session-tidy");
        tidy.setDaemon(true);
        tidy.start();
    }

    @Override
    public void onActivityStarted(Activity activity) {
        if (started == 0 && backgroundedAt > 0L
                && System.currentTimeMillis() - backgroundedAt >= REARM_INTRO_AFTER_MS) {
            launchIntroPending = true;
        }
        started++;
    }

    @Override
    public void onActivityStopped(Activity activity) {
        started = Math.max(0, started - 1);
        if (started == 0) {
            backgroundedAt = System.currentTimeMillis();
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
