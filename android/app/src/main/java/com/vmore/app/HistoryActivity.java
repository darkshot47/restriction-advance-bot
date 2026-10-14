package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.List;

/**
 * Everything the app ever moved — one row per job, with a filter for uploaded
 * and failed ones. Rows whose local copy was auto-deleted stay in the list on
 * purpose: the history is the record, the storage is what gets freed.
 */
public class HistoryActivity extends Activity implements History.Listener {

    private LinearLayout historyList;
    private TextView empty;
    private TextView summary;
    private String filter = "all";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_history);
        historyList = findViewById(R.id.historyList);
        empty = findViewById(R.id.historyEmpty);
        summary = findViewById(R.id.historySummary);

        findViewById(R.id.backButton).setOnClickListener(v -> finish());
        findViewById(R.id.clearButton).setOnClickListener(v -> confirmClear());

        bindFilter(R.id.filterAll, "all");
        bindFilter(R.id.filterUploaded, History.STATUS_UPLOADED);
        bindFilter(R.id.filterFailed, History.STATUS_FAILED);

        Anim.pageIn(findViewById(R.id.historyHeader));
        render();
    }

    private void bindFilter(int viewId, String value) {
        Button button = findViewById(viewId);
        button.setOnClickListener(v -> {
            filter = value;
            paintFilters();
            render();
        });
        Anim.pressible(button);
    }

    private void paintFilters() {
        paintChip(findViewById(R.id.filterAll), "all".equals(filter));
        paintChip(findViewById(R.id.filterUploaded), History.STATUS_UPLOADED.equals(filter));
        paintChip(findViewById(R.id.filterFailed), History.STATUS_FAILED.equals(filter));
    }

    private void paintChip(Button chip, boolean active) {
        chip.setBackgroundResource(active ? R.drawable.bg_chip_active : R.drawable.bg_chip);
        chip.setTextColor(active ? getColor(R.color.vmore_on_accent)
                : getColor(R.color.vmore_text_dim));
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
        History.get(this).addListener(this);
        render();
    }

    @Override
    protected void onPause() {
        History.get(this).removeListener(this);
        super.onPause();
    }

    @Override
    public void onHistoryChanged() {
        render();
    }

    private void render() {
        paintFilters();
        List<History.Entry> entries = History.get(this).byStatus(filter);
        long bytes = 0;
        for (History.Entry entry : entries) {
            bytes += entry.size;
        }
        summary.setText(entries.size() + " entries • " + Format.size(bytes));
        historyList.removeAllViews();
        if (entries.isEmpty()) {
            empty.setVisibility(View.VISIBLE);
            return;
        }
        empty.setVisibility(View.GONE);
        int index = 0;
        for (History.Entry entry : entries) {
            View row = LayoutInflater.from(this).inflate(R.layout.item_history,
                    historyList, false);
            bind(row, entry);
            historyList.addView(row);
            Anim.itemIn(row, index++);
        }
    }

    private void bind(View row, History.Entry entry) {
        ImageView icon = row.findViewById(R.id.historyIcon);
        TextView title = row.findViewById(R.id.historyName);
        TextView info = row.findViewById(R.id.historyInfo);
        TextView status = row.findViewById(R.id.historyStatus);

        icon.setImageResource(Ui.iconForKind(entry.kind));
        title.setText(entry.name.isEmpty() ? "Job" : entry.name);

        StringBuilder builder = new StringBuilder();
        if (entry.size > 0) {
            builder.append(Format.size(entry.size)).append(" • ");
        }
        builder.append(Format.when(entry.when));
        if (!entry.destTitle.isEmpty()) {
            builder.append(" • ").append(entry.destTitle);
        }
        if (History.STATUS_FAILED.equals(entry.status) && !entry.error.isEmpty()) {
            builder.append(" • ").append(entry.error);
        } else if (!entry.local) {
            builder.append(" • local copy removed");
        }
        info.setText(builder.toString());

        if (History.STATUS_FAILED.equals(entry.status)) {
            status.setText(R.string.common_failed);
            status.setTextColor(getColor(R.color.vmore_text));
        } else {
            status.setText(History.STATUS_UPLOADED.equals(entry.status)
                    ? "uploaded" : "downloaded");
            status.setTextColor(getColor(R.color.vmore_blue));
        }

        row.setOnClickListener(v -> open(entry));
        row.setOnLongClickListener(v -> {
            confirmDelete(entry);
            return true;
        });
        Anim.pressible(row);
    }

    private void open(History.Entry entry) {
        if (entry.local && LocalFiles.exists(entry.path)) {
            Intent intent = new Intent(this, ViewerActivity.class);
            intent.putExtra("path", entry.path);
            startActivity(intent);
            return;
        }
        showDetails(entry);
    }

    private void showDetails(History.Entry entry) {
        StringBuilder message = new StringBuilder();
        message.append("File: ").append(entry.name).append('\n');
        if (entry.size > 0) {
            message.append("Size: ").append(Format.size(entry.size)).append('\n');
        }
        message.append("When: ").append(Format.when(entry.when)).append('\n');
        if (!entry.destTitle.isEmpty()) {
            message.append("Sent to: ").append(entry.destTitle).append('\n');
        }
        if (!entry.link.isEmpty()) {
            message.append("Link: ").append(entry.link).append('\n');
        }
        if (!entry.error.isEmpty()) {
            message.append("Reason: ").append(entry.error).append('\n');
        }
        message.append(entry.local ? "The file is still on the phone."
                : "The local copy was removed after the upload.");
        new AlertDialog.Builder(this)
                .setTitle(R.string.history_title)
                .setMessage(message.toString())
                .setPositiveButton(R.string.common_ok, null)
                .setNeutralButton(R.string.common_delete, (dialog, which) ->
                        History.get(this).remove(entry.id))
                .show();
    }

    private void confirmDelete(History.Entry entry) {
        Ui.confirm(this, getString(R.string.common_delete),
                entry.name, getString(R.string.common_delete),
                () -> History.get(this).remove(entry.id));
    }

    private void confirmClear() {
        Ui.confirm(this, getString(R.string.history_clear),
                "Every entry leaves the list. Files already deleted from the phone stay deleted.",
                getString(R.string.history_clear), () -> {
                    History.get(this).clear();
                    Ui.toast(this, getString(R.string.history_cleared));
                });
    }
}
