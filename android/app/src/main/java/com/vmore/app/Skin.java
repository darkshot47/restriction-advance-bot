package com.vmore.app;

import android.app.Activity;
import android.content.Context;
import android.content.res.Configuration;
import android.view.View;

/**
 * The day and night skins.
 *
 * The app ships two palettes of the same three colours — white, blue and black
 * — and this class is the switch between them: values/colors.xml is the day
 * skin (white screens, black text) and values-night/colors.xml is the night
 * skin (black screens, white text).  Every screen calls {@link #apply} before
 * it inflates anything, and {@link #toggle} remembers the choice and rebuilds
 * the screen with a soft transition.
 *
 * The in-app setting wins over the phone's own dark-mode setting, so the app
 * always opens in the skin the user picked here.
 */
final class Skin {

    private Skin() {
    }

    static boolean isNight(Context context) {
        return Prefs.night(context);
    }

    /** What every screen calls first: skin plus the matching system bars. */
    static void prepare(Activity activity) {
        apply(activity);
        bars(activity);
    }

    /**
     * The status bar sits on the app background, so its small icons have to be
     * dark on the day skin and light on the night skin.
     */
    static void bars(Activity activity) {
        View decor = activity.getWindow().getDecorView();
        int flags = decor.getSystemUiVisibility();
        int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        decor.setSystemUiVisibility(isNight(activity) ? (flags & ~light) : (flags | light));
        //: The window itself was built before the skin changed, so its bars and
        //: background are painted again with the colour of the current skin.
        int background = activity.getColor(R.color.vmore_bg);
        activity.getWindow().setStatusBarColor(background);
        activity.getWindow().setNavigationBarColor(background);
        activity.getWindow().setBackgroundDrawable(
                new android.graphics.drawable.ColorDrawable(background));
    }

    /** Pushes the saved skin into this context's resources. */
    static void apply(Context context) {
        int wanted = isNight(context) ? Configuration.UI_MODE_NIGHT_YES
                : Configuration.UI_MODE_NIGHT_NO;
        Configuration current = context.getResources().getConfiguration();
        if ((current.uiMode & Configuration.UI_MODE_NIGHT_MASK) == wanted) {
            return;
        }
        Configuration updated = new Configuration(current);
        updated.uiMode = (current.uiMode & ~Configuration.UI_MODE_NIGHT_MASK) | wanted;
        //: Deprecated on paper, still the only way to re-pick resource
        //: qualifiers at runtime without dragging in AppCompat.
        //noinspection deprecation
        context.getResources().updateConfiguration(updated,
                context.getResources().getDisplayMetrics());
    }

    /** Flips the skin and rebuilds the screen that asked for it. */
    static void toggle(Activity activity) {
        Prefs.setNight(activity, !isNight(activity));
        activity.recreate();
    }

    /** The little sun / moon button in the header. */
    static void paintToggle(Context context, View button) {
        if (button instanceof android.widget.ImageView) {
            ((android.widget.ImageView) button).setImageResource(
                    isNight(context) ? R.drawable.ic_sun : R.drawable.ic_moon);
        }
    }

    static String label(Context context) {
        return isNight(context) ? "Night" : "Day";
    }
}
