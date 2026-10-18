package com.vmore.app;

import android.content.Context;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The numbers behind the app, and the memory of what was already uploaded.
 *
 * Everything is worked out from the history Vmore already keeps, so the
 * dashboard never disagrees with the list below it.  The duplicate index is the
 * one thing stored here: a small set of "file id and size" keys that lets the
 * queue skip a file that has already been sent once.
 */
final class Stats {

    private static final String KEY_SEEN = "seen_uploads";
    private static final int MAX_SEEN = 4000;

    /** One day of the little bar chart. */
    static final class Day {
        public long start;
        public int uploaded;
        public int downloaded;
        public int failed;

        public int total() {
            return uploaded + downloaded + failed;
        }
    }

    /** One destination chat with its share of the work. */
    static final class Chat {
        public String title = "";
        public int count;
        public long bytes;
    }

    static final class Totals {
        public int uploaded;
        public int downloaded;
        public int failed;
        public int queueSize;
        public long uploadedBytes;
        public long downloadedBytes;
        public long savedBytes;
        public long localBytes;
        public long averageBytes;
        public long firstWhen;
        public long lastWhen;
        public final List<Chat> chats = new ArrayList<>();
    }

    private Stats() {
    }

    static Totals totals(Context context) {
        Totals totals = new Totals();
        History history = History.get(context);
        Map<String, Chat> byChat = new LinkedHashMap<>();
        for (History.Entry entry : history.all()) {
            if (History.STATUS_UPLOADED.equals(entry.status)) {
                totals.uploaded++;
                totals.uploadedBytes += entry.size;
            } else if (History.STATUS_DOWNLOADED.equals(entry.status)) {
                totals.downloaded++;
                totals.downloadedBytes += entry.size;
            } else if (History.STATUS_FAILED.equals(entry.status)) {
                totals.failed++;
            } else {
                totals.downloaded++;
                totals.downloadedBytes += entry.size;
            }
            if (!entry.local) {
                totals.savedBytes += entry.size;
            } else {
                totals.localBytes += entry.size;
            }
            if (entry.when > 0) {
                if (totals.firstWhen == 0L || entry.when < totals.firstWhen) {
                    totals.firstWhen = entry.when;
                }
                if (entry.when > totals.lastWhen) {
                    totals.lastWhen = entry.when;
                }
            }
            String key = entry.destTitle == null || entry.destTitle.isEmpty()
                    ? "unknown chat" : entry.destTitle;
            Chat chat = byChat.get(key);
            if (chat == null) {
                chat = new Chat();
                chat.title = key;
                byChat.put(key, chat);
            }
            chat.count++;
            chat.bytes += entry.size;
        }
        int done = totals.uploaded + totals.downloaded;
        totals.averageBytes = done == 0 ? 0 : (totals.uploadedBytes + totals.downloadedBytes) / done;
        List<Chat> chats = new ArrayList<>(byChat.values());
        chats.sort((left, right) -> Integer.compare(right.count, left.count));
        for (int index = 0; index < chats.size() && index < 6; index++) {
            totals.chats.add(chats.get(index));
        }
        totals.queueSize = Jobs.get(context).size();
        return totals;
    }

    /** The last seven days, oldest first. */
    static List<Day> week(Context context) {
        List<Day> days = new ArrayList<>();
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.HOUR_OF_DAY, 0);
        calendar.set(Calendar.MINUTE, 0);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        long today = calendar.getTimeInMillis();
        for (int index = 6; index >= 0; index--) {
            Day day = new Day();
            day.start = today - index * 24L * 60L * 60L * 1000L;
            days.add(day);
        }
        for (History.Entry entry : History.get(context).all()) {
            if (entry.when <= 0) {
                continue;
            }
            for (Day day : days) {
                if (entry.when >= day.start && entry.when < day.start + 24L * 60L * 60L * 1000L) {
                    if (History.STATUS_UPLOADED.equals(entry.status)) {
                        day.uploaded++;
                    } else if (History.STATUS_FAILED.equals(entry.status)) {
                        day.failed++;
                    } else {
                        day.downloaded++;
                    }
                    break;
                }
            }
        }
        return days;
    }

    static int largest(Day day) {
        return Math.max(1, Math.max(day.uploaded + day.downloaded + day.failed, 1));
    }

    // ----------------------------------------------------- duplicate index //

    private static String key(String fileId, long size) {
        return fileId + ":" + size;
    }

    /** True when this very file has already been sent to a chat. */
    static boolean alreadyUploaded(Context context, String fileId, long size) {
        if (fileId == null || fileId.isEmpty() || size <= 0) {
            return false;
        }
        Set<String> seen = seen(context);
        return seen != null && seen.contains(key(fileId, size));
    }

    static void rememberUploaded(Context context, String fileId, long size) {
        if (fileId == null || fileId.isEmpty() || size <= 0) {
            return;
        }
        Set<String> seen = seen(context);
        if (seen == null) {
            return;
        }
        if (seen.size() >= MAX_SEEN) {
            seen.clear();
        }
        seen.add(key(fileId, size));
        context.getSharedPreferences("vmore", Context.MODE_PRIVATE)
                .edit().putStringSet(KEY_SEEN, seen).apply();
    }

    private static Set<String> seen(Context context) {
        Set<String> stored = context.getSharedPreferences("vmore", Context.MODE_PRIVATE)
                .getStringSet(KEY_SEEN, null);
        //: The set handed out by SharedPreferences must not be changed, so the
        //: index is always copied before it is written back.
        return stored == null ? new java.util.HashSet<>() : new java.util.HashSet<>(stored);
    }
}
