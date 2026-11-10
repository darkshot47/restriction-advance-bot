package com.vmore.app;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Pure matching logic for Smart Feature: decides send permissions for chats,
 * matches visible chat headers and rows to TDLib chats, and scores candidate
 * Telegram media messages against what sits underneath the white pointer circle.
 */
public final class SmartMatcher {

    public static final String ROLE_CREATOR = "creator";
    public static final String ROLE_ADMIN = "admin";
    public static final String ROLE_MEMBER = "member";
    public static final String ROLE_RESTRICTED = "restricted";
    public static final String ROLE_NONE = "none";

    private static final Pattern CLOCK_PATTERN = Pattern.compile(
            "\\b(\\d{1,2}:\\d{2})(?:\\s{0,4}([AaPp][Mm]))?\\b");
    private static final Pattern FILE_PATTERN = Pattern.compile(
            "([A-Za-z0-9_\\-\\. ]{2,80}\\.(?:mp4|mkv|mov|avi|webm|pdf|zip|rar|7z|apk|mp3|m4a|flac|ogg|wav|jpg|jpeg|png|webp|epub|docx|pptx|xlsx|txt))",
            Pattern.CASE_INSENSITIVE);

    /** Metadata of one candidate media message inside a Telegram chat. */
    public static final class Candidate {
        public long messageId;
        public String name = "";
        public String caption = "";
        public String kind = "document";
        public long size;
        public long durationSec;
        public long unixDateSec;
    }

    private SmartMatcher() {
    }

    /** True when non-admin members of a chat are permitted to post media or text. */
    public static boolean canSendPermissions(boolean basicMessages, boolean documents,
                                             boolean videos, boolean photos) {
        return basicMessages || documents || videos || photos;
    }

    /** Send-access rule for channels and supergroups. */
    public static boolean canSendSupergroup(boolean isChannel, String role,
                                            boolean adminCanPost, boolean memberAllowed) {
        if (ROLE_CREATOR.equals(role)) {
            return true;
        }
        if (ROLE_ADMIN.equals(role)) {
            return !isChannel || adminCanPost;
        }
        if (ROLE_MEMBER.equals(role) || ROLE_RESTRICTED.equals(role)) {
            return !isChannel && memberAllowed;
        }
        return false;
    }

    /** Send-access rule for basic groups. */
    public static boolean canSendBasicGroup(boolean active, String role, boolean memberAllowed) {
        if (!active) {
            return false;
        }
        if (ROLE_CREATOR.equals(role) || ROLE_ADMIN.equals(role)) {
            return true;
        }
        if (ROLE_MEMBER.equals(role) || ROLE_RESTRICTED.equals(role)) {
            return memberAllowed;
        }
        return false;
    }

    /** Exact send-access rule for broadcast channels. */
    public static boolean canSendToChannel(boolean isCreator, boolean isAdmin,
                                           boolean adminCanPost) {
        return isCreator || (isAdmin && adminCanPost);
    }

    /** Exact send-access rule for supergroups and basic groups. */
    public static boolean canSendToGroup(boolean isCreator, boolean isAdmin,
                                         boolean isMember, boolean isRestrictedMember,
                                         boolean chatCanSend, boolean memberCanSend) {
        if (isCreator || isAdmin) {
            return true;
        }
        if (isRestrictedMember) {
            return chatCanSend && memberCanSend;
        }
        if (isMember) {
            return chatCanSend;
        }
        return false;
    }

    /** Exact send-access rule for 1-to-1 private user chats. */
    public static boolean canSendToPrivateUser(boolean isDeletedOrUnknown,
                                               boolean chatCanSend) {
        return !isDeletedOrUnknown && chatCanSend;
    }

    /** Normalized lowercase title for exact/fuzzy comparison. */
    public static String normalizeTitle(String raw) {
        return cleanTitle(raw).toLowerCase(Locale.US);
    }

    /** Alias used by accessibility header filtering. */
    public static boolean isSubtitleNoise(String text) {
        return isHeaderNoise(text);
    }

    /** Alias used by chat ranking in Tg and tests. */
    public static int scoreChatTitle(String screenText, String chatTitle, String username) {
        return titleMatchScore(screenText, chatTitle, username);
    }

    /** Extracts approximate byte size from bubble text like "48.2 MB" or "1.4 GB". */
    public static long extractSizeBytes(List<String> lines) {
        if (lines == null) {
            return 0L;
        }
        Pattern p = Pattern.compile("\\b(\\d+(?:\\.\\d+)?)\\s{0,4}(B|KB|MB|GB)\\b",
                Pattern.CASE_INSENSITIVE);
        for (String line : lines) {
            if (line == null) {
                continue;
            }
            Matcher m = p.matcher(line);
            if (m.find()) {
                try {
                    double v = Double.parseDouble(m.group(1));
                    String unit = m.group(2).toUpperCase(Locale.US);
                    switch (unit) {
                        case "GB":
                            return (long) (v * 1024L * 1024L * 1024L);
                        case "MB":
                            return (long) (v * 1024L * 1024L);
                        case "KB":
                            return (long) (v * 1024L);
                        default:
                            return (long) v;
                    }
                } catch (NumberFormatException ignored) {
                }
            }
        }
        return 0L;
    }

    /** Extracts duration in seconds from bubble badges like "02:35" or "1:04:12". */
    public static long extractDurationSec(List<String> lines) {
        if (lines == null) {
            return 0L;
        }
        Pattern p = Pattern.compile("\\b(?:(\\d{1,2}):)?(\\d{1,2}):(\\d{2})\\b");
        for (String line : lines) {
            if (line == null || line.toLowerCase(Locale.US).contains("am")
                    || line.toLowerCase(Locale.US).contains("pm")) {
                continue;
            }
            Matcher m = p.matcher(line);
            if (m.find()) {
                try {
                    long h = m.group(1) == null ? 0L : Long.parseLong(m.group(1));
                    long min = Long.parseLong(m.group(2));
                    long sec = Long.parseLong(m.group(3));
                    return h * 3600L + min * 60L + sec;
                } catch (NumberFormatException ignored) {
                }
            }
        }
        return 0L;
    }

    /** Convenience overload scoring flat message properties directly. */
    public static int scoreMessage(List<String> targetLines, int cellIndexFromBottom,
                                   int indexFromNewest, String name, String caption,
                                   String kind, long size, long durationSec,
                                   long unixDateSec) {
        Candidate c = new Candidate();
        c.name = name == null ? "" : name;
        c.caption = caption == null ? "" : caption;
        c.kind = kind == null ? "" : kind;
        c.size = size;
        c.durationSec = durationSec;
        c.unixDateSec = unixDateSec;
        return scoreMessage(c, targetLines, 0L, indexFromNewest, cellIndexFromBottom);
    }

    /** Strip bidi markers and collapse whitespace. */
    public static String cleanTitle(String raw) {
        if (raw == null) {
            return "";
        }
        String value = raw
                .replace("\u200E", "")
                .replace("\u200F", "")
                .replace("\u202A", "")
                .replace("\u202C", "")
                .replace('\n', ' ')
                .replaceAll("\\s+", " ")
                .trim();
        return value;
    }

    /** True when a header string is status noise rather than a chat title. */
    public static boolean isHeaderNoise(String text) {
        String clean = cleanTitle(text);
        if (clean.isEmpty()) {
            return true;
        }
        String lower = clean.toLowerCase(Locale.US);
        if (clean.matches("^\\d+$") || clean.matches("^\\d{1,2}:\\d{2}(\\s{0,4}[AaPp][Mm])?$")
                || clean.matches("^\\d+%$")) {
            return true;
        }
        return lower.equals("telegram")
                || lower.equals("plus messenger")
                || lower.equals("nekogram")
                || lower.equals("search")
                || lower.equals("back")
                || lower.equals("go back")
                || lower.equals("navigate up")
                || lower.equals("more options")
                || lower.equals("mute")
                || lower.equals("unmute")
                || lower.contains("subscriber")
                || lower.contains("members")
                || lower.equals("online")
                || lower.startsWith("last seen")
                || lower.contains("typing");
    }

    /** How strongly screen text names a given chat (0 means no match). */
    public static int titleMatchScore(String screenText, String chatTitle, String username) {
        String probe = cleanTitle(screenText).toLowerCase(Locale.US);
        String title = cleanTitle(chatTitle).toLowerCase(Locale.US);
        String handle = username == null ? "" : username.trim().replace("@", "").toLowerCase(Locale.US);
        if (probe.isEmpty()) {
            return 0;
        }
        if (!title.isEmpty()) {
            if (probe.equals(title)) {
                return 100;
            }
            if (probe.startsWith(title + " ") || probe.startsWith(title + ",")) {
                return 88;
            }
            if (title.length() >= 3 && probe.contains(title)) {
                return 74;
            }
            if (probe.length() >= 4 && title.startsWith(probe)) {
                return 68;
            }
        }
        if (!handle.isEmpty()) {
            if (probe.equals(handle) || probe.equals("@" + handle)
                    || probe.contains("t.me/" + handle)) {
                return 92;
            }
        }
        return 0;
    }

    /** Pull out the best query token for server-side message search in TDLib. */
    public static String extractSearchQuery(List<String> lines) {
        if (lines == null || lines.isEmpty()) {
            return "";
        }
        String joined = String.join("\n", lines);
        Matcher fileMatch = FILE_PATTERN.matcher(joined);
        if (fileMatch.find()) {
            String fileName = fileMatch.group(1).trim();
            String stem = Format.withoutExtension(fileName).replace('_', ' ').replace('-', ' ').trim();
            return stem.length() >= 3 ? stem : fileName;
        }
        String best = "";
        for (String raw : lines) {
            if (raw == null) {
                continue;
            }
            for (String line : raw.split("\\n")) {
                String cleaned = line
                        .replaceAll("\\b\\d{1,2}:\\d{2}(\\s{0,4}[AaPp][Mm])?\\b", " ")
                        .replaceAll("\\b\\d+(\\.\\d+)?\\s{0,4}(B|KB|MB|GB)\\b", " ")
                        .replaceAll("\\s+", " ")
                        .trim();
                if (cleaned.length() >= 4 && cleaned.length() > best.length()
                        && !isHeaderNoise(cleaned)) {
                    best = cleaned;
                }
            }
        }
        if (best.length() > 48) {
            best = best.substring(0, 48).trim();
        }
        return best;
    }

    /** Extract visible clock times (both 24h and 12h equivalents) from bubble text. */
    public static List<String> extractClockTimes(String text) {
        List<String> out = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            return out;
        }
        Matcher matcher = CLOCK_PATTERN.matcher(text);
        while (matcher.find()) {
            String rawClock = matcher.group(1);
            String ampm = matcher.group(2);
            String[] parts = rawClock.split(":");
            if (parts.length != 2) {
                continue;
            }
            try {
                int hour = Integer.parseInt(parts[0]);
                int minute = Integer.parseInt(parts[1]);
                if (minute < 0 || minute > 59 || hour < 0 || hour > 23) {
                    continue;
                }
                if (ampm != null) {
                    boolean pm = ampm.equalsIgnoreCase("pm");
                    if (hour == 12) {
                        hour = pm ? 12 : 0;
                    } else if (pm) {
                        hour += 12;
                    }
                    addUnique(out, String.format(Locale.US, "%02d:%02d", hour, minute));
                } else {
                    addUnique(out, String.format(Locale.US, "%02d:%02d", hour, minute));
                    if (hour >= 1 && hour <= 11) {
                        addUnique(out, String.format(Locale.US, "%02d:%02d", hour + 12, minute));
                    } else if (hour == 12) {
                        addUnique(out, String.format(Locale.US, "00:%02d", minute));
                    }
                }
            } catch (NumberFormatException ignored) {
            }
        }
        return out;
    }

    private static void addUnique(List<String> list, String value) {
        if (!list.contains(value)) {
            list.add(value);
        }
    }

    /** Score one TDLib media message against the UI node under the pointer circle. */
    public static int scoreMessage(Candidate candidate, List<String> targetLines,
                                   long anchoredMessageId, int indexFromNewest,
                                   int cellIndexFromBottom) {
        if (candidate == null) {
            return 0;
        }
        int score = 0;
        if (anchoredMessageId != 0L && candidate.messageId == anchoredMessageId) {
            score += 135;
        }
        String combined = targetLines == null ? "" : String.join(" ", targetLines);
        String hay = combined.toLowerCase(Locale.US);

        String fileName = candidate.name == null ? "" : candidate.name.trim().toLowerCase(Locale.US);
        if (!fileName.isEmpty() && !fileName.startsWith("vmore_") && !fileName.equals("photo.jpg")) {
            if (hay.contains(fileName)) {
                score += 120;
            } else {
                String stem = Format.withoutExtension(fileName).replace('_', ' ').trim();
                if (stem.length() >= 4 && hay.replace('_', ' ').contains(stem)) {
                    score += 95;
                }
            }
        }

        String caption = candidate.caption == null ? "" : candidate.caption.trim().toLowerCase(Locale.US);
        if (!caption.isEmpty()) {
            String firstLine = caption.split("\\n")[0].trim();
            if (firstLine.length() >= 4 && hay.contains(firstLine)) {
                score += 105;
            } else {
                int matchedWords = 0;
                int checkedWords = 0;
                for (String token : firstLine.split("\\s+")) {
                    if (token.length() < 4) {
                        continue;
                    }
                    checkedWords++;
                    if (hay.contains(token)) {
                        matchedWords++;
                    }
                }
                if (checkedWords > 0 && matchedWords > 0) {
                    score += Math.min(80, matchedWords * 25);
                }
            }
        }

        if (candidate.size > 0) {
            String formattedSize = Format.size(candidate.size).toLowerCase(Locale.US);
            if (hay.contains(formattedSize)) {
                score += 55;
            }
        }

        if (candidate.durationSec > 0) {
            String clock = Format.clock(candidate.durationSec);
            String shortClock = clock.startsWith("0") ? clock.substring(1) : clock;
            if (hay.contains(clock) || hay.contains(shortClock)) {
                score += 50;
            }
        }

        if (candidate.unixDateSec > 0) {
            String hhmm = new SimpleDateFormat("HH:mm", Locale.US)
                    .format(new Date(candidate.unixDateSec * 1000L));
            List<String> clocks = extractClockTimes(combined);
            if (clocks.contains(hhmm)) {
                score += 48;
            }
        }

        if ("video".equals(candidate.kind) && (hay.contains("video") || hay.contains(".mp4")
                || hay.contains(".mkv"))) {
            score += 14;
        } else if ("photo".equals(candidate.kind) && (hay.contains("photo") || hay.contains("image"))) {
            score += 14;
        } else if ("audio".equals(candidate.kind) && (hay.contains("audio") || hay.contains("voice"))) {
            score += 14;
        }

        if (indexFromNewest >= 0 && cellIndexFromBottom >= 0) {
            int distance = Math.abs(indexFromNewest - cellIndexFromBottom);
            if (distance == 0) {
                score += 34;
            } else if (distance == 1) {
                score += 18;
            } else if (distance == 2) {
                score += 8;
            }
        }
        return score;
    }
}
