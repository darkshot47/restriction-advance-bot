package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

/**
 * Auto-copy, in one screen: pick a source out of the account's own chat list,
 * pick a destination, flip the switch.
 *
 * Nothing here reads another app's screen, and both chats are chosen from
 * Telegram's own list for the account that is signed in right now — which is
 * why a switched account can never inherit the previous one's channels.
 */
public class MirrorActivity extends Activity {

    private static final int REQUEST_SOURCE = 71;
    private static final int REQUEST_DEST = 72;

    private LinearLayout box;
    private Switch mirrorSwitch;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_mirror);
        box = findViewById(R.id.mirrorBox);

        ImageView back = findViewById(R.id.backButton);
        back.setOnClickListener(v -> finish());
        Anim.pageIn(findViewById(R.id.mirrorHeader));

        paint();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (box != null && box.getChildCount() > 0) {
            paint();
        }
    }

    private void paint() {
        box.removeAllViews();

        box.addView(Ui.section(this, getString(R.string.mirror_section)));

        mirrorSwitch = new Switch(this);
        mirrorSwitch.setText(R.string.mirror_switch);
        mirrorSwitch.setTextColor(getResources().getColor(R.color.vmore_text));
        mirrorSwitch.setTextSize(15f);
        mirrorSwitch.setPadding(0, Ui.dp(this, 10), 0, Ui.dp(this, 10));
        mirrorSwitch.setChecked(Prefs.mirrorEnabled(this));
        Ui.tintSwitch(mirrorSwitch);
        mirrorSwitch.setOnCheckedChangeListener((button, checked) -> {
            if (checked && (Prefs.mirrorSourceId(this) == 0L
                    || Prefs.mirrorDestId(this) == 0L)) {
                button.setChecked(false);
                Ui.toast(this, getString(R.string.mirror_need_both));
                return;
            }
            Prefs.setMirrorEnabled(this, checked);
            Mirror.refresh(this);
            if (checked) {
                //: Start from the newest post, never from the back catalogue.
                Prefs.setMirrorStart(this, 0L);
            }
            Ui.toast(this, getString(checked ? R.string.mirror_on : R.string.mirror_off));
        });
        box.addView(mirrorSwitch);

        LinearLayout source = Ui.row(this, R.drawable.ic_channel,
                getString(R.string.mirror_source),
                value(Prefs.mirrorSourceTitle(this), getString(R.string.mirror_pick)));
        source.setOnClickListener(v -> pickChat(REQUEST_SOURCE, "mirror_source"));
        Anim.pressible(source);
        box.addView(source);
        box.addView(Ui.divider(this));

        LinearLayout dest = Ui.row(this, R.drawable.ic_send,
                getString(R.string.mirror_dest),
                value(Prefs.mirrorDestTitle(this), getString(R.string.mirror_pick)));
        dest.setOnClickListener(v -> pickChat(REQUEST_DEST, "destination"));
        Anim.pressible(dest);
        box.addView(dest);
        box.addView(Ui.divider(this));

        TextView hint = new TextView(this);
        hint.setText(R.string.mirror_hint);
        hint.setTextColor(getResources().getColor(R.color.vmore_text_dim));
        hint.setTextSize(12.5f);
        hint.setLineSpacing(0f, 1.2f);
        hint.setPadding(Ui.dp(this, 2), Ui.dp(this, 14), Ui.dp(this, 2), Ui.dp(this, 6));
        box.addView(hint);

        Button now = new Button(this);
        now.setAllCaps(false);
        now.setText(R.string.mirror_check_now);
        now.setTextSize(14.5f);
        now.setTextColor(getResources().getColor(R.color.vmore_on_accent));
        now.setBackgroundResource(R.drawable.bg_chip_active);
        now.setStateListAnimator(null);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Ui.dp(this, 46));
        lp.topMargin = Ui.dp(this, 14);
        now.setLayoutParams(lp);
        now.setOnClickListener(v -> {
            if (!Mirror.ready(this)) {
                Ui.toast(this, getString(R.string.mirror_need_both));
                return;
            }
            Ui.toast(this, getString(R.string.mirror_checking));
            Mirror.check(this);
        });
        Anim.pressible(now);
        box.addView(now);

        Button recent = new Button(this);
        recent.setAllCaps(false);
        recent.setText(R.string.mirror_mark_now);
        recent.setTextSize(13f);
        recent.setTextColor(getResources().getColor(R.color.vmore_text));
        recent.setBackgroundResource(R.drawable.bg_chip);
        recent.setStateListAnimator(null);
        LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Ui.dp(this, 42));
        rlp.topMargin = Ui.dp(this, 10);
        recent.setLayoutParams(rlp);
        recent.setOnClickListener(v -> {
            Prefs.setMirrorStart(this, 0L);
            Ui.toast(this, getString(R.string.mirror_marked));
        });
        Anim.pressible(recent);
        box.addView(recent);
    }

    private String value(String stored, String fallback) {
        return stored == null || stored.isEmpty() ? fallback : stored;
    }

    private void pickChat(int request, String mode) {
        Intent intent = new Intent(this, ChatPickerActivity.class);
        intent.putExtra("mode", mode);
        startActivityForResult(intent, request);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null) {
            return;
        }
        long chatId = data.getLongExtra("chat_id", 0L);
        String title = data.getStringExtra("chat_title");
        if (chatId == 0L) {
            return;
        }
        if (requestCode == REQUEST_SOURCE) {
            Prefs.saveMirror(this, chatId, title, Prefs.mirrorDestId(this),
                    Prefs.mirrorDestTitle(this));
            Prefs.setMirrorStart(this, 0L);
        } else if (requestCode == REQUEST_DEST) {
            Prefs.saveMirror(this, Prefs.mirrorSourceId(this),
                    Prefs.mirrorSourceTitle(this), chatId, title);
        }
        paint();
    }
}
