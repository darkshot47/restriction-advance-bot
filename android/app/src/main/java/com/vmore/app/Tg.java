package com.vmore.app;

import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import org.drinkless.tdlib.Client;
import org.drinkless.tdlib.TdApi;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * The Telegram engine, running on the phone.
 *
 * Vmore talks to Telegram directly through TDLib: one session for the user's own
 * account, created here and stored in the app's private folder. There is no
 * server address, no access token and no middleman — the phone signs in, the
 * phone downloads, the phone uploads.
 *
 * Everything asynchronous is posted back on the main thread, so screens can use
 * the callbacks directly; the queue engine uses the {@code *Blocking} helpers
 * from its own worker thread.
 */
public final class Tg {

    /** Result of one call: a value, or a message worth showing to the user. */
    public interface Cb<T> {
        void ok(T value);

        void fail(String message);
    }

    public interface Progress {
        void onBytes(long done, long total);
    }

    /** State machine of the sign-in screen. */
    public interface Listener {
        void onState(String state, String detail);
    }

    public static final String STATE_NONE = "none";
    public static final String STATE_CREDENTIALS = "credentials";
    public static final String STATE_PARAMETERS = "parameters";
    public static final String STATE_PHONE = "phone";
    public static final String STATE_CODE = "code";
    public static final String STATE_PASSWORD = "password";
    public static final String STATE_READY = "ready";
    public static final String STATE_CLOSED = "closed";
    public static final String STATE_ERROR = "error";

    /** The signed-in account. */
    public static final class Account {
        public long id;
        public String name = "";
        public String username = "";
        public String phone = "";
    }

    /** One row of the chat list. */
    public static final class Chat {
        public long id;
        public String title = "";
        public String type = "private";
        public int unread;
        public long lastDate;
        public boolean pinned;

        public int icon() {
            switch (type) {
                case "channel":
                    return R.drawable.ic_channel;
                case "group":
                    return R.drawable.ic_group;
                default:
                    return R.drawable.ic_person;
            }
        }
    }

    /** The media behind a message — everything the app needs to move it. */
    public static final class Media {
        public String kind = "document";
        public int fileId;
        public long size;
        public String name = "";
        public String mime = "application/octet-stream";
        public String caption = "";
        public long durationSec;
        public int width;
        public int height;
        public long chatId;
        public long messageId;
        public String chatTitle = "";

        public boolean isVideo() {
            return "video".equals(kind);
        }
    }

    private static volatile Tg instance;

    public static Tg get(Context context) {
        Tg value = instance;
        if (value == null) {
            synchronized (Tg.class) {
                value = instance;
                if (value == null) {
                    value = new Tg(context.getApplicationContext());
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
    private final Map<Long, Chat> chatCache = new ConcurrentHashMap<>();

    private volatile Client client;
    private volatile boolean nativeOk = true;
    private volatile boolean ready;
    private volatile String state = STATE_NONE;
    private volatile Listener listener;
    private volatile Account account;
    private volatile String pendingPhone = "";

    private Tg(Context context) {
        app = context;
        try {
            Client.execute(new TdApi.SetLogVerbosityLevel(1));
        } catch (UnsatisfiedLinkError error) {
            //: A build without libtdjni (an emulator ABI, a plain javac check)
            //: still runs — the screens say the engine is missing.
            nativeOk = false;
        } catch (Throwable error) {
            nativeOk = false;
        }
    }

    public boolean nativeAvailable() {
        return nativeOk;
    }

    public boolean isReady() {
        return ready;
    }

    public String state() {
        return state;
    }

    public Account account() {
        return account;
    }

    // ── lifecycle ─────────────────────────────────────────────────────────

    /** Idempotent: creates the session once and reports the current state. */
    public void start(Listener auth) {
        if (auth != null) {
            listener = auth;
        }
        if (!nativeOk) {
            state = STATE_NONE;
            tell(STATE_NONE, "this build has no Telegram engine");
            return;
        }
        if (!Prefs.hasCredentials(app)) {
            state = STATE_CREDENTIALS;
            tell(STATE_CREDENTIALS, null);
            return;
        }
        if (client == null) {
            try {
                client = Client.create(this::handleUpdate, null, null);
                state = STATE_PARAMETERS;
            } catch (Throwable error) {
                state = STATE_ERROR;
                tell(STATE_ERROR, String.valueOf(error.getMessage()));
                return;
            }
        }
        tell(state, null);
    }

    public void stopListening() {
        listener = null;
    }

    private void tell(final String newState, final String detail) {
        final Listener auth = listener;
        if (auth != null) {
            main.post(() -> auth.onState(newState, detail));
        }
    }

    /**
     * Starts using another account slot: the running session is closed first,
     * the screens go back to the sign-in steps, and the queue keeps its place.
     */
    public void useSlot(int slot) {
        if (slot == Prefs.activeSlot(app)) {
            return;
        }
        closeSession();
        Prefs.setActiveSlot(app, slot);
        pendingPhone = "";
    }

    /** Closes TDLib without touching the queue, history or settings. */
    public void closeSession() {
        ready = false;
        account = null;
        chatCache.clear();
        Client current = client;
        client = null;
        if (current != null) {
            current.send(new TdApi.Close(), object -> {
            });
        }
        state = STATE_NONE;
    }

    /** Called after the user typed the api_id and api_hash for the first time. */
    public void restartWithCredentials() {
        if (client != null) {
            client.send(new TdApi.Close(), object -> {
            });
            client = null;
        }
        ready = false;
        state = STATE_PARAMETERS;
        start(listener);
    }

    public void submitPhone(String phone) {
        pendingPhone = phone == null ? "" : phone.trim();
        sendOrError(new TdApi.SetAuthenticationPhoneNumber(pendingPhone, null));
    }

    public void submitCode(String code) {
        sendOrError(new TdApi.CheckAuthenticationCode(code == null ? "" : code.trim()));
    }

    public void submitPassword(String password) {
        sendOrError(new TdApi.CheckAuthenticationPassword(password == null ? "" : password));
    }

    public void logout() {
        ready = false;
        account = null;
        chatCache.clear();
        Prefs.forgetAvatar(app);
        Prefs.saveProfile(app, "", "");
        sendOrError(new TdApi.LogOut());
    }

    private void sendOrError(TdApi.Function<?> query) {
        Client current = client;
        if (current == null) {
            tell(STATE_ERROR, "the Telegram engine is not running");
            return;
        }
        current.send(query, object -> {
            if (object instanceof TdApi.Error) {
                tell(STATE_ERROR, friendly(((TdApi.Error) object).message));
            }
        });
    }

    private void handleUpdate(TdApi.Object object) {
        if (object instanceof TdApi.UpdateAuthorizationState) {
            onAuthorizationState(((TdApi.UpdateAuthorizationState) object).authorizationState);
        } else if (object instanceof TdApi.UpdateNewChat) {
            remember(((TdApi.UpdateNewChat) object).chat);
        } else if (object instanceof TdApi.UpdateChatTitle) {
            TdApi.UpdateChatTitle update = (TdApi.UpdateChatTitle) object;
            Chat cached = chatCache.get(update.chatId);
            if (cached != null) {
                cached.title = update.title;
            }
        } else if (object instanceof TdApi.UpdateChatLastMessage) {
            TdApi.UpdateChatLastMessage update = (TdApi.UpdateChatLastMessage) object;
            Chat cached = chatCache.get(update.chatId);
            if (cached != null && update.lastMessage != null) {
                cached.lastDate = update.lastMessage.date;
            }
        } else if (object instanceof TdApi.UpdateChatPosition) {
            TdApi.UpdateChatPosition update = (TdApi.UpdateChatPosition) object;
            Chat cached = chatCache.get(update.chatId);
            if (cached != null && update.position != null) {
                cached.pinned = update.position.isPinned;
            }
        } else if (object instanceof TdApi.UpdateUser) {
            TdApi.User user = ((TdApi.UpdateUser) object).user;
            if (user != null && account != null && user.id == account.id) {
                loadAvatar(user);
            }
        } else if (object instanceof TdApi.UpdateFile) {
            TdApi.File file = ((TdApi.UpdateFile) object).file;
            FileWatch watch = downloads.get(file.id);
            if (watch != null) {
                watch.onFile(file);
                throttle(watch, file);
            }
        } else if (object instanceof TdApi.UpdateMessageSendSucceeded) {
            TdApi.UpdateMessageSendSucceeded update = (TdApi.UpdateMessageSendSucceeded) object;
            SendWatch watch = sends.remove(update.oldMessageId);
            if (watch != null) {
                watch.finish(update.message.id, null);
            }
        } else if (object instanceof TdApi.UpdateMessageSendFailed) {
            TdApi.UpdateMessageSendFailed update = (TdApi.UpdateMessageSendFailed) object;
            SendWatch watch = sends.remove(update.oldMessageId);
            if (watch != null) {
                watch.finish(0L, update.error == null ? "Telegram refused the upload"
                        : friendly(update.error.message));
            }
        }
    }

    private void remember(TdApi.Chat chat) {
        if (chat == null) {
            return;
        }
        Chat cached = chatCache.get(chat.id);
        if (cached == null) {
            cached = new Chat();
            chatCache.put(chat.id, cached);
        }
        cached.id = chat.id;
        cached.title = chat.title == null ? "" : chat.title;
        cached.type = chatType(chat.type);
        cached.unread = chat.unreadCount;
        if (chat.lastMessage != null) {
            cached.lastDate = chat.lastMessage.date;
        }
        for (TdApi.ChatPosition position : chat.positions) {
            if (position != null && position.isPinned) {
                cached.pinned = true;
            }
        }
    }

    private static String chatType(TdApi.ChatType type) {
        if (type instanceof TdApi.ChatTypeSupergroup) {
            return ((TdApi.ChatTypeSupergroup) type).isChannel ? "channel" : "group";
        }
        if (type instanceof TdApi.ChatTypeBasicGroup) {
            return "group";
        }
        return "private";
    }

    private void onAuthorizationState(TdApi.AuthorizationState auth) {
        if (auth instanceof TdApi.AuthorizationStateWaitTdlibParameters) {
            state = STATE_PARAMETERS;
            sendParameters();
        } else if (auth instanceof TdApi.AuthorizationStateWaitPhoneNumber) {
            state = STATE_PHONE;
            tell(STATE_PHONE, null);
        } else if (auth instanceof TdApi.AuthorizationStateWaitCode) {
            state = STATE_CODE;
            tell(STATE_CODE, null);
        } else if (auth instanceof TdApi.AuthorizationStateWaitPassword) {
            state = STATE_PASSWORD;
            tell(STATE_PASSWORD, ((TdApi.AuthorizationStateWaitPassword) auth).passwordHint);
        } else if (auth instanceof TdApi.AuthorizationStateReady) {
            ready = true;
            state = STATE_READY;
            loadAccount();
            tell(STATE_READY, null);
        } else if (auth instanceof TdApi.AuthorizationStateClosing) {
            state = STATE_CLOSED;
        } else if (auth instanceof TdApi.AuthorizationStateClosed) {
            ready = false;
            client = null;
            state = STATE_CLOSED;
            tell(STATE_CLOSED, null);
        } else if (auth instanceof TdApi.AuthorizationStateWaitOtherDeviceConfirmation) {
            state = STATE_PHONE;
            tell(STATE_PHONE, "confirm this login inside Telegram");
        }
    }

    private void sendParameters() {
        Client current = client;
        if (current == null) {
            return;
        }
        int apiId = Prefs.apiId(app);
        String apiHash = Prefs.apiHash(app);
        if (apiId == 0 || apiHash.isEmpty()) {
            state = STATE_CREDENTIALS;
            tell(STATE_CREDENTIALS, null);
            return;
        }
        //: Each account slot keeps its own TDLib databases, which is what makes
        //: switching accounts safe and instant.
        File dir = new File(app.getFilesDir(), "telegram_" + Prefs.activeSlot(app));
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        current.send(new TdApi.SetTdlibParameters(
                        false, dir.getAbsolutePath(), dir.getAbsolutePath(), new byte[0],
                        true, true, true, false,
                        apiId, apiHash, "en", Build.MODEL,
                        Build.VERSION.RELEASE, "Vmore " + Vmore.VERSION),
                object -> {
                    if (object instanceof TdApi.Error) {
                        state = STATE_ERROR;
                        tell(STATE_ERROR, friendly(((TdApi.Error) object).message));
                    }
                });
    }

    private void loadAccount() {
        Client current = client;
        if (current == null) {
            return;
        }
        current.send(new TdApi.GetMe(), object -> {
            if (!(object instanceof TdApi.User)) {
                return;
            }
            TdApi.User user = (TdApi.User) object;
            Account info = new Account();
            info.id = user.id;
            String first = user.firstName == null ? "" : user.firstName;
            String last = user.lastName == null ? "" : user.lastName;
            info.name = (first + " " + last).trim();
            info.username = firstUsername(user.usernames);
            info.phone = user.phoneNumber == null ? pendingPhone : user.phoneNumber;
            account = info;
            Prefs.saveAccount(app, info.id, info.name, info.phone);
            Prefs.saveProfile(app, info.name, info.username);
            loadAvatar(user);
        });
    }

    /**
     * The profile picture, kept on the phone.
     *
     * It is fetched once and never asked for again: the copy stays in the app's
     * private folder and the header simply reads that file, so opening the app
     * does not touch the network for the avatar at all.  Only a photo Telegram
     * itself replaced is downloaded again.
     */
    private void loadAvatar(TdApi.User user) {
        TdApi.ProfilePhoto photo = user.profilePhoto;
        TdApi.File picture = photo == null ? null : photo.big;
        if (picture == null || picture.id == 0) {
            Prefs.forgetAvatar(app);
            return;
        }
        String known = Prefs.avatarPath(app);
        File saved = known == null || known.isEmpty() ? null : new File(known);
        if (Prefs.avatarFileId(app) == picture.id && saved != null && saved.exists()) {
            return;
        }
        if (isComplete(picture)) {
            saveAvatar(picture.local.path, picture.id);
            return;
        }
        downloadFile(picture.id, null, new Cb<Integer>() {
            @Override
            public void ok(Integer value) {
                String path = localPath(value);
                if (path != null) {
                    saveAvatar(path, value);
                }
                releaseDownload(value);
            }

            @Override
            public void fail(String message) {
                //: A missing avatar is not worth an error on screen; the header
                //: falls back to the account initial.
            }
        });
    }

    private void saveAvatar(String sourcePath, int fileId) {
        File copied = LocalFiles.copy(sourcePath, LocalFiles.avatarFile(app));
        if (copied != null) {
            Prefs.saveAvatar(app, copied.getAbsolutePath(), fileId);
        }
    }

    /**
     * Blocks the queue's own worker thread until this session can work.
     *
     * A queue that is started by the system (or by the notification) wakes the
     * app in a fresh process, where TDLib has not been created yet.  Waiting
     * here — instead of failing every job on the spot — is what makes a batch
     * survive the app being closed.
     */
    public boolean awaitReady(long timeoutMillis) {
        if (ready) {
            return true;
        }
        if (client == null && nativeOk && Prefs.hasCredentials(app)) {
            start(null);
        }
        long deadline = System.currentTimeMillis() + Math.max(1000L, timeoutMillis);
        while (System.currentTimeMillis() < deadline) {
            if (ready) {
                return true;
            }
            if (STATE_ERROR.equals(state) || STATE_NONE.equals(state)
                    || STATE_CREDENTIALS.equals(state)) {
                return false;
            }
            try {
                Thread.sleep(250L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return ready;
    }

    /** Plain words for why the queue cannot run right now. */
    public String blockedReason() {
        if (!nativeOk) {
            return "this build has no Telegram engine";
        }
        if (!Prefs.hasCredentials(app)) {
            return "open the app and sign in with your Telegram account";
        }
        if (STATE_ERROR.equals(state)) {
            return "the Telegram session could not start. Open the app once and check it";
        }
        return "the Telegram session is not ready yet. Open the app once, then start again";
    }

    private static String firstUsername(TdApi.Usernames usernames) {
        if (usernames == null || usernames.activeUsernames == null
                || usernames.activeUsernames.length == 0) {
            return "";
        }
        return usernames.activeUsernames[0];
    }

    // ── chats ─────────────────────────────────────────────────────────────

    /** The chat list, newest first, pinned chats on top. */
    public void loadChats(int limit, Cb<List<Chat>> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.LoadChats(new TdApi.ChatListMain(), limit), object -> {
            if (object instanceof TdApi.Error) {
                //: An empty account answers with "chat list is not loaded";
                //: that is not a failure, GetChats below simply returns few rows.
            }
            current.send(new TdApi.GetChats(new TdApi.ChatListMain(), limit), chats -> {
                if (chats instanceof TdApi.Error) {
                    callback.fail(friendly(((TdApi.Error) chats).message));
                    return;
                }
                TdApi.Chats list = (TdApi.Chats) chats;
                long[] ids = list.chatIds == null ? new long[0] : list.chatIds;
                List<Chat> rows = Collections.synchronizedList(new ArrayList<>());
                if (ids.length == 0) {
                    post(callback, rows);
                    return;
                }
                final int[] pending = {ids.length};
                for (long chatId : ids) {
                    Chat cached = chatCache.get(chatId);
                    if (cached != null && cached.lastDate > 0) {
                        rows.add(cached);
                        if (--pending[0] == 0) {
                            post(callback, sort(rows));
                        }
                        continue;
                    }
                    current.send(new TdApi.GetChat(chatId), chatObject -> {
                        if (chatObject instanceof TdApi.Chat) {
                            remember((TdApi.Chat) chatObject);
                            Chat row = chatCache.get(chatId);
                            if (row != null) {
                                rows.add(row);
                            }
                        }
                        if (--pending[0] == 0) {
                            post(callback, sort(rows));
                        }
                    });
                }
            });
        });
    }

    private List<Chat> sort(List<Chat> rows) {
        rows.sort(new Comparator<Chat>() {
            @Override
            public int compare(Chat left, Chat right) {
                if (left.pinned != right.pinned) {
                    return left.pinned ? -1 : 1;
                }
                return Long.compare(right.lastDate, left.lastDate);
            }
        });
        return rows;
    }

    private <T> void post(Cb<T> callback, T value) {
        main.post(() -> callback.ok(value));
    }

    /** One chat's details (title, type) by id. */
    public void chat(long chatId, Cb<Chat> callback) {
        Chat cached = chatCache.get(chatId);
        if (cached != null && !cached.title.isEmpty()) {
            callback.ok(cached);
            return;
        }
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.GetChat(chatId), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail(friendly(((TdApi.Error) object).message));
                return;
            }
            TdApi.Chat chat = (TdApi.Chat) object;
            remember(chat);
            Chat row = chatCache.get(chat.id);
            if (row == null) {
                callback.fail("that chat could not be read");
                return;
            }
            callback.ok(row);
        });
    }

    /** Find a chat by its public @username (used when the user types one). */
    public void findPublicChat(String username, Cb<Chat> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.SearchPublicChat(username), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail("Telegram could not find @" + username);
                return;
            }
            TdApi.Chat chat = (TdApi.Chat) object;
            remember(chat);
            Chat row = chatCache.get(chat.id);
            if (row == null) {
                callback.fail("that chat could not be read");
                return;
            }
            callback.ok(row);
        });
    }

    // ── resolving links ───────────────────────────────────────────────────

    /**
     * Turn a parsed link into media the queue can move.
     *
     * Public links are resolved by Telegram itself; private t.me/c links are
     * turned into a chat id right here and read with the user's own session; an
     * invite link is inspected (and joined when needed) first.
     */
    public void resolve(TgLink link, Cb<Media> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        if (link.messageId <= 0) {
            callback.fail("that link has no message in it");
            return;
        }
        if (!link.inviteHash.isEmpty()) {
            current.send(new TdApi.CheckChatInviteLink(inviteUrl(link.inviteHash)), object -> {
                if (object instanceof TdApi.ChatInviteLinkInfo) {
                    long chatId = ((TdApi.ChatInviteLinkInfo) object).chatId;
                    if (chatId != 0L) {
                        message(current, chatId, link.messageId, callback);
                        return;
                    }
                }
                current.send(new TdApi.JoinChatByInviteLink(inviteUrl(link.inviteHash)), joined -> {
                    if (joined instanceof TdApi.ChatJoinResultSuccess) {
                        long chatId = ((TdApi.ChatJoinResultSuccess) joined).chatId;
                        message(current, chatId, link.messageId, callback);
                    } else {
                        callback.fail("that invite link cannot be used to read the message");
                    }
                });
            });
            return;
        }
        //: Both t.me/name/123 and t.me/c/… links are resolved by Telegram
        //: itself first: it is the only reader that knows whether this account
        //: may see the message, and it answers even for chats the account has
        //: never opened.  The chat-id path below stays as the fallback.
        String canonical = canonicalLink(link);
        if (canonical != null) {
            current.send(new TdApi.GetMessageLinkInfo(canonical), object -> {
                Media media = object instanceof TdApi.MessageLinkInfo
                        ? toMedia(((TdApi.MessageLinkInfo) object).message) : null;
                if (media != null && media.fileId != 0) {
                    withChatTitle(current, media, callback);
                    return;
                }
                byChat(current, link, callback);
            });
            return;
        }
        byChat(current, link, callback);
    }

    /** The public https form of a link, or null when there is none. */
    private static String canonicalLink(TgLink link) {
        if (link.messageId <= 0) {
            return null;
        }
        if (link.username != null && !link.username.isEmpty()) {
            return "https://t.me/" + link.username + "/" + link.messageId;
        }
        if (link.privateLink && link.internalId > 0) {
            return "https://t.me/c/" + link.internalId + "/" + link.messageId;
        }
        return null;
    }

    /** Fallback: go through the chat itself and read the message. */
    private void byChat(Client current, TgLink link, Cb<Media> callback) {
        if (link.privateLink) {
            long chatId = link.chatId != 0L ? link.chatId : link.privateChatId();
            if (chatId == 0L) {
                callback.fail("that private link does not carry a chat number");
                return;
            }
            message(current, chatId, link.messageId, callback);
            return;
        }
        if (link.chatId != 0L) {
            message(current, link.chatId, link.messageId, callback);
            return;
        }
        if (!link.username.isEmpty()) {
            current.send(new TdApi.SearchPublicChat(link.username), found -> {
                if (found instanceof TdApi.Error) {
                    callback.fail("Telegram could not open that link. Check that this "
                            + "account can read the chat and that the message exists.");
                    return;
                }
                message(current, ((TdApi.Chat) found).id, link.messageId, callback);
            });
            return;
        }
        callback.fail("that link does not name a chat");
    }

    private static String inviteUrl(String hash) {
        return hash.startsWith("http") ? hash : "https://t.me/+" + hash;
    }

    private void message(Client current, long chatId, long messageId, Cb<Media> callback) {
        current.send(new TdApi.GetMessage(chatId, messageId), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail(friendly(((TdApi.Error) object).message)
                        + " (message " + messageId + ")");
                return;
            }
            Media media = toMedia((TdApi.Message) object);
            if (media == null) {
                callback.fail("message " + messageId + " has no file or video in it");
                return;
            }
            withChatTitle(current, media, callback);
        });
    }

    private void withChatTitle(Client current, Media media, Cb<Media> callback) {
        if (media.chatTitle != null && !media.chatTitle.isEmpty()) {
            callback.ok(media);
            return;
        }
        current.send(new TdApi.GetChat(media.chatId), object -> {
            if (object instanceof TdApi.Chat) {
                remember((TdApi.Chat) object);
                Chat row = chatCache.get(media.chatId);
                if (row != null) {
                    media.chatTitle = row.title;
                }
            }
            callback.ok(media);
        });
    }

    /** Recent media messages of a chat, newest first — "scan this chat". */
    public void scanChat(long chatId, int limit, Cb<List<Media>> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.GetChatHistory(chatId, 0L, 0, limit, false), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail(friendly(((TdApi.Error) object).message));
                return;
            }
            TdApi.Messages messages = (TdApi.Messages) object;
            List<Media> found = new ArrayList<>();
            if (messages.messages != null) {
                for (TdApi.Message message : messages.messages) {
                    Media media = toMedia(message);
                    if (media != null) {
                        found.add(media);
                    }
                }
            }
            chat(chatId, new Cb<Chat>() {
                @Override
                public void ok(Chat value) {
                    for (Media media : found) {
                        if (media.chatTitle.isEmpty()) {
                            media.chatTitle = value.title;
                        }
                    }
                    callback.ok(found);
                }

                @Override
                public void fail(String message) {
                    callback.ok(found);
                }
            });
        });
    }

    // ── media mapping ─────────────────────────────────────────────────────

    private static Media toMedia(TdApi.Message message) {
        if (message == null || message.content == null) {
            return null;
        }
        Media media = new Media();
        media.chatId = message.chatId;
        media.messageId = message.id;
        TdApi.MessageContent content = message.content;
        TdApi.File file = null;
        if (content instanceof TdApi.MessageVideo) {
            TdApi.Video video = ((TdApi.MessageVideo) content).video;
            media.kind = "video";
            file = video.video;
            media.name = video.fileName;
            media.mime = video.mimeType;
            media.durationSec = video.duration;
            media.width = video.width;
            media.height = video.height;
        } else if (content instanceof TdApi.MessageAnimation) {
            TdApi.Animation animation = ((TdApi.MessageAnimation) content).animation;
            media.kind = "video";
            file = animation.animation;
            media.name = animation.fileName;
            media.mime = animation.mimeType;
            media.durationSec = animation.duration;
            media.width = animation.width;
            media.height = animation.height;
        } else if (content instanceof TdApi.MessageVideoNote) {
            TdApi.VideoNote note = ((TdApi.MessageVideoNote) content).videoNote;
            media.kind = "video";
            file = note.video;
            media.name = "video_note.mp4";
            media.mime = "video/mp4";
            media.durationSec = note.duration;
            media.width = note.length;
            media.height = note.length;
        } else if (content instanceof TdApi.MessageAudio) {
            TdApi.Audio audio = ((TdApi.MessageAudio) content).audio;
            media.kind = "audio";
            file = audio.audio;
            media.name = audio.fileName;
            media.mime = audio.mimeType;
            media.durationSec = audio.duration;
        } else if (content instanceof TdApi.MessageVoiceNote) {
            TdApi.VoiceNote note = ((TdApi.MessageVoiceNote) content).voiceNote;
            media.kind = "audio";
            file = note.voice;
            media.name = "voice_note.ogg";
            media.mime = note.mimeType;
            media.durationSec = note.duration;
        } else if (content instanceof TdApi.MessagePhoto) {
            TdApi.Photo photo = ((TdApi.MessagePhoto) content).photo;
            TdApi.PhotoSize[] sizes = photo.sizes;
            if (sizes == null || sizes.length == 0) {
                return null;
            }
            TdApi.PhotoSize biggest = sizes[sizes.length - 1];
            media.kind = "photo";
            file = biggest.photo;
            media.name = "photo.jpg";
            media.mime = "image/jpeg";
            media.width = biggest.width;
            media.height = biggest.height;
        } else if (content instanceof TdApi.MessageDocument) {
            TdApi.Document document = ((TdApi.MessageDocument) content).document;
            media.kind = "document";
            file = document.document;
            media.name = document.fileName;
            media.mime = document.mimeType;
        } else {
            return null;
        }
        media.fileId = file.id;
        media.size = file.size > 0 ? file.size : file.expectedSize;
        media.caption = captionOf(content);
        if (media.name == null || media.name.isEmpty()) {
            media.name = "vmore_" + media.messageId + guessExtension(media.mime);
        }
        media.name = Format.safeName(media.name, "vmore_" + media.messageId);
        media.mime = media.mime == null || media.mime.isEmpty()
                ? "application/octet-stream" : media.mime;
        return media;
    }

    private static String guessExtension(String mime) {
        if (mime == null) {
            return "";
        }
        switch (mime) {
            case "video/mp4":
                return ".mp4";
            case "image/jpeg":
                return ".jpg";
            case "image/png":
                return ".png";
            case "audio/mpeg":
                return ".mp3";
            case "audio/ogg":
                return ".ogg";
            default:
                return "";
        }
    }

    private static String captionOf(TdApi.MessageContent content) {
        TdApi.FormattedText text = null;
        if (content instanceof TdApi.MessageVideo) {
            text = ((TdApi.MessageVideo) content).caption;
        } else if (content instanceof TdApi.MessageAnimation) {
            text = ((TdApi.MessageAnimation) content).caption;
        } else if (content instanceof TdApi.MessageAudio) {
            text = ((TdApi.MessageAudio) content).caption;
        } else if (content instanceof TdApi.MessageVoiceNote) {
            text = ((TdApi.MessageVoiceNote) content).caption;
        } else if (content instanceof TdApi.MessagePhoto) {
            text = ((TdApi.MessagePhoto) content).caption;
        } else if (content instanceof TdApi.MessageDocument) {
            text = ((TdApi.MessageDocument) content).caption;
        }
        return text == null || text.text == null ? "" : text.text;
    }

    // ── downloads ─────────────────────────────────────────────────────────

    public void downloadFile(final int fileId, final Progress progress, final Cb<Integer> done) {
        Client current = client;
        if (current == null) {
            done.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.DownloadFile(fileId, 32, 0, 0, false), object -> {
            if (object instanceof TdApi.Error) {
                done.fail(friendly(((TdApi.Error) object).message));
                return;
            }
            TdApi.File file = (TdApi.File) object;
            FileWatch watch = new FileWatch(fileId, progress, done);
            if (isComplete(file)) {
                watch.path = file.local.path;
                watch.done = true;
                done.ok(fileId);
                downloads.put(fileId, watch);
                return;
            }
            downloads.put(fileId, watch);
        });
    }

    public void cancelDownload(int fileId) {
        FileWatch watch = downloads.remove(fileId);
        if (watch != null) {
            watch.finishError("cancelled");
        }
        Client current = client;
        if (current != null) {
            current.send(new TdApi.CancelDownloadFile(fileId, true), object -> {
            });
        }
    }

    /** Remove Telegram's own cached copy of a file (after an upload finished). */
    public void forgetFile(int fileId) {
        Client current = client;
        if (current != null && fileId != 0) {
            current.send(new TdApi.DeleteFile(fileId), object -> {
            });
        }
    }

    /** Forget a finished download's watch — the file itself stays on disk. */
    public void releaseDownload(int fileId) {
        downloads.remove(fileId);
    }

    /** The completed path of a download, or null while it is still running. */
    public String localPath(int fileId) {
        FileWatch watch = downloads.get(fileId);
        if (watch != null && watch.path != null && !watch.path.isEmpty()) {
            return watch.path;
        }
        return null;
    }

    /**
     * Holds a download to the user's cap.
     *
     * The whole trick is that a cancelled download is not a lost download:
     * Telegram keeps the part it has and carries on when the file is requested
     * again, so a cap is a pause loop rather than a smaller transfer.  Uploads
     * have no such switch, so the cap covers downloads.
     */
    private void throttle(FileWatch watch, TdApi.File file) {
        long cap = Prefs.speedLimitKbps(app) * 1024L;
        if (cap <= 0 || watch.done || watch.waiting) {
            return;
        }
        long now = System.currentTimeMillis();
        if (watch.anchorAt == 0L) {
            watch.anchorAt = now;
            watch.anchorBytes = watch.bytesSeen;
            return;
        }
        long allowed = watch.anchorBytes + cap * (now - watch.anchorAt) / 1000L;
        if (watch.bytesSeen <= allowed) {
            return;
        }
        long over = watch.bytesSeen - allowed;
        long pause = Math.min(4000L, Math.max(250L, over * 1000L / cap));
        watch.waiting = true;
        watch.anchorAt = now + pause;
        watch.anchorBytes = watch.bytesSeen;
        Client current = client;
        if (current != null) {
            current.send(new TdApi.CancelDownloadFile(watch.fileId, false),
                    ignored -> {
                    }, ignored -> {
                    });
        }
        main.postDelayed(() -> {
            watch.waiting = false;
            if (watch.done) {
                return;
            }
            Client restart = client;
            if (restart != null) {
                restart.send(new TdApi.DownloadFile(watch.fileId, 32, 0, 0, false),
                        ignored -> {
                        }, ignored -> {
                        });
            }
        }, pause);
    }

    private static boolean isComplete(TdApi.File file) {
        return file != null && file.local != null && file.local.isDownloadingCompleted
                && file.local.path != null && !file.local.path.isEmpty();
    }

    // ── uploads ───────────────────────────────────────────────────────────

    /**
     * Send a local file to a chat, reporting upload progress. The bytes leave
     * from this phone, so the transfer uses the user's own data.
     */
    public void sendMedia(long chatId, String path, String kind, String caption,
                          long durationSec, int width, int height, String sendAs,
                          Progress progress, Cb<Long> callback) {
        sendMedia(chatId, path, kind, caption, durationSec, width, height, sendAs, null,
                progress, callback);
    }

    /** Same send, with an optional cover image for a video. */
    public void sendMedia(long chatId, String path, String kind, String caption,
                          long durationSec, int width, int height, String sendAs,
                          String thumbPath, Progress progress, Cb<Long> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        TdApi.InputMessageContent content = buildContent(path, kind, caption, durationSec,
                width, height, sendAs, thumbPath);
        if (content == null) {
            callback.fail("the file is not on the phone any more");
            return;
        }
        current.send(new TdApi.SendMessage(chatId, null, null, sendOptions(), null, content),
                object -> {
                    if (object instanceof TdApi.Error) {
                        callback.fail(friendly(((TdApi.Error) object).message));
                        return;
                    }
                    TdApi.Message message = (TdApi.Message) object;
                    TdApi.File file = mediaFileOf(message);
                    long length = new File(path).length();
                    if (file == null) {
                        callback.ok(message.id);
                        return;
                    }
                    SendWatch watch = new SendWatch(message.id, file.id, length, progress,
                            callback);
                    sends.put(message.id, watch);
                    //: Uploads have no pause switch, so the cap covers the
                    //: download side only; the watch here is progress only.
                    downloads.put(file.id, watch.progressWatch());
                });
    }

    /** Let Telegram move an existing message: no bytes cross the phone. */
    public void forward(long destChatId, long fromChatId, long messageId, Cb<Long> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.ForwardMessages(destChatId, null, fromChatId,
                new long[]{messageId}, sendOptions(), false, false), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail(friendly(((TdApi.Error) object).message));
                return;
            }
            TdApi.Messages messages = (TdApi.Messages) object;
            long sent = messages.messages != null && messages.messages.length > 0
                    ? messages.messages[0].id : 0L;
            callback.ok(sent);
        });
    }

    public void deleteMessage(long chatId, long messageId, Cb<Boolean> callback) {
        Client current = client;
        if (current == null) {
            callback.fail("the Telegram engine is not running");
            return;
        }
        current.send(new TdApi.DeleteMessages(chatId, new long[]{messageId}, true), object -> {
            if (object instanceof TdApi.Error) {
                callback.fail(friendly(((TdApi.Error) object).message));
                return;
            }
            callback.ok(true);
        });
    }

    private static TdApi.MessageSendOptions sendOptions() {
        return new TdApi.MessageSendOptions(null, false, true, false, false,
                0, false, null, 0, 0, false);
    }

    private static TdApi.InputMessageContent buildContent(String path, String kind,
                                                          String caption, long durationSec,
                                                          int width, int height, String sendAs,
                                                          String thumbPath) {
        File local = new File(path);
        if (!local.exists()) {
            return null;
        }
        TdApi.InputFileLocal input = new TdApi.InputFileLocal(local.getAbsolutePath());
        TdApi.FormattedText text = new TdApi.FormattedText(
                caption == null ? "" : caption, null);
        String mode = sendAs == null ? Prefs.SEND_FILE : sendAs;
        String mediaKind = kind == null ? "document" : kind;
        int duration = (int) Math.max(0, durationSec);
        if ("audio".equals(mediaKind)) {
            return new TdApi.InputMessageAudio(
                    new TdApi.InputAudio(input, null, duration, "", ""), text);
        }
        boolean asVideo = "video".equals(mediaKind)
                || (Prefs.SEND_VIDEO.equals(mode) && !"photo".equals(mediaKind));
        boolean asPhoto = "photo".equals(mediaKind) || Prefs.SEND_PHOTO.equals(mode);
        if (asPhoto && !Prefs.SEND_FILE.equals(mode)) {
            return new TdApi.InputMessagePhoto(
                    new TdApi.InputPhoto(input, null, null, null, width, height),
                    text, false, null, false);
        }
        if (asVideo) {
            return new TdApi.InputMessageVideo(
                    new TdApi.InputVideo(input, thumbnail(thumbPath), null, 0, null, duration,
                            width, height, true),
                    text, false, null, false);
        }
        return new TdApi.InputMessageDocument(
                new TdApi.InputDocument(input, null, false), text);
    }

    /** Turns a local cover file into the thumbnail Telegram expects. */
    private static TdApi.InputThumbnail thumbnail(String path) {
        if (path == null || path.isEmpty()) {
            return null;
        }
        File file = new File(path);
        if (!file.exists()) {
            return null;
        }
        int[] size = MediaUtils.imageSize(file);
        if (size[0] <= 0 || size[1] <= 0) {
            return null;
        }
        return new TdApi.InputThumbnail(new TdApi.InputFileLocal(file.getAbsolutePath()),
                size[0], size[1]);
    }

    private static TdApi.File mediaFileOf(TdApi.Message message) {
        if (message == null || message.content == null) {
            return null;
        }
        TdApi.MessageContent content = message.content;
        if (content instanceof TdApi.MessageVideo) {
            return ((TdApi.MessageVideo) content).video.video;
        }
        if (content instanceof TdApi.MessageAnimation) {
            return ((TdApi.MessageAnimation) content).animation.animation;
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

    // ── blocking helpers for the queue worker ─────────────────────────────

    public Media resolveBlocking(final TgLink link, final AtomicBoolean cancelled)
            throws Exception {
        final Sync<Media> sync = new Sync<>();
        resolve(link, sync);
        Media media = sync.await(90_000, cancelled);
        if (media == null) {
            throw new Exception(sync.error == null ? "Telegram did not answer" : sync.error);
        }
        return media;
    }

    public String downloadBlocking(final int fileId, final Progress progress,
                                   final AtomicBoolean cancelled) throws Exception {
        final Sync<Integer> sync = new Sync<>();
        downloadFile(fileId, progress, sync);
        Integer result = sync.await(0, cancelled);
        FileWatch watch = downloads.get(fileId);
        if (result == null) {
            throw new Exception(sync.error == null ? "download failed" : sync.error);
        }
        //: The finished local path always lives on the watch, whether the file
        //: was already cached or arrived just now.
        String path = watch == null ? null : watch.path;
        if (path == null) {
            throw new Exception("the download did not produce a file");
        }
        return path;
    }

    public long sendBlocking(QJob job, Progress progress, AtomicBoolean cancelled)
            throws Exception {
        final Sync<Long> sync = new Sync<>();
        sendMedia(job.destChatId, job.path, job.kind, job.caption, job.durationSec,
                job.width, job.height, job.sendAs, progress, sync);
        Long result = sync.await(0, cancelled);
        if (result == null) {
            throw new Exception(sync.error == null ? "upload failed" : sync.error);
        }
        return result;
    }

    public long forwardBlocking(QJob job, AtomicBoolean cancelled) throws Exception {
        final Sync<Long> sync = new Sync<>();
        forward(job.destChatId, job.chatId, job.messageId, sync);
        Long result = sync.await(120_000, cancelled);
        if (result == null) {
            throw new Exception(sync.error == null ? "the forward failed" : sync.error);
        }
        return result;
    }

    public List<Media> scanBlocking(long chatId, int limit) throws Exception {
        final Sync<List<Media>> sync = new Sync<>();
        scanChat(chatId, limit, sync);
        List<Media> result = sync.await(120_000, null);
        if (result == null) {
            throw new Exception(sync.error == null ? "the chat could not be read" : sync.error);
        }
        return result;
    }

    public Chat chatBlocking(long chatId) throws Exception {
        final Sync<Chat> sync = new Sync<>();
        chat(chatId, sync);
        Chat result = sync.await(30_000, null);
        if (result == null) {
            throw new Exception(sync.error == null ? "the chat could not be read" : sync.error);
        }
        return result;
    }

    // ── small pieces ──────────────────────────────────────────────────────

    private static final class FileWatch {
        final int fileId;
        final Progress progress;
        final Cb<Integer> callback;
        volatile boolean done;
        volatile String path;
        //: The cap is enforced by stopping the download for a moment and
        //: starting it again: Telegram keeps the bytes it already has.
        volatile long anchorAt;
        volatile long anchorBytes;
        volatile long bytesSeen;
        volatile boolean waiting;

        FileWatch(int fileId, Progress progress, Cb<Integer> callback) {
            this.fileId = fileId;
            this.progress = progress;
            this.callback = callback;
        }

        void onFile(TdApi.File file) {
            if (done) {
                return;
            }
            long total = file.expectedSize > 0 ? file.expectedSize : file.size;
            long written = file.local == null ? 0 : file.local.downloadedSize;
            if (progress != null) {
                progress.onBytes(written, total);
            }
            bytesSeen = written;
            if (isComplete(file)) {
                done = true;
                path = file.local.path;
                if (callback != null) {
                    callback.ok(fileId);
                }
            }
        }

        void finishError(String message) {
            if (!done) {
                done = true;
                if (callback != null) {
                    callback.fail(message);
                }
            }
        }
    }

    private final class SendWatch {
        final long messageId;
        final int fileId;
        final long expected;
        final Progress progress;
        final Cb<Long> callback;
        volatile boolean done;

        SendWatch(long messageId, int fileId, long expected, Progress progress,
                  Cb<Long> callback) {
            this.messageId = messageId;
            this.fileId = fileId;
            this.expected = expected;
            this.progress = progress;
            this.callback = callback;
        }

        FileWatch progressWatch() {
            return new FileWatch(fileId, new Progress() {
                @Override
                public void onBytes(long done, long total) {
                    if (progress != null) {
                        progress.onBytes(done, total > 0 ? total : expected);
                    }
                }
            }, null);
        }

        void finish(long realMessageId, String error) {
            if (done) {
                return;
            }
            done = true;
            downloads.remove(fileId);
            if (error != null) {
                callback.fail(error);
            } else {
                callback.ok(realMessageId);
            }
        }
    }

    /** One await-able result for the worker thread. */
    private static final class Sync<T> implements Cb<T> {
        volatile T value;
        volatile String error;
        private boolean done;

        @Override
        public void ok(T result) {
            value = result;
            synchronized (this) {
                done = true;
                notifyAll();
            }
        }

        @Override
        public void fail(String message) {
            error = message;
            synchronized (this) {
                done = true;
                notifyAll();
            }
        }

        T await(long timeoutMillis, AtomicBoolean cancelled) {
            long deadline = timeoutMillis > 0 ? System.currentTimeMillis() + timeoutMillis : 0L;
            while (true) {
                synchronized (this) {
                    if (done) {
                        return value;
                    }
                    if (cancelled != null && cancelled.get()) {
                        return null;
                    }
                    long wait = 300L;
                    if (deadline > 0) {
                        long left = deadline - System.currentTimeMillis();
                        if (left <= 0) {
                            if (error == null) {
                                error = "Telegram did not answer in time";
                            }
                            return null;
                        }
                        wait = Math.min(wait, left);
                    }
                    try {
                        wait(wait);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        error = "interrupted";
                        return null;
                    }
                }
            }
        }
    }

    private static String friendly(String message) {
        String text = message == null ? "Telegram refused that request" : message.trim();
        String lower = text.toLowerCase(Locale.US);
        if (lower.contains("message not found") || lower.contains("message_not_found")) {
            return "That message does not exist any more";
        }
        if (lower.contains("chat not found") || lower.contains("chat_not_found")
                || lower.contains("username not occupied")) {
            return "Telegram cannot see that chat with this account. Open the chat once "
                    + "in Telegram, then try again";
        }
        if (lower.contains("not participant") || lower.contains("not a member")
                || lower.contains("channel private") || lower.contains("not enough rights")
                || lower.contains("have no access") || lower.contains("forbidden")
                || lower.contains("kicked")) {
            return "This Telegram account is not allowed to read that content. Join the "
                    + "chat with this account first";
        }
        if (lower.contains("too many requests") || lower.contains("flood")
                || lower.contains("retry after")) {
            return "Telegram asked to slow down (flood wait). The queue tries again by itself";
        }
        if (lower.contains("file is too big") || lower.contains("file_too_big")) {
            return "That file is too big for this chat";
        }
        if (lower.contains("timeout") || lower.contains("timed out")
                || lower.contains("time out")) {
            return "Telegram did not answer in time. Check the connection and retry";
        }
        if (lower.contains("network") || lower.contains("connection")
                || lower.contains("unreachable")) {
            return "No connection to Telegram right now";
        }
        return text;
    }
}
