package com.vmore.app;

import android.content.Context;

import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * The flight recorder.
 *
 * When something refuses to work on a phone there is no console to look at, so
 * the queue and the Telegram engine write short lines here.  The file lives in
 * the app's private folder, is trimmed to the last 128 KB, and the Settings
 * report shows its tail — one tap copies the whole thing, reason included.
 */
final class Log {

    private static final String FILE_NAME = "vmore_log.txt";
    private static final long MAX_BYTES = 128L * 1024L;
    private static final Object LOCK = new Object();

    private Log() {
    }

    /** A step of the queue: started, resolved, downloading, failed. */
    static void step(Context context, String text) {
        write(context, "queue", text);
    }

    /** A word from Telegram itself, kept as it came. */
    static void engine(Context context, String text) {
        write(context, "engine", text);
    }

    private static void write(Context context, String tag, String text) {
        if (context == null || text == null || text.isEmpty()) {
            return;
        }
        String stamp = new SimpleDateFormat("MM-dd HH:mm:ss", Locale.US)
                .format(new Date());
        String line = stamp + " " + tag + ": " + text.replace('\n', ' ') + "\n";
        synchronized (LOCK) {
            try {
                File file = new File(context.getFilesDir(), FILE_NAME);
                if (file.exists() && file.length() > MAX_BYTES) {
                    trim(file);
                }
                FileOutputStream out = new FileOutputStream(file, true);
                try {
                    out.write(line.getBytes("UTF-8"));
                } finally {
                    out.close();
                }
            } catch (Exception ignored) {
                //: A recorder that cannot write must never break the queue.
            }
        }
    }

    /** Keeps the newest half of the file, so it never grows without an end. */
    private static void trim(File file) {
        try {
            long keep = MAX_BYTES / 2;
            RandomAccessFile raf = new RandomAccessFile(file, "rw");
            try {
                long start = Math.max(0L, raf.length() - keep);
                byte[] buffer = new byte[(int) (raf.length() - start)];
                raf.seek(start);
                raf.readFully(buffer);
                raf.setLength(0);
                raf.seek(0);
                raf.write(buffer);
            } finally {
                raf.close();
            }
        } catch (Exception ignored) {
        }
    }

    /** The last lines, oldest first, for the report. */
    static String tail(Context context, int lines) {
        File file = new File(context.getFilesDir(), FILE_NAME);
        if (!file.exists()) {
            return "";
        }
        try {
            RandomAccessFile raf = new RandomAccessFile(file, "r");
            try {
                long length = raf.length();
                int read = (int) Math.min(length, 16L * 1024L);
                byte[] buffer = new byte[read];
                raf.seek(length - read);
                raf.readFully(buffer);
                String[] all = new String(buffer, "UTF-8").split("\n");
                int from = Math.max(0, all.length - lines);
                StringBuilder text = new StringBuilder();
                for (int index = from; index < all.length; index++) {
                    if (all[index].trim().isEmpty()) {
                        continue;
                    }
                    text.append(all[index]).append('\n');
                }
                return text.toString();
            } finally {
                raf.close();
            }
        } catch (Exception error) {
            return "";
        }
    }

    static void clear(Context context) {
        synchronized (LOCK) {
            try {
                //noinspection ResultOfMethodCallIgnored
                new File(context.getFilesDir(), FILE_NAME).delete();
            } catch (Exception ignored) {
            }
        }
    }
}
