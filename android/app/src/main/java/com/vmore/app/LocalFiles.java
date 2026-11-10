package com.vmore.app;

import android.content.Context;

import java.io.File;

/**
 * Where downloaded, uploaded and cached files live while Vmore works.
 *
 * Every byte of media — TDLib downloads, partial chunks, upload scratch copies,
 * chat pictures and saved files — lives inside {@link Context#getCacheDir()}, so
 * Android counts all of it under Cache rather than User Data. Clearing cache in
 * system settings frees all media at once while keeping the Telegram login, PIN,
 * queue and history intact.
 */
final class LocalFiles {

    private static final String[] LEGACY_TD_MEDIA_DIRS = {
            "documents", "videos", "photos", "music", "voice", "animations",
            "temp", "thumbnails", "stickers", "video_notes", "wallpapers",
            "secret", "profile_photos", "passport"
    };

    private LocalFiles() {
    }

    /** Android cache root — wiped by Clear Cache, never counted as User Data. */
    static File cacheRoot(Context context) {
        File cache = context.getCacheDir();
        if (cache != null && (cache.exists() || cache.mkdirs())) {
            return cache;
        }
        File ext = context.getExternalCacheDir();
        if (ext != null && (ext.exists() || ext.mkdirs())) {
            return ext;
        }
        return context.getCacheDir();
    }

    /** {@code <cache>/Vmore} — where kept downloads live inside app cache. */
    static File downloadsDir(Context context) {
        File dir = new File(cacheRoot(context), Vmore.FOLDER);
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    /**
     * Where files another app shared into Vmore wait for their upload.
     *
     * Inside Cache on purpose: a shared copy is raw material for one send, so
     * *Clear Cache* may take it, and {@link Cleanup} leaves alone any copy a
     * job still needs.
     */
    static File shareRoot(Context context) {
        return new File(cacheRoot(context), "share");
    }

    /** One folder per share, so a whole share can be dropped in one call. */
    static File shareInbox(Context context, long stamp) {
        File root = shareRoot(context);
        if (!root.exists()) {
            //noinspection ResultOfMethodCallIgnored
            root.mkdirs();
        }
        return new File(root, "u" + Math.max(1L, stamp));
    }

    /** Root directory of all TDLib file caches across account slots. */
    static File tdRootDir(Context context) {
        File dir = new File(cacheRoot(context), "tdlib");
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    /** TDLib's {@code filesDirectory} for one account slot — inside Cache. */
    static File tdFilesDir(Context context, String sessionName) {
        String safe = (sessionName == null || sessionName.isEmpty()) ? "telegram_1" : sessionName;
        File dir = new File(tdRootDir(context), safe);
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    /** Temporary upload aliases — inside Cache. */
    static File uploadScratchDir(Context context) {
        File dir = new File(cacheRoot(context), "upload");
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    /**
     * Profile pictures — the only media kept in User Data, on purpose.
     *
     * Everything else lives in Cache so "Clear Cache" really does free it, but
     * a profile picture is not disposable: clearing the cache used to wipe the
     * account's own photo and the owner's, and the header then showed an
     * initial until Telegram happened to hand the picture over again (the owner
     * card waited for the owner to change it).  A few KB per chat is a fair
     * price for the avatar surviving a cache clear.
     */
    static File avatarsDir(Context context) {
        File dir = new File(userDataRoot(context), "avatars");
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        return dir;
    }

    /** User Data root — everything that must outlive "Clear Cache". */
    static File userDataRoot(Context context) {
        File dir = context.getFilesDir();
        if (dir != null && (dir.exists() || dir.mkdirs())) {
            return dir;
        }
        return context.getFilesDir();
    }

    /** Where older builds kept the pictures, inside Cache. */
    static File legacyAvatarsDir(Context context) {
        return new File(cacheRoot(context), "avatars");
    }

    /**
     * Moves pictures saved by an older build out of Cache, once.
     *
     * The copies are renamed into place, so a picture the user could already
     * see is still on screen after the update — no re-download needed.
     */
    static void migrateAvatars(Context context) {
        File legacy = legacyAvatarsDir(context);
        if (legacy == null || !legacy.isDirectory()) {
            return;
        }
        File[] children = legacy.listFiles();
        if (children == null) {
            return;
        }
        File target = avatarsDir(context);
        for (File child : children) {
            if (!child.isFile()) {
                deleteTree(child);
                continue;
            }
            File moved = new File(target, child.getName());
            if (!moved.exists()) {
                LocalFiles.copy(child.getAbsolutePath(), moved);
            }
            //noinspection ResultOfMethodCallIgnored
            child.delete();
        }
        String[] left = legacy.list();
        if (left != null && left.length == 0) {
            //noinspection ResultOfMethodCallIgnored
            legacy.delete();
        }
    }

    /** Where a picture used to be cached, keyed by its file name. */
    static File legacyAvatarNamed(Context context, File newFile) {
        return new File(legacyAvatarsDir(context), newFile.getName());
    }

    static File targetFile(Context context, String name) {
        File dir = downloadsDir(context);
        File file = new File(dir, Format.safeName(name, "vmore"));
        if (file.exists()) {
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

    /** Where the account's profile picture is cached, one per account slot. */
    static File avatarFile(Context context) {
        return new File(avatarsDir(context), "avatar_" + Prefs.activeSlot(context) + ".jpg");
    }

    /** Where the developer's picture is cached. */
    static File developerAvatar(Context context) {
        return new File(avatarsDir(context), "developer.jpg");
    }

    /** Where a chat or channel's profile picture is cached. */
    static File chatAvatarFile(Context context, long chatId, int photoFileId) {
        return new File(avatarsDir(context), "chat_" + chatId + "_" + photoFileId + ".jpg");
    }

    /** Copy a file to an exact target path. */
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

    /** Place a finished download into {@code <cache>/Vmore} by hard link or copy. */
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
        try {
            //noinspection Since15
            java.nio.file.Files.createLink(target.toPath(), source.toPath());
            if (target.isFile()) {
                return target;
            }
        } catch (Throwable ignored) {
            // Fall through to stream copy when hard links are not supported.
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

    static void deleteTree(File target) {
        if (target == null || !target.exists()) {
            return;
        }
        File[] children = target.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteTree(child);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        target.delete();
    }

    /**
     * Sweeps any old media files that older versions stored inside User Data
     * ({@code filesDir} or {@code externalFilesDir}) while leaving the TDLib SQLite
     * login database, preferences, queue and history untouched.
     */
    static void sweepLegacyUserData(Context context) {
        try {
            File extOld = context.getExternalFilesDir(null);
            if (extOld != null) {
                deleteTree(new File(extOld, Vmore.FOLDER));
            }
        } catch (Throwable ignored) {
        }
        try {
            File internalFiles = context.getFilesDir();
            if (internalFiles == null) {
                return;
            }
            deleteTree(new File(internalFiles, Vmore.FOLDER));
            File[] children = internalFiles.listFiles();
            if (children == null) {
                return;
            }
            for (File child : children) {
                if (child.isDirectory() && child.getName().startsWith("telegram_")) {
                    for (String sub : LEGACY_TD_MEDIA_DIRS) {
                        deleteTree(new File(child, sub));
                    }
                }
            }
        } catch (Throwable ignored) {
        }
    }

    /** Every cached media byte Vmore currently holds on the phone. */
    static long totalBytes(Context context) {
        return treeBytes(downloadsDir(context))
                + treeBytes(uploadScratchDir(context))
                + treeBytes(tdRootDir(context));
    }

    static long treeBytes(File root) {
        if (root == null || !root.exists()) {
            return 0L;
        }
        if (root.isFile()) {
            return root.length();
        }
        File[] children = root.listFiles();
        if (children == null) {
            return 0L;
        }
        long total = 0L;
        for (File child : children) {
            total += treeBytes(child);
        }
        return total;
    }
}
