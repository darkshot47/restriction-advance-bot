package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.util.List;

/**
 * The home screen: paste a link and everything the bot promised happens here.
 *
 * Public link → straight to the Telegram DM (the phone downloads nothing).
 * Private link → download in the app (pause / stop, notification progress),
 * then edit (caption, thumbnail, trim) and upload through the user's own
 * session.
 */
public class MainActivity extends Activity {

    private EditText linkField;
    private TextView statusText;
    private LinearLayout actions;
    private ProgressBar progress;
    private boolean busy;
    /** The last download event the screen already reacted to. */
    private String consumed;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable watcher = new Runnable() {
        @Override
        public void run() {
            paintDownload();
            handler.postDelayed(this, 500);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!Prefs.loggedIn(this)) {
            startActivity(new Intent(this, LoginActivity.class));
            finish();
            return;
        }
        setContentView(R.layout.activity_main);
        linkField = findViewById(R.id.linkField);
        statusText = findViewById(R.id.statusText);
        actions = findViewById(R.id.actions);
        progress = findViewById(R.id.downloadProgress);

        findViewById(R.id.ownerCard).setOnClickListener(v -> Blogger.openOwner(this));
        findViewById(R.id.actionHowTo).setOnClickListener(v ->
                startActivity(new Intent(this, HowToActivity.class)));
        findViewById(R.id.actionHistory).setOnClickListener(v ->
                startActivity(new Intent(this, HistoryActivity.class)));
        findViewById(R.id.actionSettings).setOnClickListener(v -> showSettings());
        findViewById(R.id.pasteButton).setOnClickListener(v -> pasteFromClipboard());
        findViewById(R.id.openButton).setOnClickListener(v -> handleLink());
        findViewById(R.id.actionLogout).setOnClickListener(v -> confirmLogout());
        //: Pause / stop work from the screen exactly like the notification buttons.
        findViewById(R.id.pauseButton).setOnClickListener(v -> {
            if (DownloadService.Live.PAUSED.get()) {
                DownloadService.command(this, DownloadService.ACTION_RESUME);
            } else {
                DownloadService.command(this, DownloadService.ACTION_PAUSE);
            }
        });
        findViewById(R.id.stopButton).setOnClickListener(v ->
                DownloadService.command(this, DownloadService.ACTION_STOP));

        Blogger.loadOwner(this, findViewById(R.id.ownerPhoto), findViewById(R.id.ownerName));
        TextView version = findViewById(R.id.versionText);
        version.setText("Vmore v" + Api.VERSION);
        showAccount();
        findViewById(R.id.actionEditor).setOnClickListener(v -> openEditor(null));
        askForNotificationPermission();
        handler.post(watcher);
    }

    @Override
    protected void onResume() {
        super.onResume();
        showAccount();
        paintDownload();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(watcher);
        super.onDestroy();
    }

    private void showAccount() {
        TextView account = findViewById(R.id.accountText);
        String name = Prefs.accountName(this);
        long id = Prefs.accountId(this);
        account.setText(name == null || name.isEmpty()
                ? "Logged in" + (id > 0 ? " • id " + id : "")
                : name + (id > 0 ? " • id " + id : "") + " • token …"
                        + Prefs.token(this).substring(Math.max(0, Prefs.token(this).length() - 2)));
        Api.get(Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this)), result -> {
            if (!result.ok) {
                if (result.json != null && result.json.optBoolean("expired", false)) {
                    setStatus("⌛ Your token expired. Get a new one with /gentoken in the bot, "
                            + "then tap Settings → change token.");
                } else if (result.code == 401) {
                    setStatus("🔑 This token no longer works. Get a fresh one from the bot.");
                }
                return;
            }
            JSONObject info = result.optJson("account");
            if (info != null) {
                Prefs.saveAccount(this, info.optString("name", ""),
                        info.optLong("user_id", 0L));
                TextView view = findViewById(R.id.accountText);
                String label = info.optString("name", "");
                String plan = info.optBoolean("premium", false) ? "Premium" : "Free";
                String session = info.optBoolean("session", false)
                        ? "private downloads ready" : "run /login in the bot for private links";
                view.setText((label.isEmpty() ? "Logged in" : label) + " • " + plan + " • " + session);
            }
        });
    }

    // ---------------------------------------------------------------- link //

    private void pasteFromClipboard() {
        android.content.ClipboardManager clipboard =
                (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard != null && clipboard.hasPrimaryClip()
                && clipboard.getPrimaryClip() != null
                && clipboard.getPrimaryClip().getItemCount() > 0) {
            CharSequence text = clipboard.getPrimaryClip().getItemAt(0).coerceToText(this);
            if (text != null) {
                linkField.setText(text.toString().trim());
            }
        } else {
            toast("Clipboard is empty");
        }
    }

    private void handleLink() {
        String link = linkField.getText().toString().trim();
        if (link.isEmpty()) {
            toast("Paste a Telegram link first");
            return;
        }
        if (busy) {
            return;
        }
        consumed = null;
        setBusy(true);
        setStatus("🔍 Checking the link…");
        JSONObject body = new JSONObject();
        try {
            body.put("link", link);
        } catch (Exception ignored) {
        }
        Api.post(Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this)) + "/resolve", body,
                result -> {
                    setBusy(false);
                    if (!result.ok) {
                        setStatus("⚠️ " + (result.error == null ? "Could not read that link"
                                : result.error));
                        return;
                    }
                    boolean isPrivate = "private".equals(result.optString("type", ""));
                    if (isPrivate) {
                        JSONObject media = result.optJson("media");
                        //: optString, not getString: org.json throws a checked
                        //: JSONException for a missing key and this is a UI path.
                        String name = media == null ? "" : media.optString("file_name", "");
                        if (name.isEmpty()) {
                            name = null;
                        }
                        askPrivateDownload(link, name, result.optBoolean("needs_login", false));
                    } else {
                        sendToDm(link);
                    }
                });
    }

    private void sendToDm(String link) {
        setBusy(true);
        setStatus("📩 Asking the bot to send it to your Telegram DM…");
        JSONObject body = new JSONObject();
        try {
            body.put("link", link);
        } catch (Exception ignored) {
        }
        Api.post(Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this)) + "/send", body, result -> {
            setBusy(false);
            if (result.ok) {
                setStatus("✅ Sent to your Telegram DM — nothing downloaded on this phone.");
            } else {
                setStatus("⚠️ " + (result.error == null ? "Delivery failed" : result.error));
            }
        });
    }

    private void askPrivateDownload(String link, String name, boolean needsLogin) {
        String message = "⬇️ **Private link**\n\n"
                + "This content lives in a private chat, so it downloads **with your own "
                + "Telegram data** — that is what makes it unlimited.\n\n"
                + "Download it into the app, then edit (caption, thumbnail, trim) and "
                + "upload it back from your own account.";
        if (needsLogin) {
            message += "\n\n⚠️ The bot has no session for you yet — send /login in the bot "
                    + "once, then try again.";
        }
        new AlertDialog.Builder(this)
                .setTitle("Download this link?")
                .setMessage(message.replace("**", ""))
                .setPositiveButton("⬇️ Download", (dialog, which) ->
                        DownloadService.start(this, link, name))
                .setNeutralButton("📩 Send to DM", (dialog, which) -> sendToDm(link))
                .setNegativeButton("Cancel", null)
                .show();
    }

    // ------------------------------------------------------------ download //

    /** Mirror the service's progress on screen (the notification does the rest). */
    private void paintDownload() {
        String status = DownloadService.Live.STATUS;
        boolean active = DownloadService.running()
                && ("preparing".equals(status) || "downloading".equals(status)
                    || "paused".equals(status));
        progress.setVisibility(active ? View.VISIBLE : View.GONE);
        findViewById(R.id.pauseButton).setVisibility(active ? View.VISIBLE : View.GONE);
        findViewById(R.id.stopButton).setVisibility(active ? View.VISIBLE : View.GONE);
        if (active) {
            long total = DownloadService.Live.TOTAL.get();
            long written = DownloadService.Live.WRITTEN.get();
            progress.setIndeterminate(total <= 0);
            progress.setMax(1000);
            progress.setProgress(total > 0 ? (int) Math.min(1000, written * 1000 / total) : 0);
            boolean paused = DownloadService.Live.PAUSED.get();
            ((Button) findViewById(R.id.pauseButton)).setText(paused ? "▶️ Resume" : "⏸ Pause");
            setStatus((paused ? "⏸ Paused — " : "⬇️ Downloading ")
                    + DownloadService.Live.NAME + " • "
                    + Notifications.human(written)
                    + (total > 0 ? " / " + Notifications.human(total) : ""));
        } else if ("done".equals(status) && !"done".equals(consumed)) {
            String path = DownloadService.Live.PATH;
            consumed = "done";
            setStatus("✅ Download finished — edit it, watch it, or save it to your device.");
            offerTools(path);
        } else if ("error".equals(status) && !"error".equals(consumed)) {
            consumed = "error";
            setStatus("⚠️ Download failed: " + DownloadService.Live.ERROR);
        } else if ("stopped".equals(status) && !"stopped".equals(consumed)) {
            consumed = "stopped";
            setStatus("⏹ Download stopped");
        }
    }

    /** After a download the editing tools (and viewer) are one tap away. */
    private void offerTools(String path) {
        File file = path == null ? null : new File(path);
        if (file == null || !file.exists()) {
            return;
        }
        actions.setVisibility(View.VISIBLE);
        ((TextView) findViewById(R.id.readyText))
                .setText("Ready: " + file.getName() + " • " + Notifications.human(file.length()));
        findViewById(R.id.openEditorButton).setOnClickListener(v -> openEditor(path));
        findViewById(R.id.openViewerButton).setOnClickListener(v ->
                openViewer(path));
        findViewById(R.id.saveDeviceButton).setOnClickListener(v -> saveToDevice(file));
    }

    private void openEditor(String path) {
        String target = path;
        if (target == null) {
            List<LocalStore.Item> items = LocalStore.all(this);
            if (items.isEmpty()) {
                toast("Download something first");
                return;
            }
            target = items.get(0).path;
        }
        Intent intent = new Intent(this, EditorActivity.class);
        intent.putExtra("path", target);
        startActivity(intent);
    }

    private void openViewer(String path) {
        Intent intent = new Intent(this, ViewerActivity.class);
        intent.putExtra("path", path);
        startActivity(intent);
    }

    private void saveToDevice(File file) {
        try {
            String where = MediaUtils.saveToDevice(this, file);
            setStatus("📥 Saved to " + where);
            toast("Saved to " + where);
        } catch (Exception exc) {
            setStatus("⚠️ Could not save: " + exc.getMessage());
        }
    }

    // ------------------------------------------------------------ settings //

    private void showSettings() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad, pad, pad);

        TextView baseLabel = new TextView(this);
        baseLabel.setText("Server address");
        EditText base = new EditText(this);
        base.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        base.setText(Prefs.baseUrl(this));

        TextView tokenLabel = new TextView(this);
        tokenLabel.setText("Access token");
        EditText token = new EditText(this);
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        token.setText(Prefs.token(this));

        box.addView(baseLabel);
        box.addView(base);
        box.addView(tokenLabel);
        box.addView(token);

        TextView hint = new TextView(this);
        hint.setText("Both values are editable any time. The token is your only login.");
        hint.setTextSize(12f);
        box.addView(hint);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);

        new AlertDialog.Builder(this)
                .setTitle("Settings")
                .setView(scroll)
                .setPositiveButton("Save", (dialog, which) -> {
                    Prefs.setBaseUrl(this, base.getText().toString());
                    Prefs.setToken(this, token.getText().toString());
                    toast("Saved");
                    showAccount();
                })
                .setNeutralButton("Revoke token", (dialog, which) -> revokeToken())
                .setNegativeButton("Close", null)
                .show();
    }

    private void revokeToken() {
        Api.post(Api.tokenUrl(Prefs.baseUrl(this), Prefs.token(this)) + "/revoke",
                new JSONObject(), result -> {
                    Prefs.logout(this);
                    toast(result.ok ? "Token revoked — the app is signed out"
                            : "Token revoked locally");
                    startActivity(new Intent(this, LoginActivity.class));
                    finish();
                });
    }

    private void confirmLogout() {
        new AlertDialog.Builder(this)
                .setTitle("Sign out?")
                .setMessage("The token stays valid on the server until you revoke it with "
                        + "/revoketoken. You can sign back in with the same token.")
                .setPositiveButton("Sign out", (dialog, which) -> {
                    Prefs.logout(this);
                    startActivity(new Intent(this, LoginActivity.class));
                    finish();
                })
                .setNegativeButton("Stay", null)
                .show();
    }

    // --------------------------------------------------------------- helpers //

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
                                          int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != 601) {
            return;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == android.content.pm.PackageManager.PERMISSION_GRANTED;
        if (!granted) {
            //: Say it out loud: downloads still work, the progress notification
            //: just stays quiet until the permission is given in Settings.
            setStatus("ℹ️ Notification permission is off, so download progress stays inside "
                    + "the app. Downloads keep running in the background either way.");
        }
    }

    /** Android 13+ needs this once, otherwise no progress notification appears. */
    private void askForNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 601);
        }
    }

    private void setStatus(String text) {
        statusText.setText(text);
        statusText.setVisibility(View.VISIBLE);
    }

    private void setBusy(boolean value) {
        busy = value;
        findViewById(R.id.openButton).setEnabled(!value);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }
}
