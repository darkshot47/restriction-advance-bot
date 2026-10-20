package com.vmore.app;

import android.content.Context;

import java.io.File;
import java.util.HashSet;
import java.util.Set;

/**
 * Deletes cached media files Vmore downloaded or staged, and nothing else.
 *
 * History, queue, settings and the Telegram login database stay untouched; any
 * file still needed by a queued, paused or running job is left in place.
 */
final class Cleanup {

    /** How many files went, and how many bytes that gave back. */
    static final class Freed {
        int files;
        long bytes;
    }

    private Cleanup() {
    }

    /** Deletes every cached download or upload file no active job needs right now. */
    static Freed downloads(Context context) {
        Context app = context.getApplicationContext();
        Freed freed = new Freed();

        Set<String> inUse = inUse(app);
        sweepFolder(LocalFiles.downloadsDir(app), inUse, freed, false);
        sweepFolder(LocalFiles.uploadScratchDir(app), inUse, freed, false);
        sweepFolder(LocalFiles.tdRootDir(app), inUse, freed, false);

        History.get(app).forgetMissingFiles();
        return freed;
    }

    private static void sweepFolder(File dir, Set<String> inUse, Freed freed, boolean deleteSelf) {
        if (dir == null || !dir.exists()) {
            return;
        }
        File[] children = dir.listFiles();
        if (children != null) {
            for (File entry : children) {
                if (entry.isDirectory()) {
                    sweepFolder(entry, inUse, freed, true);
                } else if (!inUse.contains(entry.getAbsolutePath())) {
                    long size = entry.length();
                    //noinspection ResultOfMethodCallIgnored
                    if (entry.delete()) {
                        freed.files++;
                        freed.bytes += size;
                    }
                }
            }
        }
        if (deleteSelf) {
            String[] left = dir.list();
            if (left != null && left.length == 0) {
                //noinspection ResultOfMethodCallIgnored
                dir.delete();
            }
        }
    }

    /** The files that a queued, paused, running or waiting job still needs. */
    private static Set<String> inUse(Context context) {
        Set<String> paths = new HashSet<>();
        for (QJob job : Jobs.get(context).all()) {
            if (job.path == null || job.path.isEmpty()) {
                continue;
            }
            if (QJob.FAILED.equals(job.stage)) {
                continue;
            }
            if (!job.isFinished()) {
                paths.add(new File(job.path).getAbsolutePath());
            }
        }
        return paths;
    }
}
