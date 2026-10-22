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

    /**
     * Telegram's "come back in N seconds", in seconds, or 0 when it is not a
     * flood wait at all.
     *
     * The number is read out of `FLOOD_WAIT_42` — and out of the friendlier
     * sentence the app builds around it — because waiting exactly as long as
     * Telegram asked is the only way to make the next attempt land.
     */
    static long floodSeconds(String reason) {
        if (reason == null || reason.isEmpty()) {
            return 0L;
        }
        String lower = reason.toLowerCase(Locale.US);
        if (!lower.contains("flood_wait") && !lower.contains("flood wait")
                && !lower.contains("too many requests") && !lower.contains("asked to wait")
                && !lower.contains("slow down")) {
            return 0L;
        }
        String digits = "";
        for (String token : reason.split("[^0-9]+")) {
            if (!token.isEmpty()) {
                digits = token;
                break;
            }
        }
        if (digits.isEmpty()) {
            //: "Slow down" without a number still deserves a short pause.
            return 30L;
        }
        try {
            return Math.max(1L, Long.parseLong(digits));
        } catch (NumberFormatException notANumber) {
            return 30L;
        }
    }

    /**
     * True when Telegram refused to *forward* the message, as opposed to
     * refusing to move it at all.
     *
     * A chat that protects its content forbids forwarding and saving, and
     * Telegram answers with exactly those words.  The bytes may still be
     * downloaded for viewing, so the queue answers this refusal by moving the
     * file as a copy instead of giving up on the job.
     */
    static boolean forwardBlocked(String reason) {
        if (reason == null || reason.isEmpty()) {
            return false;
        }
        String lower = reason.toLowerCase(Locale.US);
        return lower.contains("protected")
                || lower.contains("can't be forwarded")
                || lower.contains("cannot be forwarded")
                || lower.contains("forward")
                && (lower.contains("not allowed") || lower.contains("restricted")
                    || lower.contains("forbidden"));
    }

    /** The simplest form: a step that failed with only words to judge it by. */
    static boolean worthIt(String reason) {
        return !fatal(reason);
    }
}
