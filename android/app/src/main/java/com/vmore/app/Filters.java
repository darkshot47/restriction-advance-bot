package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/**
 * The batch filter, shared by the home screen and by Settings.
 *
 * A filter decides what a batch keeps: only video, say, and nothing smaller
 * than ten megabytes.  It is applied when a link is read, so a range of five
 * hundred messages can be narrowed down before a single byte is downloaded.
 */
final class Filters {

    private Filters() {
    }

    static void show(final Activity activity, final Runnable changed) {
        final LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(Ui.dp(activity, 20), Ui.dp(activity, 14), Ui.dp(activity, 20), 0);

        TextView title = Ui.section(activity, activity.getString(R.string.filters_kinds));
        box.addView(title);

        final List<String> chosen = new ArrayList<>();
        String current = Prefs.filterKinds(activity);
        if (current != null && !current.isEmpty()) {
            for (String part : current.split(",")) {
                if (!part.trim().isEmpty()) {
                    chosen.add(part.trim());
                }
            }
        }

        final LinearLayout[] rows = new LinearLayout[1];
        rows[0] = new LinearLayout(activity);
        rows[0].setOrientation(LinearLayout.HORIZONTAL);
        box.addView(rows[0]);

        final String[] kinds = {"video", "photo", "audio", "document"};
        final String[] labels = {
                activity.getString(R.string.settings_send_as_video),
                activity.getString(R.string.settings_send_as_photo),
                activity.getString(R.string.common_audio),
                activity.getString(R.string.common_file),
        };
        final Runnable[] repaint = new Runnable[1];
        repaint[0] = () -> {
            rows[0].removeAllViews();
            for (int index = 0; index < kinds.length; index++) {
                final String kind = kinds[index];
                rows[0].addView(Ui.chip(activity, labels[index], chosen.contains(kind), v -> {
                    if (chosen.contains(kind)) {
                        chosen.remove(kind);
                    } else {
                        chosen.add(kind);
                    }
                    repaint[0].run();
                }));
            }
            rows[0].addView(Ui.chip(activity, activity.getString(R.string.filters_all),
                    chosen.isEmpty(), v -> {
                        chosen.clear();
                        repaint[0].run();
                    }));
        };
        repaint[0].run();

        TextView sizeTitle = Ui.section(activity, activity.getString(R.string.filters_size));
        box.addView(sizeTitle);

        final EditText min = sizeField(activity, activity.getString(R.string.filters_min),
                Prefs.filterMinSize(activity));
        final EditText max = sizeField(activity, activity.getString(R.string.filters_max),
                Prefs.filterMaxSize(activity));
        LinearLayout sizes = new LinearLayout(activity);
        sizes.setOrientation(LinearLayout.HORIZONTAL);
        sizes.setGravity(Gravity.CENTER_VERTICAL);
        sizes.addView(min, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        LinearLayout.LayoutParams gap = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        gap.setMargins(Ui.dp(activity, 8), 0, Ui.dp(activity, 8), 0);
        TextView dash = new TextView(activity);
        dash.setText("\u2013");
        dash.setTextColor(activity.getColor(R.color.vmore_text_faint));
        sizes.addView(dash, gap);
        sizes.addView(max, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        box.addView(sizes);

        TextView hint = new TextView(activity);
        hint.setText(R.string.filters_hint);
        hint.setTextColor(activity.getColor(R.color.vmore_text_faint));
        hint.setTextSize(12f);
        hint.setPadding(0, Ui.dp(activity, 10), 0, 0);
        box.addView(hint);

        new AlertDialog.Builder(activity)
                .setTitle(R.string.filters_title)
                .setView(box)
                .setPositiveButton(R.string.common_ok, (dialog, which) -> {
                    StringBuilder builder = new StringBuilder();
                    for (String kind : chosen) {
                        if (builder.length() > 0) {
                            builder.append(',');
                        }
                        builder.append(kind);
                    }
                    Prefs.setFilterKinds(activity, builder.toString());
                    Prefs.setFilterMinSize(activity, megabytes(min));
                    Prefs.setFilterMaxSize(activity, megabytes(max));
                    if (changed != null) {
                        changed.run();
                    }
                })
                .setNeutralButton(R.string.filters_clear, (dialog, which) -> {
                    Prefs.setFilterKinds(activity, "");
                    Prefs.setFilterMinSize(activity, 0L);
                    Prefs.setFilterMaxSize(activity, 0L);
                    if (changed != null) {
                        changed.run();
                    }
                })
                .setNegativeButton(R.string.common_cancel, null)
                .show();
    }

    private static EditText sizeField(Activity activity, String hint, long bytes) {
        EditText field = new EditText(activity);
        field.setHint(hint);
        field.setInputType(InputType.TYPE_CLASS_NUMBER);
        field.setSingleLine(true);
        field.setBackgroundResource(R.drawable.bg_field);
        field.setTextColor(activity.getColor(R.color.vmore_text));
        field.setHintTextColor(activity.getColor(R.color.vmore_text_faint));
        field.setTextSize(14f);
        field.setPadding(Ui.dp(activity, 12), Ui.dp(activity, 10), Ui.dp(activity, 12),
                Ui.dp(activity, 10));
        if (bytes > 0) {
            field.setText(String.valueOf(bytes / (1024L * 1024L)));
        }
        return field;
    }

    private static long megabytes(EditText field) {
        try {
            String text = field.getText().toString().trim();
            if (text.isEmpty()) {
                return 0L;
            }
            return Long.parseLong(text) * 1024L * 1024L;
        } catch (Exception error) {
            return 0L;
        }
    }
}
