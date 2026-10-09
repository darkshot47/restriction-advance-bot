package com.vmore.app;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import org.json.JSONObject;

/**
 * The direct-mode login: the user signs into **Telegram itself** on this
 * phone (TDLib — phone number, code, optional 2FA password).  After that,
 * every byte of private content travels phone ↔ Telegram and the Render
 * host spends no bandwidth on that user at all.
 *
 * The screen is deliberately tiny: a status line, one input that changes
 * meaning with the auth state, and a Continue button.
 */
public class TdLoginActivity extends Activity implements TdDirect.Listener {

    private TextView status;
    private EditText input;
    private Button submit;
    private Button logout;
    private String state = "init";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_tdlogin);
        status = findViewById(R.id.tdStatus);
        input = findViewById(R.id.tdInput);
        submit = findViewById(R.id.tdSubmit);
        logout = findViewById(R.id.tdLogout);

        logout.setOnClickListener(v -> TdDirect.get(this).logout());
        submit.setOnClickListener(v -> submit());

        if (TdDirect.get(this).nativeAvailable()) {
            rememberServerConfig();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        TdDirect.get(this).start(this);
    }

    @Override
    protected void onPause() {
        TdDirect.get(this).stopListening();
        super.onPause();
    }

    /** Learn (and cache) the TDLib credentials + bot username from the server. */
    private void rememberServerConfig() {
        if (Prefs.tdApiId(this) != 0 && !Prefs.botUsername(this).isEmpty()) {
            return;
        }
        String base = Prefs.baseUrl(this);
        if (base.isEmpty()) {
            return;
        }
        Api.get(base + "/api/v2/app", result -> {
            if (result.ok && result.json != null) {
                JSONObject json = result.json;
                Prefs.saveTdConfig(this, json.optInt("td_api_id", 0),
                        json.optString("td_api_hash", ""),
                        json.optString("bot_username", ""));
                if (Prefs.tdApiId(this) != 0) {
                    TdDirect.get(this).start(this);
                } else {
                    status.setText("⚠️ This server did not hand over the Telegram app "
                            + "credentials, so direct mode cannot start here.");
                }
            }
        });
    }

    // ------------------------------------------------------------- state //

    @Override
    public void onState(String newState, String detail) {
        state = newState;
        switch (newState) {
            case "parameters":
                setWaiting("Waking the Telegram engine up…");
                break;
            case "phone":
                showInput("Your Telegram phone number", "+91 90000 00000",
                        InputType.TYPE_CLASS_PHONE);
                break;
            case "code":
                showInput("The code Telegram just sent you", "12345",
                        InputType.TYPE_CLASS_NUMBER);
                break;
            case "password":
                showInput(detail == null || detail.isEmpty()
                                ? "Two-step verification password"
                                : "Two-step password (hint: " + detail + ")",
                        "password", InputType.TYPE_CLASS_TEXT
                                | InputType.TYPE_TEXT_VARIATION_PASSWORD);
                break;
            case "ready":
                input.setVisibility(View.GONE);
                submit.setVisibility(View.GONE);
                logout.setVisibility(View.VISIBLE);
                status.setText("✅ Direct mode is ON. Downloads and uploads now use your "
                        + "phone data only — the server spends nothing on them.");
                break;
            case "closed":
                setWaiting("Signed out of direct mode.");
                break;
            case "error":
                setWaiting("⚠️ " + (detail == null ? "something went wrong" : detail));
                break;
            default:
                setWaiting("Starting…");
                break;
        }
    }

    private void setWaiting(String text) {
        status.setText(text);
        input.setVisibility(View.GONE);
        submit.setVisibility(View.GONE);
        logout.setVisibility(View.GONE);
    }

    private void showInput(String label, String hint, int inputType) {
        status.setText(label);
        input.setText("");
        input.setHint(hint);
        input.setInputType(inputType);
        input.setVisibility(View.VISIBLE);
        submit.setVisibility(View.VISIBLE);
        logout.setVisibility(View.GONE);
        submit.setEnabled(true);
    }

    private void submit() {
        String value = input.getText().toString().trim();
        if (value.isEmpty()) {
            input.setError("type it first");
            return;
        }
        submit.setEnabled(false);
        TdDirect direct = TdDirect.get(this);
        switch (state) {
            case "phone":
                direct.submitPhone(value);
                break;
            case "code":
                direct.submitCode(value);
                break;
            case "password":
                direct.submitPassword(value);
                break;
            default:
                submit.setEnabled(true);
                break;
        }
        android.os.Handler main = new android.os.Handler(android.os.Looper.getMainLooper());
        main.postDelayed(() -> submit.setEnabled(true), 1500);
    }
}
