package com.vmore.app;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Everything Vmore remembers between launches.
 *
 * There is no server and no access token in this app: the login is the user's
 * own Telegram account (kept by TDLib on this phone), and every setting below
 * lives in this one preferences file.
 */
public final class Prefs {

    private static final String FILE = "vmore";

    private static final String KEY_API_ID = "tg_api_id";
    private static final String KEY_API_HASH = "tg_api_hash";
    private static final String KEY_PHONE = "tg_phone";
    private static final String KEY_NAME = "tg_name";
    private static final String KEY_USER_ID = "tg_user_id";

    private static final String KEY_DEST_ID = "dest_chat_id";
    private static final String KEY_DEST_TITLE = "dest_title";
    private static final String KEY_ASK_DEST = "ask_destination";

    private static final String KEY_AUTO_UPLOAD = "auto_upload";
    private static final String KEY_AUTO_DELETE = "auto_delete_local";
    private static final String KEY_SEND_AS = "send_as";
    private static final String KEY_CAPTION = "caption_template";
    private static final String KEY_KEEP_SCREEN = "keep_screen";
    private static final String KEY_SPEED = "playback_speed";
    private static final String KEY_SETUP_DONE = "setup_done";
    private static final String KEY_NIGHT = "night_skin";
    private static final String KEY_USERNAME = "tg_username";
    private static final String KEY_AVATAR = "tg_avatar_path";
    private static final String KEY_AVATAR_ID = "tg_avatar_file";

    /** Data saving, scheduling, filters, skin, lock and the account slots. */
    private static final String KEY_WIFI_ONLY = "wifi_only";
    private static final String KEY_CHARGING_ONLY = "charging_only";
    private static final String KEY_SKIN_MODE = "skin_mode";
    private static final String KEY_SCHEDULE_AT = "schedule_at";
    private static final String KEY_SCHEDULE_DAILY = "schedule_daily";
    private static final String KEY_FILTER_KINDS = "filter_kinds";
    private static final String KEY_FILTER_MIN = "filter_min_size";
    private static final String KEY_FILTER_MAX = "filter_max_size";
    private static final String KEY_LOCK_HASH = "lock_hash";
    private static final String KEY_LOCK_SALT = "lock_salt";
    private static final String KEY_SLOT = "account_slot";
    private static final String KEY_SLOTS = "account_slots";
    /** The TDLib folder of one slot; a new sign-in gets a new name. */
    private static final String KEY_SESSION = "session_dir";
    /** The developer card, the same for every account on this phone. */
    private static final String KEY_DEV_NAME = "dev_name";
    private static final String KEY_DEV_BIO = "dev_bio";
    private static final String KEY_DEV_AVATAR = "dev_avatar";
    private static final String KEY_DEV_FILE = "dev_file";
    /** The built-in key that last worked, so the next sign-in starts with it. */
    private static final String KEY_GOOD_KEY = "good_key_id";
    private static final String KEY_GOOD_HASH = "good_key_hash";
    public static final int MAX_SLOTS = 3;

    /** Send mode: keep the original file, or let Telegram show it inline. */
    public static final String SEND_FILE = "document";
    public static final String SEND_VIDEO = "video";
    public static final String SEND_PHOTO = "photo";

    private Prefs() {
    }

    private static volatile boolean migrated;

    private static SharedPreferences prefs(Context context) {
        SharedPreferences store = context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
        if (!migrated) {
            migrated = true;
            migrate(store);
        }
        return store;
    }

    /**
     * The first account lives in slot 1.  Settings written by an older build
     * used the bare keys; they are copied into slot 1 once, so an update never
     * asks anybody to sign in again.
     */
    private static void migrate(SharedPreferences store) {
        if (store.getInt(KEY_SLOTS, 0) != 0) {
            return;
        }
        SharedPreferences.Editor edit = store.edit().putInt(KEY_SLOT, 1).putInt(KEY_SLOTS, 1);
        if (store.contains(KEY_API_ID)) {
            edit.putInt(KEY_API_ID + "_s1", store.getInt(KEY_API_ID, 0));
        }
        copy(store, edit, KEY_API_HASH, 1);
        copy(store, edit, KEY_PHONE, 1);
        copy(store, edit, KEY_NAME, 1);
        copy(store, edit, KEY_USERNAME, 1);
        copy(store, edit, KEY_AVATAR, 1);
        edit.putLong(KEY_USER_ID + "_s1", store.getLong(KEY_USER_ID, 0L));
        edit.putInt(KEY_AVATAR_ID + "_s1", store.getInt(KEY_AVATAR_ID, 0));
        edit.apply();
    }

    private static void copy(SharedPreferences store, SharedPreferences.Editor edit,
                             String base, int slot) {
        if (store.contains(base)) {
            edit.putString(base + "_s" + slot, store.getString(base, ""));
        }
    }

    /** Which account slot is in use right now. */
    public static int activeSlot(Context context) {
        return Math.max(1, prefs(context).getInt(KEY_SLOT, 1));
    }

    public static int slotCount(Context context) {
        return Math.max(1, prefs(context).getInt(KEY_SLOTS, 1));
    }

    public static void setActiveSlot(Context context, int slot) {
        //: Committed, not applied: the app can be killed the moment the switch
        //: starts, and coming back into the old slot would look like the
        //: switch never happened.
        prefs(context).edit().putInt(KEY_SLOT, Math.max(1, slot)).commit();
    }

    /** Opens one more account slot to sign into. */
    public static int addSlot(Context context) {
        int count = slotCount(context);
        if (count >= MAX_SLOTS) {
            return 0;
        }
        count++;
        prefs(context).edit().putInt(KEY_SLOTS, count).apply();
        return count;
    }

    public static String slotLabel(Context context, int slot) {
        String name = prefs(context).getString(KEY_NAME + "_s" + slot, "");
        String phone = prefs(context).getString(KEY_PHONE + "_s" + slot, "");
        if (!name.isEmpty()) {
            return name;
        }
        return phone.isEmpty() ? "Account " + slot : phone;
    }

    public static boolean slotUsed(Context context, int slot) {
        return prefs(context).getInt(KEY_API_ID + "_s" + slot, 0) != 0;
    }

    /**
     * True when this slot holds an account someone actually signed into.
     *
     * An api_id can survive a sign-out, so it says very little on its own; a
     * name or a number is written only once Telegram has answered with the
     * account, which is the thing worth offering a way back to.
     */
    public static boolean slotHasAccount(Context context, int slot) {
        String name = prefs(context).getString(KEY_NAME + "_s" + slot, "");
        String phone = prefs(context).getString(KEY_PHONE + "_s" + slot, "");
        return (name != null && !name.isEmpty()) || (phone != null && !phone.isEmpty());
    }

    /**
     * The folder this slot's Telegram session lives in.
     *
     * A slot that has never been reset keeps the plain name older builds used,
     * so an update never signs anybody out.  A reset picks a fresh name and the
     * old folder is deleted afterwards, which is why wiping a session can no
     * longer race the session that is still closing.
     */
    public static String sessionDirForSlot(Context context, int slot) {
        String stored = prefs(context).getString(KEY_SESSION + "_s" + slot, "");
        return stored == null || stored.isEmpty() ? "telegram_" + slot : stored;
    }

    public static String sessionDir(Context context) {
        return sessionDirForSlot(context, activeSlot(context));
    }

    /** Reserves a new, empty session folder for the account in use. */
    public static String newSessionDir(Context context) {
        int slot = activeSlot(context);
        String name = "telegram_" + slot + "_" + System.currentTimeMillis();
        //: Committed for the same reason, and one more: the start-up tidy-up
        //: deletes folders no slot claims, so a name that never reached the
        //: disk would get the new session folder deleted under it.
        prefs(context).edit().putString(KEY_SESSION + "_s" + slot, name).commit();
        return name;
    }

    /** Drops the credentials of one slot (used when switching accounts). */
    public static void clearSlot(Context context, int slot) {
        String suffix = "_s" + slot;
        prefs(context).edit()
                .remove(KEY_API_ID + suffix).remove(KEY_API_HASH + suffix)
                .remove(KEY_PHONE + suffix).remove(KEY_NAME + suffix)
                .remove(KEY_USERNAME + suffix).remove(KEY_AVATAR + suffix)
                .remove(KEY_AVATAR_ID + suffix).remove(KEY_USER_ID + suffix)
                .remove(KEY_SESSION + suffix)
                .apply();
    }

    // ------------------------------------------------- Telegram credentials //

    private static String slotKey(Context context, String base) {
        return base + "_s" + activeSlot(context);
    }

    public static int apiId(Context context) {
        return prefs(context).getInt(slotKey(context, KEY_API_ID), 0);
    }

    public static String apiHash(Context context) {
        return prefs(context).getString(KEY_API_HASH + "_s" + activeSlot(context), "");
    }

    public static boolean hasCredentials(Context context) {
        return apiId(context) != 0 && !apiHash(context).isEmpty();
    }

    public static void saveCredentials(Context context, int apiId, String apiHash) {
        prefs(context).edit()
                .putInt(slotKey(context, KEY_API_ID), apiId)
                .putString(slotKey(context, KEY_API_HASH), apiHash == null ? "" : apiHash.trim())
                .apply();
    }

    /** Forgets the stored pair, so the sign-in screen asks for it again. */
    public static void clearCredentials(Context context) {
        prefs(context).edit()
                .remove(slotKey(context, KEY_API_ID))
                .remove(slotKey(context, KEY_API_HASH))
                .apply();
    }

    // ------------------------------------------------------------ account //

    public static String phone(Context context) {
        return prefs(context).getString(slotKey(context, KEY_PHONE), "");
    }

    public static String accountName(Context context) {
        return prefs(context).getString(slotKey(context, KEY_NAME), "");
    }

    public static long accountId(Context context) {
        return prefs(context).getLong(slotKey(context, KEY_USER_ID), 0L);
    }

    public static void saveAccount(Context context, long userId, String name, String phone) {
        prefs(context).edit()
                .putLong(slotKey(context, KEY_USER_ID), userId)
                .putString(slotKey(context, KEY_NAME), name == null ? "" : name)
                .putString(slotKey(context, KEY_PHONE), phone == null ? "" : phone)
                .putBoolean(KEY_SETUP_DONE, true)
                .apply();
    }

    public static boolean setupDone(Context context) {
        return prefs(context).getBoolean(KEY_SETUP_DONE, false);
    }

    public static String accountUsername(Context context) {
        return prefs(context).getString(slotKey(context, KEY_USERNAME), "");
    }

    public static void saveProfile(Context context, String name, String username) {
        prefs(context).edit()
                .putString(slotKey(context, KEY_NAME), name == null ? "" : name)
                .putString(slotKey(context, KEY_USERNAME), username == null ? "" : username)
                .apply();
    }

    // ------------------------------------------------------- the developer //

    public static String developerName(Context context) {
        return prefs(context).getString(KEY_DEV_NAME, "");
    }

    public static String developerBio(Context context) {
        return prefs(context).getString(KEY_DEV_BIO, "");
    }

    public static String developerAvatar(Context context) {
        return prefs(context).getString(KEY_DEV_AVATAR, "");
    }

    public static int developerAvatarFile(Context context) {
        return prefs(context).getInt(KEY_DEV_FILE, 0);
    }

    public static void saveDeveloper(Context context, String name, String bio,
                                     String avatarPath, int fileId) {
        prefs(context).edit()
                .putString(KEY_DEV_NAME, name == null ? "" : name)
                .putString(KEY_DEV_BIO, bio == null ? "" : bio)
                .putString(KEY_DEV_AVATAR, avatarPath == null ? "" : avatarPath)
                .putInt(KEY_DEV_FILE, fileId)
                .apply();
    }

    // ------------------------------------------------------ the built-in key //

    public static int lastGoodKeyId(Context context) {
        return prefs(context).getInt(KEY_GOOD_KEY, 0);
    }

    public static String lastGoodKeyHash(Context context) {
        return prefs(context).getString(KEY_GOOD_HASH, "");
    }

    public static void saveLastGoodKey(Context context, int apiId, String apiHash) {
        prefs(context).edit()
                .putInt(KEY_GOOD_KEY, apiId)
                .putString(KEY_GOOD_HASH, apiHash == null ? "" : apiHash)
                .apply();
    }

    /** Where the profile picture was copied to, once, on this phone. */
    public static String avatarPath(Context context) {
        return prefs(context).getString(slotKey(context, KEY_AVATAR), "");
    }

    public static int avatarFileId(Context context) {
        return prefs(context).getInt(slotKey(context, KEY_AVATAR_ID), 0);
    }

    public static void saveAvatar(Context context, String path, int fileId) {
        prefs(context).edit()
                .putString(slotKey(context, KEY_AVATAR), path == null ? "" : path)
                .putInt(slotKey(context, KEY_AVATAR_ID), fileId)
                .apply();
    }

    public static void forgetAvatar(Context context) {
        prefs(context).edit()
                .remove(slotKey(context, KEY_AVATAR))
                .remove(slotKey(context, KEY_AVATAR_ID))
                .apply();
    }

    // ---------------------------------------------------------------- skin //

    /** 0 = day, 1 = night, 2 = automatic (night between 18:00 and 06:00). */
    public static int skinMode(Context context) {
        return prefs(context).getInt(KEY_SKIN_MODE, 0);
    }

    public static void setSkinMode(Context context, int mode) {
        prefs(context).edit().putInt(KEY_SKIN_MODE, Math.max(0, Math.min(2, mode))).apply();
    }

    /** The plain old switch, kept so older callers keep working. */
    public static boolean night(Context context) {
        return skinMode(context) == 1;
    }

    public static void setNight(Context context, boolean value) {
        setSkinMode(context, value ? 1 : 0);
    }

    // ----------------------------------------------------------- data save //

    /** Only download and upload while the phone is on Wi-Fi. */
    public static boolean wifiOnly(Context context) {
        return prefs(context).getBoolean(KEY_WIFI_ONLY, false);
    }

    public static void setWifiOnly(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_WIFI_ONLY, value).apply();
    }

    /** Only work while the phone is charging — kind to the battery. */
    /**
     * The download cap in kilobytes per second; 0 means the full speed.
     * Telegram resumes a cancelled download, so the cap only slows it down.
     */
    public static int speedLimitKbps(Context context) {
        return prefs(context).getInt("speed_limit_kbps", 0);
    }

    public static void setSpeedLimitKbps(Context context, int value) {
        prefs(context).edit().putInt("speed_limit_kbps", Math.max(0, value)).apply();
    }

    public static boolean chargingOnly(Context context) {
        return prefs(context).getBoolean(KEY_CHARGING_ONLY, false);
    }

    public static void setChargingOnly(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_CHARGING_ONLY, value).apply();
    }

    // ------------------------------------------------------------- schedule //

    public static long scheduleAt(Context context) {
        return prefs(context).getLong(KEY_SCHEDULE_AT, 0L);
    }

    public static void setScheduleAt(Context context, long when) {
        prefs(context).edit().putLong(KEY_SCHEDULE_AT, when).apply();
    }

    /**
     * Set when the user starts the queue by hand: the start time is then
     * skipped once, because a tap means now.
     */
    public static boolean startNow(Context context) {
        return prefs(context).getBoolean("start_now", false);
    }

    public static void setStartNow(Context context, boolean value) {
        prefs(context).edit().putBoolean("start_now", value).apply();
    }

    public static boolean scheduleDaily(Context context) {
        return prefs(context).getBoolean(KEY_SCHEDULE_DAILY, false);
    }

    public static void setScheduleDaily(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_SCHEDULE_DAILY, value).apply();
    }

    // -------------------------------------------------------------- filters //

    /** Which kinds a batch keeps: empty means everything. */
    public static String filterKinds(Context context) {
        return prefs(context).getString(KEY_FILTER_KINDS, "");
    }

    public static void setFilterKinds(Context context, String kinds) {
        prefs(context).edit().putString(KEY_FILTER_KINDS, kinds == null ? "" : kinds).apply();
    }

    public static long filterMinSize(Context context) {
        return prefs(context).getLong(KEY_FILTER_MIN, 0L);
    }

    public static void setFilterMinSize(Context context, long bytes) {
        prefs(context).edit().putLong(KEY_FILTER_MIN, Math.max(0L, bytes)).apply();
    }

    public static long filterMaxSize(Context context) {
        return prefs(context).getLong(KEY_FILTER_MAX, 0L);
    }

    public static void setFilterMaxSize(Context context, long bytes) {
        prefs(context).edit().putLong(KEY_FILTER_MAX, Math.max(0L, bytes)).apply();
    }

    // ------------------------------------------------------------------ lock //

    public static boolean lockEnabled(Context context) {
        return !prefs(context).getString(KEY_LOCK_HASH, "").isEmpty();
    }

    public static String lockHash(Context context) {
        return prefs(context).getString(KEY_LOCK_HASH, "");
    }

    public static String lockSalt(Context context) {
        return prefs(context).getString(KEY_LOCK_SALT, "");
    }

    public static void setLock(Context context, String salt, String hash) {
        prefs(context).edit().putString(KEY_LOCK_SALT, salt).putString(KEY_LOCK_HASH, hash)
                .apply();
    }

    public static void clearLock(Context context) {
        prefs(context).edit().remove(KEY_LOCK_HASH).remove(KEY_LOCK_SALT).apply();
    }

    // ----------------------------------------------------------- transfer //

    /** A link another app shared into Vmore, waiting for the home screen. */
    public static String takePendingShare(Context context) {
        String value = prefs(context).getString("pending_share", "");
        if (value != null && !value.isEmpty()) {
            prefs(context).edit().remove("pending_share").apply();
        }
        return value == null ? "" : value;
    }

    public static void setPendingShare(Context context, String value) {
        prefs(context).edit().putString("pending_share",
                value == null ? "" : value.trim()).apply();
    }

    // -------------------------------------------------------- destination //

    public static long destChatId(Context context) {
        return prefs(context).getLong(KEY_DEST_ID, 0L);
    }

    public static String destTitle(Context context) {
        return prefs(context).getString(KEY_DEST_TITLE, "");
    }

    public static void saveDestination(Context context, long chatId, String title) {
        prefs(context).edit()
                .putLong(KEY_DEST_ID, chatId)
                .putString(KEY_DEST_TITLE, title == null ? "" : title)
                .apply();
    }

    public static boolean askDestination(Context context) {
        return prefs(context).getBoolean(KEY_ASK_DEST, false);
    }

    public static void setAskDestination(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_ASK_DEST, value).apply();
    }

    // ----------------------------------------------------------- behaviour //

    public static boolean autoUpload(Context context) {
        return prefs(context).getBoolean(KEY_AUTO_UPLOAD, true);
    }

    public static void setAutoUpload(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_AUTO_UPLOAD, value).apply();
    }

    /** Delete the phone copy as soon as the file is safely in the chat. */
    public static boolean autoDeleteLocal(Context context) {
        return prefs(context).getBoolean(KEY_AUTO_DELETE, true);
    }

    public static void setAutoDeleteLocal(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_AUTO_DELETE, value).apply();
    }

    public static String sendAs(Context context) {
        return prefs(context).getString(KEY_SEND_AS, SEND_FILE);
    }

    public static void setSendAs(Context context, String value) {
        prefs(context).edit().putString(KEY_SEND_AS, value == null ? SEND_FILE : value).apply();
    }

    public static String captionTemplate(Context context) {
        return prefs(context).getString(KEY_CAPTION, "");
    }

    public static void setCaptionTemplate(Context context, String value) {
        prefs(context).edit().putString(KEY_CAPTION, value == null ? "" : value).apply();
    }

    /** Leave out a file that was uploaded before (same file id and size). */
    public static boolean skipDuplicates(Context context) {
        return prefs(context).getBoolean("skip_duplicates", true);
    }

    public static void setSkipDuplicates(Context context, boolean value) {
        prefs(context).edit().putBoolean("skip_duplicates", value).apply();
    }

    public static boolean keepScreenOn(Context context) {
        return prefs(context).getBoolean(KEY_KEEP_SCREEN, true);
    }

    public static void setKeepScreenOn(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_KEEP_SCREEN, value).apply();
    }

    /** Keep playing the next file of the folder when one ends. */
    public static boolean autoplayNext(Context context) {
        return prefs(context).getBoolean("autoplay_next", true);
    }

    public static void setAutoplayNext(Context context, boolean value) {
        prefs(context).edit().putBoolean("autoplay_next", value).apply();
    }

    public static float playbackSpeed(Context context) {
        return prefs(context).getFloat(KEY_SPEED, 1.0f);
    }

    public static void setPlaybackSpeed(Context context, float value) {
        prefs(context).edit().putFloat(KEY_SPEED, value).apply();
    }
}
