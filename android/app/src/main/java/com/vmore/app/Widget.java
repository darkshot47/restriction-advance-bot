package com.vmore.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/**
 * The home-screen widget: one tap to pause or resume the queue, one tap to open
 * it.  It reads the same live state the screens do, so it never lies about what
 * the queue is doing.
 */
public class Widget extends AppWidgetProvider {

    public static final String ACTION_TOGGLE = "com.vmore.app.WIDGET_TOGGLE";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) {
            manager.updateAppWidget(id, build(context));
        }
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (intent != null && ACTION_TOGGLE.equals(intent.getAction())) {
            if (Jobs.get(context).pausedAll()) {
                QueueService.resumeAll(context);
            } else {
                QueueService.pauseAll(context);
            }
        }
        repaint(context);
    }

    private static long lastTouch;

    /**
     * Called by the queue whenever the state changes: the widget and the Quick
     * Settings tile catch up.  Progress ticks come thick and fast, so the work
     * happens at most once a second.
     */
    public static void touch(Context context) {
        long now = System.currentTimeMillis();
        if (now - lastTouch < 1000L) {
            return;
        }
        lastTouch = now;
        repaint(context);
        try {
            android.service.quicksettings.TileService.requestListeningState(context,
                    new ComponentName(context, QSTile.class));
        } catch (Exception ignored) {
        }
    }

    /** Called by the queue whenever the state changes. */
    public static void repaint(Context context) {
        try {
            AppWidgetManager manager = AppWidgetManager.getInstance(context);
            int[] ids = manager.getAppWidgetIds(new ComponentName(context, Widget.class));
            for (int id : ids) {
                manager.updateAppWidget(id, build(context));
            }
        } catch (Exception ignored) {
        }
    }

    private static RemoteViews build(Context context) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_queue);
        Jobs jobs = Jobs.get(context);
        boolean paused = jobs.pausedAll();
        String stage = Ui.stageLabel(QueueService.Live.STAGE);
        String name = QueueService.Live.NAME;
        if (name == null || name.isEmpty()) {
            name = paused ? context.getString(R.string.common_paused)
                    : context.getString(R.string.stats_queue);
        }
        views.setTextViewText(R.id.widgetTitle, name);
        views.setTextViewText(R.id.widgetLine, jobs.size() + " \u2022 "
                + (stage.isEmpty() ? context.getString(R.string.common_queued) : stage));
        views.setTextViewText(R.id.widgetToggle,
                paused ? context.getString(R.string.queue_resume_all)
                        : context.getString(R.string.queue_pause_all));

        Intent toggle = new Intent(context, Widget.class).setAction(ACTION_TOGGLE);
        views.setOnClickPendingIntent(R.id.widgetToggle, PendingIntent.getBroadcast(context, 11,
                toggle, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        Intent open = new Intent(context, QueueActivity.class);
        views.setOnClickPendingIntent(R.id.widgetOpen, PendingIntent.getActivity(context, 12,
                open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        return views;
    }
}
