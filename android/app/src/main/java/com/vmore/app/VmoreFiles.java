package com.vmore.app;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

/**
 * A tiny {@code content://} provider for the downloaded files.
 *
 * Android 7+ forbids handing a {@code file://} URI to another app
 * ({@code FileUriExposedException}), which broke "Open in another app" and
 * "Share".  The usual cure is {@code androidx.core.FileProvider}; this app ships
 * without AndroidX, so the provider is thirty lines of the same thing: only the
 * files inside the app's own download folder are exposed, and only to apps that
 * were handed an explicit grant.
 *
 * Authority: {@code <applicationId>.files} → {@code content://com.vmore.app.files/<name>}
 */
public class VmoreFiles extends ContentProvider {

    public static final String AUTHORITY_SUFFIX = ".files";

    public static String authority(Context context) {
        return context.getPackageName() + AUTHORITY_SUFFIX;
    }

    /** The shareable URI for one downloaded file. */
    public static Uri uriFor(Context context, File file) {
        return Uri.parse("content://" + authority(context) + "/"
                + Uri.encode(file.getName()));
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    private File resolve(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || name.isEmpty()) {
            throw new FileNotFoundException("no file in " + uri);
        }
        File root = LocalStore.downloadsDir(getContext());
        File target = new File(root, name);
        try {
            //: Never serve anything outside the download folder.
            if (!target.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator)) {
                throw new FileNotFoundException("outside the download folder");
            }
        } catch (IOException exc) {
            throw new FileNotFoundException("could not resolve " + name);
        }
        if (!target.exists()) {
            throw new FileNotFoundException(name + " is gone");
        }
        return target;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        return ParcelFileDescriptor.open(resolve(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        try {
            File file = resolve(uri);
            String extension = MediaUtils.extension(file.getName());
            String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
            return mime == null ? MediaUtils.mimeOf(file) : mime;
        } catch (FileNotFoundException exc) {
            return "application/octet-stream";
        }
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs,
                        String sortOrder) {
        try {
            File file = resolve(uri);
            MatrixCursor cursor = new MatrixCursor(new String[]{
                    OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
            cursor.addRow(new Object[]{file.getName(), file.length()});
            return cursor;
        } catch (FileNotFoundException exc) {
            return null;
        }
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        return 0;
    }
}
