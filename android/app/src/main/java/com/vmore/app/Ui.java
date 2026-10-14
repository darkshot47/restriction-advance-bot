package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * The app's design system in one place: spacing, type and the row builders the
 * dynamic lists use.
 *
 * Only three colours exist here — white, blue and black — and no emoji or
 * asterisks are ever put on screen.
 */
final class Ui {

    private Ui() {
    }

    /**
     * A round crop of a bitmap: the account picture sits in a circle in the
     * header, and no third-party image library is involved.
     */
    static android.graphics.Bitmap circle(Context context, android.graphics.Bitmap source,
                                          int sizeDp) {
        int size = Math.max(1, dp(context, sizeDp));
        int side = Math.min(source.getWidth(), source.getHeight());
        android.graphics.Bitmap squared = android.graphics.Bitmap.createBitmap(source,
                (source.getWidth() - side) / 2, (source.getHeight() - side) / 2, side, side);
        android.graphics.Bitmap scaled = android.graphics.Bitmap.createScaledBitmap(squared,
                size, size, true);
        android.graphics.Bitmap out = android.graphics.Bitmap.createBitmap(size, size,
                android.graphics.Bitmap.Config.ARGB_8888);
        android.graphics.Canvas canvas = new android.graphics.Canvas(out);
        android.graphics.Paint paint = new android.graphics.Paint(
                android.graphics.Paint.ANTI_ALIAS_FLAG);
        paint.setShader(new android.graphics.BitmapShader(scaled,
                android.graphics.Shader.TileMode.CLAMP, android.graphics.Shader.TileMode.CLAMP));
        float radius = size / 2f;
        canvas.drawCircle(radius, radius, radius, paint);
        return out;
    }

    static int dp(Context context, float value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    /** A plain labelled row: icon, title, subtitle. */
    static LinearLayout row(Context context, int iconRes, String title, String subtitle) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(context, 16), dp(context, 14), dp(context, 16), dp(context, 14));

        ImageView icon = new ImageView(context);
        icon.setImageResource(iconRes);
        LinearLayout.LayoutParams iconParams =
                new LinearLayout.LayoutParams(dp(context, 22), dp(context, 22));
        iconParams.setMargins(0, 0, dp(context, 14), 0);
        row.addView(icon, iconParams);

        LinearLayout texts = new LinearLayout(context);
        texts.setOrientation(LinearLayout.VERTICAL);
        TextView titleView = new TextView(context);
        titleView.setText(title);
        titleView.setTextColor(context.getColor(R.color.vmore_text));
        titleView.setTextSize(15f);
        texts.addView(titleView);
        if (subtitle != null && !subtitle.isEmpty()) {
            TextView subtitleView = new TextView(context);
            subtitleView.setText(subtitle);
            subtitleView.setTextColor(context.getColor(R.color.vmore_text_dim));
            subtitleView.setTextSize(12.5f);
            subtitleView.setPadding(0, dp(context, 3), 0, 0);
            texts.addView(subtitleView);
        }
        row.addView(texts, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        return row;
    }

    static TextView title(Context context, String text) {
        TextView view = new TextView(context);
        view.setText(text);
        view.setTextColor(context.getColor(R.color.vmore_text));
        view.setTextSize(15f);
        view.setMaxLines(2);
        return view;
    }

    static TextView subtitle(Context context, String text) {
        TextView view = new TextView(context);
        view.setText(text);
        view.setTextColor(context.getColor(R.color.vmore_text_dim));
        view.setTextSize(12.5f);
        view.setPadding(0, dp(context, 3), 0, 0);
        view.setMaxLines(2);
        return view;
    }

    static TextView section(Context context, String text) {
        TextView view = new TextView(context);
        view.setText(text);
        view.setTextColor(context.getColor(R.color.vmore_text_faint));
        view.setTextSize(11f);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setLetterSpacing(0.12f);
        view.setAllCaps(true);
        view.setPadding(dp(context, 4), dp(context, 16), dp(context, 4), dp(context, 8));
        return view;
    }

    static View divider(Context context) {
        View view = new View(context);
        view.setBackgroundColor(context.getColor(R.color.vmore_stroke_soft));
        view.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Math.max(1, dp(context, 0.8f))));
        return view;
    }

    /** A pill chip; `active` paints it blue, exactly like the design asks. */
    static Button chip(Activity activity, String label, boolean active,
                       View.OnClickListener click) {
        Button button = new Button(activity);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(13f);
        button.setBackgroundResource(active ? R.drawable.bg_chip_active : R.drawable.bg_chip);
        button.setTextColor(active ? activity.getColor(R.color.vmore_on_accent)
                : activity.getColor(R.color.vmore_text_dim));
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        int padH = dp(activity, 14);
        int padV = dp(activity, 8);
        button.setPadding(padH, padV, padH, padV);
        button.setStateListAnimator(null);
        button.setOnClickListener(click);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 0, dp(activity, 8), dp(activity, 8));
        button.setLayoutParams(params);
        Anim.pressible(button);
        return button;
    }

    static ImageView icon(Context context, int resId, int sizeDp) {
        ImageView view = new ImageView(context);
        view.setImageResource(resId);
        view.setLayoutParams(new LinearLayout.LayoutParams(dp(context, sizeDp),
                dp(context, sizeDp)));
        return view;
    }

    static int iconForKind(String kind) {
        if ("video".equals(kind)) {
            return R.drawable.ic_play;
        }
        if ("photo".equals(kind)) {
            return R.drawable.ic_image;
        }
        if ("audio".equals(kind)) {
            return R.drawable.ic_speed;
        }
        return R.drawable.ic_folder;
    }

    static String kindLabel(String kind) {
        if ("video".equals(kind)) {
            return "video";
        }
        if ("photo".equals(kind)) {
            return "photo";
        }
        if ("audio".equals(kind)) {
            return "audio";
        }
        return "file";
    }

    static String stageLabel(String stage) {
        if (stage == null) {
            return "";
        }
        switch (stage) {
            case QJob.QUEUED:
                return "Queued";
            case QJob.RESOLVING:
                return "Reading the link";
            case QJob.DOWNLOADING:
                return "Downloading";
            case QJob.UPLOADING:
                return "Uploading";
            case QJob.DONE:
                return "Done";
            case QJob.FAILED:
                return "Failed";
            case QJob.PAUSED:
                return "Paused";
            case QJob.CANCELLED:
                return "Cancelled";
            default:
                return stage;
        }
    }

    static void toast(Context context, String text) {
        Toast.makeText(context, text, Toast.LENGTH_SHORT).show();
    }

    /** The confirm dialog every destructive action goes through. */
    static void confirm(Activity activity, String title, String message, String positive,
                        Runnable action) {
        new AlertDialog.Builder(activity)
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton(positive, (dialog, which) -> action.run())
                .setNegativeButton(R.string.common_cancel, null)
                .show();
    }

    static void tintSwitch(android.widget.Switch view) {
        int blue = view.getContext().getColor(R.color.vmore_blue);
        int white = view.getContext().getColor(R.color.vmore_white_dim);
        view.setThumbTintList(new ColorStateList(
                new int[][]{
                        new int[]{android.R.attr.state_checked},
                        new int[]{-android.R.attr.state_checked}},
                new int[]{blue, white}));
        view.setTrackTintList(new ColorStateList(
                new int[][]{
                        new int[]{android.R.attr.state_checked},
                        new int[]{-android.R.attr.state_checked}},
                new int[]{view.getContext().getColor(R.color.vmore_blue_soft),
                        view.getContext().getColor(R.color.vmore_stroke)}));
    }
}
