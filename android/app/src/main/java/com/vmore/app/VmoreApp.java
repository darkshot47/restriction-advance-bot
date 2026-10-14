package com.vmore.app;

import android.app.Application;

/**
 * The application object: it pushes the saved skin into the process as soon as
 * the app starts, so notifications, dialogs and every screen share the same
 * day or night palette from the very first frame.
 */
public class VmoreApp extends Application {

    @Override
    public void onCreate() {
        super.onCreate();
        Skin.apply(this);
    }
}
