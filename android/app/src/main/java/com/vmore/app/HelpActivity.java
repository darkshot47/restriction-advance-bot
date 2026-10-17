package com.vmore.app;

import android.app.Activity;
import android.os.Bundle;
import android.widget.ImageView;
import android.widget.TextView;

/**
 * The short guide: how a link becomes a file in a chat, and what the settings
 * change. Plain words, no emoji.
 */
public class HelpActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_help);
        ImageView back = findViewById(R.id.backButton);
        back.setOnClickListener(v -> finish());
        TextView body = findViewById(R.id.helpText);
        body.setText(R.string.help_body);
        Anim.pageIn(findViewById(R.id.helpHeader));
        Anim.pageIn(body);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
    }

}
