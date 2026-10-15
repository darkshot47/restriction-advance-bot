package com.vmore.app;

import java.util.Locale;

/**
 * The rule that decides whether a failed step deserves another attempt.
 *
 * It lives in its own class, free of Android types, because it is the rule that
 * turned one hiccup into a dead job: whatever happens, a retry must never be
 * wasted on something that can only fail again, and a retry must never be
 * refused for something that was only temporary.
 */
final class Retry {

    private Retry() {
    }

    /**
     * The keep-going list: Telegram asking to wait, a dropped connection, a
     * file reference that went stale, an answer that never came.  These are
     * temporary by nature, so a fresh attempt usually lands.
     */
    static boolean recoverable(String reason) {
        if (reason == null) {
            return false;
        }
        String lower = reason.toLowerCase(Locale.US);
        return lower.contains("slow down") || lower.contains("flood")
                || lower.contains("too many requests") || lower.contains("retry")
                || lower.contains("did not answer") || lower.contains("timeout")
                || lower.contains("timed out") || lower.contains("connection")
                || lower.contains("network") || lower.contains("unavailable")
                || lower.contains("internal") || lower.contains("reference")
                || lower.contains("expired") || lower.contains("stale")
                || lower.contains("half way") || lower.contains("did not finish")
                || lower.contains("did not arrive") || lower.contains("closed")
                || lower.contains("reset") || lower.contains("aborted")
                || lower.contains("interrupted") || lower.contains("not respond");
    }

    /**
     * The never-again list: no room on the phone, a file size Telegram will not
     * move, content the owner protects, a chat this account may not read, a
     * message that is gone.  Another attempt would only burn the user's data.
     */
    static boolean fatal(String reason) {
        if (reason == null || reason.isEmpty()) {
            return false;
        }
        String lower = reason.toLowerCase(Locale.US);
        return lower.contains("not enough space") || lower.contains("no space")
                || lower.contains("disk") || lower.contains("insufficient")
                || lower.contains("too big") || lower.contains("too large")
                || lower.contains("protected") || lower.contains("cannot be saved")
                || lower.contains("not allowed") || lower.contains("does not exist")
                || lower.contains("not found") || lower.contains("has no file")
                || lower.contains("no destination") || lower.contains("not signed in")
                || lower.contains("sign in")
                || lower.contains("no telegram engine") || lower.contains("not ready")
                || lower.contains("unsupported") || lower.contains("invalid")
                || lower.contains("cannot see that chat") || lower.contains("could not find")
                || lower.contains("does not name") || lower.contains("invite link cannot")
                || lower.contains("not a member") || lower.contains("no access")
                || lower.contains("not enough rights") || lower.contains("kicked")
                || lower.contains("banned") || lower.contains("deleted");
    }

    /** The simplest form: a step that failed with only words to judge it by. */
    static boolean worthIt(String reason) {
        return !fatal(reason);
    }
}
