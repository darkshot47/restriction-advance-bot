package com.vmore.app;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

/**
 * "How to use?" — served by the bot itself (``/api/v2/howto``) so the text can be
 * improved server-side without shipping a new APK.  A bundled copy is shown when
 * the server cannot be reached.
 */
public class HowToActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_howto);
        TextView body = findViewById(R.id.howtoBody);
        body.setText(bundled());
        Api.get(Api.normalizeBase(Prefs.baseUrl(this)) + Api.API + "/howto", result -> {
            if (result.ok) {
                String text = result.optString("text", "");
                if (!text.isEmpty()) {
                    body.setText(text.replace("**", ""));
                }
            }
        });
    }

    private String bundled() {
        return "How to use Vmore\n\n"
                + "1. Get your access token\n"
                + "Send /gentoken in the bot. You get a short code — that is your login. "
                + "No phone number, no OTP.\n\n"
                + "2. Log in here\n"
                + "Enter the server address and the token on the first screen.\n\n"
                + "3. Paste a link\n"
                + "Public link → the bot sends it to your Telegram DM, nothing downloads "
                + "here.\nPrivate link → it downloads into the app using your own Telegram "
                + "data, so it is unlimited.\n\n"
                + "4. Edit before uploading\n"
                + "Change the caption, set a thumbnail, trim the video from the front or "
                + "the back — then upload. The file goes back through your own account.\n\n"
                + "5. Keep or watch\n"
                + "Save to device, play the video, open documents — and see every download "
                + "and history in one list.\n\n"
                + "Downloading keeps running with the app closed: the notification shows "
                + "progress with Pause and Stop, and tells you the moment it finishes.\n\n"
                + "A token is valid for 30 days. Afterwards send /gentoken again for a "
                + "fresh code, or revoke a token any time with /revoketoken.";
    }
}
