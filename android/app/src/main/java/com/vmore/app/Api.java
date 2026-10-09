package com.vmore.app;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The whole HTTP surface of {@code /api/v2} in one small class.
 *
 * Deliberately built on {@link HttpURLConnection}: the app ships without any
 * third-party dependency, so the APK stays tiny and the build never depends on
 * a library that may disappear.
 */
public final class Api {

    public static final String API = "/api/v2";
    /** Version reported to the server (matched by the workflow's release name). */
    public static final String VERSION = "1.0.0";
    private static final int TIMEOUT_MS = 30_000;

    /** One background pool for every call; results are posted back to the UI thread. */
    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private Api() {
    }

    /** What every call returns: {@code ok}, a JSON body and/or the failure reason. */
    public static final class Result {
        public final boolean ok;
        public final JSONObject json;
        public final String error;
        public final int code;

        Result(boolean ok, JSONObject json, String error, int code) {
            this.ok = ok;
            this.json = json;
            this.error = error;
            this.code = code;
        }

        public String optString(String key, String fallback) {
            return json == null ? fallback : json.optString(key, fallback);
        }

        public JSONObject optJson(String key) {
            return json == null ? null : json.optJSONObject(key);
        }

        public boolean optBoolean(String key, boolean fallback) {
            return json == null ? fallback : json.optBoolean(key, fallback);
        }

        public int optInt(String key, int fallback) {
            return json == null ? fallback : json.optInt(key, fallback);
        }

        public long optLong(String key, long fallback) {
            return json == null ? fallback : json.optLong(key, fallback);
        }
    }

    public interface Callback {
        void done(Result result);
    }

    public static String normalizeBase(String base) {
        return Urls.normalizeBase(base);
    }

    public static String tokenUrl(String base, String token) {
        return Urls.tokenUrl(base, token);
    }

    /** The token inside a pasted login link ({@code …/api/v2/token/HPSEG9}). */
    public static String tokenFromUrl(String value) {
        return Urls.tokenFromUrl(value);
    }

    public static void get(final String url, final Callback callback) {
        request("GET", url, null, null, callback);
    }

    public static void post(final String url, final JSONObject body, final Callback callback) {
        request("POST", url, body == null ? null : body.toString(), "application/json", callback);
    }

    public static void request(final String method, final String url, final String body,
                               final String contentType, final Callback callback) {
        POOL.execute(() -> {
            Result result = execute(method, url, body, contentType);
            MAIN.post(() -> callback.done(result));
        });
    }

    private static Result execute(String method, String url, String body, String contentType) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestMethod(method);
            connection.setConnectTimeout(TIMEOUT_MS);
            connection.setReadTimeout(TIMEOUT_MS);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("X-App-Version", VERSION);
            if (body != null) {
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", contentType);
                byte[] payload = body.getBytes(StandardCharsets.UTF_8);
                connection.setFixedLengthStreamingMode(payload.length);
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(payload);
                }
            }
            int code = connection.getResponseCode();
            InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
            String text = readAll(stream);
            JSONObject json = null;
            try {
                json = new JSONObject(text);
            } catch (Exception ignored) {
                // not JSON — keep the raw text as the error message below
            }
            boolean ok = code >= 200 && code < 300 && (json == null || json.optBoolean("ok", true));
            String error = null;
            if (!ok) {
                error = json != null ? json.optString("error", null) : null;
                if (error == null || error.isEmpty()) {
                    error = text == null || text.isEmpty() ? "HTTP " + code : text;
                }
            }
            return new Result(ok, json, error, code);
        } catch (Exception exc) {
            return new Result(false, null, friendly(exc), 0);
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static String friendly(Exception exc) {
        String message = exc.getMessage() == null ? exc.getClass().getSimpleName() : exc.getMessage();
        if (exc instanceof java.net.UnknownHostException) {
            return "Server not found — check the server address.";
        }
        if (exc instanceof java.net.SocketTimeoutException) {
            return "The server took too long to answer.";
        }
        if (exc instanceof IOException) {
            return "Network problem: " + message;
        }
        return message;
    }

    private static String readAll(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line).append('\n');
            }
        }
        return builder.toString();
    }

    // -------------------------------------------------------------------- //
    //  Streaming download with pause / resume support
    // -------------------------------------------------------------------- //

    /** Called from the download thread; returning false aborts the transfer. */
    public interface Progress {
        boolean onBytes(long written, long total);
    }

    /** Thrown when the user stopped the download on purpose. */
    public static final class Stopped extends IOException {
        public Stopped(String message) {
            super(message);
        }
    }

    /**
     * Download {@code url} into {@code target}, resuming at its current length.
     *
     * The partial file is what makes pause cheap: pausing only closes the socket,
     * and resuming sends a {@code Range} header from the byte we stopped at.
     */
    public static void download(String url, File target, Progress progress) throws IOException {
        long start = target.exists() ? target.length() : 0L;
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setConnectTimeout(TIMEOUT_MS);
            connection.setReadTimeout(60_000);
            connection.setRequestProperty("Accept", "*/*");
            if (start > 0) {
                connection.setRequestProperty("Range", "bytes=" + start + "-");
            }
            int code = connection.getResponseCode();
            if (code == 416) {                     // already complete
                return;
            }
            if (code >= 400) {
                throw new IOException("Server answered HTTP " + code);
            }
            long total = connection.getContentLength() > 0 ? connection.getContentLength() + start : 0;
            try (InputStream in = connection.getInputStream();
                 OutputStream out = new java.io.FileOutputStream(target, start > 0)) {
                byte[] buffer = new byte[64 * 1024];
                long written = start;
                int read;
                while ((read = in.read(buffer)) > 0) {
                    out.write(buffer, 0, read);
                    written += read;
                    if (!progress.onBytes(written, total)) {
                        throw new Stopped("paused or stopped");
                    }
                }
                out.flush();
            }
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    // -------------------------------------------------------------------- //
    //  Multipart upload (the edited file goes back through the user session)
    // -------------------------------------------------------------------- //

    public interface UploadProgress {
        boolean onBytes(long sent, long total);
    }

    /**
     * Upload {@code file} (plus an optional thumbnail) to the token's upload
     * endpoint.  The server pushes it out through the user's own Telegram
     * session, so the bot never re-uploads a byte.
     */
    public static JSONObject upload(String base, String token, File file, String caption,
                                    File thumbnail, String kind, String fileName,
                                    long durationMs, int width, int height,
                                    UploadProgress progress) throws IOException {
        String boundary = "----Vmore" + System.currentTimeMillis();
        String url = tokenUrl(base, token) + "/upload";
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(TIMEOUT_MS);
        connection.setReadTimeout(30 * 60 * 1000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        connection.setChunkedStreamingMode(64 * 1024);

        try (OutputStream out = connection.getOutputStream()) {
            writeField(out, boundary, "kind", kind);
            writeField(out, boundary, "file_name", fileName);
            writeField(out, boundary, "caption", caption == null ? "" : caption);
            if (durationMs > 0) {
                writeField(out, boundary, "duration", String.valueOf(durationMs / 1000));
            }
            if (width > 0) {
                writeField(out, boundary, "width", String.valueOf(width));
            }
            if (height > 0) {
                writeField(out, boundary, "height", String.valueOf(height));
            }
            writeFile(out, boundary, "file", file, fileName, "application/octet-stream",
                    file.length(), progress);
            if (thumbnail != null && thumbnail.exists()) {
                writeFile(out, boundary, "thumbnail", thumbnail, "thumb.jpg", "image/jpeg",
                        thumbnail.length(), null);
            }
            out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
        }

        int code = connection.getResponseCode();
        InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
        String text = readAll(stream);
        connection.disconnect();
        try {
            return new JSONObject(text);
        } catch (Exception exc) {
            throw new IOException(text.isEmpty() ? "HTTP " + code : text);
        }
    }

    /**
     * Commit an upload **without re-sending the bytes**: only the caption (and
     * maybe a thumbnail) travel to the server, which re-sends what it already
     * has — the still-warm download job, or the original message by reference
     * through the user's own session.  When none of that is possible the reply
     * says {@code needs_bytes} and the caller falls back to {@link #upload}.
     */
    public static JSONObject uploadMeta(String base, String token, String link, String jobId,
                                        String caption, File thumbnail, String kind,
                                        String fileName) throws IOException {
        String boundary = "----Vmore" + System.currentTimeMillis();
        String url = tokenUrl(base, token) + "/upload";
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(TIMEOUT_MS);
        connection.setReadTimeout(30 * 60 * 1000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        connection.setChunkedStreamingMode(64 * 1024);

        try (OutputStream out = connection.getOutputStream()) {
            if (kind != null && !kind.isEmpty()) {
                writeField(out, boundary, "kind", kind);
            }
            if (fileName != null && !fileName.isEmpty()) {
                writeField(out, boundary, "file_name", fileName);
            }
            writeField(out, boundary, "caption", caption == null ? "" : caption);
            if (link != null && !link.isEmpty()) {
                writeField(out, boundary, "link", link);
            }
            if (jobId != null && !jobId.isEmpty()) {
                writeField(out, boundary, "job_id", jobId);
            }
            if (thumbnail != null && thumbnail.exists()) {
                writeFile(out, boundary, "thumbnail", thumbnail, "thumb.jpg", "image/jpeg",
                        thumbnail.length(), null);
            }
            out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
        }

        int code = connection.getResponseCode();
        InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
        String text = readAll(stream);
        connection.disconnect();
        try {
            return new JSONObject(text);
        } catch (Exception exc) {
            throw new IOException(text.isEmpty() ? "HTTP " + code : text);
        }
    }

    private static void writeField(OutputStream out, String boundary, String name, String value)
            throws IOException {
        String head = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.UTF_8));
        out.write((value == null ? "" : value).getBytes(StandardCharsets.UTF_8));
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private static void writeFile(OutputStream out, String boundary, String field, File file,
                                  String fileName, String mime, long total,
                                  UploadProgress progress) throws IOException {
        String head = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + field + "\"; filename=\""
                + fileName + "\"\r\n"
                + "Content-Type: " + mime + "\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.UTF_8));
        long sent = 0;
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
                sent += read;
                if (progress != null && !progress.onBytes(sent, total)) {
                    throw new IOException("upload cancelled");
                }
            }
        }
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    /** Fetch raw bytes (the owner's profile picture). */
    public static byte[] bytes(String url) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(20_000);
            int code = connection.getResponseCode();
            if (code >= 400) {
                return null;
            }
            try (InputStream in = connection.getInputStream();
                 ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[16 * 1024];
                int read;
                while ((read = in.read(buffer)) > 0) {
                    out.write(buffer, 0, read);
                }
                return out.toByteArray();
            }
        } catch (Exception exc) {
            return null;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    public static String encode(String value) {
        return Urls.encode(value);
    }
}
