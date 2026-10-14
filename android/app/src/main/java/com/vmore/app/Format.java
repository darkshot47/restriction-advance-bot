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
