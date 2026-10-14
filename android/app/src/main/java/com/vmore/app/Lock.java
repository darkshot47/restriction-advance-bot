package com.vmore.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Locale;

/**
 * The optional app lock: a four to eight digit PIN, stored as a salted SHA-256
 * hash, never as the digits themselves.
 *
 * The lock is asked for when the app comes to the front after having been left
 * alone for a while, so a long queue keeps running but nobody else can open the
 * screens.
 */
final class Lock {

    /** How long the app may stay in the background before it locks again. */
    private static final long GRACE_MS = 30_000L;
    private static final String CHARS = "0123456789";

    private static long leftAt;
    private static boolean unlocked;

    private Lock() {
    }

    static boolean enabled(Context context) {
        return Prefs.lockEnabled(context);
    }

    static void setPin(Context context, String pin) {
        String salt = salt();
        Prefs.setLock(context, salt, hash(pin, salt));
        unlocked = true;
        leftAt = 0L;
    }

    static void clear(Context context) {
        Prefs.clearLock(context);
        unlocked = true;
        leftAt = 0L;
    }

    static boolean verify(Context context, String pin) {
        if (pin == null || pin.isEmpty()) {
            return false;
        }
        String salt = Prefs.lockSalt(context);
        String stored = Prefs.lockHash(context);
        return !stored.isEmpty() && stored.equals(hash(pin, salt));
    }

    static void unlocked() {
        unlocked = true;
        leftAt = 0L;
    }

    /**
     * The app went to the background (the last screen stopped).  The lock arms
     * itself here, and the grace period decides whether coming back needs the
     * PIN or not.
     */
    static void appLeft() {
        leftAt = System.currentTimeMillis();
        unlocked = false;
    }

    /** True when this screen should hand over to the PIN screen. */
    static boolean needsPin(Context context) {
        if (!enabled(context)) {
            return false;
        }
        if (unlocked) {
            return false;
        }
        if (leftAt == 0L) {
            return true;
        }
        if (System.currentTimeMillis() - leftAt <= GRACE_MS) {
            unlocked = true;
            return false;
        }
        return true;
    }

    /**
     * One line for any screen's onResume: it returns true when the PIN screen
     * has taken over, and the caller stops painting.
     */
    static boolean guard(Activity activity) {
        if (!needsPin(activity)) {
            return false;
        }
        ask(activity);
        return true;
    }

    /** Sends the user to the PIN screen and leaves the current one. */
    static void ask(Activity activity) {
        Intent intent = new Intent(activity, LockActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
        activity.startActivity(intent);
        activity.finish();
    }

    static boolean valid(String pin) {
        if (pin == null || pin.length() < 4 || pin.length() > 8) {
            return false;
        }
        for (int index = 0; index < pin.length(); index++) {
            if (CHARS.indexOf(pin.charAt(index)) < 0) {
                return false;
            }
        }
        return true;
    }

    private static String salt() {
        byte[] bytes = new byte[12];
        new SecureRandom().nextBytes(bytes);
        StringBuilder builder = new StringBuilder();
        for (byte value : bytes) {
            builder.append(String.format(Locale.US, "%02x", value));
        }
        return builder.toString();
    }

    private static String hash(String pin, String salt) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update((salt == null ? "" : salt).getBytes("UTF-8"));
            byte[] out = digest.digest((pin == null ? "" : pin).getBytes("UTF-8"));
            StringBuilder builder = new StringBuilder();
            for (byte value : out) {
                builder.append(String.format(Locale.US, "%02x", value));
            }
            return builder.toString();
        } catch (Exception error) {
            return "";
        }
    }
}
