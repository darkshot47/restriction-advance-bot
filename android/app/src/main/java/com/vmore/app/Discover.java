package com.vmore.app;

import android.app.Activity;
import android.view.View;
import android.widget.EditText;

/**
 * Fills the server address when the APK was built with a default.
 *
 * The owner asked for the address to be typed in the app, so nothing is
 * hard-coded: the workflow may bake in a default URL (optional input) and this
 * helper only offers it as a starting point — the field stays editable.
 */
final class Discover {

    private Discover() {
    }

    static void fillKnownBase(Activity activity, EditText baseField, View progress) {
        if (progress != null) {
            progress.setVisibility(View.GONE);
        }
        if (!baseField.getText().toString().trim().isEmpty()) {
            return;
        }
        try {
            String baked = activity.getString(R.string.default_base_url);
            if (baked != null && !baked.trim().isEmpty()) {
                baseField.setText(baked.trim());
            }
        } catch (Exception ignored) {
        }
    }
}
