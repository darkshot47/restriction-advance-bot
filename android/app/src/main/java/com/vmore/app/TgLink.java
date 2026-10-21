package com.vmore.app;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * One Telegram link, understood without any network call.
 *
 * The app accepts every shape a phone clipboard can produce:
 *
 * <pre>
 *   https://t.me/channel/145          → username + one message
 *   t.me/channel/145-200              → username + a range
 *   https://t.me/c/1234567890/145     → private chat (id built from the link)
 *   t.me/+AbCdEfGh / t.me/joinchat/…  → an invite link
 *   @channel  /  channel              → a chat, no message yet
 *   -1001234567890                    → a numeric chat id
 *   tg://openmessage?chat_id=…&message_id=… → the same thing, tg:// style
 *   145  /  145-200                   → a message (or range) in the chat that is already selected
 * </pre>
 *
 * Pure Java on purpose: the parsing rules are unit tested on the JVM.
 */
public final class TgLink {

    /** A range link may describe a big stretch of a channel; this keeps it sane. */
    public static final int MAX_RANGE = 500;

    public String raw = "";
    public String username = "";
    public long chatId = 0L;
    public boolean privateLink = false;
    public long internalId = 0L;
    public long messageId = 0L;
    public long endMessageId = 0L;
    public String inviteHash = "";
    /** A bare "145" says nothing about *which* chat — the caller supplies it. */
    public boolean needsChatContext = false;
    public boolean valid = false;
    public String error = "";
    /** Something worth telling the user, without rejecting the link. */
    public String note = "";

    public boolean isRange() {
        return endMessageId > 0 && endMessageId >= messageId;
    }

    /** How many messages this link describes (1 for a single message). */
    public int count() {
        if (messageId <= 0) {
            return 0;
        }
        if (isRange()) {
            return (int) Math.min(MAX_RANGE, endMessageId - messageId + 1);
        }
        return 1;
    }

    public boolean hasChat() {
        return chatId != 0L || !username.isEmpty() || !inviteHash.isEmpty() || privateLink;
    }

    /** The chat id a private link points at. */
    public long privateChatId() {
        return privateLink && internalId > 0 ? chatIdFromInternal(internalId) : 0L;
    }

    /** Telegram's t.me/c/<internal>/… → the real -100… chat id. */
    public static long chatIdFromInternal(long internal) {
        return internal <= 0 ? 0L : -(1000000000000L + internal);
    }

    /** The reverse: a -100… supergroup id → the number t.me/c/ links use. */
    public static long internalFromChatId(long chatId) {
        if (chatId >= -1000000000000L) {
            return 0L;
        }
        return -chatId - 1000000000000L;
    }

    /** "t.me/c/1234567890/15" built from a chat id and a message id. */
    public static String deepLink(long chatId, long messageId) {
        long internal = internalFromChatId(chatId);
        if (internal > 0) {
            return "https://t.me/c/" + internal + "/" + messageId;
        }
        return "";
    }

    /**
     * Every link inside a pasted blob: one per line, per space, per comma.
     * Invalid pieces are returned too, with {@link #error} filled in, so the
     * screen can say exactly which line it did not understand.
     */
    public static List<TgLink> parseAll(String text) {
        List<TgLink> links = new ArrayList<>();
        if (text == null) {
            return links;
        }
        String normalized = text.replace('\r', '\n')
                .replace(',', '\n')
                .replace(';', '\n')
                .replace('\t', '\n');
        for (String chunk : normalized.split("\\s+")) {
            String value = chunk.trim();
            if (value.isEmpty()) {
                continue;
            }
            links.add(parse(value));
        }
        return links;
    }

    public static TgLink parse(String chunk) {
        TgLink link = new TgLink();
        if (chunk == null) {
            link.error = "empty";
            return link;
        }
        String value = clean(chunk);
        link.raw = value;
        if (value.isEmpty()) {
            link.error = "empty";
            return link;
        }

        // tg://openmessage?chat_id=-1001234567890&message_id=42
        if (value.toLowerCase(Locale.US).startsWith("tg://")) {
            return parseTgScheme(link, value);
        }

        // Drop any scheme or www. prefix, then the telegram hosts.
        String lower = value.toLowerCase(Locale.US);
        for (String scheme : new String[]{"https://", "http://"}) {
            if (lower.startsWith(scheme)) {
                value = value.substring(scheme.length());
                lower = value.toLowerCase(Locale.US);
                break;
            }
        }
        if (lower.startsWith("www.")) {
            value = value.substring(4);
            lower = value.toLowerCase(Locale.US);
        }
        boolean hadTelegramHost = false;
        for (String host : new String[]{"t.me/", "telegram.me/", "telegram.dog/", "telegram.org/"}) {
            if (lower.startsWith(host)) {
                value = value.substring(host.length());
                lower = value.toLowerCase(Locale.US);
                hadTelegramHost = true;
                break;
            }
        }
        if (value.startsWith("/")) {
            value = value.substring(1);
            lower = value.toLowerCase(Locale.US);
        }

        // Explicit @username, @username/145, or @username/10-20
        if (value.startsWith("@")) {
            String handleRest = value.substring(1);
            if (handleRest.contains("/")) {
                String[] parts = handleRest.split("/");
                link.username = parts[0];
                if (!isUsername(link.username)) {
                    link.error = "that @username looks wrong";
                    return link;
                }
                if (parts.length >= 2) {
                    applyMessagePart(link, parts[1]);
                }
                link.valid = link.error.isEmpty();
                return link;
            }
            link.username = handleRest;
            link.valid = isUsername(link.username);
            link.error = link.valid ? "" : "that @username looks wrong";
            return link;
        }

        // Without a real Telegram host (t.me / telegram.me) or explicit @ prefix,
        // NEVER guess or auto-prepend '@' onto plain words or ordinary sentences.
        if (!hadTelegramHost) {
            if (looksLikeMessagePart(value)) {
                link.needsChatContext = true;
                applyMessagePart(link, value);
                link.valid = link.messageId > 0 && link.error.isEmpty();
                if (link.messageId <= 0 && link.error.isEmpty()) {
                    link.error = "that message number is not valid";
                }
                return link;
            }
            if (value.startsWith("-") && isNumber(value) && value.length() >= 8) {
                link.chatId = parseLong(value);
                link.valid = link.chatId != 0;
                return link;
            }
            link.error = "paste a direct Telegram link (https://t.me/...) or @username";
            return link;
        }

        // Invite links: t.me/+hash and t.me/joinchat/hash
        if (value.startsWith("+")) {
            link.inviteHash = value.substring(1);
            link.valid = !link.inviteHash.isEmpty();
            link.error = link.valid ? "" : "invite link without a code";
            return link;
        }
        if (lower.startsWith("joinchat/")) {
            link.inviteHash = value.substring("joinchat/".length());
            link.valid = !link.inviteHash.isEmpty();
            link.error = link.valid ? "" : "invite link without a code";
            return link;
        }

        // Private links: t.me/c/<internal>/<message>
        if (lower.startsWith("c/")) {
            String rest = value.substring(2);
            String[] parts = rest.split("/");
            if (parts.length == 0 || !isNumber(parts[0])) {
                link.error = "that private link has no chat id";
                return link;
            }
            link.privateLink = true;
            link.internalId = parseLong(parts[0]);
            link.chatId = chatIdFromInternal(link.internalId);
            if (parts.length >= 2) {
                applyMessagePart(link, parts[1]);
            }
            link.valid = link.internalId > 0;
            if (!link.valid) {
                link.error = "that private link has no chat id";
            } else if (link.error.isEmpty() && link.messageId <= 0) {
                link.valid = true;
            }
            return link;
        }

        // t.me/username/message or t.me/username/start-end
        if (value.contains("/")) {
            String[] parts = value.split("/");
            link.username = parts[0];
            if (!isUsername(link.username)) {
                link.error = "that link does not name a chat";
                return link;
            }
            if (parts.length >= 2) {
                applyMessagePart(link, parts[1]);
            }
            link.valid = link.error.isEmpty();
            return link;
        }

        // t.me/username
        link.username = value;
        link.valid = isUsername(value);
        link.error = link.valid ? "" : "that link was not understood";
        return link;
    }

    // ------------------------------------------------------------- helpers //

    private static TgLink parseTgScheme(TgLink link, String value) {
        String query = value.contains("?") ? value.substring(value.indexOf('?') + 1) : "";
        String path = value.substring("tg://".length());
        if (path.contains("?")) {
            path = path.substring(0, path.indexOf('?'));
        }
        String domain = "";
        long chatId = 0L;
        long messageId = 0L;
        for (String pair : query.split("&")) {
            int equals = pair.indexOf('=');
            if (equals <= 0) {
                continue;
            }
            String key = pair.substring(0, equals).toLowerCase(Locale.US);
            String raw = pair.substring(equals + 1);
            if ("domain".equals(key)) {
                domain = raw;
            } else if ("chat_id".equals(key)) {
                chatId = parseLong(raw);
            } else if ("message_id".equals(key) || "post".equals(key)) {
                messageId = parseLong(raw);
            }
        }
        if (path.startsWith("openmessage") && chatId != 0L) {
            link.chatId = chatId;
            link.messageId = messageId > 0 ? messageId : 1;
            link.valid = true;
            return link;
        }
        if (!domain.isEmpty()) {
            link.username = domain;
            link.messageId = messageId;
            link.valid = isUsername(domain);
            link.error = link.valid ? "" : "that username looks wrong";
            return link;
        }
        link.error = "that tg:// link was not understood";
        return link;
    }

    /** "145" / "145-200" / "145?single" → the message id(s). */
    private static void applyMessagePart(TgLink link, String part) {
        if (part == null || part.isEmpty()) {
            return;
        }
        String value = part;
        int query = value.indexOf('?');
        if (query >= 0) {
            value = value.substring(0, query);
        }
        int dash = value.indexOf('-');
        if (dash > 0) {
            String start = value.substring(0, dash);
            String end = value.substring(dash + 1);
            if (isNumber(start) && isNumber(end)) {
                link.messageId = parseLong(start);
                link.endMessageId = parseLong(end);
                if (link.messageId <= 0) {
                    link.error = "that message number is not valid";
                } else if (link.endMessageId < link.messageId) {
                    // t.me/channel/500-100 is read as 100-500, like Telegram does.
                    long swap = link.messageId;
                    link.messageId = link.endMessageId;
                    link.endMessageId = swap;
                }
                if (link.isRange() && link.count() >= MAX_RANGE) {
                    //: A cap is not a failure: the first MAX_RANGE messages are
                    //: queued and the screen says so.
                    link.note = "only the first " + MAX_RANGE + " messages of this range are taken";
                    link.endMessageId = link.messageId + MAX_RANGE - 1;
                }
                return;
            }
            link.error = "that range is not valid";
            return;
        }
        if (isNumber(value)) {
            link.messageId = parseLong(value);
            if (link.messageId <= 0) {
                link.error = "that message number is not valid";
            }
            return;
        }
        if (value.equals("single") || value.isEmpty()) {
            return;
        }
        link.error = "that part of the link was not understood";
    }

    private static boolean looksLikeMessagePart(String value) {
        if (value.isEmpty()) {
            return false;
        }
        int dash = value.indexOf('-');
        if (dash > 0) {
            return isNumber(value.substring(0, dash)) && isNumber(value.substring(dash + 1));
        }
        return isNumber(value) && !value.startsWith("-");
    }

    private static String clean(String chunk) {
        String value = chunk.trim();
        //: Quotes and brackets travel with copied links all the time.
        while (value.length() > 0) {
            char first = value.charAt(0);
            char last = value.charAt(value.length() - 1);
            if (first == '"' || first == '\'' || first == '(' || first == '[' || first == '<') {
                value = value.substring(1);
                continue;
            }
            if (last == '"' || last == '\'' || last == ')' || last == ']' || last == '>'
                    || last == '.' || last == ',' || last == ';' || last == '!') {
                value = value.substring(0, value.length() - 1);
                continue;
            }
            break;
        }
        return value.trim();
    }

    private static boolean isNumber(String value) {
        if (value == null || value.isEmpty()) {
            return false;
        }
        int start = value.charAt(0) == '-' ? 1 : 0;
        if (start >= value.length()) {
            return false;
        }
        for (int index = start; index < value.length(); index++) {
            if (!Character.isDigit(value.charAt(index))) {
                return false;
            }
        }
        return true;
    }

    private static boolean isUsername(String value) {
        if (value == null || value.length() < 4 || value.length() > 32) {
            return false;
        }
        for (int index = 0; index < value.length(); index++) {
            char letter = value.charAt(index);
            boolean ok = (letter >= 'a' && letter <= 'z') || (letter >= 'A' && letter <= 'Z')
                    || (letter >= '0' && letter <= '9') || letter == '_';
            if (!ok) {
                return false;
            }
        }
        return true;
    }

    private static long parseLong(String value) {
        try {
            return Long.parseLong(value);
        } catch (Exception exc) {
            return 0L;
        }
    }
}
