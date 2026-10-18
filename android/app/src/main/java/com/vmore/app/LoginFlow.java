package com.vmore.app;

import java.util.Locale;

/**
 * The small decisions the sign-in screen makes, kept away from Android so they
 * can be read and tested on their own.
 *
 * The screen has one rule that matters more than any other: an error may only
 * take the user back to the field that is actually wrong.  Mistaking a wrong
 * two-step password for a wrong api_id (both arrive with the word "hash" in
 * them) is what used to throw people back to the very first step and ask for
 * everything again.
 */
final class LoginFlow {

    private LoginFlow() {
    }

    /**
     * True when Telegram is complaining about the app key itself.
     *
     * Deliberately narrow: api_id, api_hash, a published key.  The refusals
     * for a wrong two-step password carry the word hash as well, and they are
     * about the password, never about the app.
     */
    static boolean keyProblem(String detail) {
        if (detail == null || detail.isEmpty()) {
            return false;
        }
        String lower = detail.toLowerCase(Locale.US);
        if (lower.contains("api_id") || lower.contains("api id")
                || lower.contains("api_hash") || lower.contains("api hash")
                || lower.contains("app_id") || lower.contains("app key")
                || lower.contains("published")) {
            return true;
        }
        //: "That api_id or api_hash is not valid" is written by Tg.friendly
        //: without those exact tokens on purpose?  It does carry them; this
        //: line only covers a raw answer that names the app instead.
        return lower.contains("app credentials") && lower.contains("refused");
    }

    /**
     * True when a failure during the ready-made key walk means the key was
     * refused, rather than something the user has to fix (a wrong number, a
     * wrong code, a flood wait).
     *
     * Only a key problem moves the walk on.  Anything else stops it and leaves
     * the screen on the step that failed with the reason on it; burning through
     * every remaining key because a phone number was mistyped is how the walk
     * used to end with "every key was refused".
     */
    static boolean anotherKeyMayWork(String detail) {
        return keyProblem(detail);
    }

    /**
     * Which screen belongs under an error: the step Telegram is waiting in,
     * never the error itself.
     */
    static String stepFor(String rememberedStep) {
        if (Tg.STATE_CODE.equals(rememberedStep)
                || Tg.STATE_PASSWORD.equals(rememberedStep)
                || Tg.STATE_PHONE.equals(rememberedStep)) {
            return rememberedStep;
        }
        return Tg.STATE_CREDENTIALS;
    }
}
