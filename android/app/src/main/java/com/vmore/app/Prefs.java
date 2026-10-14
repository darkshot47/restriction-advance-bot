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

    /** Send mode: keep the original file, or let Telegram show it inline. */
    public static final String SEND_FILE = "document";
    public static final String SEND_VIDEO = "video";
    public static final String SEND_PHOTO = "photo";

    private Prefs() {
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    // ------------------------------------------------- Telegram credentials //

    public static int apiId(Context context) {
        return prefs(context).getInt(KEY_API_ID, 0);
    }

    public static String apiHash(Context context) {
        return prefs(context).getString(KEY_API_HASH, "");
    }

    public static boolean hasCredentials(Context context) {
        return apiId(context) != 0 && !apiHash(context).isEmpty();
    }

    public static void saveCredentials(Context context, int apiId, String apiHash) {
        prefs(context).edit()
                .putInt(KEY_API_ID, apiId)
                .putString(KEY_API_HASH, apiHash == null ? "" : apiHash.trim())
                .apply();
    }

    // ------------------------------------------------------------ account //

    public static String phone(Context context) {
        return prefs(context).getString(KEY_PHONE, "");
    }

    public static String accountName(Context context) {
        return prefs(context).getString(KEY_NAME, "");
    }

    public static long accountId(Context context) {
        return prefs(context).getLong(KEY_USER_ID, 0L);
    }

    public static void saveAccount(Context context, long userId, String name, String phone) {
        prefs(context).edit()
                .putLong(KEY_USER_ID, userId)
                .putString(KEY_NAME, name == null ? "" : name)
                .putString(KEY_PHONE, phone == null ? "" : phone)
                .putBoolean(KEY_SETUP_DONE, true)
                .apply();
    }

    public static boolean setupDone(Context context) {
        return prefs(context).getBoolean(KEY_SETUP_DONE, false);
    }

    public static String accountUsername(Context context) {
        return prefs(context).getString(KEY_USERNAME, "");
    }

    public static void saveProfile(Context context, String name, String username) {
        prefs(context).edit()
                .putString(KEY_NAME, name == null ? "" : name)
                .putString(KEY_USERNAME, username == null ? "" : username)
                .apply();
    }

    /** Where the profile picture was copied to, once, on this phone. */
    public static String avatarPath(Context context) {
        return prefs(context).getString(KEY_AVATAR, "");
    }

    public static int avatarFileId(Context context) {
        return prefs(context).getInt(KEY_AVATAR_ID, 0);
    }

    public static void saveAvatar(Context context, String path, int fileId) {
        prefs(context).edit()
                .putString(KEY_AVATAR, path == null ? "" : path)
                .putInt(KEY_AVATAR_ID, fileId)
                .apply();
    }

    public static void forgetAvatar(Context context) {
        prefs(context).edit().remove(KEY_AVATAR).remove(KEY_AVATAR_ID).apply();
    }

    // ---------------------------------------------------------------- skin //

    /** True once the user asked for the night skin; the day skin is default. */
    public static boolean night(Context context) {
        return prefs(context).getBoolean(KEY_NIGHT, false);
    }

    public static void setNight(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_NIGHT, value).apply();
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

    public static boolean keepScreenOn(Context context) {
        return prefs(context).getBoolean(KEY_KEEP_SCREEN, true);
    }

    public static void setKeepScreenOn(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_KEEP_SCREEN, value).apply();
    }

    public static float playbackSpeed(Context context) {
        return prefs(context).getFloat(KEY_SPEED, 1.0f);
    }

    public static void setPlaybackSpeed(Context context, float value) {
        prefs(context).edit().putFloat(KEY_SPEED, value).apply();
    }
}
