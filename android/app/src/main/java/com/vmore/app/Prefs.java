package com.vmore.app;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Everything the app remembers between launches: the server address, the access
 * token and the last local download.
 *
 * The token is the whole login — there is no session string, no phone number and
 * no Telegram account data stored on the phone.
 */
public final class Prefs {

    /** The owner of the bot — the account behind the top-right corner. */
    public static final String DEFAULT_OWNER = "XyrDeveloper";

    private static final String FILE = "vmore";
    private static final String KEY_BASE = "base_url";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_NAME = "account_name";
    private static final String KEY_USER_ID = "account_id";
    private static final String KEY_CAPTION = "last_caption";
    private static final String KEY_THUMB = "thumbnail_path";
    private static final String KEY_TRIM = "trim_enabled";
    private static final String KEY_OWNER = "owner_username";
    private static final String KEY_OWNER_NAME = "owner_name";

    private Prefs() {
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    /** The owner's Telegram handle shown in the top-right corner. */
    public static String ownerUsername(Context context) {
        return prefs(context).getString(KEY_OWNER, DEFAULT_OWNER);
    }

    public static String ownerName(Context context) {
        return prefs(context).getString(KEY_OWNER_NAME, DEFAULT_OWNER);
    }

    public static void setOwner(Context context, String username, String name) {
        prefs(context).edit()
                .putString(KEY_OWNER, username == null || username.isEmpty() ? DEFAULT_OWNER : username)
                .putString(KEY_OWNER_NAME, name == null ? "" : name)
                .apply();
    }

    public static String baseUrl(Context context) {
        return prefs(context).getString(KEY_BASE, "");
    }

    public static void setBaseUrl(Context context, String value) {
        prefs(context).edit().putString(KEY_BASE, Api.normalizeBase(value)).apply();
    }

    public static String token(Context context) {
        return prefs(context).getString(KEY_TOKEN, "");
    }

    public static void setToken(Context context, String value) {
        prefs(context).edit().putString(KEY_TOKEN, value == null ? "" : value.trim().toUpperCase())
                .apply();
    }

    public static String accountName(Context context) {
        return prefs(context).getString(KEY_NAME, "");
    }

    public static long accountId(Context context) {
        return prefs(context).getLong(KEY_USER_ID, 0L);
    }

    public static void saveAccount(Context context, String name, long userId) {
        prefs(context).edit().putString(KEY_NAME, name).putLong(KEY_USER_ID, userId).apply();
    }

    public static boolean loggedIn(Context context) {
        return !token(context).isEmpty() && !baseUrl(context).isEmpty();
    }

    public static void logout(Context context) {
        SharedPreferences p = prefs(context);
        p.edit().remove(KEY_TOKEN).remove(KEY_NAME).remove(KEY_USER_ID).apply();
    }

    public static String lastCaption(Context context) {
        return prefs(context).getString(KEY_CAPTION, "");
    }

    public static void setLastCaption(Context context, String caption) {
        prefs(context).edit().putString(KEY_CAPTION, caption == null ? "" : caption).apply();
    }

    public static String thumbnailPath(Context context) {
        return prefs(context).getString(KEY_THUMB, "");
    }

    public static void setThumbnailPath(Context context, String path) {
        prefs(context).edit().putString(KEY_THUMB, path == null ? "" : path).apply();
    }

    public static boolean trimEnabled(Context context) {
        return prefs(context).getBoolean(KEY_TRIM, false);
    }

    public static void setTrimEnabled(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_TRIM, value).apply();
    }
}
