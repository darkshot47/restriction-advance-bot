package com.vmore.app;

import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import org.drinkless.tdlib.Client;
import org.drinkless.tdlib.TdApi;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Direct mode: a real Telegram session living **on the phone** (TDLib).
 *
 * Once the user logs in here, private downloads ride Telegram → phone and
 * uploads ride phone → Telegram — the Render host moves zero media bytes,
 * which is exactly the owner's bandwidth requirement ("user download kare ya
 * upload kare, uska data lage").  Everything falls back to the server flow
 * when direct mode is not ready, so nothing ever breaks.
 *
 * Callers talk to {@link #get(Context)}; every method is non-blocking except
 * the two {@code *Blocking} helpers the foreground service uses.
 */
public final class TdDirect {

    // --------------------------------------------------------------------- //

    /** A finished call: the TDLib object, or a readable error. */
    public interface ResultCallback {
        void onOk(TdApi.Object object);
        void onError(String message);
    }

    /** Byte progress for downloads and uploads alike. */
    public interface Progress {
        void onBytes(long done, long total);
    }

    /** The login screen watches the authorization state machine. */
    public interface Listener {
        /** state: init | parameters | phone | code | password | ready | closed | error */
        void onState(String state, String detail);
    }

    /** What a t.me message link resolves to — the media there is to move.
     *  Extends {@link TdApi.Object} only so it can ride the generic callback. */
    public static final class Resolved extends TdApi.Object {
        public String kind = "document";
        public int fileId;
        public long fileSize;
        public long duration;
        public long width;
        public long height;
        public String fileName = "Vmore.bin";
        public String mimeType = "application/octet-stream";
        public String caption = "";
        public long chatId;
        public long messageId;

        @Override
        public int getConstructor() {
            return -1;
        }
    }

    // --------------------------------------------------------------------- //

    private static volatile TdDirect instance;

    public static TdDirect get(Context context) {
        TdDirect value = instance;
        if (value == null) {
            synchronized (TdDirect.class) {
                value = instance;
                if (value == null) {
                    value = new TdDirect(context.getApplicationContext());
                    instance = value;
                }
            }
        }
        return value;
    }

    private final Context app;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<Integer, FileWatch> downloads = new ConcurrentHashMap<>();
    private final Map<Long, SendWatch> sends = new ConcurrentHashMap<>();

    private volatile Client client;
    private volatile boolean nativeOk = true;
    private volatile boolean ready = false;
    private volatile String authState = "init";
    private volatile long botChatId = 0;
    private volatile Listener listener;

    private TdDirect(Context context) {
        app = context.getApplicationContext();
        try {
            Client.execute(new TdApi.SetLogVerbosityLevel(1));
        } catch (UnsatisfiedLinkError e) {
            //: A build without the native library (emulator ABI, a local javac
            //: check) still compiles and runs — direct mode just says no.
            nativeOk = false;
        } catch (Throwable e) {
            nativeOk = false;
        }
    }

    public boolean nativeAvailable() {
        return nativeOk;
    }

    public boolean isReady() {
        return ready;
    }

    public String authState() {
        return authState;
    }

    // ── lifecycle & login ─────────────────────────────────────────────────

    /** Idempotent: create the client once, re-create after a closed session. */
    public void start(Listener auth) {
        if (auth != null) {
            listener = auth;
        }
        if (!nativeOk) {
            tell("error", "this build has no Telegram engine (no libtdjni)");
            return;
        }
        if (client == null) {
            client = Client.create(this::handleUpdate, null, null);
            authState = "parameters";
        }
        tell(authState, null);
    }

    public void stopListening() {
        listener = null;
    }

    private void tell(final String state, final String detail) {
        final Listener auth = listener;
        if (auth != null) {
            main.post(() -> auth.onState(state, detail));
        }
    }

    private void handleUpdate(TdApi.Object object) {
        if (object instanceof TdApi.UpdateAuthorizationState) {
            onAuthorizationState(((TdApi.UpdateAuthorizationState) object).authorizationState);
        } else if (object instanceof TdApi.UpdateFile) {
            TdApi.File file = ((TdApi.UpdateFile) object).file;
            FileWatch watch = downloads.get(file.id);
            if (watch != null) {
                watch.onFile(file);
            }
        } else if (object instanceof TdApi.UpdateMessageSendSucceeded) {
            TdApi.UpdateMessageSendSucceeded update = (TdApi.UpdateMessageSendSucceeded) object;
            SendWatch watch = sends.remove(update.oldMessageId);
            if (watch != null) {
                watch.finishOk(update.message);
            }
        } else if (object instanceof TdApi.UpdateMessageSendFailed) {
            TdApi.UpdateMessageSendFailed update = (TdApi.UpdateMessageSendFailed) object;
            SendWatch watch = sends.remove(update.oldMessageId);
            if (watch != null) {
                watch.finishError(update.error != null ? update.error.message : "send failed");
            }
        }
    }

    private void onAuthorizationState(TdApi.AuthorizationState state) {
        if (state instanceof TdApi.AuthorizationStateWaitTdlibParameters) {
            authState = "parameters";
            sendParameters();
        } else if (state instanceof TdApi.AuthorizationStateWaitPhoneNumber) {
            authState = "phone";
            tell("phone", null);
        } else if (state instanceof TdApi.AuthorizationStateWaitCode) {
            authState = "code";
            tell("code", null);
        } else if (state instanceof TdApi.AuthorizationStateWaitPassword) {
            authState = "password";
            tell("password",
                    ((TdApi.AuthorizationStateWaitPassword) state).passwordHint);
        } else if (state instanceof TdApi.AuthorizationStateReady) {
            ready = true;
            authState = "ready";
            tell("ready", null);
        } else if (state instanceof TdApi.AuthorizationStateClosing) {
            authState = "closed";
        } else if (state instanceof TdApi.AuthorizationStateClosed) {
            ready = false;
            authState = "closed";
            client = null;
            tell("closed", null);
        }
    }

    private void sendParameters() {
        if (client == null) {
            return;
        }
        int apiId = Prefs.tdApiId(app);
        String apiHash = Prefs.tdApiHash(app);
        if (apiId == 0 || apiHash.isEmpty()) {
            tell("error", "the server did not provide the Telegram app credentials yet");
            return;
        }
        java.io.File dir = new java.io.File(app.getFilesDir(), "td");
        //: TDLib wants an existing directory and throws otherwise.
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        client.send(new TdApi.SetTdlibParameters(
                false, dir.getAbsolutePath(), dir.getAbsolutePath(), new byte[0],
                true, true, true, false,
                apiId, apiHash, "en", Build.MODEL,
                Build.VERSION.RELEASE, "Vmore " + Api.VERSION), object -> {
            if (object instanceof TdApi.Error) {
                tell("error", ((TdApi.Error) object).message);
            }
        });
    }

    public void submitPhone(String phone) {
        sendOrError(new TdApi.SetAuthenticationPhoneNumber(phone.trim(), null));
    }

    public void submitCode(String code) {
        sendOrError(new TdApi.CheckAuthenticationCode(code.trim()));
    }

    public void submitPassword(String password) {
        sendOrError(new TdApi.CheckAuthenticationPassword(password));
    }

    /** Full sign-out of the on-phone Telegram session (keeps the bot token). */
    public void logout() {
        ready = false;
        botChatId = 0;
        sendOrError(new TdApi.LogOut());
    }

    private void sendOrError(TdApi.Function<?> query) {
        Client current = client;
        if (current == null) {
            tell("error", "the Telegram engine is not running");
            return;
        }
        current.send(query, object -> {
            if (object instanceof TdApi.Error) {
                tell("error", ((TdApi.Error) object).message);
            }
        });
    }

    // ── link resolution ───────────────────────────────────────────────────

    /** Resolve a t.me message link into the media descriptor (metadata only). */
    public void resolve(String link, ResultCallback callback) {
        if (client == null) {
            callback.onError("the Telegram engine is not running");
            return;
        }
        client.send(new TdApi.GetMessageLinkInfo(link), object -> {
            if (object instanceof TdApi.Error) {
                callback.onError(((TdApi.Error) object).message);
                return;
            }
            TdApi.MessageLinkInfo info = (TdApi.MessageLinkInfo) object;
            Resolved resolved = toResolved(info.message);
            if (resolved == null) {
                callback.onError("that link has no downloadable media");
                return;
            }
            callback.onOk(resolved);
        });
    }

    /** Blocking variant for the foreground service (45 s ceiling). */
    public Resolved resolveBlocking(String link) {
        final Object lock = new Object();
        final Resolved[] holder = new Resolved[1];
        final String[] error = new String[1];
        resolve(link, new ResultCallback() {
            @Override
            public void onOk(TdApi.Object object) {
                synchronized (lock) {
                    holder[0] = (Resolved) object;
                    lock.notifyAll();
                }
            }

            @Override
            public void onError(String message) {
                synchronized (lock) {
                    error[0] = message;
                    lock.notifyAll();
                }
            }
        });
        long deadline = System.currentTimeMillis() + 45_000;
        synchronized (lock) {
            while (holder[0] == null && error[0] == null
                    && System.currentTimeMillis() < deadline) {
                try {
                    lock.wait(250);
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    error[0] = "interrupted";
                    break;
                }
            }
        }
        if (error[0] != null) {
            throw new RuntimeException(error[0]);
        }
        if (holder[0] == null) {
            throw new RuntimeException("Telegram did not answer in time");
        }
        return holder[0];
    }

    // ── downloads (Telegram → phone) ──────────────────────────────────────

    /**
     * Download {@code fileId} to TDLib's files directory, reporting progress.
     * TDLib resumes interrupted downloads natively — pausing re-calls this.
     */
    public void startDownload(int fileId, Progress progress, ResultCallback callback) {
        Client current = client;
        if (current == null) {
            callback.onError("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.DownloadFile(fileId, 32, 0, 0, false), object -> {
            if (object instanceof TdApi.Error) {
                callback.onError(((TdApi.Error) object).message);
                return;
            }
            TdApi.File file = (TdApi.File) object;
            if (file.local != null && file.local.isDownloadingCompleted
                    && file.local.path != null && !file.local.path.isEmpty()) {
                callback.onOk(new LocalResult(file.local.path));
                return;
            }
            FileWatch watch = new FileWatch(fileId, progress, callback, false);
            downloads.put(fileId, watch);
        });
    }

    /** Stop feeding a download (Pause) or throw it away (Stop). */
    public void cancelDownload(int fileId) {
        FileWatch watch = downloads.remove(fileId);
        if (watch != null) {
            watch.finishError("cancelled");
        }
        Client current = client;
        if (current != null) {
            current.send(new TdApi.CancelDownloadFile(fileId, false), object -> {
            });
        }
    }

    /** Blocking variant for the service loop: returns the completed path. */
    public String downloadBlocking(final int fileId, final Progress progress,
                                   final AtomicBoolean cancelled) {
        final Object lock = new Object();
        final String[] result = new String[2];   // [0]=path, [1]=error
        startDownload(fileId, progress, new ResultCallback() {
            @Override
            public void onOk(TdApi.Object object) {
                synchronized (lock) {
                    result[0] = ((LocalResult) object).path;
                    lock.notifyAll();
                }
            }

            @Override
            public void onError(String message) {
                synchronized (lock) {
                    result[1] = message;
                    lock.notifyAll();
                }
            }
        });
        while (true) {
            synchronized (lock) {
                if (result[0] != null || result[1] != null) {
                    break;
                }
                try {
                    lock.wait(300);
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    result[1] = "interrupted";
                    break;
                }
            }
            if (cancelled != null && cancelled.get()) {
                cancelDownload(fileId);
            }
        }
        if (result[0] == null) {
            throw new RuntimeException(result[1] == null ? "download failed" : result[1]);
        }
        return result[0];
    }

    // ── uploads (phone → Telegram) ────────────────────────────────────────

    /** The bot's chat id, resolved once through the phone's own session. */
    public void botChat(ResultCallback callback) {
        if (botChatId != 0) {
            callback.onOk(new ChatResult(botChatId));
            return;
        }
        String username = Prefs.botUsername(app);
        if (username.isEmpty()) {
            callback.onError("the bot username is not known — open the app info screen once");
            return;
        }
        Client current = client;
        if (current == null) {
            callback.onError("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.SearchPublicChat(username), object -> {
            if (object instanceof TdApi.Error) {
                callback.onError(((TdApi.Error) object).message);
                return;
            }
            botChatId = ((TdApi.Chat) object).id;
            callback.onOk(new ChatResult(botChatId));
        });
    }

    /**
     * Send a media file to {@code chatId} with upload progress — the whole
     * byte stream leaves straight from the phone, so this costs the user's
     * own data and the server nothing at all.
     */
    public void sendMedia(final long chatId, final String path, final String kind,
                          final String caption, final int durationSec, final int width,
                          final int height, final Progress progress,
                          final ResultCallback callback) {
        Client current = client;
        if (current == null) {
            callback.onError("the Telegram engine is not running");
            return;
        }
        TdApi.InputMessageContent content = buildContent(path, kind, caption,
                durationSec, width, height);
        if (content == null) {
            callback.onError("no such file: " + path);
            return;
        }
        current.send(new TdApi.SendMessage(chatId, null, null, sendOptions(), null, content),
                object -> {
                    if (object instanceof TdApi.Error) {
                        callback.onError(((TdApi.Error) object).message);
                        return;
                    }
                    TdApi.Message message = (TdApi.Message) object;
                    TdApi.File file = mediaFileOf(message);
                    if (file == null) {
                        callback.onOk(message);
                        return;
                    }
                    SendWatch watch = new SendWatch(message.id, file.id,
                            new java.io.File(path).length(), progress, callback);
                    sends.put(message.id, watch);
                    downloads.put(file.id, watch.progressWatch());
                });
    }

    /** Convenient: send to the bot chat the way the server-mode upload does. */
    public void sendMediaToBot(final String path, final String kind, final String caption,
                               final int durationSec, final int width, final int height,
                               final Progress progress, final ResultCallback callback) {
        botChat(new ResultCallback() {
            @Override
            public void onOk(TdApi.Object object) {
                long chatId = ((ChatResult) object).chatId;
                sendMedia(chatId, path, kind, caption, durationSec, width, height,
                        progress, callback);
            }

            @Override
            public void onError(String message) {
                callback.onError(message);
            }
        });
    }

    /**
     * Zero-byte re-send: Telegram moves the message server-side, so an
     * *untouched* download can be sent back without either side transferring
     * the media again — the strongest form of "no new data".
     */
    public void forwardToBot(final long fromChatId, final long messageId,
                             final ResultCallback callback) {
        botChat(new ResultCallback() {
            @Override
            public void onOk(TdApi.Object object) {
                long chatId = ((ChatResult) object).chatId;
                Client current = client;
                if (current == null) {
                    callback.onError("the Telegram engine is not running");
                    return;
                }
                current.send(new TdApi.ForwardMessages(chatId, null, fromChatId,
                        new long[]{messageId}, sendOptions(), true, false), object2 -> {
                    if (object2 instanceof TdApi.Error) {
                        callback.onError(((TdApi.Error) object2).message);
                        return;
                    }
                    callback.onOk(object2);
                });
            }

            @Override
            public void onError(String message) {
                callback.onError(message);
            }
        });
    }

    // ── internals ─────────────────────────────────────────────────────────

    private static TdApi.MessageSendOptions sendOptions() {
        return new TdApi.MessageSendOptions(null, false, true, false, false,
                0, false, null, 0, 0, false);
    }

    private static TdApi.InputMessageContent buildContent(String path, String kind,
                                                          String caption,
                                                          int durationSec, int width,
                                                          int height) {
        java.io.File local = new java.io.File(path);
        if (!local.exists()) {
            return null;
        }
        TdApi.InputFileLocal input = new TdApi.InputFileLocal(local.getAbsolutePath());
        TdApi.FormattedText text = new TdApi.FormattedText(
                caption == null ? "" : caption, null);
        switch (kind == null ? "" : kind) {
            case "video":
                return new TdApi.InputMessageVideo(
                        new TdApi.InputVideo(input, null, null, 0, null,
                                durationSec, width, height, true),
                        text, false, null, false);
            case "photo":
                return new TdApi.InputMessagePhoto(
                        new TdApi.InputPhoto(input, null, null, null, 0, 0),
                        text, false, null, false);
            case "audio":
                return new TdApi.InputMessageAudio(
                        new TdApi.InputAudio(input, null, durationSec, "", ""), text);
            default:
                return new TdApi.InputMessageDocument(
                        new TdApi.InputDocument(input, null, false), text);
        }
    }

    /** The media descriptor of a message (null for text messages). */
    private static Resolved toResolved(TdApi.Message message) {
        if (message == null || message.content == null) {
            return null;
        }
        Resolved resolved = new Resolved();
        resolved.chatId = message.chatId;
        resolved.messageId = message.id;
        TdApi.MessageContent content = message.content;
        TdApi.File file = null;
        if (content instanceof TdApi.MessageVideo) {
            TdApi.MessageVideo media = (TdApi.MessageVideo) content;
            resolved.kind = "video";
            file = media.video.video;
            resolved.fileName = media.video.fileName == null || media.video.fileName.isEmpty()
                    ? "video.mp4" : media.video.fileName;
            resolved.mimeType = media.video.mimeType == null ? "video/mp4" : media.video.mimeType;
            resolved.duration = media.video.duration;
            resolved.width = media.video.width;
            resolved.height = media.video.height;
        } else if (content instanceof TdApi.MessageAudio) {
            TdApi.MessageAudio media = (TdApi.MessageAudio) content;
            resolved.kind = "audio";
            file = media.audio.audio;
            resolved.fileName = media.audio.fileName == null || media.audio.fileName.isEmpty()
                    ? "audio.mp3" : media.audio.fileName;
            resolved.mimeType = media.audio.mimeType == null ? "audio/mpeg" : media.audio.mimeType;
            resolved.duration = media.audio.duration;
        } else if (content instanceof TdApi.MessagePhoto) {
            TdApi.MessagePhoto media = (TdApi.MessagePhoto) content;
            TdApi.PhotoSize[] sizes = media.photo.sizes;
            if (sizes == null || sizes.length == 0) {
                return null;
            }
            TdApi.PhotoSize biggest = sizes[sizes.length - 1];
            resolved.kind = "photo";
            file = biggest.photo;
            resolved.fileName = "photo.jpg";
            resolved.mimeType = "image/jpeg";
            resolved.width = biggest.width;
            resolved.height = biggest.height;
        } else if (content instanceof TdApi.MessageDocument) {
            TdApi.MessageDocument media = (TdApi.MessageDocument) content;
            resolved.kind = "document";
            file = media.document.document;
            resolved.fileName = media.document.fileName == null
                    || media.document.fileName.isEmpty()
                    ? "document.bin" : media.document.fileName;
            resolved.mimeType = media.document.mimeType == null
                    ? "application/octet-stream" : media.document.mimeType;
        } else {
            return null;
        }
        resolved.fileId = file.id;
        resolved.fileSize = file.size > 0 ? file.size : file.expectedSize;
        resolved.caption = captionOf(content);
        return resolved;
    }

    private static String captionOf(TdApi.MessageContent content) {
        TdApi.FormattedText text = null;
        if (content instanceof TdApi.MessageVideo) {
            text = ((TdApi.MessageVideo) content).caption;
        } else if (content instanceof TdApi.MessageAudio) {
            text = ((TdApi.MessageAudio) content).caption;
        } else if (content instanceof TdApi.MessagePhoto) {
            text = ((TdApi.MessagePhoto) content).caption;
        } else if (content instanceof TdApi.MessageDocument) {
            text = ((TdApi.MessageDocument) content).caption;
        }
        return text == null || text.text == null ? "" : text.text;
    }

    /** The media file inside a message we just sent (for upload progress). */
    private static TdApi.File mediaFileOf(TdApi.Message message) {
        if (message == null || message.content == null) {
            return null;
        }
        TdApi.MessageContent content = message.content;
        if (content instanceof TdApi.MessageVideo) {
            return ((TdApi.MessageVideo) content).video.video;
        }
        if (content instanceof TdApi.MessageAudio) {
            return ((TdApi.MessageAudio) content).audio.audio;
        }
        if (content instanceof TdApi.MessagePhoto) {
            TdApi.PhotoSize[] sizes = ((TdApi.MessagePhoto) content).photo.sizes;
            return sizes == null || sizes.length == 0 ? null : sizes[sizes.length - 1].photo;
        }
        if (content instanceof TdApi.MessageDocument) {
            return ((TdApi.MessageDocument) content).document.document;
        }
        return null;
    }

    /** A download finished or errored — the watch holds both. */
    private static final class FileWatch {
        final int fileId;
        final Progress progress;
        final ResultCallback callback;
        final boolean upload;
        volatile boolean done;

        FileWatch(int fileId, Progress progress, ResultCallback callback, boolean upload) {
            this.fileId = fileId;
            this.progress = progress;
            this.callback = callback;
            this.upload = upload;
        }

        void onFile(TdApi.File file) {
            if (done) {
                return;
            }
            if (upload) {
                long doneBytes = file.remote == null ? 0 : file.remote.uploadedSize;
                if (progress != null) {
                    progress.onBytes(doneBytes, file.size > 0 ? file.size : file.expectedSize);
                }
                return;   // uploads finish via UpdateMessageSendSucceeded
            }
            long total = file.expectedSize > 0 ? file.expectedSize : file.size;
            long doneBytes = file.local == null ? 0 : file.local.downloadedSize;
            if (progress != null) {
                progress.onBytes(doneBytes, total);
            }
            if (file.local != null && file.local.isDownloadingCompleted
                    && file.local.path != null && !file.local.path.isEmpty()) {
                done = true;
                callback.onOk(new LocalResult(file.local.path));
            }
        }

        void finishError(String message) {
            if (!done) {
                done = true;
                callback.onError(message);
            }
        }
    }

    /** An in-flight send: progress from the file updates, done from the send updates. */
    private final class SendWatch {
        final long messageId;
        final int fileId;
        final long expected;
        final Progress progress;
        final ResultCallback callback;
        volatile boolean done;

        SendWatch(long messageId, int fileId, long expected, Progress progress,
                  ResultCallback callback) {
            this.messageId = messageId;
            this.fileId = fileId;
            this.expected = expected;
            this.progress = progress;
            this.callback = callback;
        }

        FileWatch progressWatch() {
            return new FileWatch(fileId, new Progress() {
                @Override
                public void onBytes(long doneBytes, long total) {
                    if (progress != null) {
                        progress.onBytes(doneBytes, total > 0 ? total : expected);
                    }
                }
            }, null, true);
        }

        void finishOk(TdApi.Message message) {
            if (!done) {
                done = true;
                downloads.remove(fileId);
                callback.onOk(message);
            }
        }

        void finishError(String message) {
            if (!done) {
                done = true;
                downloads.remove(fileId);
                callback.onError(message);
            }
        }
    }

    /** Callback value: a completed local path. */
    private static final class LocalResult extends TdApi.Object {
        final String path;

        LocalResult(String path) {
            this.path = path;
        }

        @Override
        public int getConstructor() {
            return -1;
        }
    }

    /** Callback value: a resolved chat id. */
    private static final class ChatResult extends TdApi.Object {
        final long chatId;

        ChatResult(long chatId) {
            this.chatId = chatId;
        }

        @Override
        public int getConstructor() {
            return -1;
        }
    }
}
