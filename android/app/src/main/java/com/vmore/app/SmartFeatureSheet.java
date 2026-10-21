package com.vmore.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

// Launcher dialog opened from the top-left "Smart feature" button in MainActivity.
// Uses ZERO Play-Protect-restricted permissions (no Accessibility service at all):
// only standard floating overlay permission so the compact Smart button & white dot
// float over Telegram across all signed-in accounts.
public final class SmartFeatureSheet {

    private SmartFeatureSheet() {
    }

    public static void show(final Activity activity) {
        if (activity == null || activity.isFinishing()) {
            return;
        }
        final Dialog dialog = new Dialog(activity);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);

        final AuroraDrawable aurora =
                new AuroraDrawable(activity.getResources().getDisplayMetrics().density);
        final Handler watcher = new Handler(Looper.getMainLooper());

        ScrollView scroll = new ScrollView(activity);
        scroll.setVerticalScrollBarEnabled(false);

        LinearLayout card = new LinearLayout(activity);
        card.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable cardBg = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0xFF111827, 0xFF0B1120});
        cardBg.setCornerRadius(Ui.dp(activity, 24));
        cardBg.setStroke(Ui.dp(activity, 1), 0x66818CF8);
        card.setBackground(cardBg);
        card.setPadding(Ui.dp(activity, 18), Ui.dp(activity, 18),
                Ui.dp(activity, 18), Ui.dp(activity, 18));

        LinearLayout hero = new LinearLayout(activity);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setBackground(aurora);
        hero.setPadding(Ui.dp(activity, 16), Ui.dp(activity, 16),
                Ui.dp(activity, 16), Ui.dp(activity, 16));

        LinearLayout headTop = new LinearLayout(activity);
        headTop.setOrientation(LinearLayout.HORIZONTAL);
        headTop.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = new TextView(activity);
        title.setText(R.string.smart_setup_title);
        title.setTextColor(Color.WHITE);
        title.setTextSize(21f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        headTop.addView(title, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button close = actionChip(activity, activity.getString(R.string.common_close),
                0x33FFFFFF, Color.WHITE);
        close.setOnClickListener(v -> dialog.dismiss());
        headTop.addView(close);
        hero.addView(headTop);

        TextView subtitle = new TextView(activity);
        subtitle.setText(R.string.smart_setup_subtitle);
        subtitle.setTextColor(0xFFE0E7FF);
        subtitle.setTextSize(13.5f);
        subtitle.setLineSpacing(0f, 1.15f);
        LinearLayout.LayoutParams subLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        subLp.topMargin = Ui.dp(activity, 8);
        subtitle.setLayoutParams(subLp);
        hero.addView(subtitle);
        card.addView(hero);

        final Button overlayBtn = actionChip(activity,
                activity.getString(R.string.smart_perm_grant), 0xFF2563EB, Color.WHITE);
        overlayBtn.setOnClickListener(v -> openOverlayPermission(activity));
        card.addView(permissionCard(activity,
                activity.getString(R.string.smart_perm_overlay_title),
                activity.getString(R.string.smart_perm_overlay_hint),
                overlayBtn));

        LinearLayout guideBox = new LinearLayout(activity);
        guideBox.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable guideBg = new GradientDrawable();
        guideBg.setColor(0xFF151E2E);
        guideBg.setCornerRadius(Ui.dp(activity, 18));
        guideBg.setStroke(Ui.dp(activity, 1), 0x3338BDF8);
        guideBox.setBackground(guideBg);
        guideBox.setPadding(Ui.dp(activity, 16), Ui.dp(activity, 14),
                Ui.dp(activity, 16), Ui.dp(activity, 14));
        LinearLayout.LayoutParams gLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        gLp.topMargin = Ui.dp(activity, 14);
        guideBox.setLayoutParams(gLp);

        TextView steps = new TextView(activity);
        steps.setText(R.string.smart_guide_steps);
        steps.setTextColor(0xFFCBD5E1);
        steps.setTextSize(13f);
        steps.setLineSpacing(0f, 1.2f);
        guideBox.addView(steps);
        card.addView(guideBox);

        final Button startBtn = new Button(activity);
        startBtn.setAllCaps(false);
        startBtn.setTextSize(15f);
        startBtn.setTypeface(Typeface.DEFAULT_BOLD);
        startBtn.setTextColor(Color.WHITE);
        startBtn.setBackgroundResource(R.drawable.bg_button_glow);
        startBtn.setStateListAnimator(null);
        LinearLayout.LayoutParams startLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(activity, 50));
        startLp.topMargin = Ui.dp(activity, 16);
        startBtn.setLayoutParams(startLp);
        Anim.pressible(startBtn);
        card.addView(startBtn);

        final Button stopBtn = actionChip(activity,
                activity.getString(R.string.smart_stop), 0xFFDC2626, Color.WHITE);
        LinearLayout.LayoutParams stopLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(activity, 44));
        stopLp.topMargin = Ui.dp(activity, 10);
        stopBtn.setLayoutParams(stopLp);
        card.addView(stopBtn);

        final Runnable refreshUi = new Runnable() {
            @Override
            public void run() {
                if (!dialog.isShowing()) {
                    return;
                }
                boolean overlayOk = SmartOverlayService.canDrawOverlays(activity);
                paintPermButton(activity, overlayBtn, overlayOk);

                boolean active = SmartOverlayService.isRunning();
                stopBtn.setVisibility(active ? View.VISIBLE : View.GONE);
                if (!overlayOk) {
                    startBtn.setText(R.string.smart_perm_overlay_title);
                } else {
                    startBtn.setText(active ? R.string.smart_open_menu : R.string.smart_start);
                }
                watcher.postDelayed(this, 750L);
            }
        };

        startBtn.setOnClickListener(v -> {
            if (!SmartOverlayService.canDrawOverlays(activity)) {
                openOverlayPermission(activity);
                return;
            }
            SmartOverlayService.start(activity, true);
            Ui.toast(activity, activity.getString(R.string.smart_started));
            dialog.dismiss();
        });

        stopBtn.setOnClickListener(v -> {
            SmartOverlayService.stop(activity);
            Ui.toast(activity, activity.getString(R.string.smart_stopped));
            dialog.dismiss();
        });

        scroll.addView(card);
        dialog.setContentView(scroll);
        Window win = dialog.getWindow();
        if (win != null) {
            win.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            win.setLayout(ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT);
        }
        dialog.setOnDismissListener(d -> {
            watcher.removeCallbacksAndMessages(null);
            aurora.stop();
            if (activity instanceof MainActivity) {
                Button smartBtn = activity.findViewById(R.id.smartFeatureButton);
                if (smartBtn != null) {
                    smartBtn.setText(SmartOverlayService.isRunning()
                            ? R.string.smart_button_on : R.string.smart_button);
                }
            }
        });
        aurora.start();
        dialog.show();
        refreshUi.run();
    }

    private static View permissionCard(Activity activity, String heading, String detail,
                                       Button action) {
        LinearLayout row = new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xFF151E2E);
        bg.setCornerRadius(Ui.dp(activity, 16));
        bg.setStroke(Ui.dp(activity, 1), 0x3394A3B8);
        row.setBackground(bg);
        row.setPadding(Ui.dp(activity, 14), Ui.dp(activity, 12),
                Ui.dp(activity, 12), Ui.dp(activity, 12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = Ui.dp(activity, 12);
        row.setLayoutParams(lp);

        LinearLayout texts = new LinearLayout(activity);
        texts.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        tlp.rightMargin = Ui.dp(activity, 10);
        texts.setLayoutParams(tlp);

        TextView t1 = new TextView(activity);
        t1.setText(heading);
        t1.setTextColor(Color.WHITE);
        t1.setTextSize(14f);
        t1.setTypeface(Typeface.DEFAULT_BOLD);
        texts.addView(t1);

        TextView t2 = new TextView(activity);
        t2.setText(detail);
        t2.setTextColor(0xFF94A3B8);
        t2.setTextSize(12f);
        t2.setPadding(0, Ui.dp(activity, 3), 0, 0);
        texts.addView(t2);

        row.addView(texts);
        row.addView(action);
        return row;
    }

    private static Button actionChip(Activity activity, String text, int fill, int fg) {
        Button b = new Button(activity);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(12.5f);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setTextColor(fg);
        b.setStateListAnimator(null);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(fill);
        bg.setCornerRadius(Ui.dp(activity, 999));
        b.setBackground(bg);
        b.setPadding(Ui.dp(activity, 14), Ui.dp(activity, 6), Ui.dp(activity, 14), Ui.dp(activity, 6));
        return b;
    }

    private static void paintPermButton(Activity activity, Button btn, boolean granted) {
        btn.setText(granted ? R.string.smart_perm_granted : R.string.smart_perm_grant);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(granted ? 0xFF065F46 : 0xFF2563EB);
        bg.setCornerRadius(Ui.dp(activity, 999));
        btn.setBackground(bg);
        btn.setTextColor(granted ? 0xFFA7F3D0 : Color.WHITE);
    }

    private static void openOverlayPermission(Activity activity) {
        try {
            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + activity.getPackageName()));
            activity.startActivity(intent);
        } catch (Throwable fallback) {
            try {
                activity.startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION));
            } catch (Throwable ignored) {
                Ui.toast(activity, activity.getString(R.string.smart_need_overlay));
            }
        }
    }
}
