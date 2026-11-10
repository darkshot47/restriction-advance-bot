package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;

/**
 * The app's design system in one place: spacing, type, circular profile avatars
 * and the row builders the dynamic lists use.
 */
final class Ui {

    private Ui() {
    }

    /** A round crop of a bitmap with no third-party image library. */
    static Bitmap circle(Context context, Bitmap source, int sizeDp) {
        int size = Math.max(1, dp(context, sizeDp));
        int side = Math.min(source.getWidth(), source.getHeight());
        Bitmap squared = Bitmap.createBitmap(source,
                (source.getWidth() - side) / 2, (source.getHeight() - side) / 2, side, side);
        Bitmap scaled = Bitmap.createScaledBitmap(squared, size, size, true);
        Bitmap out = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(out);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setShader(new android.graphics.BitmapShader(scaled,
                android.graphics.Shader.TileMode.CLAMP, android.graphics.Shader.TileMode.CLAMP));
        float radius = size / 2f;
        canvas.drawCircle(radius, radius, radius, paint);
        return out;
    }

    /** Crisp circular monogram fallback when a chat has no Telegram profile photo. */
    static Bitmap monogram(Context context, String label, int sizeDp) {
        int size = Math.max(1, dp(context, sizeDp));
        Bitmap out = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(out);
        Paint bg = new Paint(Paint.ANTI_ALIAS_FLAG);
        bg.setColor(context.getColor(R.color.vmore_blue));
        float r = size / 2f;
        canvas.drawCircle(r, r, r, bg);

        String glyph = initial(label);
        Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
        text.setColor(context.getColor(R.color.vmore_on_accent));
        text.setTypeface(Typeface.DEFAULT_BOLD);
        text.setTextAlign(Paint.Align.CENTER);
        text.setTextSize(size * 0.42f);
        Paint.FontMetrics fm = text.getFontMetrics();
        float baseline = r - (fm.ascent + fm.descent) / 2f;
        canvas.drawText(glyph, r, baseline, text);
        return out;
    }

    static String initial(String label) {
        if (label != null) {
            String trimmed = label.trim();
            for (int index = 0; index < trimmed.length(); index++) {
                char ch = trimmed.charAt(index);
                if (Character.isLetterOrDigit(ch)) {
                    return String.valueOf(Character.toUpperCase(ch));
                }
            }
        }
        return "V";
    }

    /**
     * Paints a chat or destination channel's real circular profile picture into
     * an {@link ImageView}, downloading it into app cache on demand when needed.
     */
    static void paintChatAvatar(final Context context, final ImageView target,
                                final Tg.Chat chat, final int sizeDp) {
        if (target == null) {
            return;
        }
        if (chat == null) {
            target.setPadding(dp(context, 9), dp(context, 9), dp(context, 9), dp(context, 9));
            target.setScaleType(ImageView.ScaleType.FIT_CENTER);
            target.setImageResource(R.drawable.ic_chat);
            return;
        }
        target.setTag(chat.id);
        target.setPadding(0, 0, 0, 0);
        target.setScaleType(ImageView.ScaleType.FIT_CENTER);

        if (chat.photoPath != null && !chat.photoPath.isEmpty() && new File(chat.photoPath).exists()) {
            Bitmap full = BitmapFactory.decodeFile(chat.photoPath);
            if (full != null) {
                target.setImageBitmap(circle(context, full, sizeDp));
                return;
            }
        }
        if (chat.miniThumb != null && chat.miniThumb.length > 0) {
            Bitmap mini = BitmapFactory.decodeByteArray(chat.miniThumb, 0, chat.miniThumb.length);
            if (mini != null) {
                target.setImageBitmap(circle(context, mini, sizeDp));
            } else {
                target.setImageBitmap(monogram(context, chat.title, sizeDp));
            }
        } else {
            target.setImageBitmap(monogram(context, chat.title, sizeDp));
        }

        if (chat.photoFileId != 0) {
            Tg.get(context).loadChatPhoto(chat, new Tg.Cb<String>() {
                @Override
                public void ok(String path) {
                    if (!Long.valueOf(chat.id).equals(target.getTag()) || path == null || path.isEmpty()) {
                        return;
                    }
                    Bitmap loaded = BitmapFactory.decodeFile(path);
                    if (loaded != null) {
                        target.setPadding(0, 0, 0, 0);
                        target.setScaleType(ImageView.ScaleType.FIT_CENTER);
                        target.setImageBitmap(circle(context, loaded, sizeDp));
                    }
                }

                @Override
                public void fail(String message) {
                }
            });
        }
    }

    /** A chat row with a real 42dp circular profile photo, title and subtitle. */
    static LinearLayout chatRow(Context context, Tg.Chat chat, String subtitle) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(context, 16), dp(context, 11), dp(context, 16), dp(context, 11));

        ImageView avatar = new ImageView(context);
        avatar.setBackgroundResource(R.drawable.bg_avatar);
        int px = dp(context, 42);
        LinearLayout.LayoutParams avatarParams = new LinearLayout.LayoutParams(px, px);
        avatarParams.setMargins(0, 0, dp(context, 14), 0);
        row.addView(avatar, avatarParams);
        paintChatAvatar(context, avatar, chat, 42);

        LinearLayout texts = new LinearLayout(context);
        texts.setOrientation(LinearLayout.VERTICAL);
        TextView titleView = new TextView(context);
        titleView.setText(chat == null ? "" : chat.title);
        titleView.setTextColor(context.getColor(R.color.vmore_text));
        titleView.setTextSize(15f);
        titleView.setMaxLines(1);
        titleView.setEllipsize(android.text.TextUtils.TruncateAt.END);
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

    /** A pill chip; {@code active} paints it blue, matching the app palette. */
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
            case QJob.COPYING:
                return "Copying instantly";
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
        int white = view.getContext().getColor(R.color.vmore_text_dim);
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
