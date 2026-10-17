package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The formatting behind the signature row in Settings, the value people compare
 * against the release notes when an update will not install.
 */
public class AppSignatureTest {

    private static final String FULL =
            "a2c63a182375bd5cb65499f088110bd86b8321bdd3cba036705acc5385d0330a";

    @Test
    public void aFullFingerprintIsShownInPairs() {
        String grouped = AppSignature.grouped(FULL);
        assertEquals("64 hex characters become 32 pairs", 95, grouped.length());
        assertTrue(grouped.startsWith("a2:c6:3a:18:23:75"));
        assertTrue(grouped.endsWith(":85:d0:33:0a"));
        assertEquals("a pair per colon", 32, grouped.split(":").length);
        assertEquals("a trailing half pair is dropped", "ab", AppSignature.grouped("abc"));
    }

    @Test
    public void theSummaryIsTheFirstEightBytes() {
        assertEquals("a2c63a18 2375bd5c", AppSignature.shortForm(FULL));
    }

    @Test
    public void nothingToShowIsEmptyAndNotEmptyLooking() {
        assertEquals("", AppSignature.grouped(""));
        assertEquals("", AppSignature.grouped(null));
        assertEquals("", AppSignature.shortForm(""));
        assertEquals("", AppSignature.shortForm(null));
        assertEquals("a short value is not padded out", "", AppSignature.shortForm("a2c63a18237"));
    }
}
