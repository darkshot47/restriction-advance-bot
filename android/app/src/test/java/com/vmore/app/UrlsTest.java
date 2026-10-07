package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The URL rules the app lives by: what a user may paste into the "server
 * address" field, and what the app then sends to {@code /api/v2}.
 *
 * Plain JVM tests (no emulator, no Android types) — {@link Urls} is deliberately
 * free of both so these run in the build workflow.
 */
public class UrlsTest {

    @Test
    public void aBareHostGetsHttps() {
        assertEquals("https://your-app.onrender.com", Urls.normalizeBase("your-app.onrender.com"));
    }

    @Test
    public void trailingSlashesAreTrimmed() {
        assertEquals("https://host", Urls.normalizeBase("https://host///"));
        assertEquals("https://host", Urls.normalizeBase("  https://host/  "));
    }

    @Test
    public void theWholeLoginLinkTheBotPrintsBecomesTheHost() {
        String printed = "https://your-app.onrender.com/api/v2/token/HPSEG9";
        assertEquals("https://your-app.onrender.com", Urls.normalizeBase(printed));
        assertEquals("HPSEG9", Urls.tokenFromUrl(printed));
    }

    @Test
    public void aPathQueryOrFragmentIsDropped() {
        assertEquals("https://host", Urls.normalizeBase("https://host/api/v2/app/apk?device=1"));
        assertEquals("https://host", Urls.normalizeBase("https://host/#docs"));
        assertEquals("https://host/base", Urls.normalizeBase("https://host/base/api/v2/app"));
    }

    @Test
    public void aHostThatMerelyStartsWithApiIsKept() {
        assertEquals("https://api-v2.example.com", Urls.normalizeBase("api-v2.example.com"));
    }

    @Test
    public void emptyInputStaysEmpty() {
        assertEquals("", Urls.normalizeBase(null));
        assertEquals("", Urls.normalizeBase("   "));
    }

    @Test
    public void theTokenUrlMatchesTheBotExactly() {
        assertEquals("https://host/api/v2/token/HPSEG9",
                Urls.tokenUrl("host", "hpseg9"));
        assertEquals("https://host/api/v2/token/HPSEG9",
                Urls.tokenUrl("https://host/api/v2/token/OTHER1", "HPSEG9"));
    }

    @Test
    public void noTokenInAPlainAddress() {
        assertEquals("", Urls.tokenFromUrl("https://host"));
        assertEquals("", Urls.tokenFromUrl(null));
        assertTrue(Urls.tokenFromUrl("https://host/api/v2/token/ab12cd").equals("AB12CD"));
    }
}
