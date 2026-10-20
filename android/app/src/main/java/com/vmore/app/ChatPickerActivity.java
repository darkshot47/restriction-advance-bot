package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Switch;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * The chat list — displaying real profile pictures on every row and strictly
 * filtering destination picks to chats where this account can actually send
 * or post messages.
 */
public class ChatPickerActivity extends Activity {

    private String mode = "destination";
    private EditText searchField;
    private LinearLayout chatList;
    private ProgressBar progress;
    private TextView hint;
    private Switch rememberSwitch;
    private final List<Tg.Chat> chats = new ArrayList<>();
    private final List<Tg.Chat> shown = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_chats);
        mode = getIntent().getStringExtra("mode");
        if (mode == null) {
            mode = "destination";
        }

        searchField = findViewById(R.id.searchField);
        chatList = findViewById(R.id.chatList);
        progress = findViewById(R.id.chatsProgress);
        hint = findViewById(R.id.chatsHint);
        rememberSwitch = findViewById(R.id.rememberSwitch);

        TextView title = findViewById(R.id.chatsTitle);
        title.setText("scan".equals(mode) ? R.string.chats_scan : R.string.chats_title);

        ImageView back = findViewById(R.id.backButton);
        back.setOnClickListener(v -> finish());

        if ("scan".equals(mode)) {
            rememberSwitch.setVisibility(View.GONE);
        } else {
            rememberSwitch.setChecked(true);
            Ui.tintSwitch(rememberSwitch);
        }

        searchField.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable editable) {
                render(editable == null ? "" : editable.toString().trim());
            }
        });

        Anim.pageIn(findViewById(R.id.chatsHeader));
        load();
    }

    private void load() {
        progress.setVisibility(View.VISIBLE);
        hint.setText(R.string.chats_loading);
        hint.setVisibility(View.VISIBLE);
        Tg.Cb<List<Tg.Chat>> callback = new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> value) {
                progress.setVisibility(View.GONE);
                chats.clear();
                chats.addAll(value);
                render(searchField.getText().toString().trim());
            }

            @Override
            public void fail(String message) {
                progress.setVisibility(View.GONE);
                hint.setText(message);
            }
        };
        if ("scan".equals(mode)) {
            Tg.get(this).loadChats(150, callback);
        } else {
            Tg.get(this).loadWritableChats(150, callback);
        }
    }

    private void render(String query) {
        chatList.removeAllViews();
        shown.clear();
        String needle = query.toLowerCase(Locale.US);
        for (Tg.Chat chat : chats) {
            boolean matchesTitle = chat.title.toLowerCase(Locale.US).contains(needle);
            boolean matchesUser = chat.username != null && !chat.username.isEmpty()
                    && chat.username.toLowerCase(Locale.US).contains(
                    needle.startsWith("@") ? needle.substring(1) : needle);
            if (needle.isEmpty() || matchesTitle || matchesUser) {
                shown.add(chat);
            }
        }
        if (shown.isEmpty()) {
            hint.setText(R.string.chats_empty);
            hint.setVisibility(View.VISIBLE);
        } else {
            hint.setVisibility(View.GONE);
        }
        int index = 0;
        for (Tg.Chat chat : shown) {
            View row = rowFor(chat);
            chatList.addView(row);
            Anim.itemIn(row, index++);
        }
        String username = query.startsWith("@") ? query.substring(1) : query;
        if (username.length() >= 4 && username.matches("[A-Za-z0-9_]+") && shown.isEmpty()) {
            View row = Ui.row(this, R.drawable.ic_search,
                    getString(R.string.chats_open_username) + username,
                    "public username");
            row.setOnClickListener(v -> openUsername(username));
            chatList.addView(row);
            Anim.itemIn(row, 0);
            hint.setVisibility(View.GONE);
        }
    }

    private View rowFor(Tg.Chat chat) {
        String subtitle;
        if ("channel".equals(chat.type)) {
            subtitle = "channel";
        } else if ("group".equals(chat.type)) {
            subtitle = "group";
        } else {
            subtitle = "private chat";
        }
        if (chat.username != null && !chat.username.isEmpty()) {
            subtitle = subtitle + " \u2022 @" + chat.username;
        }
        if (chat.unread > 0) {
            subtitle = subtitle + " \u2022 " + chat.unread + " unread";
        }
        View row = Ui.chatRow(this, chat, subtitle);
        row.setOnClickListener(v -> choose(chat));
        Anim.pressible(row);
        LinearLayout wrapper = new LinearLayout(this);
        wrapper.setOrientation(LinearLayout.VERTICAL);
        wrapper.addView(row);
        wrapper.addView(Ui.divider(this));
        return wrapper;
    }

    private void choose(Tg.Chat chat) {
        if (!"scan".equals(mode) && !chat.canSend) {
            Ui.toast(this, getString(R.string.chats_no_send_permission));
            return;
        }
        Intent result = new Intent();
        result.putExtra("chat_id", chat.id);
        result.putExtra("chat_title", chat.title);
        result.putExtra("remember", rememberSwitch.isChecked());
        setResult(RESULT_OK, result);
        finish();
    }

    private void openUsername(String username) {
        progress.setVisibility(View.VISIBLE);
        Tg.get(this).findPublicChat(username, new Tg.Cb<Tg.Chat>() {
            @Override
            public void ok(Tg.Chat value) {
                progress.setVisibility(View.GONE);
                if (!"scan".equals(mode) && !value.canSend) {
                    Ui.toast(ChatPickerActivity.this,
                            getString(R.string.chats_no_send_permission));
                    return;
                }
                choose(value);
            }

            @Override
            public void fail(String message) {
                progress.setVisibility(View.GONE);
                Ui.toast(ChatPickerActivity.this, message);
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
    }
}
