package com.vmore.app;

import android.os.Handler;
import android.os.Looper;

/**
 * The main thread, in one place.
 *
 * Screens belong to the thread that built them.  The queue works on its own
 * thread and Telegram answers on its own too, so anything that ends up touching
 * a view has to come back here first — otherwise Android throws
 * "Only the original thread that created a view hierarchy can touch its views",
 * which used to surface as a failed job with that very sentence as its reason.
 */
final class UiThread {

    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private UiThread() {
    }

    /** Runs the work on the main thread, now or at the next turn. */
    static void run(Runnable task) {
        if (task == null) {
            return;
        }
        if (Looper.myLooper() == Looper.getMainLooper()) {
            task.run();
            return;
        }
        MAIN.post(task);
    }

    /**
     * The same, but a broken screen can never take the queue down with it: a
     * listener that throws is swallowed here instead of failing a download.
     */
    static void safe(Runnable task) {
        if (task == null) {
            return;
        }
        run(() -> {
            try {
                task.run();
            } catch (Throwable ignored) {
                //: A screen that misbehaves is not a reason to lose a transfer.
            }
        });
    }
}
