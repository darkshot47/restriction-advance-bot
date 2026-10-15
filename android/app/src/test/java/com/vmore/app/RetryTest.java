package com.vmore.app;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The rule that decides whether a failed step gets another try.
 *
 * This is the rule the owner felt on the phone: a job that gave up after one
 * hiccup.  Both halves are pinned here — a temporary problem must be retried,
 * and a permanent one must not.
 */
public class RetryTest {

    @Test
    public void temporaryTroubleIsWorthAnotherAttempt() {
        assertFalse(Retry.fatal("Slow down: 34"));
        assertTrue(Retry.recoverable("Too Many Requests: retry after 30"));
        assertTrue(Retry.recoverable("FLOOD_WAIT_34"));
        assertTrue(Retry.recoverable("File reference has expired"));
        assertTrue(Retry.recoverable("Connection closed"));
        assertTrue(Retry.recoverable("Connection reset by peer"));
        assertTrue(Retry.recoverable("Request aborted"));
        assertTrue(Retry.recoverable("Telegram did not answer in time"));
        assertTrue(Retry.recoverable("Internal Server Error"));
        assertTrue(Retry.recoverable("the download stopped half way"));
        assertTrue(Retry.recoverable("the upload did not finish"));
        assertTrue(Retry.recoverable("the file did not arrive on the phone"));
    }

    @Test
    public void permanentRefusalsAreNeverRetried() {
        assertTrue(Retry.fatal("not enough space on this phone: this file needs 2.0 GB"));
        assertTrue(Retry.fatal("That message does not exist any more"));
        assertTrue(Retry.fatal("message is protected and cannot be saved"));
        assertTrue(Retry.fatal("not enough rights to read this chat"));
        assertTrue(Retry.fatal("no destination chat was chosen"));
        assertTrue(Retry.fatal("open the app and sign in with your Telegram account"));
        assertTrue(Retry.fatal("Telegram could not find @nosuchchannel"));
        assertTrue(Retry.fatal("that link does not name a chat"));
        assertTrue(Retry.fatal("that invite link cannot be used to read the message"));
    }

    @Test
    public void aStaleReferenceIsTemporaryAndNotPermanent() {
        String reason = "file reference has expired";
        assertFalse(Retry.fatal(reason));
        assertTrue(Retry.recoverable(reason));
        assertTrue(Retry.worthIt(reason));
    }

    @Test
    public void unknownWordsAreJudgedKindlyByTheStepItself() {
        //: A step that failed without Telegram's words (a null message) is not
        //: declared permanent: the caller falls back to its own rules.
        assertFalse(Retry.fatal(null));
        assertFalse(Retry.fatal(""));
        assertTrue(Retry.worthIt("something no list knows about"));
    }
}
