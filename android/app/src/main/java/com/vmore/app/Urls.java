package com.vmore.app;

import java.net.URLEncoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Pure URL helpers — no Android types at all, so they can be unit tested on the
 * JVM (the bot prints a *whole* login link, users paste it everywhere).
 *
 * The bot's `/gentoken` screen shows `https://host/api/v2/token/HPSEG9`, and
 * people naturally copy that entire line into the app's "server address" field.
 * {@link #normalizeBase(String)} accepts either shape.
 */
public final class Urls {

    private static final Pattern API_PATH = Pattern.compile("/api/v\\d+", Pattern.CASE_INSENSITIVE);
    private static final Pattern TOKEN_IN_URL =
            Pattern.compile("/api/v\\d+/token/([A-Za-z0-9]+)", Pattern.CASE_INSENSITIVE);

    private Urls() {
    }

    /**
     * The deployment root of whatever the user typed.
     *
     * <pre>
     *   "your-app.onrender.com/"                        → "https://your-app.onrender.com"
     *   "https://your-app.onrender.com/api/v2/token/H9" → "https://your-app.onrender.com"
     *   "https://host/base/api/v2/app/apk?x=1"          → "https://host/base"
     * </pre>
     */
    public static String normalizeBase(String base) {
        if (base == null) {
            return "";
        }
        String value = base.trim();
        if (value.isEmpty()) {
            return "";
        }
        //: A pasted link may carry a trailing path, query or fragment.
        int cut = value.length();
        for (String marker : new String[]{" ", "\n", "\t", "?", "#"}) {
            int at = value.indexOf(marker);
            if (at >= 0 && at < cut) {
                cut = at;
            }
        }
        value = value.substring(0, cut);
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "https://" + value;
        }
        Matcher matcher = API_PATH.matcher(value);
        if (matcher.find() && matcher.start() > 8) {         // keep the host itself
            value = value.substring(0, matcher.start());
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    /** The token hidden inside a pasted login link, or "" when there is none. */
    public static String tokenFromUrl(String value) {
        if (value == null) {
            return "";
        }
        Matcher matcher = TOKEN_IN_URL.matcher(value);
        return matcher.find() ? matcher.group(1).toUpperCase() : "";
    }

    /** The API base for one token: {@code <base>/api/v2/token/<TOKEN>}. */
    public static String tokenUrl(String base, String token) {
        return normalizeBase(base) + Api.API + "/token/"
                + (token == null ? "" : token.trim().toUpperCase());
    }

    public static String encode(String value) {
        try {
            return URLEncoder.encode(value == null ? "" : value, "UTF-8");
        } catch (Exception exc) {
            return "";
        }
    }
}
