package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The rules that keep the sign-in screen on the step that is actually wrong.
 *
 * On the phone this was the worst of the login bugs: a wrong two-step password
 * sent the screen back to api_id and api_hash, so the next attempt asked for
 * everything again and then failed.  Both halves are pinned here.
 */
public class LoginFlowTest {

    @Test
    public void onlyAnAppKeyRefusalCountsAsAKeyProblem() {
        assertTrue(LoginFlow.keyProblem(
                "Telegram refused this app key: it is a published key that belongs "
                        + "to another app (API_ID_PUBLISHED_FLOOD)"));
        assertTrue(LoginFlow.keyProblem("That api_id or api_hash is not valid"));
        assertTrue(LoginFlow.keyProblem("API_ID_INVALID"));
        assertTrue(LoginFlow.keyProblem("APP_ID_INVALID"));
    }

    @Test
    public void aWrongPasswordOrCodeIsNotAKeyProblem() {
        //: Both of these carry the word hash or the word api in other builds;
        //: neither is about the app key, and neither may send the user back.
        assertFalse(LoginFlow.keyProblem("The two-step password is not correct"));
        assertFalse(LoginFlow.keyProblem("PASSWORD_HASH_INVALID"));
        assertFalse(LoginFlow.keyProblem("PHONE_CODE_INVALID"));
        assertFalse(LoginFlow.keyProblem("PHONE_NUMBER_INVALID"));
        assertFalse(LoginFlow.keyProblem("Telegram asked to wait 40 seconds"));
        assertFalse(LoginFlow.keyProblem(""));
        assertFalse(LoginFlow.keyProblem(null));
    }

    @Test
    public void theKeyWalkOnlyMovesOnForAKey() {
        assertTrue(LoginFlow.anotherKeyMayWork("API_ID_INVALID"));
        assertFalse(LoginFlow.anotherKeyMayWork("PHONE_CODE_INVALID"));
        assertFalse(LoginFlow.anotherKeyMayWork("The two-step password is not correct"));
    }

    @Test
    public void anErrorIsPaintedOnTheStepItCameFrom() {
        assertEquals(Tg.STATE_CODE, LoginFlow.stepFor(Tg.STATE_CODE));
        assertEquals(Tg.STATE_PASSWORD, LoginFlow.stepFor(Tg.STATE_PASSWORD));
        assertEquals(Tg.STATE_PHONE, LoginFlow.stepFor(Tg.STATE_PHONE));
        //: Anything else (an error, a closed session, a state with no field of
        //: its own) lands on the keys step, which always exists.
        assertEquals(Tg.STATE_CREDENTIALS, LoginFlow.stepFor(Tg.STATE_ERROR));
        assertEquals(Tg.STATE_CREDENTIALS, LoginFlow.stepFor(Tg.STATE_CLOSED));
        assertEquals(Tg.STATE_CREDENTIALS, LoginFlow.stepFor(null));
    }
}
