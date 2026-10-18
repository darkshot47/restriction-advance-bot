package com.vmore.app;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Ready-made Telegram app keys.
 *
 * Telegram asks every app to carry its own api_id and api_hash, which is why the
 * sign-in screen lets the user paste the pair from my.telegram.org at any time.
 * That page is also the step people get stuck on, so Vmore carries a few pairs
 * that open-source Telegram clients publish, and tries them one after another
 * until Telegram accepts one and sends the login code.
 *
 * Telegram refuses a published key more often than not (its answer is
 * "API_ID_PUBLISHED_FLOOD"), which is exactly why the attempt walks the whole
 * list instead of betting on one, and why the user's own pair stays one tap
 * away on the same screen.
 */
final class ApiKeys {

    private ApiKeys() {
    }

    /** One candidate: the pair and how to name it on screen. */
    static final class Key {
        final int id;
        final String hash;
        final String label;

        Key(int id, String hash, String label) {
            this.id = id;
            this.hash = hash;
            this.label = label;
        }

        /** "2040 / b18441a1" — enough to recognise, never the whole secret. */
        String shortName() {
            String tail = hash.length() > 8 ? hash.substring(0, 8) : hash;
            return id + " / " + tail;
        }
    }

    private static final Key[] POOL = {
            new Key(2040, "b18441a1ff607e10a989891a5462e627", "desktop"),
            new Key(4, "014b35b6184100b085b0d0572f9b5103", "android"),
            new Key(9, "3975f648bb682ee889f35483bc618d1c", "macos"),
            new Key(2496, "8da85b0d5bfe62527e5b244c209159c3", "web"),
            new Key(21724, "3e0cb5efcd52300aec5994baa72a91e3", "android x"),
    };

    /** How many keys one attempt may walk. */
    static int count() {
        return POOL.length;
    }

    /**
     * The order for this attempt.  A shuffle means two attempts do not hammer
     * the same key first, which is what the owner asked for when he said a
     * random key should be tried.
     */
    static List<Key> order() {
        List<Key> keys = new ArrayList<>(Arrays.asList(POOL));
        Collections.shuffle(keys);
        return keys;
    }

    /**
     * The same order, but the key that worked on this phone goes first.
     *
     * The owner did not want a random key tried every time.  A shuffle alone
     * means the sign-in may start with a key Telegram has already refused for
     * this account; starting with the one that last produced a login code makes
     * the attempt short and predictable, and the rest of the list stays behind
     * it in case that key is refused too.
     */
    static List<Key> order(int preferredId, String preferredHash) {
        List<Key> keys = order();
        Key preferred = find(preferredId, preferredHash);
        if (preferred != null) {
            keys.remove(preferred);
            keys.add(0, preferred);
        }
        return keys;
    }

    /** The pool entry for a pair, or null when the pair is not one of ours. */
    static Key find(int apiId, String apiHash) {
        if (apiId <= 0 || apiHash == null || apiHash.isEmpty()) {
            return null;
        }
        for (Key key : POOL) {
            if (key.id == apiId && key.hash.equalsIgnoreCase(apiHash.trim())) {
                return key;
            }
        }
        return null;
    }
}
