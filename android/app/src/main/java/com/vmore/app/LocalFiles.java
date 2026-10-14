package com.vmore.app;

import android.content.Context;

import java.io.File;

/**
 * Where downloaded files live while a job is running.
 *
 * Everything stays inside the app's private storage: no gallery entry, no
 * shared folder, and the copy can be deleted the moment the upload finished.
 */
final class LocalFiles {

    private LocalFiles() {
    }

    /** {@code <app storage>/files/Vmore} — created on first use. */
    static File downloadsDir(Context context) {
        File dir = new File(context.getExternalFilesDir(null), Vmore.FOLDER);
        if (!dir.exists() && !dir.mkdirs()) {
            //: Older phones without external storage: fall back to app storage.
            dir = new File(context.getFilesDir(), Vmore.FOLDER);
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    static File targetFile(Context context, String name) {
        File dir = downloadsDir(context);
        File file = new File(dir, Format.safeName(name, "vmore"));
        if (file.exists()) {
            //: Same name twice: keep both instead of overwriting the first one.
            String base = Format.withoutExtension(file.getName());
            String extension = file.getName().substring(base.length());
            int index = 2;
            while (file.exists() && index < 1000) {
                file = new File(dir, base + "_" + index + extension);
                index++;
            }
        }
        return file;
    }

    /** Where the account's profile picture is kept, once, in app storage. */
    static File avatarFile(Context context) {
        //: One picture per account slot, so switching accounts switches faces.
        return new File(context.getFilesDir(), "avatar_" + Prefs.activeSlot(context) + ".jpg");
    }

    /** Copy a file (or move-and-replace) to an exact target path. */
    static File copy(String sourcePath, File target) {
        if (sourcePath == null || sourcePath.isEmpty() || target == null) {
            return null;
        }
        File source = new File(sourcePath);
        if (!source.exists()) {
            return null;
        }
        if (source.getAbsolutePath().equals(target.getAbsolutePath())) {
            return target;
        }
        File parent = target.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            return null;
        }
        try (java.io.InputStream in = new java.io.FileInputStream(source);
             java.io.OutputStream out = new java.io.FileOutputStream(target)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            out.flush();
            return target;
        } catch (Exception error) {
            return null;
        }
    }

    /** Copy a Telegram file out of TDLib's cache into the app's own folder. */
    static File adopt(Context context, String sourcePath, String name) {
        if (sourcePath == null || sourcePath.isEmpty()) {
            return null;
        }
        File source = new File(sourcePath);
        if (!source.exists()) {
            return null;
        }
        File target = targetFile(context, name);
        if (source.getAbsolutePath().equals(target.getAbsolutePath())) {
            return target;
        }
        try (java.io.InputStream in = new java.io.FileInputStream(source);
             java.io.OutputStream out = new java.io.FileOutputStream(target)) {
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            out.flush();
            return target;
        } catch (Exception error) {
            return source;
        }
    }

    static long length(String path) {
        File file = path == null || path.isEmpty() ? null : new File(path);
        return file != null && file.exists() ? file.length() : 0L;
    }

    static boolean exists(String path) {
        return path != null && !path.isEmpty() && new File(path).exists();
    }

    static void delete(String path) {
        if (path == null || path.isEmpty()) {
            return;
        }
        File file = new File(path);
        if (file.exists()) {
            //noinspection ResultOfMethodCallIgnored
            file.delete();
        }
    }

    /** Every file the app still holds on the phone (About screen counter). */
    static long totalBytes(Context context) {
        File[] files = downloadsDir(context).listFiles();
        if (files == null) {
            return 0L;
        }
        long total = 0L;
        for (File file : files) {
            if (file.isFile()) {
                total += file.length();
            }
        }
        return total;
    }
}
