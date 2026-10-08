package com.vmore.app;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMetadataRetriever;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.util.Locale;

/**
 * File helpers: mime detection, saving to the phone's Downloads folder, video
 * trimming and video metadata.
 *
 * Trimming runs entirely on the phone ({@link MediaExtractor} +
 * {@link MediaMuxer}), so the bytes that would have been cut away are never
 * uploaded — bandwidth first, exactly like the rest of the app.
 */
final class MediaUtils {

    private MediaUtils() {
    }

    static String extension(String name) {
        if (name == null) {
            return "";
        }
        int dot = name.lastIndexOf('.');
        return dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
    }

    static String mimeOf(File file) {
        String ext = extension(file.getName());
        switch (ext) {
            case "mp4":
            case "m4v":
                return "video/mp4";
            case "mkv":
                return "video/x-matroska";
            case "webm":
                return "video/webm";
            case "avi":
                return "video/x-msvideo";
            case "mov":
                return "video/quicktime";
            case "jpg":
            case "jpeg":
                return "image/jpeg";
            case "png":
                return "image/png";
            case "gif":
                return "image/gif";
            case "webp":
                return "image/webp";
            case "mp3":
                return "audio/mpeg";
            case "m4a":
                return "audio/mp4";
            case "ogg":
            case "opus":
                return "audio/ogg";
            case "wav":
                return "audio/wav";
            case "pdf":
                return "application/pdf";
            case "txt":
            case "log":
            case "json":
            case "xml":
            case "csv":
                return "text/plain";
            case "apk":
                return "application/vnd.android.package-archive";
            case "zip":
                return "application/zip";
            default:
                return "application/octet-stream";
        }
    }

    static boolean isVideo(File file) {
        return mimeOf(file).startsWith("video/");
    }

    static boolean isImage(File file) {
        return mimeOf(file).startsWith("image/");
    }

    static boolean isAudio(File file) {
        return mimeOf(file).startsWith("audio/");
    }

    static boolean isPdf(File file) {
        return "application/pdf".equals(mimeOf(file));
    }

    static boolean isText(File file) {
        String mime = mimeOf(file);
        return mime.startsWith("text/");
    }

    static long[] videoMeta(File file) {
        long[] meta = new long[]{0L, 0L, 0L};   // durationMs, width, height
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(file.getAbsolutePath());
            meta[0] = parseLong(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION));
            meta[1] = parseLong(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH));
            meta[2] = parseLong(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT));
        } catch (Exception ignored) {
        } finally {
            try {
                retriever.release();
            } catch (Exception ignored) {
            }
        }
        return meta;
    }

    /** Grab a frame out of a video to use as the upload thumbnail. */
    static File thumbnailFrom(File video, File target) {
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(video.getAbsolutePath());
            android.graphics.Bitmap frame = retriever.getFrameAtTime(0,
                    MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
            if (frame == null) {
                return null;
            }
            try (FileOutputStream out = new FileOutputStream(target)) {
                frame.compress(android.graphics.Bitmap.CompressFormat.JPEG, 88, out);
            }
            return target;
        } catch (Exception exc) {
            return null;
        } finally {
            try {
                retriever.release();
            } catch (Exception ignored) {
            }
        }
    }

    private static long parseLong(String value) {
        try {
            return value == null ? 0L : Long.parseLong(value);
        } catch (NumberFormatException exc) {
            return 0L;
        }
    }

    // -------------------------------------------------------------------- //
    //  Save to device (the phone's own Downloads folder)
    // -------------------------------------------------------------------- //

    static String saveToDevice(Context context, File source) throws IOException {
        String name = source.getName();
        String mime = mimeOf(source);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentResolver resolver = context.getContentResolver();
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                    Environment.DIRECTORY_DOWNLOADS + "/Vmore");
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                throw new IOException("The gallery refused the file");
            }
            try (InputStream in = new FileInputStream(source);
                 OutputStream out = resolver.openOutputStream(uri)) {
                if (out == null) {
                    throw new IOException("could not open the destination");
                }
                copy(in, out);
            }
            return Environment.DIRECTORY_DOWNLOADS + "/Vmore/" + name;
        }
        File dir = new File(Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_DOWNLOADS), "Vmore");
        if (!dir.exists()) {
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
        }
        File target = new File(dir, name);
        try (InputStream in = new FileInputStream(source);
             OutputStream out = new FileOutputStream(target)) {
            copy(in, out);
        }
        return target.getAbsolutePath();
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buffer = new byte[128 * 1024];
        int read;
        while ((read = in.read(buffer)) > 0) {
            out.write(buffer, 0, read);
        }
        out.flush();
    }

    // -------------------------------------------------------------------- //
    //  Trim (front / back) — MP4 in, MP4 out, no re-encode
    // -------------------------------------------------------------------- //

    static boolean canTrim(File file) {
        String ext = extension(file.getName());
        return "mp4".equals(ext) || "m4v".equals(ext) || "mov".equals(ext);
    }

    /**
     * Cut {@code source} from {@code startMs} to {@code endMs} without touching
     * a frame: the tracks are copied as they are, so the trim is instant and the
     * result loses no quality.
     */
    static File trim(File source, File target, long startMs, long endMs) throws IOException {
        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;
        try {
            extractor.setDataSource(source.getAbsolutePath());
            int tracks = extractor.getTrackCount();
            muxer = new MediaMuxer(target.getAbsolutePath(),
                    MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            int[] trackMap = new int[tracks];
            for (int index = 0; index < tracks; index++) {
                MediaFormat format = extractor.getTrackFormat(index);
                trackMap[index] = muxer.addTrack(format);
                extractor.selectTrack(index);
            }
            muxer.start();
            long offsetUs = startMs * 1000L;
            long endUs = endMs * 1000L;
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            ByteBuffer buffer = ByteBuffer.allocateDirect(2 * 1024 * 1024);
            for (int index = 0; index < tracks; index++) {
                extractor.unselectTrack(index);
            }
            for (int index = 0; index < tracks; index++) {
                extractor.selectTrack(index);
                extractor.seekTo(offsetUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC);
                while (true) {
                    long timeUs = extractor.getSampleTime();
                    if (timeUs < 0 || timeUs > endUs) {
                        break;                // ran past the new end of the video
                    }
                    buffer.clear();
                    int size = extractor.readSampleData(buffer, 0);
                    if (size <= 0) {
                        break;
                    }
                    info.offset = 0;
                    info.size = size;
                    info.presentationTimeUs = Math.max(0L, timeUs - offsetUs);
                    info.flags = (extractor.getSampleFlags() & MediaExtractor.SAMPLE_FLAG_SYNC) != 0
                            ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0;
                    buffer.position(0);
                    buffer.limit(size);
                    muxer.writeSampleData(trackMap[index], buffer, info);
                    if (!extractor.advance()) {
                        break;
                    }
                }
            }
            return target;
        } finally {
            try {
                if (muxer != null) {
                    muxer.stop();
                    muxer.release();
                }
            } catch (Exception ignored) {
            }
            extractor.release();
        }
    }
}
