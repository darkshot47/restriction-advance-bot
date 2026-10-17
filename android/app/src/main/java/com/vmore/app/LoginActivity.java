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
    private Button otherAccountButton;
    private ProgressBar progress;
    private View brand;
    /** The last real step; an error is painted on top of it, never instead. */
    private String step = Tg.STATE_CREDENTIALS;
    private String lastDetail = "";
    /** One line the next paint of the keys step should carry. */
    private String note = "";
    /**
     * The pair that was in the boxes when the ready-made walk started.
     *
     * The walk stores each candidate as the app's credentials, so without this
     * a user who pasted their own api_id and api_hash and then tried the keys
     * got them silently overwritten — and the step that asks for them again
     * was asking for something it had just thrown away.
     */
    private String ownApiId = "";
    private String ownApiHash = "";

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

    /** How long a "Connecting…" screen may sit with no answer at all. */
    private static final long ANSWER_SECONDS = 45L;

    /**
     * Gives the screen back when Telegram never answers.
     *
     * The waiting paint hides every field, so before this a request that was
     * sent into a dead connection left the user with nothing to tap.  Now the
     * step returns by itself, with the reason on it.
     */
    private final Runnable noAnswer = new Runnable() {
        @Override
        public void run() {
            if (isFinishing() || trying || Tg.get(LoginActivity.this).isReady()) {
                //: While the ready-made keys are being walked, their own clock
                //: is the timeout; this watchdog would only end the walk early.
                return;
            }
            showError(getString(R.string.login_no_answer));
        }
    };

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
        otherAccountButton = findViewById(R.id.otherAccountButton);

        primaryButton.setOnClickListener(v -> act());
        otherAccountButton.setOnClickListener(v -> switchToOtherAccount());
        apiButton.setOnClickListener(v -> tryReadyKeys());
        backButton.setOnClickListener(v -> secondary());
        linkButton.setOnClickListener(v -> thirdAction());
        Anim.pressible(primaryButton);
        Anim.pressible(linkButton);
        Anim.pressible(apiButton);
        Anim.pressible(backButton);
        Anim.pressible(otherAccountButton);
        Anim.pageIn(brand);
        //: The logo wears the story ring, and the arc never stops travelling.
        StoryRingView ring = findViewById(R.id.logoRing);
        ring.setTurnSeconds(6f);
    }

    @Override
    protected void onResume() {
        super.onResume();
        paintOtherAccount();
        if (trying) {
            handler.removeCallbacks(keyWatch);
            handler.postDelayed(keyWatch, 1000L);
        }
        Tg.get(this).start(this);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(noAnswer);
        handler.removeCallbacks(keyWatch);
        //: The key clock is stopped with the screen; resuming arms it again if
        //: the attempt is still running.
        Tg.get(this).stopListening();
        super.onPause();
    }

    @Override
    public void onState(String newState, String detail) {
        //: Something arrived, so the "no answer" watchdog is no longer needed.
        handler.removeCallbacks(noAnswer);
        if (!Tg.STATE_ERROR.equals(newState)) {
            //: The step the user is really on.  Painting an error must not
            //: forget it, or the screen loses the code field it should return to.
            step = newState;
            paintOtherAccount();
        }
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
            case Tg.STATE_CLOSED:
                //: TDLib closed the session (the phone killed it, another
                //: device logged out, the process was rebuilt).  Ask for a new
                //: one instead of sitting on a dead engine.
                showMessage(getString(R.string.login_working));
                Tg.get(this).start(this);
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
        step = Tg.STATE_CREDENTIALS;
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
        step = Tg.STATE_PHONE;
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
        step = Tg.STATE_CODE;
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
        step = Tg.STATE_PASSWORD;
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
        handler.removeCallbacks(noAnswer);
        if (!trying) {
            handler.postDelayed(noAnswer, ANSWER_SECONDS * 1000L);
        }
    }

    private void showError(String detail) {
        String reason = detail == null || detail.isEmpty()
                ? getString(R.string.common_failed) : detail;
        if (trying) {
            //: Only a refused *key* moves the walk on.  A wrong number, a wrong
            //: code or a flood wait is the user's to fix, and marching through
            //: the rest of the keys would hide it behind "every key was refused".
            if (LoginFlow.anotherKeyMayWork(reason)) {
                nextCandidate(getString(R.string.login_key_refused));
                return;
            }
            stopTrying();
            reason = reason + "\n\n" + getString(R.string.login_key_attempt_paused);
        }
        //: The error is painted on top of the step Telegram is waiting in, so
        //: the field that has to be corrected stays on the screen.
        switch (LoginFlow.stepFor(step)) {
            case Tg.STATE_CODE:
                showCode();
                stepHelp.setText(reason + "\n\n" + getString(R.string.login_code_help));
                break;
            case Tg.STATE_PASSWORD:
                showPassword();
                stepHelp.setText(reason + "\n\n" + getString(R.string.login_password_help));
                break;
            case Tg.STATE_PHONE:
                showPhone();
                stepHelp.setText(reason + "\n\n" + getString(R.string.login_phone_help));
                break;
            default:
                //: The api_id was refused: back to the keys step, with the pair
                //: still in the fields so a typo is one edit away.
                showCredentials();
                stepHelp.setText(reason + "\n\n" + getString(R.string.login_key_hint));
                break;
        }
    }

    private void onSignedIn() {
        //: Remember which built-in key this account accepted, so the next
        //: sign-in does not start with a random one.
        ApiKeys.Key used = ApiKeys.find(Prefs.apiId(this), Prefs.apiHash(this));
        if (used != null) {
            Prefs.saveLastGoodKey(this, used.id, used.hash);
        }
        stepTitle.setText(R.string.login_done);
        stepHelp.setText(Prefs.accountName(this));
        progress.setVisibility(View.GONE);
        primaryButton.setEnabled(false);
        openHome();
    }

    // -------------------------------------------------------------- actions //

    private void act() {
        //: The step the screen is really on.  Reading `state` here meant that
        //: after any error the fields were back on screen but Continue did
        //: nothing at all — the button was alive, the state was "error".
        String current = LoginFlow.stepFor(step);
        if (Tg.STATE_CREDENTIALS.equals(current)) {
            saveCredentials();
            return;
        }
        if (Tg.STATE_PHONE.equals(current)) {
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
        if (Tg.STATE_CODE.equals(current)) {
            String code = codeField.getText().toString().trim();
            if (code.isEmpty()) {
                codeField.setError("type the code Telegram sent");
                return;
            }
            showMessage(getString(R.string.login_working));
            Tg.get(this).submitCode(code);
            return;
        }
        if (Tg.STATE_PASSWORD.equals(current)) {
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
        ownApiId = apiIdField.getText().toString().trim();
        ownApiHash = apiHashField.getText().toString().trim();
        candidates.clear();
        //: The key that produced a code on this phone last time goes first;
        //: the rest follow in a fresh order.
        candidates.addAll(ApiKeys.order(Prefs.lastGoodKeyId(this),
                Prefs.lastGoodKeyHash(this)));
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
            //: Whatever the user had typed is still theirs.
            restoreOwnPair();
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

    /** Puts the pair that was in the boxes back into the stored credentials. */
    private void restoreOwnPair() {
        int id = 0;
        try {
            id = Integer.parseInt(ownApiId);
        } catch (Exception ignored) {
            id = 0;
        }
        if (id > 0 && ownApiHash != null && ownApiHash.length() >= 8) {
            Prefs.saveCredentials(this, id, ownApiHash);
        } else {
            Prefs.clearCredentials(this);
        }
    }

    /** The way out of any step that is not the keys step. */
    private void secondary() {
        if (trying) {
            //: Stop the hunt and hand the screen back for the user's own key,
            //: with the pair they had typed put back where it was.
            stopTrying();
            Tg.get(this).startOver();
            restoreOwnPair();
            note = getString(R.string.login_attempt_stopped);
            showCredentials();
            return;
        }
        //: Back to the keys, with the pair still in the fields so a typo is one
        //: edit away, and with the half session thrown out.  The stored pair is
        //: kept on purpose: clearing it here used to leave someone who only
        //: wanted to correct a phone number staring at two empty boxes.
        Tg.get(this).startOver();
        showCredentials();
    }

    /**
     * The way back to an account that is already signed in.
     *
     * Tapping "switch account" by mistake used to be a one-way door: the app
     * moved to an empty slot, asked for a phone number, and the other account's
     * session was still on the phone but had no button anywhere.  This is that
     * button, and it is on the sign-in screen itself so it survives every step
     * and every error.
     */
    private void paintOtherAccount() {
        if (otherAccountButton == null) {
            return;
        }
        int active = Prefs.activeSlot(this);
        for (int slot = 1; slot <= Prefs.slotCount(this); slot++) {
            if (slot == active || !Prefs.slotHasAccount(this, slot)) {
                continue;
            }
            otherAccountButton.setTag(slot);
            otherAccountButton.setText(getString(R.string.login_back_to_account)
                    + " " + Prefs.slotLabel(this, slot));
            if (otherAccountButton.getVisibility() != View.VISIBLE) {
                otherAccountButton.setVisibility(View.VISIBLE);
                Anim.fadeIn(otherAccountButton, 220);
            }
            return;
        }
        otherAccountButton.setTag(null);
        otherAccountButton.setVisibility(View.GONE);
    }

    /**
     * The device's own Back button follows the same rule as the button on the
     * screen: an account that is still signed in is one tap away, and a switch
     * made by mistake can never leave the phone on a login nobody asked for.
     */
    @Override
    public void onBackPressed() {
        if (otherAccountButton != null
                && otherAccountButton.getVisibility() == View.VISIBLE) {
            switchToOtherAccount();
            return;
        }
        super.onBackPressed();
    }

    /** Moves back to a signed-in slot, whichever step this screen is on. */
    private void switchToOtherAccount() {
        Object tag = otherAccountButton.getTag();
        int target = tag instanceof Integer ? (Integer) tag : 0;
        if (target <= 0 || target == Prefs.activeSlot(this)) {
            paintOtherAccount();
            return;
        }
        stopTrying();
        Tg.get(this).useSlot(target);
        Tg.get(this).start(null);
        openHome();
    }

    /**
     * The home screen, reusing the one already in the stack.
     *
     * Without the two flags every sign-in left a second MainActivity under the
     * first, so Back walked through copies of the same screen.
     */
    private void openHome() {
        Intent home = new Intent(this, MainActivity.class);
        home.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(home);
        finish();
    }

    /** The third action: my.telegram.org on the keys step, another code on the
     *  code step. */
    private void thirdAction() {
        if (Tg.STATE_CODE.equals(LoginFlow.stepFor(step))) {
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
