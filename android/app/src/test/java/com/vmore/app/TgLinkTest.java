package com.vmore.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.List;

/** The link parser is the front door of the app — every shape is pinned here. */
public class TgLinkTest {

    @Test
    public void publicLinkWithMessage() {
        TgLink link = TgLink.parse("https://t.me/some_channel/145");
        assertTrue(link.valid);
        assertEquals("some_channel", link.username);
        assertEquals(145L, link.messageId);
        assertFalse(link.isRange());
    }

    @Test
    public void publicLinkWithoutSchemeAndTrailingSlash() {
        TgLink link = TgLink.parse("t.me/some_channel/145/");
        assertTrue(link.valid);
        assertEquals("some_channel", link.username);
        assertEquals(145L, link.messageId);
    }

    @Test
    public void rangeLinkCountsMessages() {
        TgLink link = TgLink.parse("https://t.me/some_channel/10-14");
        assertTrue(link.valid);
        assertTrue(link.isRange());
        assertEquals(5, link.count());
    }

    @Test
    public void reversedRangeIsReadTheWayTelegramReadsIt() {
        TgLink link = TgLink.parse("t.me/some_channel/90-12");
        assertEquals(12L, link.messageId);
        assertEquals(90L, link.endMessageId);
    }

    @Test
    public void privateLinkBecomesARealChatId() {
        TgLink link = TgLink.parse("https://t.me/c/1234567890/15");
        assertTrue(link.valid);
        assertTrue(link.privateLink);
        assertEquals(1234567890L, link.internalId);
        assertEquals(-1001234567890L, link.privateChatId());
    }

    @Test
    public void privateChatIdRoundTrips() {
        long chatId = -1001234567890L;
        assertEquals(1234567890L, TgLink.internalFromChatId(chatId));
        assertEquals(chatId, TgLink.chatIdFromInternal(1234567890L));
        assertEquals("https://t.me/c/1234567890/15", TgLink.deepLink(chatId, 15));
    }

    @Test
    public void inviteLinksAreRecognised() {
        assertEquals("AbCdEf", TgLink.parse("https://t.me/+AbCdEf").inviteHash);
        assertEquals("AbCdEf", TgLink.parse("t.me/joinchat/AbCdEf").inviteHash);
    }

    @Test
    public void usernameOnly() {
        TgLink link = TgLink.parse("@some_channel");
        assertTrue(link.valid);
        assertEquals("some_channel", link.username);
        assertEquals(0L, link.messageId);
        TgLink plain = TgLink.parse("some_channel");
        assertTrue(plain.valid);
        assertEquals("some_channel", plain.username);
    }

    @Test
    public void numericChatId() {
        TgLink link = TgLink.parse("-1001234567890");
        assertTrue(link.valid);
        assertEquals(-1001234567890L, link.chatId);
        assertEquals(0L, link.messageId);
    }

    @Test
    public void bareNumbersNeedAChatContext() {
        TgLink single = TgLink.parse("145");
        assertTrue(single.valid);
        assertTrue(single.needsChatContext);
        assertEquals(145L, single.messageId);

        TgLink range = TgLink.parse("20-24");
        assertTrue(range.valid);
        assertTrue(range.needsChatContext);
        assertEquals(20L, range.messageId);
        assertEquals(24L, range.endMessageId);
    }

    @Test
    public void tgSchemeOpenMessage() {
        TgLink link = TgLink.parse("tg://openmessage?chat_id=-1001234567890&message_id=42");
        assertTrue(link.valid);
        assertEquals(-1001234567890L, link.chatId);
        assertEquals(42L, link.messageId);
    }

    @Test
    public void batchSplitsOnLinesSpacesAndCommas() {
        List<TgLink> links = TgLink.parseAll(
                "https://t.me/chan_one/1, https://t.me/chan_two/2\n"
                        + "https://t.me/c/1234567890/3  145");
        assertEquals(4, links.size());
        assertTrue(links.get(0).valid);
        assertEquals("chan_one", links.get(0).username);
        assertTrue(links.get(1).valid);
        assertTrue(links.get(2).valid);
        assertEquals(145L, links.get(3).messageId);
    }

    @Test
    public void trailingBracketAndQuoteAreDropped() {
        TgLink link = TgLink.parse("(https://t.me/some_channel/7)");
        assertTrue(link.valid);
        assertEquals(7L, link.messageId);
    }

    @Test
    public void junkIsRejectedWithAReason() {
        TgLink link = TgLink.parse("https://example.com/hello/world");
        assertFalse(link.valid);
        assertFalse(link.error.isEmpty());
    }

    @Test
    public void hugeRangeIsCappedButStillAccepted() {
        TgLink link = TgLink.parse("t.me/some_channel/1-9000");
        assertTrue(link.valid);
        assertEquals(TgLink.MAX_RANGE, link.count());
        assertTrue(link.endMessageId - link.messageId + 1 <= TgLink.MAX_RANGE);
        assertFalse(link.note.isEmpty());
    }

    @Test
    public void queryStringsAreIgnored() {
        TgLink link = TgLink.parse("https://t.me/some_channel/145?single&comment=1");
        assertTrue(link.valid);
        assertEquals(145L, link.messageId);
    }
}
