package com.vmore.app;

import android.content.Context;

import java.io.File;
import java.util.HashSet;
import java.util.Set;

/**
 * Deletes what Vmore downloaded, and nothing else.
 *
 * This is the smaller sibling of a factory reset: the files the app kept on the
 * phone go, while the history, the queue, the settings and the Telegram account
 * stay exactly as they are.  The history keeps saying what happened, it just
 * stops offering to open a file that is no longer there.
 *
 * A file that a waiting or running job still needs is left alone: deleting it
 * from under a download or an upload would fail that job for no reason.
 */
final class Cleanup {

    /** How many files went, and how many bytes that gave back. */
    static final class Freed {
        int files;
        long bytes;
    }

    private Cleanup() {
    }

    /** Deletes every downloaded file no job is using right now. */
    static Freed downloads(Context context) {
        Context app = context.getApplicationContext();
        Freed freed = new Freed();

        Set<String> inUse = inUse(app);
        File[] children = LocalFiles.downloadsDir(app).listFiles();
        if (children != null) {
            for (File file : children) {
                if (!file.isFile() || inUse.contains(file.getAbsolutePath())) {
                    continue;
                }
                long size = file.length();
                //noinspection ResultOfMethodCallIgnored
                if (file.delete()) {
                    freed.files++;
                    freed.bytes += size;
                }
            }
        }

        History.get(app).forgetMissingFiles();
        return freed;
    }

    /** The files that a queued, paused, running or waiting job still needs. */
    private static Set<String> inUse(Context context) {
        Set<String> paths = new HashSet<>();
        for (QJob job : Jobs.get(context).all()) {
            if (job.path == null || job.path.isEmpty()) {
                continue;
            }
            if (QJob.FAILED.equals(job.stage)) {
                //: A failed job is not going to read the file by itself; its
                //: leftovers are exactly what this button is for.
                continue;
            }
            if (!job.isFinished()) {
                paths.add(new File(job.path).getAbsolutePath());
            }
        }
        return paths;
    }
}
