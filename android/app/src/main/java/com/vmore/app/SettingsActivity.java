package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

/**
 * Everything that can be tuned, and nothing that needs a server.
 *
 * The two settings the owner asked for live here in plain words: the automatic
 * deletion of the phone copy after a successful upload, and the chat that
 * receives the files.
 */
public class SettingsActivity extends Activity {

    private static final int PICK_CHAT = 701;

    private LinearLayout box;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_settings);
        box = findViewById(R.id.settingsBox);
        findViewById(R.id.backButton).setOnClickListener(v -> finish());
        Anim.pageIn(findViewById(R.id.settingsHeader));
        render();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
        render();
    }

    private void render() {
        box.removeAllViews();

        box.addView(Ui.section(this, getString(R.string.home_send_to)));
        addRow(R.drawable.ic_chat, Prefs.destTitle(this).isEmpty()
                        ? getString(R.string.home_no_destination) : Prefs.destTitle(this),
                "tap to choose the chat that receives every upload",
                v -> startActivityForResult(
                        new Intent(this, ChatPickerActivity.class).putExtra("mode", "destination"),
                        PICK_CHAT));
        addSwitch(R.string.settings_ask_every_time, Prefs.askDestination(this),
                value -> Prefs.setAskDestination(this, value));

        box.addView(Ui.section(this, getString(R.string.settings_appearance)));
        LinearLayout skins = new LinearLayout(this);
        skins.setOrientation(LinearLayout.HORIZONTAL);
        skins.setPadding(Ui.dp(this, 2), 0, 0, Ui.dp(this, 6));
        boolean night = Skin.isNight(this);
        skins.addView(Ui.chip(this, getString(R.string.settings_day), !night, v -> {
            if (Skin.isNight(this)) {
                Skin.toggle(this);
            }
        }));
        skins.addView(Ui.chip(this, getString(R.string.settings_night), night, v -> {
            if (!Skin.isNight(this)) {
                Skin.toggle(this);
            }
        }));
        skins.addView(Ui.chip(this, getString(R.string.settings_auto), Prefs.skinMode(this) == 2,
                v -> Skin.setMode(this, 2)));
        box.addView(skins);
        TextView skinHint = new TextView(this);
        skinHint.setText(R.string.settings_skin_hint);
        skinHint.setTextColor(getColor(R.color.vmore_text_faint));
        skinHint.setTextSize(12f);
        skinHint.setPadding(Ui.dp(this, 4), 0, Ui.dp(this, 4), Ui.dp(this, 8));
        box.addView(skinHint);

        box.addView(Ui.section(this, getString(R.string.settings_data)));
        addSwitch(R.string.settings_wifi_only, Prefs.wifiOnly(this),
                value -> Prefs.setWifiOnly(this, value), R.string.settings_wifi_hint);
        addSwitch(R.string.settings_charging_only, Prefs.chargingOnly(this),
                value -> Prefs.setChargingOnly(this, value), R.string.settings_charging_hint);
        boolean restricted = Net.batteryRestricted(this);
        addRow(R.drawable.ic_lock,
                restricted ? getString(R.string.settings_battery_on)
                        : getString(R.string.settings_battery_off),
                getString(R.string.settings_battery_hint),
                restricted ? v -> Net.askForBatteryFreedom(this) : null);

        box.addView(Ui.section(this, getString(R.string.settings_schedule)));
        long at = Prefs.scheduleAt(this);
        addRow(R.drawable.ic_history,
                at > System.currentTimeMillis()
                        ? getString(R.string.settings_schedule_at) + " " + Format.when(at)
                        : getString(R.string.settings_schedule_none),
                getString(R.string.settings_schedule_hint), v -> pickSchedule());
        addSwitch(R.string.settings_schedule_daily, Prefs.scheduleDaily(this),
                value -> Prefs.setScheduleDaily(this, value));
        if (at > System.currentTimeMillis()) {
            addRow(R.drawable.ic_close, getString(R.string.settings_schedule_clear),
                    getString(R.string.settings_schedule_clear_hint), v -> {
                        Prefs.setScheduleAt(this, 0L);
                        render();
                    });
        }

        box.addView(Ui.section(this, getString(R.string.filters_title)));
        addRow(R.drawable.ic_folder, filterSummary(),
                getString(R.string.filters_hint), v -> Filters.show(this, this::render));

        box.addView(Ui.section(this, getString(R.string.settings_delete_local)));
        addSwitch(R.string.settings_upload_after, Prefs.autoUpload(this),
                value -> Prefs.setAutoUpload(this, value));
        addSwitch(R.string.settings_delete_local, Prefs.autoDeleteLocal(this),
                value -> Prefs.setAutoDeleteLocal(this, value), R.string.settings_delete_local_hint);
        addSwitch(R.string.settings_keep_screen, Prefs.keepScreenOn(this),
                value -> Prefs.setKeepScreenOn(this, value));
        addSwitch(R.string.settings_autoplay, Prefs.autoplayNext(this),
                value -> Prefs.setAutoplayNext(this, value), R.string.settings_autoplay_hint);

        box.addView(Ui.section(this, getString(R.string.settings_send_as)));
        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        chips.setPadding(Ui.dp(this, 2), 0, 0, Ui.dp(this, 6));
        String current = Prefs.sendAs(this);
        chips.addView(Ui.chip(this, getString(R.string.settings_send_as_file),
                Prefs.SEND_FILE.equals(current), v -> {
                    Prefs.setSendAs(this, Prefs.SEND_FILE);
                    render();
                }));
        chips.addView(Ui.chip(this, getString(R.string.settings_send_as_video),
                Prefs.SEND_VIDEO.equals(current), v -> {
                    Prefs.setSendAs(this, Prefs.SEND_VIDEO);
                    render();
                }));
        chips.addView(Ui.chip(this, getString(R.string.settings_send_as_photo),
                Prefs.SEND_PHOTO.equals(current), v -> {
                    Prefs.setSendAs(this, Prefs.SEND_PHOTO);
                    render();
                }));
        box.addView(chips);
        TextView hint = new TextView(this);
        hint.setText(R.string.settings_send_as_hint);
        hint.setTextColor(getColor(R.color.vmore_text_faint));
        hint.setTextSize(12f);
        hint.setPadding(Ui.dp(this, 4), 0, Ui.dp(this, 4), Ui.dp(this, 8));
        box.addView(hint);

        addRow(R.drawable.ic_edit, Prefs.captionTemplate(this).isEmpty()
                        ? "No caption template" : Prefs.captionTemplate(this),
                "captions for every upload; {name} becomes the file name",
                v -> editCaption());

        box.addView(Ui.section(this, getString(R.string.settings_library)));
        addRow(R.drawable.ic_folder, getString(R.string.files_title),
                onPhone(), v -> startActivity(new Intent(this, FilesActivity.class)));
        addRow(R.drawable.ic_speed, getString(R.string.stats_title),
                getString(R.string.settings_stats_hint),
                v -> startActivity(new Intent(this, StatsActivity.class)));

        box.addView(Ui.section(this, getString(R.string.settings_privacy)));
        addSwitch(R.string.settings_lock, Prefs.lockEnabled(this), value -> {
            if (value) {
                askNewPin();
            } else {
                Lock.clear(this);
                render();
            }
        }, R.string.settings_lock_hint);

        box.addView(Ui.section(this, getString(R.string.settings_account)));
        String name = Prefs.accountName(this);
        String phone = Prefs.phone(this);
        addRow(R.drawable.ic_person, name == null || name.isEmpty() ? "Signed in" : name,
                phone.isEmpty() ? "Telegram account" : phone, null);
        accounts();
        addRow(R.drawable.ic_lock, getString(R.string.settings_sign_out),
                getString(R.string.settings_sign_out_hint), v -> confirmSignOut());

        box.addView(Ui.section(this, getString(R.string.settings_about)));
        addRow(R.drawable.ic_vmore, getString(R.string.settings_version) + " " + Vmore.VERSION,
                "Vmore runs everything on this phone", null);
        addRow(R.drawable.ic_refresh, getString(R.string.settings_check),
                getString(R.string.settings_check_hint), v -> checkConnection());
        addRow(R.drawable.ic_person, getString(R.string.settings_developer),
                "@XyrDeveloper", v -> openTelegram());
        addRow(R.drawable.ic_help, getString(R.string.settings_help),
                "a short guide to every screen", v -> startActivity(
                        new Intent(this, HelpActivity.class)));

        Anim.stagger(box);
    }

    // ------------------------------------------------------------- builders //

    private void addRow(int icon, String title, String subtitle, View.OnClickListener click) {
        View row = Ui.row(this, icon, title, subtitle);
        if (click != null) {
            row.setOnClickListener(click);
            Anim.pressible(row);
        }
        box.addView(row);
        box.addView(Ui.divider(this));
    }

    private interface Toggle {
        void onChanged(boolean value);
    }

    private void addSwitch(int titleRes, boolean value, Toggle toggle) {
        addSwitch(titleRes, value, toggle, 0);
    }

    private void addSwitch(int titleRes, boolean value, Toggle toggle, int hintRes) {
        LinearLayout wrapper = new LinearLayout(this);
        wrapper.setOrientation(LinearLayout.VERTICAL);
        wrapper.setPadding(Ui.dp(this, 16), Ui.dp(this, 10), Ui.dp(this, 16), Ui.dp(this, 10));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = new TextView(this);
        title.setText(titleRes);
        title.setTextColor(getColor(R.color.vmore_text));
        title.setTextSize(15f);
        row.addView(title, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        Switch toggleView = new Switch(this);
        toggleView.setChecked(value);
        Ui.tintSwitch(toggleView);
        toggleView.setOnCheckedChangeListener((button, checked) -> toggle.onChanged(checked));
        row.addView(toggleView);
        wrapper.addView(row);

        if (hintRes != 0) {
            TextView hint = new TextView(this);
            hint.setText(hintRes);
            hint.setTextColor(getColor(R.color.vmore_text_faint));
            hint.setTextSize(12f);
            hint.setPadding(0, Ui.dp(this, 6), 0, 0);
            wrapper.addView(hint);
        }
        box.addView(wrapper);
        box.addView(Ui.divider(this));
    }

    // ------------------------------------------------------ new sections //

    private String onPhone() {
        return Format.size(LocalFiles.totalBytes(this)) + " \u2022 "
                + getString(R.string.settings_library_hint);
    }

    private String filterSummary() {
        String kinds = Prefs.filterKinds(this);
        long min = Prefs.filterMinSize(this);
        long max = Prefs.filterMaxSize(this);
        if ((kinds == null || kinds.isEmpty()) && min == 0 && max == 0) {
            return getString(R.string.filters_off);
        }
        StringBuilder builder = new StringBuilder();
        builder.append(kinds == null || kinds.isEmpty() ? getString(R.string.filters_all) : kinds);
        if (min > 0) {
            builder.append(" \u2022 from ").append(Format.size(min));
        }
        if (max > 0) {
            builder.append(" \u2022 up to ").append(Format.size(max));
        }
        return builder.toString();
    }

    /** Every account slot, with the one in use marked. */
    private void accounts() {
        int active = Prefs.activeSlot(this);
        for (int slot = 1; slot <= Prefs.slotCount(this); slot++) {
            final int target = slot;
            boolean used = Prefs.slotUsed(this, slot);
            String title = getString(R.string.settings_account) + " " + slot
                    + (used ? " \u2022 " + Prefs.slotLabel(this, slot) : "");
            String subtitle = slot == active
                    ? getString(R.string.settings_account_current)
                    : used ? getString(R.string.settings_account_switch)
                    : getString(R.string.settings_account_empty);
            addRow(R.drawable.ic_person, title, subtitle, v -> switchAccount(target));
        }
        if (Prefs.slotCount(this) < Prefs.MAX_SLOTS) {
            addRow(R.drawable.ic_add, getString(R.string.settings_account_add),
                    getString(R.string.settings_account_add_hint), v -> {
                        int slot = Prefs.addSlot(this);
                        if (slot == 0) {
                            Ui.toast(this, getString(R.string.settings_account_full));
                            return;
                        }
                        switchAccount(slot);
                    });
        }
    }

    /** Moves the app to another account slot and asks for its sign-in. */
    private void switchAccount(int slot) {
        if (slot == Prefs.activeSlot(this)) {
            Ui.toast(this, getString(R.string.settings_account_current));
            return;
        }
        Ui.confirm(this, getString(R.string.settings_account_switch),
                getString(R.string.settings_account_switch_confirm),
                getString(R.string.settings_account_switch), () -> {
                    Tg.get(this).useSlot(slot);
                    startActivity(new Intent(this, LoginActivity.class));
                    finish();
                });
    }

    private void pickSchedule() {
        java.util.Calendar calendar = java.util.Calendar.getInstance();
        long at = Prefs.scheduleAt(this);
        if (at > System.currentTimeMillis()) {
            calendar.setTimeInMillis(at);
        } else {
            calendar.add(java.util.Calendar.HOUR_OF_DAY, 1);
        }
        new android.app.TimePickerDialog(this, (view, hour, minute) -> {
            java.util.Calendar chosen = java.util.Calendar.getInstance();
            chosen.set(java.util.Calendar.HOUR_OF_DAY, hour);
            chosen.set(java.util.Calendar.MINUTE, minute);
            chosen.set(java.util.Calendar.SECOND, 0);
            if (chosen.getTimeInMillis() <= System.currentTimeMillis()) {
                chosen.add(java.util.Calendar.DAY_OF_YEAR, 1);
            }
            Prefs.setScheduleAt(this, chosen.getTimeInMillis());
            render();
        }, calendar.get(java.util.Calendar.HOUR_OF_DAY),
                calendar.get(java.util.Calendar.MINUTE), true).show();
    }

    /** Asks for a new PIN twice, then stores the salted hash. */
    private void askNewPin() {
        EditText field = pinField(getString(R.string.settings_lock_new));
        LinearLayout holder = new LinearLayout(this);
        holder.setPadding(Ui.dp(this, 20), Ui.dp(this, 12), Ui.dp(this, 20), 0);
        holder.addView(field);
        new AlertDialog.Builder(this)
                .setTitle(R.string.settings_lock)
                .setView(holder)
                .setPositiveButton(R.string.common_ok, (dialog, which) -> {
                    String pin = field.getText().toString().trim();
                    if (!Lock.valid(pin)) {
                        Ui.toast(this, getString(R.string.settings_lock_bad));
                        render();
                        return;
                    }
                    Lock.setPin(this, pin);
                    Ui.toast(this, getString(R.string.settings_lock_set));
                    render();
                })
                .setNegativeButton(R.string.common_cancel, (dialog, which) -> render())
                .show();
    }

    private EditText pinField(String hint) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setInputType(android.text.InputType.TYPE_CLASS_NUMBER
                | android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        field.setSingleLine(true);
        field.setBackgroundResource(R.drawable.bg_field);
        field.setTextColor(getColor(R.color.vmore_text));
        field.setHintTextColor(getColor(R.color.vmore_text_faint));
        field.setPadding(Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12));
        return field;
    }

    // -------------------------------------------------------------- actions //

    private void editCaption() {
        EditText field = new EditText(this);
        field.setHint("Leave empty to keep the original caption");
        field.setText(Prefs.captionTemplate(this));
        field.setBackgroundResource(R.drawable.bg_field);
        field.setTextColor(getColor(R.color.vmore_text));
        field.setTextSize(14f);
        field.setPadding(Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12));

        LinearLayout holder = new LinearLayout(this);
        holder.setPadding(Ui.dp(this, 20), Ui.dp(this, 10), Ui.dp(this, 20), 0);
        holder.addView(field);

        new AlertDialog.Builder(this)
                .setTitle(R.string.settings_caption)
                .setView(holder)
                .setPositiveButton(R.string.common_ok, (dialog, which) -> {
                    Prefs.setCaptionTemplate(this, field.getText().toString());
                    render();
                })
                .setNegativeButton(R.string.common_cancel, null)
                .show();
    }

    private void confirmSignOut() {
        Ui.confirm(this, getString(R.string.settings_sign_out),
                getString(R.string.settings_sign_out_confirm),
                getString(R.string.settings_sign_out), () -> {
                    Tg.get(this).logout();
                    Prefs.saveAccount(this, 0L, "", "");
                    getSharedPreferences("vmore", MODE_PRIVATE).edit()
                            .putBoolean("setup_done", false).apply();
                    startActivity(new Intent(this, LoginActivity.class));
                    finish();
                });
    }

    private void openTelegram() {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW,
                    Uri.parse("https://t.me/" + Vmore.DEVELOPER)));
        } catch (Exception error) {
            Ui.toast(this, "@" + Vmore.DEVELOPER);
        }
    }

    /**
     * One screen's worth of plain facts: the session, the chat that receives
     * the files and the last jobs that failed, with Telegram's own words.
     */
    private void checkConnection() {
        StringBuilder report = new StringBuilder();
        Tg tg = Tg.get(this);
        report.append("Skin: ").append(Skin.label(this)).append('\n');
        report.append("Engine: ").append(tg.nativeAvailable() ? "present" : "missing")
                .append('\n');
        report.append("Session: ").append(tg.state()).append('\n');
        Tg.Account account = tg.account();
        report.append("Account: ").append(account == null ? "still loading"
                : account.name + (account.username.isEmpty() ? "" : " @" + account.username))
                .append('\n');
        report.append("Destination: ").append(Prefs.destTitle(this).isEmpty()
                ? "not chosen" : Prefs.destTitle(this)).append('\n');
        report.append("Auto upload: ").append(Prefs.autoUpload(this) ? "on" : "off")
                .append(", delete local copy: ")
                .append(Prefs.autoDeleteLocal(this) ? "on" : "off").append('\n');

        int shown = 0;
        for (QJob job : Jobs.get(this).all()) {
            if (QJob.FAILED.equals(job.stage) && shown < 8) {
                shown++;
                report.append("\n").append(job.title())
                        .append("\n  ").append(job.error.isEmpty() ? "failed" : job.error);
            }
        }
        if (shown == 0) {
            for (History.Entry entry : History.get(this).all()) {
                if (History.STATUS_FAILED.equals(entry.status) && shown < 8) {
                    shown++;
                    report.append("\n").append(entry.name)
                            .append("\n  ").append(entry.error.isEmpty() ? "failed" : entry.error);
                }
            }
        }
        if (shown == 0) {
            report.append("\nNo failed job is waiting.");
        }

        TextView view = new TextView(this);
        view.setText(report.toString());
        view.setTextColor(getColor(R.color.vmore_text));
        view.setTextSize(13f);
        view.setTypeface(android.graphics.Typeface.MONOSPACE);
        view.setPadding(Ui.dp(this, 20), Ui.dp(this, 14), Ui.dp(this, 20), Ui.dp(this, 4));
        ScrollView scroll = new ScrollView(this);
        scroll.addView(view);

        final String text = report.toString();
        new AlertDialog.Builder(this)
                .setTitle(R.string.settings_check_title)
                .setView(scroll)
                .setPositiveButton(R.string.settings_check_copy, (dialog, which) -> copy(text))
                .setNegativeButton(R.string.common_close, null)
                .show();
    }

    private void copy(String text) {
        android.content.ClipboardManager clipboard =
                (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard != null) {
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Vmore", text));
            Ui.toast(this, getString(R.string.settings_check_copied));
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_CHAT && resultCode == RESULT_OK && data != null) {
            long chatId = data.getLongExtra("chat_id", 0L);
            if (chatId != 0L) {
                Prefs.saveDestination(this, chatId, data.getStringExtra("chat_title"));
            }
            render();
        }
    }
}
