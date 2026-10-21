package com.vmore.app;

import org.json.JSONObject;

/**
 * One unit of work: a single message (or a whole range expanded into one job per
 * message) that Vmore should download and/or send to a chat.
 *
 * A job is plain data — the queue ({@link Jobs}) stores it, the engine
 * ({@link QueueService}) runs it, and every screen reads the very same object,
 * which is why the app can be closed and reopened without losing anything.
 */
public final class QJob {

    public static final String QUEUED = "queued";
    public static final String RESOLVING = "resolving";
    public static final String COPYING = "copying";
    public static final String DOWNLOADING = "downloading";
    public static final String UPLOADING = "uploading";
    public static final String DONE = "done";
    public static final String FAILED = "failed";
    public static final String PAUSED = "paused";
    public static final String CANCELLED = "cancelled";

    /** Download the file to the phone and (optionally) upload it. */
    public static final String METHOD_DOWNLOAD = "download";
    /** Let Telegram move the message itself: no bytes cross the phone. */
    public static final String METHOD_FORWARD = "forward";
    /** A link that names a chat but no message: take its recent files. */
    public static final String METHOD_SCAN = "scan";

    public String id = "";
    public String batchId = "";
    public String batchLabel = "";

    /** What the user pasted, kept so History can show the source. */
    public String raw = "";

    // Where the media lives.
    public long chatId;
    public long messageId;
    public String username = "";
    public String inviteHash = "";
    public boolean privateLink;
    public long internalId;

    // Where it goes.
    public long destChatId;
    public String destTitle = "";
    public String method = METHOD_DOWNLOAD;
    public String sendAs = Prefs.SEND_FILE;
    public boolean uploadAfter = true;
    public boolean deleteLocal = true;

    // Live state.
    public String stage = QUEUED;
    public String name = "";
    public String kind = "document";
    public long size;
    public long done;
    public long uploaded;
    public int fileId;
    public String remoteFileId = "";
    public String path = "";
    public String caption = "";
    public long durationSec;
    public int width;
    public int height;
    public String error = "";
    public String note = "";
    public long created;
    public long updated;
    public int attempts;

    /**
     * Per-batch rules, carried by every job of the batch: which kinds to keep,
     * how big a file may be, and whether a file that was already uploaded once
     * should be skipped instead of sent again.
     */
    public String onlyKinds = "";
    public long minSize;
    public long maxSize;
    public boolean skipDuplicates = true;
    /** Set while the engine skips this job, so the screens can say why. */
    public boolean skipped;
    /**
     * The source chat protects its content.
     *
     * The file can still be downloaded, but not re-sent by reference: the
     * upload has to use the bytes as a new file, which is what the engine does
     * when this is set (and again if Telegram refuses anyway).
     */
    public boolean protectedContent;

    /** True when this media passes the batch's filter. */
    public boolean allows(String kind, long size) {
        if (onlyKinds != null && !onlyKinds.isEmpty()) {
            String clean = kind == null ? "document" : kind;
            if (!onlyKinds.contains(clean)) {
                return false;
            }
        }
        if (minSize > 0 && size > 0 && size < minSize) {
            return false;
        }
        return maxSize <= 0 || size <= 0 || size <= maxSize;
    }

    public boolean isFinished() {
        return DONE.equals(stage) || CANCELLED.equals(stage);
    }

    public boolean isActive() {
        return RESOLVING.equals(stage) || COPYING.equals(stage)
                || DOWNLOADING.equals(stage) || UPLOADING.equals(stage);
    }

    public int percent() {
        if (UPLOADING.equals(stage)) {
            long total = size > 0 ? size : uploaded;
            return Math.min(99, Format.percent(uploaded, total));
        }
        return Format.percent(done, size);
    }

    /** A short line for the queue and history lists. */
    public String title() {
        if (name != null && !name.isEmpty()) {
            return name;
        }
        if (messageId > 0) {
            return "Message " + messageId + (username.isEmpty() ? "" : " in " + username);
        }
        return raw.isEmpty() ? "Job" : raw;
    }

    public JSONObject toJson() {
        JSONObject json = new JSONObject();
        try {
            json.put("id", id);
            json.put("batch", batchId);
            json.put("batch_label", batchLabel);
            json.put("raw", raw);
            json.put("chat_id", chatId);
            json.put("message_id", messageId);
            json.put("username", username);
            json.put("invite", inviteHash);
            json.put("private_link", privateLink);
            json.put("internal_id", internalId);
            json.put("dest_chat_id", destChatId);
            json.put("dest_title", destTitle);
            json.put("method", method);
            json.put("send_as", sendAs);
            json.put("upload_after", uploadAfter);
            json.put("delete_local", deleteLocal);
            json.put("stage", stage);
            json.put("name", name);
            json.put("kind", kind);
            json.put("size", size);
            json.put("done", done);
            json.put("uploaded", uploaded);
            json.put("file_id", fileId);
            json.put("remote_file_id", remoteFileId);
            json.put("path", path);
            json.put("caption", caption);
            json.put("duration", durationSec);
            json.put("width", width);
            json.put("height", height);
            json.put("error", error);
            json.put("note", note);
            json.put("created", created);
            json.put("updated", updated);
            json.put("attempts", attempts);
            json.put("only_kinds", onlyKinds);
            json.put("min_size", minSize);
            json.put("max_size", maxSize);
            json.put("skip_duplicates", skipDuplicates);
            json.put("protected_content", protectedContent);
        } catch (Exception ignored) {
        }
        return json;
    }

    public static QJob from(JSONObject json) {
        QJob job = new QJob();
        job.id = json.optString("id", "");
        job.batchId = json.optString("batch", "");
        job.batchLabel = json.optString("batch_label", "");
        job.raw = json.optString("raw", "");
        job.chatId = json.optLong("chat_id", 0L);
        job.messageId = json.optLong("message_id", 0L);
        job.username = json.optString("username", "");
        job.inviteHash = json.optString("invite", "");
        job.privateLink = json.optBoolean("private_link", false);
        job.internalId = json.optLong("internal_id", 0L);
        job.destChatId = json.optLong("dest_chat_id", 0L);
        job.destTitle = json.optString("dest_title", "");
        job.method = json.optString("method", METHOD_DOWNLOAD);
        job.sendAs = json.optString("send_as", Prefs.SEND_FILE);
        job.uploadAfter = json.optBoolean("upload_after", true);
        job.deleteLocal = json.optBoolean("delete_local", true);
        job.stage = json.optString("stage", QUEUED);
        job.name = json.optString("name", "");
        job.kind = json.optString("kind", "document");
        job.size = json.optLong("size", 0L);
        job.done = json.optLong("done", 0L);
        job.uploaded = json.optLong("uploaded", 0L);
        job.fileId = json.optInt("file_id", 0);
        job.remoteFileId = json.optString("remote_file_id", "");
        job.path = json.optString("path", "");
        job.caption = json.optString("caption", "");
        job.durationSec = json.optLong("duration", 0L);
        job.width = json.optInt("width", 0);
        job.height = json.optInt("height", 0);
        job.error = json.optString("error", "");
        job.note = json.optString("note", "");
        job.created = json.optLong("created", 0L);
        job.updated = json.optLong("updated", 0L);
        job.attempts = json.optInt("attempts", 0);
        job.onlyKinds = json.optString("only_kinds", "");
        job.minSize = json.optLong("min_size", 0L);
        job.maxSize = json.optLong("max_size", 0L);
        job.skipDuplicates = json.optBoolean("skip_duplicates", true);
        job.protectedContent = json.optBoolean("protected_content", false);
        //: A job that was running when the app died comes back as queued — the
        //: engine picks it up again instead of leaving it stuck on "downloading".
        if (job.isActive()) {
            job.stage = QUEUED;
        }
        return job;
    }
}
