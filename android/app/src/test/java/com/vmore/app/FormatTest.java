package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The names a chat shows for a file.
 *
 * Telegram takes the uploaded file name straight from the local path, so every
 * name Vmore invents here is visible to the recipients.  The old build's
 * "vmore_4838" prefix came exactly from this layer and must never come back.
 */
public class FormatTest {

    @Test
    public void aCaptionBecomesTheFileStem() {
        assertEquals("Holiday in Goa", Format.stemFrom("Holiday in Goa", 48));
        assertEquals("Holiday in Goa",
                Format.stemFrom("Holiday in Goa\nsecond line is ignored", 48));
        //: Path separators and reserved characters never reach the file system
        //: or the chat; runs of spaces collapse to one.
        assertEquals("abcdefghi", Format.stemFrom("a/b:c?d*e\"f<g>h|i", 48));
        assertEquals("one two", Format.stemFrom("one     two", 48));
        assertEquals("report", Format.stemFrom("  report  ", 48));
        assertEquals("", Format.stemFrom("   ", 48));
        assertEquals("", Format.stemFrom(null, 48));
        assertTrue(Format.stemFrom("x".repeat(200), 48).length() <= 48);
        assertFalse(Format.stemFrom("...hidden...", 48).startsWith("."));
    }

    @Test
    public void unnamedMediaGetsAReadableDatedName() {
        String name = Format.datedName("photo", 1_760_000_000L, ".jpg");
        assertTrue(name.startsWith("photo_"));
        assertTrue(name.endsWith(".jpg"));
        assertTrue(name.matches("photo_\\d{4}-\\d{2}-\\d{2}_\\d{6}\\.jpg"));
        assertFalse(name.contains("vmore"));

        assertTrue(Format.datedName("video", 0L, "mp4").endsWith(".mp4"));
        assertEquals("file_", Format.datedName("", 0L, "").substring(0, 5));
    }

    @Test
    public void theRetiredInternalPrefixIsStrippedEverywhere() {
        assertEquals("holiday.mp4", Format.displayName("vmore_4838_holiday.mp4", "x"));
        assertEquals("4838.mp4", Format.displayName("vmore_4838.mp4", "x"));
        assertEquals("clip.mp4", Format.displayName("clip.mp4", "x"));
        //: A real file whose name happens to start with the word is untouched
        //: beyond its first segment.
        assertEquals("note.txt", Format.displayName("vmore_note.txt", "x"));
        assertEquals("fallback", Format.displayName("", "fallback"));
        assertEquals("fallback", Format.displayName(null, "fallback"));
    }

    @Test
    public void safeNameStillGuardsTheFileSystem() {
        assertEquals("a_b_c", Format.safeName("a/b\\c", "x"));
        assertEquals("Vmore", Format.safeName("", null));
        assertEquals("x", Format.withoutExtension("x"));
        assertEquals("clip", Format.withoutExtension("clip.mp4"));
    }
}
