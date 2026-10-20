package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

// Unit tests covering chat send-permission filtering, title matching, clock and
// size parsing, and multi-signal message scoring for Smart Feature, plus the
// active COPYING stage and UI monogram helpers.
public class SmartMatcherTest {

    @Test
    public void broadcastChannelsRequireCreatorOrPostAdminRights() {
        assertTrue(SmartMatcher.canSendToChannel(true, false, false));
        assertTrue(SmartMatcher.canSendToChannel(false, true, true));
        assertFalse(SmartMatcher.canSendToChannel(false, true, false));
        assertFalse(SmartMatcher.canSendToChannel(false, false, false));
    }

    @Test
    public void groupsRespectMemberAndRestrictedPermissions() {
        assertTrue(SmartMatcher.canSendToGroup(true, false, false, false, false, false));
        assertTrue(SmartMatcher.canSendToGroup(false, true, false, false, false, false));
        assertTrue(SmartMatcher.canSendToGroup(false, false, true, false, true, false));
        assertFalse(SmartMatcher.canSendToGroup(false, false, true, false, false, false));
        assertTrue(SmartMatcher.canSendToGroup(false, false, false, true, true, true));
        assertFalse(SmartMatcher.canSendToGroup(false, false, false, true, true, false));
        assertFalse(SmartMatcher.canSendToGroup(false, false, false, false, true, true));
    }

    @Test
    public void deletedOrBlockedPrivateChatsAreExcluded() {
        assertTrue(SmartMatcher.canSendToPrivateUser(false, true));
        assertFalse(SmartMatcher.canSendToPrivateUser(true, true));
        assertFalse(SmartMatcher.canSendToPrivateUser(false, false));
    }

    @Test
    public void headerTitlesMatchExactPrefixAndHandlesWhileIgnoringNoise() {
        assertTrue(SmartMatcher.scoreChatTitle("Cinema Vault", "Cinema Vault", "") == 100);
        assertTrue(SmartMatcher.scoreChatTitle("@cinemavault", "Cinema Vault", "cinemavault") >= 90);
        assertEquals(0, SmartMatcher.scoreChatTitle("Unrelated Group", "Cinema Vault", "cinemavault"));
        assertTrue(SmartMatcher.isSubtitleNoise("14,820 subscribers"));
        assertTrue(SmartMatcher.isSubtitleNoise("last seen recently"));
        assertTrue(SmartMatcher.isSubtitleNoise("10:42 PM"));
        assertFalse(SmartMatcher.isSubtitleNoise("Course Lecture Notes"));
    }

    @Test
    public void mediaScoringPinpointsExactFileUnderWhiteCircle() {
        List<String> lines = Arrays.asList(
                "Physics_Chapter_04_HD.mp4",
                "48.0 MB • 12:30",
                "2:15 PM"
        );
        int exact = SmartMatcher.scoreMessage(
                lines, 0, 0,
                "Physics_Chapter_04_HD.mp4", "Chapter 4 full lecture",
                "video", 48L * 1024L * 1024L, 750L, 0L);
        int wrong = SmartMatcher.scoreMessage(
                lines, 0, 3,
                "Chemistry_Notes.pdf", "Organic summary",
                "document", 2L * 1024L * 1024L, 0L, 0L);
        assertTrue(exact > wrong + 150);
    }

    @Test
    public void extractsSearchQueriesSizesDurationsAndClocks() {
        List<String> lines = Arrays.asList("02:05", "128.0 MB", "Quantum_Mechanics_01.mkv", "9:30 PM");
        assertEquals("Quantum Mechanics 01", SmartMatcher.extractSearchQuery(lines));
        assertEquals(128L * 1024L * 1024L, SmartMatcher.extractSizeBytes(lines));
        assertEquals(125L, SmartMatcher.extractDurationSec(Collections.singletonList("02:05")));
        assertTrue(SmartMatcher.extractClockTimes("9:30 PM").contains("21:30"));
    }

    @Test
    public void copyingStageCountsAsActiveAndMonogramHandlesEdgeTitles() {
        QJob job = new QJob();
        job.stage = QJob.COPYING;
        assertTrue(job.isActive());
        assertEquals("Copying instantly", Ui.stageLabel(QJob.COPYING));
        assertEquals("S", Ui.initial("Saved Messages"));
        assertEquals("V", Ui.initial("   "));
    }
}
