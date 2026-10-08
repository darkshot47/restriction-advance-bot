package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.drawable.BitmapDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * The first screen: **server address + access token** — that is the whole login.
 *
 * The owner's profile picture sits in the top-right corner (tap it to open
 * {@code @XyrDeveloper}), exactly as the bot promises.
 */
public class LoginActivity extends Activity {

    private EditText baseField;
    private EditText tokenField;
    private Button loginButton;
    private View progress;
    private ImageView ownerPhoto;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        baseField = findViewById(R.id.baseField);
        tokenField = findViewById(R.id.tokenField);
        loginButton = findViewById(R.id.loginButton);
        progress = findViewById(R.id.loginProgress);
        ownerPhoto = findViewById(R.id.ownerPhoto);

        baseField.setText(Prefs.baseUrl(this));
        tokenField.setText(Prefs.token(this));
        //: The bot prints the whole login link; if that is what was pasted, keep
        //: the token and drop the rest (normalizeBase does the dropping).
        String pastedToken = Api.tokenFromUrl(baseField.getText().toString());
        if (!pastedToken.isEmpty() && tokenField.getText().toString().trim().isEmpty()) {
            tokenField.setText(pastedToken);
        }

        findViewById(R.id.ownerCard).setOnClickListener(v -> Blogger.openOwner(this));
        findViewById(R.id.howToLogin).setOnClickListener(v ->
                startActivity(new Intent(this, HowToActivity.class)));
        loginButton.setOnClickListener(v -> attemptLogin());

        Blogger.loadOwner(this, ownerPhoto, findViewById(R.id.ownerName));
        //: The server address is the one piece of setup we can help with: fill in
        //: whatever the bot last published, when the phone has nothing stored.
        if (baseField.getText().toString().trim().isEmpty()) {
            Discover.fillKnownBase(this, baseField, progress);
        }
    }

    private void attemptLogin() {
        final String base = Api.normalizeBase(baseField.getText().toString());
        final String token = tokenField.getText().toString().trim().toUpperCase();
        if (base.isEmpty()) {
            toast(getString(R.string.error_base_required));
            return;
        }
        if (token.isEmpty()) {
            toast(getString(R.string.error_token_required));
            return;
        }
        setBusy(true);
        final AtomicBoolean finished = new AtomicBoolean(false);
        Api.get(Api.tokenUrl(base, token), result -> {
            if (result.ok) {
                Prefs.setBaseUrl(this, base);
                Prefs.setToken(this, token);
                JSONObject account = result.optJson("account");
                String name = account == null ? "" : account.optString("name", "");
                long userId = account == null ? 0L : account.optLong("user_id", 0L);
                Prefs.saveAccount(this, name, userId);
                //: Tell the bot "login in app successful" (it DMs the user once).
                Api.post(Api.tokenUrl(base, token) + "/login", Blogger.loginBody(this), loginResult -> {
                    setBusy(false);
                    if (finished.getAndSet(true)) {
                        return;
                    }
                    toast(loginResult.ok
                            ? getString(R.string.login_ok)
                            : getString(R.string.login_ok_offline));
                    startActivity(new Intent(this, MainActivity.class));
                    finish();
                });
            } else {
                setBusy(false);
                toast(result.error == null ? getString(R.string.login_failed) : result.error);
            }
        });
    }

    private void setBusy(boolean busy) {
        progress.setVisibility(busy ? View.VISIBLE : View.GONE);
        loginButton.setEnabled(!busy);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }
}

/**
 * Shared helpers for the app's little "chrome": the owner card, the version line
 * and the pieces every screen shows in its header.
 */
final class Blogger {

    private Blogger() {
    }

    static void openOwner(Activity activity) {
        String username = Prefs.ownerUsername(activity);
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW,
                    Uri.parse("https://t.me/" + username)));
        } catch (Exception exc) {
            Toast.makeText(activity, "https://t.me/" + username, Toast.LENGTH_LONG).show();
        }
    }

    static JSONObject loginBody(Activity activity) {
        JSONObject body = new JSONObject();
        try {
            body.put("device", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL);
            body.put("app_version", Api.VERSION);
        } catch (Exception ignored) {
        }
        return body;
    }

    /** Load the owner's name + picture into the header (cached per launch). */
    static void loadOwner(Activity activity, ImageView photo, TextView nameView) {
        if (nameView != null) {
            nameView.setText("@" + Prefs.ownerUsername(activity));
        }
        if (photo == null) {
            return;
        }
        String base = Prefs.baseUrl(activity);
        if (base.isEmpty()) {
            return;
        }
        Api.get(Api.normalizeBase(base) + Api.API + "/owner", result -> {
            if (result.ok && nameView != null) {
                JSONObject owner = result.optJson("owner");
                if (owner != null) {
                    String username = owner.optString("username", Prefs.ownerUsername(activity));
                    String display = owner.optString("name", username);
                    Prefs.setOwner(activity, username, display);
                    nameView.setText("@" + username);
                }
            }
        });
        //: The picture is a normal HTTP GET — the app ships no image library.
        new Thread(() -> {
            byte[] data = Api.bytes(Api.normalizeBase(base) + Api.API + "/owner/photo");
            if (data != null && data.length > 0) {
                Bitmap bitmap = BitmapFactory.decodeByteArray(data, 0, data.length);
                if (bitmap != null) {
                    Bitmap round = circle(bitmap);
                    photo.post(() -> photo.setImageDrawable(
                            new BitmapDrawable(activity.getResources(), round)));
                }
            }
        }).start();
    }

    static Bitmap circle(Bitmap source) {
        int size = Math.min(source.getWidth(), source.getHeight());
        Bitmap output = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(output);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        RectF rect = new RectF(0, 0, size, size);
        canvas.drawARGB(0, 0, 0, 0);
        paint.setColor(Color.WHITE);
        canvas.drawOval(rect, paint);
        paint.setXfermode(new android.graphics.PorterDuffXfermode(android.graphics.PorterDuff.Mode.SRC_IN));
        int left = (source.getWidth() - size) / 2;
        int top = (source.getHeight() - size) / 2;
        canvas.drawBitmap(source, -left, -top, paint);
        return output;
    }

    /** A simple labelled field row used by the editor and the settings sheet. */
    static LinearLayout row(Activity activity, String label, View field) {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        TextView text = new TextView(activity);
        text.setText(label);
        text.setTextColor(activity.getColor(R.color.vmore_text_dim));
        text.setTextSize(12f);
        box.addView(text);
        box.addView(field);
        return box;
    }
}
