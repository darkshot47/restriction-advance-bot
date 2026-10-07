package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.List;

/**
 * Downloads **and** history in one list, exactly as the owner asked: what this
 * phone downloaded (tap to open / edit) and what the account did on the server.
 */
public class HistoryActivity extends Activity {

    private LinearLayout list;
    private TextView empty;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_history);
        list = findViewById(R.id.historyList);
        empty = findViewById(R.id.historyEmpty);
        findViewById(R.id.refreshButton).setOnClickListener(v -> load());
        load();
    }

    private void load() {
        list.removeAllViews();
        List<LocalStore.Item> local = LocalStore.all(this);
        int index = 0;
        for (LocalStore.Item item : local) {
            addRow("📥 " + item.name,
                    Notifications.human(item.size) + " • " + when(item.date)
                            + (new File(item.path).exists() ? "" : " • file removed"),
                    v -> openDownloaded(item));
            index++;
        }
        if (index == 0) {
            empty.setText("Nothing downloaded on this phone yet.\n\n"
                    + "Paste a private link on the home screen to start.");
            empty.setVisibility(View.VISIBLE);
        } else {
            empty.setVisibility(View.GONE);
        }
        addHeader("Server history");
        Api.get(Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this)) + "/history?limit=50",
                result -> {
                    if (!result.ok || result.json == null) {
                        addRow("⚠️ Could not load history",
                                result.error == null ? "unknown error" : result.error, null);
                        return;
                    }
                    JSONArray items = result.json.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        addRow("Nothing yet", "Public links you send and app downloads show up here.",
                                null);
                        return;
                    }
                    for (int i = 0; i < items.length(); i++) {
                        JSONObject item = items.optJSONObject(i);
                        if (item == null) {
                            continue;
                        }
                        String icon = "app".equals(item.optString("source")) ? "📱" : "🤖";
                        String status = item.optString("status", "done");
                        String title = icon + " " + ("done".equals(status) ? "" : status + " • ")
                                + item.optString("kind", "download");
                        String detail = firstNonEmpty(item.optString("file_name", ""),
                                item.optString("caption", ""), item.optString("link", ""));
                        addRow(title, (detail.isEmpty() ? "" : detail + "\n")
                                + prettyDate(item.optString("date", "")), null);
                    }
                });
    }

    private void openDownloaded(LocalStore.Item item) {
        File file = new File(item.path);
        if (!file.exists()) {
            LocalStore.forget(this, item.path);
            load();
            return;
        }
        Intent intent = new Intent(this, ViewerActivity.class);
        intent.putExtra("path", item.path);
        startActivity(intent);
    }

    private void addHeader(String text) {
        TextView header = new TextView(this);
        header.setText(text);
        header.setPadding(8, 24, 8, 8);
        header.setTextSize(14f);
        header.setAllCaps(false);
        list.addView(header);
    }

    private void addRow(String title, String subtitle, View.OnClickListener click) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad, pad, pad);
        TextView head = new TextView(this);
        head.setText(title);
        head.setTextSize(15f);
        TextView sub = new TextView(this);
        sub.setText(subtitle);
        sub.setTextSize(12f);
        box.addView(head);
        box.addView(sub);
        if (click != null) {
            box.setOnClickListener(click);
        }
        list.addView(box);
    }

    private String firstNonEmpty(String... values) {
        for (String value : values) {
            if (value != null && !value.isEmpty()) {
                return value;
            }
        }
        return "";
    }

    private String when(long stamp) {
        return prettyDate(new java.util.Date(stamp).toInstant().toString());
    }

    private String prettyDate(String iso) {
        if (iso == null || iso.length() < 16) {
            return iso == null ? "" : iso;
        }
        return iso.substring(0, 10) + " " + iso.substring(11, 16);
    }
}
