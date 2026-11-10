package com.vmore.app;

import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * A file another app handed to Vmore through "Share".
 *
 * Until this existed Vmore could only send what it had downloaded from
 * Telegram: a photo from the camera, a PDF from a mail app or a voice note from
 * a recorder had no way in at all — the only share filter was {@code
 * text/plain}, so those apps did not even offer Vmore in their chooser.
 *
 * Two things make this different from a link: the bytes are already on the
 * phone (there is nothing to download), and the file name is chosen by the app
 * that shared it, so it is kept exactly as it is.  The copy lives in its own
 * folder inside Cache, one folder per share, and it is deleted the moment the
 * upload lands — the folder is raw material for one send, not a library.
 */
final class ShareIntake {

    /** Telegram refuses an upload above two gigabytes on a normal account. */
    static final long MAX_BYTES = 2L * 1024L * 1024L * 1024L;

    /** A share of five hundred photos is a mistake, not a batch. */
    static final int MAX_FILES = 50;

    /** One file copied out of a share, ready to be uploaded. */
    static final class Item {
        String path = "";
        String name = "";
        String kind = "document";
        long size;

        File file() {
            return new File(path);
        }
    }

    private ShareIntake() {
    }

    /** True when this intent carries files rather than a link. */
    static boolean hasFiles(Intent intent) {
        return !uris(intent).isEmpty();
    }

    /**
     * Every file in the intent, in the order the sharing app listed them.
     *
     * The same uri can appear twice (some galleries send both the single and
     * the multiple extra), which would upload the file twice, so duplicates are
     * dropped here.
     */
    static List<Uri> uris(Intent intent) {
        List<Uri> found = new ArrayList<>();
        if (intent == null) {
            return found;
        }
        String action = intent.getAction();
        if (!Intent.ACTION_SEND.equals(action) && !Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            return found;
        }
        Set<Uri> unique = new LinkedHashSet<>();
        Uri single = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (single != null) {
            unique.add(single);
        }
        ArrayList<Uri> many = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
        if (many != null) {
            for (Uri uri : many) {
                if (uri != null) {
                    unique.add(uri);
                }
            }
        }
        found.addAll(unique);
        return found;
    }

    /**
     * Copies every shared file into one folder of its own.
     *
     * A content uri cannot be uploaded: TDLib uploads a path, and the permission
     * behind the uri dies with the app that granted it.  So each file is copied
     * once, under the name its owner gave it, and the copy is what the queue
     * carries from there on.
     */
    static List<Item> copyInto(Context context, List<Uri> uris) throws Exception {
        Context app = context.getApplicationContext();
        File folder = LocalFiles.shareInbox(app, System.currentTimeMillis());
        //noinspection ResultOfMethodCallIgnored
        folder.mkdirs();
        List<Item> items = new ArrayList<>();
        for (Uri uri : uris) {
            if (items.size() >= MAX_FILES) {
                break;
            }
            Item item = copyOne(app, uri, folder, items.size() + 1);
            if (item != null) {
                items.add(item);
            }
        }
        if (items.isEmpty()) {
            LocalFiles.deleteTree(folder);
            throw new Exception("nothing in that share could be read");
        }
        return items;
    }

    private static Item copyOne(Context context, Uri uri, File folder, int index) {
        String display = declaredName(context, uri);
        String mime = mimeOf(context, uri);
        String kind = kindOf(mime, display);
        String suffix = suffixOf(display, mime, kind);
        String name = unique(folder, nameFor(display, suffix, kind, index));
        long declared = declaredSize(context, uri);
        if (declared > MAX_BYTES || freeBytes(folder) < declared + 8L * 1024L * 1024L) {
            return null;
        }
        File target = new File(folder, name);
        InputStream in = null;
        OutputStream out = null;
        try {
            in = context.getContentResolver().openInputStream(uri);
            if (in == null) {
                return null;
            }
            out = new FileOutputStream(target);
            byte[] buffer = new byte[64 * 1024];
            long written = 0L;
            int read;
            while ((read = in.read(buffer)) > 0) {
                written += read;
                if (written > MAX_BYTES) {
                    close(out);
                    out = null;
                    //noinspection ResultOfMethodCallIgnored
                    target.delete();
                    return null;
                }
                out.write(buffer, 0, read);
            }
            out.flush();
            if (written <= 0L) {
                //noinspection ResultOfMethodCallIgnored
                target.delete();
                return null;
            }
            Item item = new Item();
            item.path = target.getAbsolutePath();
            item.name = target.getName();
            item.kind = kind;
            item.size = written;
            return item;
        } catch (Exception error) {
            //noinspection ResultOfMethodCallIgnored
            target.delete();
            return null;
        } finally {
            close(in);
            close(out);
        }
    }

    /** The name the file already had, never a name Vmore invents. */
    private static String nameFor(String display, String suffix, String kind, int index) {
        String stem = Format.withoutExtension(Format.displayName(display, ""));
        if (stem.trim().isEmpty()) {
            stem = Format.withoutExtension(Format.datedName(kind, 0L, ""));
        }
        String name = Format.safeName(stem.trim(), "shared_" + index) + suffix;
        return Format.safeName(name, "shared_" + index);
    }

    /** Two files called "IMG_0001.jpg" must not overwrite each other. */
    private static String unique(File folder, String name) {
        String candidate = name;
        String stem = Format.withoutExtension(name);
        String suffix = name.substring(stem.length());
        for (int copy = 2; copy < 1000; copy++) {
            if (!new File(folder, candidate).exists()) {
                return candidate;
            }
            candidate = stem + "-" + copy + suffix;
        }
        return stem + "-" + System.currentTimeMillis() + suffix;
    }

    private static String suffixOf(String display, String mime, String kind) {
        if (display != null) {
            int dot = display.lastIndexOf('.');
            if (dot > 0 && dot < display.length() - 1) {
                String suffix = display.substring(dot).toLowerCase(Locale.US);
                if (suffix.length() <= 8 && suffix.substring(1).matches("[a-z0-9]+")) {
                    return suffix;
                }
            }
        }
        String fromMime = MimeTypeMap.getSingleton()
                .getExtensionFromMimeType(mime == null ? "" : mime);
        if (fromMime != null && fromMime.matches("[a-z0-9]+")) {
            return "." + fromMime;
        }
        if ("photo".equals(kind)) {
            return ".jpg";
        }
        if ("video".equals(kind)) {
            return ".mp4";
        }
        if ("audio".equals(kind)) {
            return ".m4a";
        }
        return "";
    }

    /**
     * What this file is, from the type the sharing app declared and, when it
     * declared nothing, from the extension the name already carries.
     */
    static String kindOf(String mime, String name) {
        String type = mime == null ? "" : mime.toLowerCase(Locale.US);
        if (type.startsWith("image/")) {
            return "photo";
        }
        if (type.startsWith("video/")) {
            return "video";
        }
        if (type.startsWith("audio/")) {
            return "audio";
        }
        if (!type.isEmpty() && !type.equals("application/octet-stream")) {
            return "document";
        }
        String lower = name == null ? "" : name.toLowerCase(Locale.US);
        int dot = lower.lastIndexOf('.');
        String suffix = dot < 0 ? "" : lower.substring(dot + 1);
        if (suffix.matches("jpe?g|png|gif|webp|bmp|heic|heif|avif")) {
            return "photo";
        }
        if (suffix.matches("mp4|mkv|mov|webm|3gp|m4v|avi")) {
            return "video";
        }
        if (suffix.matches("mp3|m4a|aac|ogg|opus|flac|wav|amr")) {
            return "audio";
        }
        return "document";
    }

    private static String mimeOf(Context context, Uri uri) {
        try {
            String type = context.getContentResolver().getType(uri);
            return type == null ? "" : type;
        } catch (Exception error) {
            return "";
        }
    }

    private static String declaredName(Context context, Uri uri) {
        Cursor cursor = null;
        try {
            cursor = context.getContentResolver()
                    .query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (cursor != null && cursor.moveToFirst()) {
                int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (column >= 0) {
                    String value = cursor.getString(column);
                    if (value != null && !value.trim().isEmpty()) {
                        return value.trim();
                    }
                }
            }
        } catch (Exception ignored) {
            //: A provider that answers nothing is not a reason to refuse the file.
        } finally {
            close(cursor);
        }
        String last = uri.getLastPathSegment();
        return last == null ? "" : last;
    }

    private static long declaredSize(Context context, Uri uri) {
        Cursor cursor = null;
        try {
            cursor = context.getContentResolver()
                    .query(uri, new String[]{OpenableColumns.SIZE}, null, null, null);
            if (cursor != null && cursor.moveToFirst()) {
                int column = cursor.getColumnIndex(OpenableColumns.SIZE);
                if (column >= 0 && !cursor.isNull(column)) {
                    return cursor.getLong(column);
                }
            }
        } catch (Exception ignored) {
            //: Unknown size: the copy itself still guards the limit.
        } finally {
            close(cursor);
        }
        return 0L;
    }

    private static long freeBytes(File folder) {
        try {
            android.os.StatFs stat = new android.os.StatFs(folder.getAbsolutePath());
            return stat.getAvailableBytes();
        } catch (Exception error) {
            return Long.MAX_VALUE;
        }
    }

    private static void close(Object closeable) {
        try {
            if (closeable instanceof InputStream) {
                ((InputStream) closeable).close();
            } else if (closeable instanceof OutputStream) {
                ((OutputStream) closeable).close();
            } else if (closeable instanceof Cursor) {
                ((Cursor) closeable).close();
            }
        } catch (Exception ignored) {
            //: Closing a stream that is already gone is not a failure.
        }
    }

    // ------------------------------------------------------------ pending //

    /**
     * The share is written down as well as copied.
     *
     * A share can arrive before the account is signed in, and Android may kill
     * this screen while the user is on the sign-in page; the files are already
     * on disk, so remembering where they are is what makes them survive.
     */
    static String encode(List<Item> items) {
        JSONArray array = new JSONArray();
        for (Item item : items) {
            JSONObject row = new JSONObject();
            try {
                row.put("path", item.path);
                row.put("name", item.name);
                row.put("kind", item.kind);
                row.put("size", item.size);
                array.put(row);
            } catch (Exception ignored) {
                //: A row that cannot be written is a row that cannot be sent.
            }
        }
        return array.toString();
    }

    static List<Item> decode(String json) {
        List<Item> items = new ArrayList<>();
        if (json == null || json.isEmpty()) {
            return items;
        }
        try {
            JSONArray array = new JSONArray(json);
            for (int index = 0; index < array.length(); index++) {
                JSONObject row = array.optJSONObject(index);
                if (row == null) {
                    continue;
                }
                Item item = new Item();
                item.path = row.optString("path", "");
                item.name = row.optString("name", "");
                item.kind = row.optString("kind", "document");
                item.size = row.optLong("size", 0L);
                File file = item.file();
                if (file.isFile() && file.length() > 0L) {
                    items.add(item);
                }
            }
        } catch (Exception ignored) {
            //: Unreadable means nothing to send, which the sheet says in words.
        }
        return items;
    }

    /** Drops a share nobody is going to send, and everything it copied. */
    static void discard(List<Item> items) {
        if (items == null) {
            return;
        }
        for (Item item : items) {
            File file = item.file();
            //noinspection ResultOfMethodCallIgnored
            file.delete();
            File parent = file.getParentFile();
            if (parent == null) {
                continue;
            }
            String[] left = parent.list();
            if (left == null || left.length == 0) {
                //noinspection ResultOfMethodCallIgnored
                parent.delete();
            }
        }
    }
}
