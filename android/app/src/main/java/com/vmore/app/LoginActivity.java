package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;

/**
 * The first screen — and the only login Vmore has.
 *
 * There is no server address and no access token any more. The user signs into
 * their own Telegram account: once the app credentials are stored (my.telegram.org),
 * the phone number, the code Telegram sends and — when the account has it — the
 * two-step password bring the session up. TDLib keeps that session on the phone,
 * so reopening the app lands straight on the home screen.
 */
public class LoginActivity extends Activity implements Tg.Listener {

    private TextView stepTitle;
    private TextView stepHelp;
    private EditText apiIdField;
    private EditText apiHashField;
    private EditText phoneField;
    private EditText codeField;
    private EditText passwordField;
    private Button primaryButton;
    private Button linkButton;
    private ProgressBar progress;
    private View brand;
    private String state = Tg.STATE_CREDENTIALS;
    private String lastDetail = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_login);

        stepTitle = findViewById(R.id.stepTitle);
        stepHelp = findViewById(R.id.stepHelp);
        apiIdField = findViewById(R.id.apiIdField);
        apiHashField = findViewById(R.id.apiHashField);
        phoneField = findViewById(R.id.phoneField);
        codeField = findViewById(R.id.codeField);
        passwordField = findViewById(R.id.passwordField);
        primaryButton = findViewById(R.id.primaryButton);
        linkButton = findViewById(R.id.linkButton);
        progress = findViewById(R.id.loginProgress);
        brand = findViewById(R.id.brandBox);

        TextView version = findViewById(R.id.versionText);
        version.setText(getString(R.string.settings_version) + " " + Vmore.VERSION);

        apiIdField.setText(Prefs.apiId(this) == 0 ? "" : String.valueOf(Prefs.apiId(this)));
        apiHashField.setText(Prefs.apiHash(this));

        primaryButton.setOnClickListener(v -> act());
        linkButton.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Vmore.CREDENTIALS_URL)));
            } catch (Exception exc) {
                Ui.toast(this, Vmore.CREDENTIALS_URL);
            }
        });
        Anim.pressible(primaryButton);
        Anim.pressible(linkButton);
        Anim.pageIn(brand);
    }

    @Override
    protected void onResume() {
        super.onResume();
        Tg.get(this).start(this);
    }

    @Override
    protected void onPause() {
        Tg.get(this).stopListening();
        super.onPause();
    }

    @Override
    public void onState(String newState, String detail) {
        state = newState;
        lastDetail = detail == null ? "" : detail;
        switch (newState) {
            case Tg.STATE_NONE:
                showMessage(getString(R.string.login_no_engine));
                break;
            case Tg.STATE_CREDENTIALS:
                showCredentials();
                break;
            case Tg.STATE_PARAMETERS:
                showMessage(getString(R.string.login_working));
                break;
            case Tg.STATE_PHONE:
                showPhone();
                break;
            case Tg.STATE_CODE:
                showCode();
                break;
            case Tg.STATE_PASSWORD:
                showPassword();
                break;
            case Tg.STATE_READY:
                onSignedIn();
                break;
            case Tg.STATE_ERROR:
                showError(detail);
                break;
            default:
                showMessage(getString(R.string.login_working));
                break;
        }
    }

    // ------------------------------------------------------------ the steps //

    private void showCredentials() {
        stepTitle.setText(R.string.login_step_credentials);
        stepHelp.setText(R.string.login_credentials_help);
        visible(apiIdField, apiHashField);
        primaryButton.setText(R.string.login_continue);
        linkButton.setText(R.string.login_open_my_telegram);
        linkButton.setVisibility(View.VISIBLE);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        Anim.fadeIn(apiIdField, 220);
        Anim.fadeIn(apiHashField, 260);
    }

    private void showPhone() {
        stepTitle.setText(R.string.login_step_phone);
        stepHelp.setText(R.string.login_phone_help);
        phoneField.setText(Prefs.phone(this));
        phoneField.setInputType(InputType.TYPE_CLASS_PHONE);
        visible(phoneField);
        primaryButton.setText(R.string.login_continue);
        linkButton.setVisibility(View.GONE);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        Anim.fadeIn(phoneField, 220);
    }

    private void showCode() {
        stepTitle.setText(R.string.login_step_code);
        stepHelp.setText(R.string.login_code_help);
        codeField.setText("");
        codeField.setInputType(InputType.TYPE_CLASS_NUMBER);
        visible(codeField);
        primaryButton.setText(R.string.login_continue);
        linkButton.setVisibility(View.GONE);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        Anim.fadeIn(codeField, 220);
    }

    private void showPassword() {
        stepTitle.setText(R.string.login_step_password);
        stepHelp.setText(lastDetail.isEmpty()
                ? getString(R.string.login_password_help)
                : getString(R.string.login_password_help) + " (hint: " + lastDetail + ")");
        passwordField.setText("");
        passwordField.setInputType(InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        visible(passwordField);
        primaryButton.setText(R.string.login_continue);
        linkButton.setVisibility(View.GONE);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        Anim.fadeIn(passwordField, 220);
    }

    private void showMessage(String message) {
        stepTitle.setText(R.string.login_working);
        stepHelp.setText(message);
        hide(apiIdField, apiHashField, phoneField, codeField, passwordField);
        primaryButton.setText(R.string.login_continue);
        primaryButton.setEnabled(false);
        linkButton.setVisibility(View.GONE);
        progress.setVisibility(View.VISIBLE);
    }

    private void showError(String detail) {
        stepTitle.setText(R.string.login_working);
        stepHelp.setText(detail == null || detail.isEmpty()
                ? getString(R.string.common_failed) : detail);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        //: Re-show the field that matches the state Telegram is waiting in.
        switch (state) {
            case Tg.STATE_CODE:
                visible(codeField);
                break;
            case Tg.STATE_PASSWORD:
                visible(passwordField);
                break;
            case Tg.STATE_CREDENTIALS:
                visible(apiIdField, apiHashField);
                linkButton.setVisibility(View.VISIBLE);
                break;
            default:
                visible(phoneField);
                break;
        }
    }

    private void onSignedIn() {
        stepTitle.setText(R.string.login_done);
        stepHelp.setText(Prefs.accountName(this));
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(false);
        startActivity(new Intent(this, MainActivity.class));
        finish();
    }

    // -------------------------------------------------------------- actions //

    private void act() {
        if (Tg.STATE_CREDENTIALS.equals(state)) {
            saveCredentials();
            return;
        }
        if (Tg.STATE_PHONE.equals(state)) {
            String phone = phoneField.getText().toString().trim();
            if (phone.length() < 6) {
                phoneField.setError("enter your number with the country code");
                return;
            }
            showMessage(getString(R.string.login_working));
            Tg.get(this).submitPhone(phone);
            return;
        }
        if (Tg.STATE_CODE.equals(state)) {
            String code = codeField.getText().toString().trim();
            if (code.isEmpty()) {
                codeField.setError("type the code Telegram sent");
                return;
            }
            showMessage(getString(R.string.login_working));
            Tg.get(this).submitCode(code);
            return;
        }
        if (Tg.STATE_PASSWORD.equals(state)) {
            String password = passwordField.getText().toString();
            if (password.isEmpty()) {
                passwordField.setError("type your two-step password");
                return;
            }
            showMessage(getString(R.string.login_working));
            Tg.get(this).submitPassword(password);
        }
    }

    private void saveCredentials() {
        String idText = apiIdField.getText().toString().trim();
        String hash = apiHashField.getText().toString().trim();
        int apiId;
        try {
            apiId = Integer.parseInt(idText);
        } catch (Exception exc) {
            apiIdField.setError("api_id is a number");
            return;
        }
        if (apiId <= 0 || hash.length() < 8) {
            apiHashField.setError("paste the api_hash from my.telegram.org");
            return;
        }
        Prefs.saveCredentials(this, apiId, hash);
        showMessage(getString(R.string.login_working));
        Tg.get(this).restartWithCredentials();
    }

    // -------------------------------------------------------------- helpers //

    private void visible(View... views) {
        for (View view : views) {
            view.setVisibility(View.VISIBLE);
        }
    }

    private void hide(View... views) {
        for (View view : views) {
            view.setVisibility(View.GONE);
        }
    }
}
