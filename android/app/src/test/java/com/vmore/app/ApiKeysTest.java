package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** The ready-made key pool behind the sign-in screen. */
public class ApiKeysTest {

    @Test
    public void everyKeyIsCompleteEnoughToAskTelegram() {
        for (ApiKeys.Key key : ApiKeys.order()) {
            assertTrue("an api_id must be a real number", key.id > 0);
            assertEquals("api_hash is 32 hex characters", 32, key.hash.length());
            assertTrue(key.hash.matches("[0-9a-f]{32}"));
            assertFalse(key.label.isEmpty());
        }
    }

    @Test
    public void anAttemptWalksEveryKeyExactlyOnce() {
        List<ApiKeys.Key> order = ApiKeys.order();
        assertEquals(ApiKeys.count(), order.size());
        Set<Integer> ids = new HashSet<>();
        for (ApiKeys.Key key : order) {
            ids.add(key.id);
        }
        assertEquals("no key is tried twice in one attempt", ApiKeys.count(), ids.size());
    }

    @Test
    public void theOrderIsShuffledSoRetriesLookDifferent() {
        boolean sawAnotherOrder = false;
        List<ApiKeys.Key> first = ApiKeys.order();
        for (int attempt = 0; attempt < 40 && !sawAnotherOrder; attempt++) {
            List<ApiKeys.Key> again = ApiKeys.order();
            for (int index = 0; index < first.size(); index++) {
                if (first.get(index).id != again.get(index).id) {
                    sawAnotherOrder = true;
                    break;
                }
            }
        }
        assertTrue("two attempts must not always start on the same key", sawAnotherOrder);
    }

    @Test
    public void aKeyNameShowsEnoughToRecogniseItButNotAllOfIt() {
        ApiKeys.Key key = ApiKeys.order().get(0);
        String shown = key.shortName();
        assertTrue(shown.startsWith(String.valueOf(key.id)));
        assertFalse("the whole secret is never put on screen", shown.contains(key.hash));
    }
}
