package com.vmore.app;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * The dashboard: how much has moved through this phone, how much space the
 * automatic cleanup has given back, and a small blue bar chart of the last
 * seven days.
 *
 * Every number is worked out from the history Vmore already keeps.
 */
public class StatsActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_stats);
        if (findViewById(R.id.backButton) != null) {
            findViewById(R.id.backButton).setOnClickListener(v -> finish());
        }
        Anim.pageIn(findViewById(R.id.screenHeader));
        render();
    }

    private void render() {
        LinearLayout box = findViewById(R.id.statsBox);
        box.removeAllViews();
        Stats.Totals totals = Stats.totals(this);

        if (totals.uploaded + totals.downloaded + totals.failed == 0) {
            TextView empty = Ui.subtitle(this, getString(R.string.stats_empty));
            empty.setPadding(0, Ui.dp(this, 12), 0, 0);
            box.addView(empty);
            Anim.fadeIn(empty, 240);
            return;
        }

        box.addView(Ui.section(this, getString(R.string.stats_overview)));
        addNumber(box, getString(R.string.stats_uploaded), String.valueOf(totals.uploaded));
        addNumber(box, getString(R.string.stats_downloaded), String.valueOf(totals.downloaded));
        addNumber(box, getString(R.string.stats_failed), String.valueOf(totals.failed));
        addNumber(box, getString(R.string.stats_bytes_up), Format.size(totals.uploadedBytes));
        addNumber(box, getString(R.string.stats_bytes_down), Format.size(totals.downloadedBytes));
        addNumber(box, getString(R.string.stats_saved), Format.size(totals.savedBytes));
        addNumber(box, getString(R.string.stats_on_phone), Format.size(totals.localBytes));
        addNumber(box, getString(R.string.stats_average), Format.size(totals.averageBytes));
        addNumber(box, getString(R.string.stats_queue), String.valueOf(totals.queueSize));
        if (totals.lastWhen > 0) {
            addNumber(box, getString(R.string.stats_last), Format.when(totals.lastWhen));
        }

        box.addView(Ui.section(this, getString(R.string.stats_week)));
        box.addView(chart(Stats.week(this)));

        if (!totals.chats.isEmpty()) {
            box.addView(Ui.section(this, getString(R.string.stats_chats)));
            for (Stats.Chat chat : totals.chats) {
                View row = Ui.row(this, R.drawable.ic_chat, chat.title,
                        chat.count + " jobs \u2022 " + Format.size(chat.bytes));
                box.addView(row);
                box.addView(Ui.divider(this));
            }
        }
        Anim.stagger(box);
    }

    private void addNumber(LinearLayout box, String label, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 8));

        TextView name = new TextView(this);
        name.setText(label);
        name.setTextColor(getColor(R.color.vmore_text_dim));
        name.setTextSize(14f);
        row.addView(name, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        TextView number = new TextView(this);
        number.setText(value);
        number.setTextColor(getColor(R.color.vmore_text));
        number.setTextSize(15f);
        number.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        row.addView(number);
        box.addView(row);
    }

    /** Seven bars, one per day, scaled to the busiest day. */
    private View chart(List<Stats.Day> days) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.BOTTOM);
        row.setPadding(0, Ui.dp(this, 8), 0, 0);
        int busiest = 1;
        for (Stats.Day day : days) {
            busiest = Math.max(busiest, day.total());
        }
        SimpleDateFormat format = new SimpleDateFormat("EEE", Locale.getDefault());
        for (Stats.Day day : days) {
            LinearLayout column = new LinearLayout(this);
            column.setOrientation(LinearLayout.VERTICAL);
            column.setGravity(Gravity.CENTER_HORIZONTAL);
            column.setLayoutParams(new LinearLayout.LayoutParams(0,
                    LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

            TextView count = new TextView(this);
            count.setText(day.total() == 0 ? "" : String.valueOf(day.total()));
            count.setTextColor(getColor(R.color.vmore_text_faint));
            count.setTextSize(11f);
            column.addView(count);

            View bar = new View(this);
            int height = day.total() == 0 ? Ui.dp(this, 3)
                    : Ui.dp(this, 6 + 54f * day.total() / busiest);
            LinearLayout.LayoutParams barParams =
                    new LinearLayout.LayoutParams(Ui.dp(this, 18), height);
            barParams.setMargins(0, Ui.dp(this, 4), 0, Ui.dp(this, 4));
            bar.setLayoutParams(barParams);
            bar.setBackgroundResource(day.total() == 0 ? R.drawable.bg_dot : R.drawable.bg_bar);
            column.addView(bar);

            TextView label = new TextView(this);
            label.setText(format.format(new Date(day.start)));
            label.setTextColor(getColor(R.color.vmore_text_faint));
            label.setTextSize(11f);
            column.addView(label);
            row.addView(column);
        }
        return row;
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
    }

}
