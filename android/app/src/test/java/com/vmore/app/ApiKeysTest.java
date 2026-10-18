package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** The ready-made key pool behind the sign-in screen. */
public class ApiKeysTest {

    private static java.util.List<Integer> ids(List<ApiKeys.Key> keys) {
        java.util.List<Integer> out = new java.util.ArrayList<>();
        for (ApiKeys.Key key : keys) {
            out.add(key.id);
        }
        return out;
    }

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
    public void theKeyThatWorkedLastTimeGoesFirst() {
        List<ApiKeys.Key> plain = ApiKeys.order();
        ApiKeys.Key chosen = plain.get(plain.size() - 1);
        List<ApiKeys.Key> ordered = ApiKeys.order(chosen.id, chosen.hash);
        assertEquals("the remembered key leads the attempt", chosen.id,
                ordered.get(0).id);
        assertEquals("and the list still holds every key", plain.size(), ordered.size());
        assertEquals("still one pass per key",
                plain.size(), new HashSet<>(ids(ordered)).size());
    }

    @Test
    public void aPairThatIsNotOursIsNotPromised() {
        assertNull(ApiKeys.find(12345, "00000000000000000000000000000000"));
        assertNull(ApiKeys.find(0, ""));
        assertNull(ApiKeys.find(ApiKeys.order().get(0).id, "ffff"));
        ApiKeys.Key first = ApiKeys.order().get(0);
        assertNotNull(ApiKeys.find(first.id, first.hash));
        //: The handle this app is signed in with is never one of the pool.
        assertNull(ApiKeys.find(2040, "not-the-hash-of-it"));
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
