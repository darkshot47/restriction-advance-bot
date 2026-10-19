package com.vmore.app;

/**
 * App-wide constants: the version stamped into the APK, the pages Vmore links
 * out to, and the playback speeds the player offers.
 */
public final class Vmore {

    /** Reported to no server at all — only shown on the About screen. */
    public static final String VERSION = "2.2.12";

    /** The Telegram handle of whoever built the app — the only credit in it. */
    public static final String DEVELOPER = "XyrDeveloper";

    /** Telegram's own page for the api_id / api_hash the app asks for once. */
    public static final String CREDENTIALS_URL = "https://my.telegram.org";

    /** Folder inside the app's private storage where downloads land. */
    public static final String FOLDER = "Vmore";

    /** How many recent messages "scan this chat" reads. */
    public static final int SCAN_LIMIT = 60;

    /** Playback speeds of the built-in player, slowest first. */
    public static final float[] SPEEDS = {0.25f, 0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 1.75f, 2.0f, 2.5f, 3.0f};

    public static String speedLabel(float speed) {
        if (speed == Math.round(speed)) {
            return ((int) speed) + "x";
        }
        return String.valueOf(speed) + "x";
    }

    private Vmore() {
    }
}
