package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

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
    private Button apiButton;
    private Button backButton;
    private ProgressBar progress;
    private View brand;
    private String state = Tg.STATE_CREDENTIALS;
    private String lastDetail = "";
    /** One line the next paint of the keys step should carry. */
    private String note = "";

    //: The ready-made key attempt: which keys are left, how long the current
    //: one has had, and the countdown that gives up on it.
    private final List<ApiKeys.Key> candidates = new ArrayList<>();
    private int candidate = -1;
    private boolean trying;
    private long keyStartedAt;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable keyWatch = new Runnable() {
        @Override
        public void run() {
            if (!trying) {
                return;
            }
            long used = (System.currentTimeMillis() - keyStartedAt) / 1000L;
            long left = KEY_SECONDS - used;
            if (left <= 0) {
                nextCandidate(getString(R.string.login_key_refused));
                return;
            }
            stepHelp.setText(getString(R.string.login_trying_key) + " "
                    + (candidate + 1) + " / " + candidates.size()
                    + " • " + left + " " + getString(R.string.login_trying_left));
            handler.postDelayed(this, 1000L);
        }
    };

    /** How long one ready-made key is given to produce a login code. */
    private static final long KEY_SECONDS = 60L;

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

        apiButton = findViewById(R.id.apiButton);
        backButton = findViewById(R.id.backButton);

        primaryButton.setOnClickListener(v -> act());
        apiButton.setOnClickListener(v -> tryReadyKeys());
        backButton.setOnClickListener(v -> secondary());
        linkButton.setOnClickListener(v -> thirdAction());
        Anim.pressible(primaryButton);
        Anim.pressible(linkButton);
        Anim.pressible(apiButton);
        Anim.pressible(backButton);
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
        String help = getString(R.string.login_credentials_help) + "\n\n"
                + getString(R.string.login_ready_help);
        if (!note.isEmpty()) {
            help = help + "\n\n" + note;
            note = "";
        }
        stepHelp.setText(help);
        apiIdField.setText(Prefs.apiId(this) == 0 ? "" : String.valueOf(Prefs.apiId(this)));
        apiHashField.setText(Prefs.apiHash(this));
        visible(apiIdField, apiHashField);
        primaryButton.setText(R.string.login_continue);
        primaryButton.setVisibility(View.VISIBLE);
        linkButton.setText(R.string.login_open_my_telegram);
        linkButton.setVisibility(View.VISIBLE);
        apiButton.setVisibility(View.VISIBLE);
        backButton.setVisibility(View.GONE);
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
        primaryButton.setVisibility(View.VISIBLE);
        linkButton.setVisibility(View.GONE);
        apiButton.setVisibility(View.GONE);
        //: On the credentials step this button is the way back to the keys; a
        //: wrong api_id used to leave the number screen with no way out of it.
        backButton.setText(R.string.login_change_keys);
        backButton.setVisibility(View.VISIBLE);
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(true);
        Anim.fadeIn(phoneField, 220);
        if (trying) {
            //: The key was accepted — Telegram only asks for a number after it
            //: has taken the app credentials.  A known number is sent right away
            //: so the attempt can measure real progress; with no number yet the
            //: clock waits for the human instead of counting down on them.
            backButton.setText(R.string.login_stop_trying);
            String saved = Prefs.phone(this);
            if (saved.length() >= 6) {
                Tg.get(this).submitPhone(saved);
            } else {
                handler.removeCallbacks(keyWatch);
                stepHelp.setText(R.string.login_key_accepted);
            }
        }
    }

    /** Starts (or restarts) the countdown for the key being tried. */
    private void startKeyClock() {
        keyStartedAt = System.currentTimeMillis();
        handler.removeCallbacks(keyWatch);
        handler.postDelayed(keyWatch, 1000L);
    }

    private void showCode() {
        if (trying) {
            //: The code is on its way, which is exactly what the attempt was
            //: waiting for: it stops here, on whichever key Telegram accepted.
            stopTrying();
            Ui.toast(this, getString(R.string.login_key_worked));
        }
        stepTitle.setText(R.string.login_step_code);
        stepHelp.setText(R.string.login_code_help);
        codeField.setText("");
        codeField.setInputType(InputType.TYPE_CLASS_NUMBER);
        visible(codeField);
        primaryButton.setText(R.string.login_continue);
        primaryButton.setVisibility(View.VISIBLE);
        linkButton.setText(R.string.login_resend_code);
        linkButton.setVisibility(View.VISIBLE);
        apiButton.setVisibility(View.GONE);
        backButton.setText(R.string.login_change_keys);
        backButton.setVisibility(View.VISIBLE);
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
        primaryButton.setVisibility(View.VISIBLE);
        linkButton.setVisibility(View.GONE);
        apiButton.setVisibility(View.GONE);
        backButton.setText(R.string.login_change_keys);
        backButton.setVisibility(View.VISIBLE);
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
        primaryButton.setVisibility(View.INVISIBLE);
        linkButton.setVisibility(View.GONE);
        apiButton.setVisibility(View.GONE);
        if (trying) {
            //: The way out of the attempt survives every repaint of the screen.
            backButton.setText(R.string.login_stop_trying);
            backButton.setVisibility(View.VISIBLE);
        } else {
            backButton.setVisibility(View.GONE);
        }
        progress.setVisibility(View.VISIBLE);
    }

    private void showError(String detail) {
        if (trying) {
            //: A refused key is not the end of the attempt: the next one goes.
            nextCandidate(getString(R.string.login_key_refused));
            return;
        }
        if (looksLikeKeyProblem(detail) || Tg.STATE_CREDENTIALS.equals(state)) {
            //: The api_id was refused.  Before this, the screen fell through to
            //: the number field and there was no way back to the keys.
            showCredentials();
            stepHelp.setText((detail == null || detail.isEmpty()
                    ? getString(R.string.common_failed) : detail) + "\n\n"
                    + getString(R.string.login_key_hint));
            return;
        }
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
                showCredentials();
                stepHelp.setText((detail == null || detail.isEmpty()
                        ? getString(R.string.common_failed) : detail) + "\n\n"
                        + getString(R.string.login_key_hint));
                break;
            default:
                //: Any other complaint gets a way back to the keys as well, so
                //: a wrong number or a dead session is never a dead end.
                visible(phoneField);
                backButton.setText(R.string.login_change_keys);
                backButton.setVisibility(View.VISIBLE);
                primaryButton.setVisibility(View.VISIBLE);
                break;
        }
    }

    /** True when Telegram is complaining about the app key, not about a code. */
    private static boolean looksLikeKeyProblem(String detail) {
        String lower = detail == null ? "" : detail.toLowerCase(Locale.US);
        return lower.contains("api_id") || lower.contains("api id")
                || lower.contains("api_hash") || lower.contains("api hash")
                || lower.contains("published") || lower.contains("app key")
                || lower.contains("app_id") || lower.contains("hash");
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
            if (trying) {
                //: The user supplied the number the attempt needed: from here it
                //: is Telegram's turn, and the deadline applies again.
                startKeyClock();
            }
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

    // ------------------------------------------------- the ready-made keys //

    /**
     * Walks the ready-made keys the owner asked for.
     *
     * Each key gets {@link #KEY_SECONDS} seconds to produce a login code.  A key
     * Telegram refuses is left behind at once, the number is sent the moment the
     * phone step appears, and the whole attempt ends — success or exhaustion —
     * with the screen back in the user's hands.
     */
    private void tryReadyKeys() {
        candidates.clear();
        candidates.addAll(ApiKeys.order());
        candidate = -1;
        trying = true;
        Log.step(this, "key attempt: trying " + candidates.size() + " ready-made keys");
        nextCandidate("");
    }

    private void nextCandidate(String why) {
        if (!trying) {
            return;
        }
        candidate++;
        if (candidate >= candidates.size()) {
            stopTrying();
            //: Every key was refused: the user's own pair is the way forward.
            Tg.get(this).forgetCredentials();
            Tg.get(this).startOver();
            note = getString(R.string.login_keys_exhausted);
            showCredentials();
            Log.step(this, "key attempt: every ready-made key was refused");
            return;
        }
        ApiKeys.Key key = candidates.get(candidate);
        keyStartedAt = System.currentTimeMillis();
        stepTitle.setText(R.string.login_working);
        stepHelp.setText(getString(R.string.login_trying_key) + " " + (candidate + 1)
                + " / " + candidates.size() + " • " + key.shortName());
        hide(apiIdField, apiHashField, phoneField, codeField, passwordField);
        progress.setVisibility(View.VISIBLE);
        primaryButton.setVisibility(View.INVISIBLE);
        linkButton.setVisibility(View.GONE);
        apiButton.setVisibility(View.GONE);
        backButton.setText(R.string.login_stop_trying);
        backButton.setVisibility(View.VISIBLE);
        Prefs.saveCredentials(this, key.id, key.hash);
        Tg.get(this).restartWithCredentials();
        startKeyClock();
        if (!why.isEmpty()) {
            Log.step(this, "key attempt: " + why + " — moved to key " + (candidate + 1));
        }
    }

    private void stopTrying() {
        trying = false;
        handler.removeCallbacks(keyWatch);
    }

    /** The way out of any step that is not the keys step. */
    private void secondary() {
        if (trying) {
            //: Stop the hunt and hand the screen back for the user's own key.
            stopTrying();
            note = getString(R.string.login_attempt_stopped);
            showCredentials();
            return;
        }
        //: Back to the keys, with the pair still in the fields so a typo is one
        //: edit away, and with the half session thrown out.
        Tg.get(this).forgetCredentials();
        Tg.get(this).startOver();
        showCredentials();
    }

    /** The third action: my.telegram.org on the keys step, another code on the
     *  code step. */
    private void thirdAction() {
        if (Tg.STATE_CODE.equals(state)) {
            Tg.get(this).resendCode();
            Ui.toast(this, getString(R.string.login_resend_sent));
            return;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Vmore.CREDENTIALS_URL)));
        } catch (Exception exc) {
            Ui.toast(this, Vmore.CREDENTIALS_URL);
        }
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
