package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The small rules the screens and the queue lean on: which media a batch keeps,
 * how a PIN is judged before it is ever stored, and how sizes and times are
 * written out.
 */
public class RulesTest {

    @Test
    public void anEmptyFilterKeepsEverything() {
        QJob job = new QJob();
        assertTrue(job.allows("video", 5L * 1024L * 1024L));
        assertTrue(job.allows("document", 0L));
        assertTrue(job.allows(null, 1L));
    }

    @Test
    public void onlyTheChosenKindsSurviveTheFilter() {
        QJob job = new QJob();
        job.onlyKinds = "video,photo";
        assertTrue(job.allows("video", 10L));
        assertTrue(job.allows("photo", 10L));
        assertFalse(job.allows("audio", 10L));
        assertFalse(job.allows("document", 10L));
    }

    @Test
    public void sizeBoundsAreHonouredBothWays() {
        QJob job = new QJob();
        job.minSize = 1024L;
        job.maxSize = 4096L;
        assertTrue(job.allows("video", 2048L));
        assertTrue(job.allows("video", 1024L));
        assertTrue(job.allows("video", 4096L));
        assertFalse(job.allows("video", 1023L));
        assertFalse(job.allows("video", 4097L));
        //: A size Telegram has not reported yet is never thrown away.
        assertTrue(job.allows("video", 0L));
    }

    @Test
    public void aPinIsFourToEightDigits() {
        assertFalse(Lock.valid(null));
        assertFalse(Lock.valid(""));
        assertFalse(Lock.valid("123"));
        assertTrue(Lock.valid("1234"));
        assertTrue(Lock.valid("12345678"));
        assertFalse(Lock.valid("123456789"));
        assertFalse(Lock.valid("12a4"));
        assertFalse(Lock.valid("12 4"));
    }

    @Test
    public void sizesReadTheWayPeopleReadThem() {
        assertEquals("0 B", Format.size(0));
        assertEquals("512 B", Format.size(512));
        assertEquals("1.0 KB", Format.size(1024));
        assertEquals("1.0 MB", Format.size(1024L * 1024L));
        assertEquals("1.0 GB", Format.size(1024L * 1024L * 1024L));
        assertEquals("100 KB", Format.size(102400L));
    }

    @Test
    public void percentNeverLeavesItsRange() {
        assertEquals(0, Format.percent(0, 0));
        assertEquals(0, Format.percent(0, 100));
        assertEquals(50, Format.percent(50, 100));
        assertEquals(100, Format.percent(150, 100));
    }

    @Test
    public void durationsAndClocksAreShort() {
        assertEquals("00:00", Format.duration(0));
        assertEquals("00:05", Format.duration(5_000L));
        assertEquals("01:00", Format.duration(60_000L));
        assertEquals("1:00:00", Format.clock(3600));
        assertEquals("00:45", Format.clock(45));
        assertEquals("", Format.speed(0));
        assertEquals("1.0 MB/s", Format.speed(1024 * 1024));
    }

    @Test
    public void namesAreMadeSafeForEveryPhone() {
        assertEquals("clip.mp4", Format.safeName("clip.mp4", "Vmore"));
        assertEquals("a_b_c", Format.safeName("a/b:c", "Vmore"));
        assertEquals("Vmore", Format.safeName("   ", "Vmore"));
        assertEquals("clip", Format.withoutExtension("clip.mp4"));
        assertEquals("clip", Format.withoutExtension("clip"));
        assertEquals("", Format.withoutExtension(null));
    }
}
