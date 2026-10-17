package com.vmore.app;

import android.content.Context;
import android.content.Intent;

import java.io.File;

/**
 * The one button in Settings that empties the app.
 *
 * It is the same thing Android does when the user taps "Clear storage", done
 * inside the app so nobody has to leave it: the queue stops, the Telegram
 * session closes, the history and the queue are forgotten, every file Vmore
 * wrote is deleted, and the preferences file goes last.
 *
 * The order matters.  A running job writes its own row back into queue.json,
 * so the service is stopped before anything is cleared, and the preferences
 * are cleared after the files so an interrupted wipe can never leave settings
 * that point at files which are already gone.
 */
final class Wipe {

    private Wipe() {
    }

    /** Removes everything this app stored on this phone. */
    static void everything(Context context) {
        Context app = context.getApplicationContext();

        //: 1. The queue goes quiet first.  Without this, a job that is still
        //: downloading would recreate its files and its queue row after the
        //: wipe had already been through.
        try {
            app.stopService(new Intent(app, QueueService.class));
        } catch (Throwable ignored) {
        }

        //: 2. The session is closed, not signed out: the whole TDLib folder is
        //: deleted below, so there is nothing left to sign out of.
        try {
            Tg.get(app).closeSession();
        } catch (Throwable ignored) {
        }

        //: 3. The lists that are already in memory are emptied too, so a
        //: screen sitting behind Settings paints nothing instead of rows whose
        //: files no longer exist.
        try {
            Jobs.get(app).clear();
        } catch (Throwable ignored) {
        }
        try {
            History.get(app).clear();
        } catch (Throwable ignored) {
        }
        QueueService.Live.reset();

        //: 4. Every file: downloads, the upload copy, avatars, the developer
        //: picture, the queue and history files, the log and the TDLib folders.
        deleteChildren(app.getFilesDir());
        deleteChildren(app.getCacheDir());
        deleteChildren(app.getExternalFilesDir(null));

        //: 5. The settings, accounts, PIN and statistics counters last.
        Prefs.clearAll(app);

        //: 6. A brand-new session folder is reserved for the first account.
        //: TDLib may still be closing while the folders above are deleted, and
        //: a database it recreates a moment later must never be the one the
        //: next sign-in opens: the new name points somewhere empty, and
        //: Tg.tidySessions removes the old folder on the next launch.
        Prefs.newSessionDir(app);
    }

    /** Empties a folder without ever following a path outside it. */
    private static void deleteChildren(File dir) {
        if (dir == null || !dir.exists()) {
            return;
        }
        File[] children = dir.listFiles();
        if (children != null) {
            for (File child : children) {
                delete(child);
            }
        }
    }

    private static void delete(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        File[] children = file.isDirectory() ? file.listFiles() : null;
        if (children != null) {
            for (File child : children) {
                delete(child);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }
}
