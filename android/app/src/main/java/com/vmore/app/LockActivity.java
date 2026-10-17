package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * The PIN screen, shown when the app comes back after being left alone.
 *
 * The keypad is drawn here instead of being a dialog, and the PIN is compared
 * against a salted hash, never against the digits themselves.
 */
public class LockActivity extends Activity {

    private final StringBuilder entered = new StringBuilder();
    private TextView dots;
    private TextView message;
    private LinearLayout box;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_lock);
        box = findViewById(R.id.lockBox);
        Anim.pageIn(findViewById(R.id.screenHeader));
        render();
    }

    @Override
    public void onBackPressed() {
        //: Leaving the lock screen by the back button would show the app again.
        moveTaskToBack(true);
    }

    private void render() {
        box.removeAllViews();

        TextView title = new TextView(this);
        title.setText(R.string.lock_title);
        title.setTextColor(getColor(R.color.vmore_text));
        title.setTextSize(17f);
        title.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        title.setPadding(0, Ui.dp(this, 18), 0, Ui.dp(this, 6));
        box.addView(title);

        TextView hint = new TextView(this);
        hint.setText(R.string.lock_hint);
        hint.setTextColor(getColor(R.color.vmore_text_faint));
        hint.setTextSize(13f);
        hint.setGravity(Gravity.CENTER_HORIZONTAL);
        box.addView(hint);

        dots = new TextView(this);
        dots.setTextColor(getColor(R.color.vmore_blue));
        dots.setTextSize(30f);
        dots.setGravity(Gravity.CENTER_HORIZONTAL);
        dots.setPadding(0, Ui.dp(this, 22), 0, Ui.dp(this, 10));
        box.addView(dots);

        message = new TextView(this);
        message.setTextColor(getColor(R.color.vmore_text_dim));
        message.setTextSize(13f);
        message.setGravity(Gravity.CENTER_HORIZONTAL);
        message.setPadding(0, 0, 0, Ui.dp(this, 10));
        box.addView(message);

        box.addView(keypad());

        Button forgot = new Button(this);
        forgot.setText(R.string.lock_forgot);
        forgot.setAllCaps(false);
        forgot.setBackgroundResource(R.drawable.bg_button_ghost);
        forgot.setTextColor(getColor(R.color.vmore_blue));
        forgot.setStateListAnimator(null);
        forgot.setOnClickListener(v -> forgotPin());
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.setMargins(0, Ui.dp(this, 18), 0, 0);
        box.addView(forgot, params);
        Anim.pressible(forgot);

        paintDots();
    }

    private View keypad() {
        LinearLayout grid = new LinearLayout(this);
        grid.setOrientation(LinearLayout.VERTICAL);
        grid.setGravity(Gravity.CENTER_HORIZONTAL);
        String[] rows = {"123", "456", "789"};
        for (String rowValue : rows) {
            grid.addView(keyRow(rowValue));
        }
        grid.addView(keyRow("0"));
        return grid;
    }

    private View keyRow(String digits) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_HORIZONTAL);
        for (int index = 0; index < digits.length(); index++) {
            row.addView(key(String.valueOf(digits.charAt(index))));
        }
        row.addView(key("DEL"));
        return row;
    }

    private Button key(String label) {
        Button button = new Button(this);
        button.setText("DEL".equals(label) ? "\u2190" : label);
        button.setTextSize(18f);
        button.setAllCaps(false);
        button.setBackgroundResource(R.drawable.bg_chip);
        button.setTextColor(getColor(R.color.vmore_text));
        button.setStateListAnimator(null);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                Ui.dp(this, 74), Ui.dp(this, 62));
        params.setMargins(Ui.dp(this, 5), Ui.dp(this, 5), Ui.dp(this, 5), Ui.dp(this, 5));
        button.setLayoutParams(params);
        button.setOnClickListener(v -> press(label));
        Anim.pressible(button);
        return button;
    }

    private void press(String label) {
        if ("DEL".equals(label)) {
            if (entered.length() > 0) {
                entered.deleteCharAt(entered.length() - 1);
            }
            message.setText("");
            paintDots();
            return;
        }
        if (entered.length() >= 8) {
            return;
        }
        entered.append(label);
        paintDots();
        if (entered.length() >= 4 && Lock.verify(this, entered.toString())) {
            unlock();
            return;
        }
        if (entered.length() == 8) {
            message.setText(R.string.lock_wrong);
            entered.setLength(0);
            paintDots();
            Anim.fadeIn(message, 180);
        }
    }

    private void unlock() {
        Lock.unlocked();
        entered.setLength(0);
        dots.setText("");
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(intent);
        finish();
    }

    private void paintDots() {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < entered.length(); index++) {
            builder.append("\u2022 ");
        }
        dots.setText(builder.toString().trim());
    }

    private void forgotPin() {
        Ui.confirm(this, getString(R.string.lock_forgot),
                getString(R.string.lock_forgot_confirm),
                getString(R.string.lock_forgot_yes), () -> {
                    Lock.clear(this);
                    Tg.get(this).logout();
                    Prefs.clearSlot(this, Prefs.activeSlot(this));
                    Prefs.saveAccount(this, 0L, "", "");
                    Ui.toast(this, getString(R.string.lock_cleared));
                    startActivity(new Intent(this, LoginActivity.class));
                    finish();
                });
    }
}
