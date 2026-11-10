package com.vmore.app;

import java.util.Locale;

/**
 * Pure text formatting for the whole app — sizes, durations, dates, speeds.
 *
 * Kept free of Android types on purpose: these are the numbers users read all
 * day, so they are unit tested on the JVM.
 */
public final class Format {

    private Format() {
    }

    /** 1234567 → "1.2 MB". */
    public static String size(long bytes) {
        if (bytes <= 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        double value = bytes;
        int unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit++;
        }
        if (unit == 0 || value >= 100) {
            return String.format(Locale.US, "%.0f %s", value, units[unit]);
        }
        return String.format(Locale.US, "%.1f %s", value, units[unit]);
    }

    /** Milliseconds → "12:04" or "1:02:33". */
    public static String duration(long millis) {
        if (millis <= 0) {
            return "00:00";
        }
        long total = millis / 1000;
        long hours = total / 3600;
        long minutes = (total % 3600) / 60;
        long seconds = total % 60;
        if (hours > 0) {
            return String.format(Locale.US, "%d:%02d:%02d", hours, minutes, seconds);
        }
        return String.format(Locale.US, "%02d:%02d", minutes, seconds);
    }

    /** Seconds (player position) → "01:23" / "1:02:33". */
    public static String clock(double seconds) {
        return duration((long) (seconds * 1000));
    }

    /** Transfer speed of a finished or running job. */
    public static String speed(double bytesPerSecond) {
        if (bytesPerSecond <= 0) {
            return "";
        }
        return size((long) bytesPerSecond) + "/s";
    }

    /** Remaining time from a speed measurement, or "" when it is unknown. */
    public static String eta(long done, long total, double bytesPerSecond) {
        if (total <= 0 || bytesPerSecond <= 0 || done >= total) {
            return "";
        }
        long seconds = (long) ((total - done) / bytesPerSecond);
        if (seconds <= 0) {
            return "";
        }
        if (seconds < 60) {
            return seconds + "s left";
        }
        if (seconds < 3600) {
            return (seconds / 60) + "m " + (seconds % 60) + "s left";
        }
        return (seconds / 3600) + "h " + ((seconds % 3600) / 60) + "m left";
    }

    public static int percent(long done, long total) {
        if (total <= 0) {
            return 0;
        }
        long value = done * 100 / total;
        if (value < 0) {
            return 0;
        }
        return value > 100 ? 100 : (int) value;
    }

    /** "today 14:20", "yesterday 09:05", "12 Oct 18:40". */
    public static String when(long millis) {
        if (millis <= 0) {
            return "";
        }
        java.util.Calendar then = java.util.Calendar.getInstance();
        then.setTimeInMillis(millis);
        java.util.Calendar now = java.util.Calendar.getInstance();
        String time = String.format(Locale.US, "%02d:%02d",
                then.get(java.util.Calendar.HOUR_OF_DAY), then.get(java.util.Calendar.MINUTE));
        long dayThen = dayNumber(then);
        long dayNow = dayNumber(now);
        if (dayThen == dayNow) {
            return "today " + time;
        }
        if (dayThen == dayNow - 1) {
            return "yesterday " + time;
        }
        String[] months = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
        String date = then.get(java.util.Calendar.DAY_OF_MONTH) + " "
                + months[then.get(java.util.Calendar.MONTH)];
        if (then.get(java.util.Calendar.YEAR) != now.get(java.util.Calendar.YEAR)) {
            date = date + " " + then.get(java.util.Calendar.YEAR);
        }
        return date + " " + time;
    }

    private static long dayNumber(java.util.Calendar calendar) {
        return calendar.get(java.util.Calendar.YEAR) * 1000L
                + calendar.get(java.util.Calendar.DAY_OF_YEAR);
    }

    /**
     * A caption turned into a file stem.
     *
     * Captions are how most Telegram posts name their media, so the first real
     * line of the caption is the most honest file name available.  It is
     * reduced to what every phone and Telegram itself can display: no path
     * separators, no reserved characters, no runs of spaces, no trailing dots
     * and no length beyond {@code limit}.
     */
    public static String stemFrom(String text, int limit) {
        //: Only the first non-empty line names the file: a caption's second line
        //: is usually a credit or a link, not part of the name.
        String value = "";
        if (text != null) {
            for (String line : text.split("\n")) {
                String trimmed = oneLine(line);
                if (!trimmed.isEmpty()) {
                    value = oneLine(trimmed);
                    break;
                }
            }
        }
        if (value.isEmpty()) {
            return "";
        }
        StringBuilder out = new StringBuilder(value.length());
        boolean lastSpace = false;
        for (int index = 0; index < value.length(); index++) {
            char char0 = value.charAt(index);
            boolean illegal = char0 < 0x20
                    || char0 == '\\' || char0 == '/' || char0 == ':'
                    || char0 == '?' || char0 == 0x22 || char0 == '<'
                    || char0 == '>' || char0 == '|' || char0 == 0x2A;
            if (illegal) {
                continue;
            }
            boolean space = char0 == ' ';
            if (space && lastSpace) {
                continue;
            }
            lastSpace = space;
            out.append(char0);
        }
        String stem = out.toString().trim();
        while (stem.endsWith(".")) {
            stem = stem.substring(0, stem.length() - 1).trim();
        }
        if (stem.length() > limit) {
            stem = stem.substring(0, limit).trim();
        }
        //: A dot is allowed inside a caption but a leading one hides the file
        //: on every phone, so a stem never starts with it.
        while (stem.startsWith(".")) {
            stem = stem.substring(1).trim();
        }
        return stem;
    }

    /**
     * A readable name for media Telegram did not name itself.
     *
     * Photos, voice notes, video notes and plenty of forwarded documents carry
     * no file name at all.  The old build filled that gap with an internal id
     * ("vmore_4838") which then showed up in every chat the file was sent to.
     * The date and time of the post is stable, unique enough and says something
     * a person can read, so the fallback is "photo_2026-10-20_143012.jpg".
     */
    public static String datedName(String kind, long unixSeconds, String extension) {
        String label = oneLine(kind).toLowerCase(Locale.US).replace(' ', '_');
        if (label.isEmpty()) {
            label = "file";
        }
        String suffix = extension == null || extension.isEmpty()
                ? "" : (extension.charAt(0) == '.' ? extension : "." + extension);
        java.util.Calendar stamp = java.util.Calendar.getInstance();
        stamp.setTimeInMillis(unixSeconds > 0 ? unixSeconds * 1000L
                : System.currentTimeMillis());
        String when = String.format(Locale.US, "%04d-%02d-%02d_%02d%02d%02d",
                stamp.get(java.util.Calendar.YEAR),
                stamp.get(java.util.Calendar.MONTH) + 1,
                stamp.get(java.util.Calendar.DAY_OF_MONTH),
                stamp.get(java.util.Calendar.HOUR_OF_DAY),
                stamp.get(java.util.Calendar.MINUTE),
                stamp.get(java.util.Calendar.SECOND));
        return label + "_" + when + suffix;
    }

    /**
     * The name a chat should show for a file that has arrived from anywhere.
     *
     * Older builds wrote {@code vmore_4838.mp4} / {@code vmore_1729_now.jpg}
     * into the upload path, and Telegram takes the file name straight from that
     * path.  Anything that still carries the prefix is cleaned here, so a job
     * that was queued before the fix is uploaded with a readable name too.
     */
    public static String displayName(String name, String fallback) {
        String value = safeName(name, fallback);
        String lower = value.toLowerCase(Locale.US);
        if (lower.startsWith("vmore_")) {
            String rest = value.substring("vmore_".length());
            int cut = rest.indexOf('_');
            //: "vmore_4838_holiday.mp4" → "holiday.mp4"
            if (cut > 0 && cut < rest.length() - 1 && isDigits(rest.substring(0, cut))) {
                String tail = rest.substring(cut + 1).trim();
                if (!tail.isEmpty()) {
                    return tail;
                }
            }
            //: "vmore_4838.mp4" → "4838.mp4" (still better than the prefix)
            if (rest.startsWith("vmore_")) {
                return rest;
            }
            return rest.isEmpty() ? value : rest;
        }
        return value;
    }

    private static boolean isDigits(String text) {
        if (text.isEmpty()) {
            return false;
        }
        for (int index = 0; index < text.length(); index++) {
            if (!Character.isDigit(text.charAt(index))) {
                return false;
            }
        }
        return true;
    }

    /** A file name that is safe on every phone and readable in a chat. */
    public static String safeName(String name, String fallback) {
        String value = name == null ? "" : name.trim();
        if (value.isEmpty()) {
            value = fallback == null ? "Vmore" : fallback;
        }
        value = value.replace('/', '_').replace('\\', '_').replace(':', '_');
        return value;
    }

    /** The file name without its extension — a good default caption. */
    public static String withoutExtension(String name) {
        if (name == null) {
            return "";
        }
        int dot = name.lastIndexOf('.');
        return dot <= 0 ? name : name.substring(0, dot);
    }

    /** A short, readable label for a chat: a long title is trimmed once. */
    public static String oneLine(String text) {
        if (text == null) {
            return "";
        }
        String value = text.trim().replace('\n', ' ');
        while (value.contains("  ")) {
            value = value.replace("  ", " ");
        }
        return value;
    }
}
