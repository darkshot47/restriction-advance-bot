package com.vmore.app;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.app.Activity;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PathMeasure;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.SweepGradient;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewAnimationUtils;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

// Opening intro curtain played when Vmore launches before revealing app UI.
public final class LaunchIntro {

    private static final long INTRO_DURATION_MS = 1580L;
    private static final long REDUCED_DURATION_MS = 420L;

    private LaunchIntro() {
    }

    public static boolean playIfNeeded(final Activity activity, final Runnable onComplete) {
        if (activity == null || activity.isFinishing() || !VmoreApp.consumeLaunchIntro()) {
            if (onComplete != null) {
                onComplete.run();
            }
            return false;
        }
        final View decor = activity.getWindow() == null
                ? null : activity.getWindow().getDecorView();
        final ViewGroup root = decor instanceof ViewGroup ? (ViewGroup) decor : null;
        if (root == null) {
            if (onComplete != null) {
                onComplete.run();
            }
            return false;
        }

        final float density = activity.getResources().getDisplayMetrics().density;
        final AuroraDrawable aurora = new AuroraDrawable(density);

        final FrameLayout curtain = new FrameLayout(activity);
        curtain.setClickable(true);
        curtain.setFocusable(true);
        curtain.setBackground(aurora);
        curtain.setElevation(Ui.dp(activity, 96));

        final EmblemCanvas stage = new EmblemCanvas(activity);
        curtain.addView(stage, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        LinearLayout captionBox = new LinearLayout(activity);
        captionBox.setOrientation(LinearLayout.VERTICAL);
        captionBox.setGravity(Gravity.CENTER_HORIZONTAL);
        captionBox.setPadding(Ui.dp(activity, 28), Ui.dp(activity, 152),
                Ui.dp(activity, 28), Ui.dp(activity, 32));
        captionBox.setAlpha(0f);
        captionBox.setTranslationY(Ui.dp(activity, 18));

        TextView brandTitle = new TextView(activity);
        brandTitle.setText(R.string.app_name);
        brandTitle.setTextColor(0xFFFFFFFF);
        brandTitle.setTextSize(30f);
        brandTitle.setTypeface(Typeface.DEFAULT_BOLD);
        brandTitle.setLetterSpacing(0.04f);
        brandTitle.setGravity(Gravity.CENTER);
        captionBox.addView(brandTitle);

        TextView subtitle = new TextView(activity);
        subtitle.setText(R.string.intro_subtitle);
        subtitle.setTextColor(0xFFBBD0FF);
        subtitle.setTextSize(13.5f);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        subParams.topMargin = Ui.dp(activity, 6);
        subtitle.setLayoutParams(subParams);
        captionBox.addView(subtitle);

        FrameLayout.LayoutParams boxParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER);
        curtain.addView(captionBox, boxParams);

        root.addView(curtain, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        aurora.start();

        long duration = Anim.motionOff(activity) ? REDUCED_DURATION_MS : INTRO_DURATION_MS;
        final ValueAnimator timeline = ValueAnimator.ofFloat(0f, 1f);
        timeline.setDuration(duration);
        timeline.setInterpolator(new DecelerateInterpolator(1.35f));
        timeline.addUpdateListener(anim -> {
            float t = (Float) anim.getAnimatedValue();
            stage.setProgress(t);
            float textPhase = clamp((t - 0.22f) / 0.34f);
            captionBox.setAlpha(textPhase);
            captionBox.setTranslationY(Ui.dp(activity, 18) * (1f - textPhase));
        });
        timeline.addListener(new AnimatorListenerAdapter() {
            private boolean finished;

            @Override
            public void onAnimationEnd(Animator animation) {
                if (finished) {
                    return;
                }
                finished = true;
                dismissCurtain(activity, root, curtain, aurora, onComplete);
            }
        });
        curtain.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener() {
            @Override
            public void onViewAttachedToWindow(View v) {
            }

            @Override
            public void onViewDetachedFromWindow(View v) {
                aurora.stop();
                if (timeline.isRunning()) {
                    timeline.cancel();
                }
            }
        });
        timeline.start();
        return true;
    }

    private static void dismissCurtain(final Activity activity, final ViewGroup root,
                                       final FrameLayout curtain, final AuroraDrawable aurora,
                                       final Runnable onComplete) {
        if (activity.isFinishing() || activity.isDestroyed()) {
            aurora.stop();
            root.removeView(curtain);
            return;
        }
        if (onComplete != null) {
            onComplete.run();
        }
        if (activity.isFinishing()) {
            // Activity is transitioning into Home with fade transition; keep curtain
            // steady during the outgoing window fade so there is zero flash.
            aurora.stop();
            return;
        }
        int cx = curtain.getWidth() / 2;
        int cy = curtain.getHeight() / 2 - Ui.dp(activity, 34);
        float startRadius = (float) Math.hypot(
                Math.max(cx, curtain.getWidth() - cx),
                Math.max(cy, curtain.getHeight() - cy));
        if (!Anim.motionOff(activity) && curtain.isAttachedToWindow() && startRadius > 0f) {
            try {
                Animator reveal = ViewAnimationUtils.createCircularReveal(
                        curtain, cx, Math.max(0, cy), startRadius, 0f);
                reveal.setDuration(300L);
                reveal.setInterpolator(new DecelerateInterpolator());
                reveal.addListener(new AnimatorListenerAdapter() {
                    @Override
                    public void onAnimationEnd(Animator animation) {
                        aurora.stop();
                        root.removeView(curtain);
                    }
                });
                curtain.animate().alpha(0.15f).setDuration(300L).start();
                reveal.start();
                return;
            } catch (Throwable ignored) {
            }
        }
        curtain.animate()
                .alpha(0f)
                .setDuration(220L)
                .withEndAction(() -> {
                    aurora.stop();
                    root.removeView(curtain);
                })
                .start();
    }

    private static float clamp(float v) {
        return v < 0f ? 0f : (v > 1f ? 1f : v);
    }

    private static final class EmblemCanvas extends View {
        private final Paint cardPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint borderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint orbitPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint ripplePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint glyphPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint glyphGlowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint railTrackPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint railFillPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF cardRect = new RectF();
        private final RectF orbitRect = new RectF();
        private final RectF railRect = new RectF();
        private final Path glyphFull = new Path();
        private final Path glyphPartial = new Path();
        private final PathMeasure measure = new PathMeasure();
        private final Matrix shaderMatrix = new Matrix();
        private SweepGradient sweep;
        private LinearGradient railGradient;
        private float progress;

        EmblemCanvas(Context context) {
            super(context);
            cardPaint.setColor(0xE6111625);
            borderPaint.setStyle(Paint.Style.STROKE);
            borderPaint.setStrokeWidth(Ui.dp(context, 2));
            orbitPaint.setStyle(Paint.Style.STROKE);
            orbitPaint.setStrokeCap(Paint.Cap.ROUND);
            orbitPaint.setStrokeWidth(Ui.dp(context, 3));
            ripplePaint.setStyle(Paint.Style.STROKE);
            ripplePaint.setStrokeWidth(Ui.dp(context, 2));

            glyphPaint.setStyle(Paint.Style.STROKE);
            glyphPaint.setStrokeCap(Paint.Cap.ROUND);
            glyphPaint.setStrokeJoin(Paint.Join.ROUND);
            glyphPaint.setStrokeWidth(Ui.dp(context, 6));
            glyphPaint.setColor(0xFFFFFFFF);

            glyphGlowPaint.setStyle(Paint.Style.STROKE);
            glyphGlowPaint.setStrokeCap(Paint.Cap.ROUND);
            glyphGlowPaint.setStrokeJoin(Paint.Join.ROUND);
            glyphGlowPaint.setStrokeWidth(Ui.dp(context, 12));
            glyphGlowPaint.setColor(0x5538BDF8);

            railTrackPaint.setColor(0x33FFFFFF);
        }

        void setProgress(float value) {
            progress = value;
            invalidate();
        }

        @Override
        protected void onSizeChanged(int w, int h, int oldw, int oldh) {
            super.onSizeChanged(w, h, oldw, oldh);
            sweep = new SweepGradient(0f, 0f,
                    new int[]{0xFF38BDF8, 0xFF818CF8, 0xFFC084FC, 0xFF34D399, 0xFF38BDF8},
                    null);
            orbitPaint.setShader(sweep);
            borderPaint.setShader(sweep);
            float railHalf = Ui.dp(getContext(), 76);
            railGradient = new LinearGradient(-railHalf, 0f, railHalf, 0f,
                    new int[]{0xFF38BDF8, 0xFF818CF8, 0xFF34D399},
                    null, Shader.TileMode.CLAMP);
            railFillPaint.setShader(railGradient);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            int w = getWidth();
            int h = getHeight();
            if (w <= 0 || h <= 0) {
                return;
            }
            float cx = w * 0.5f;
            float cy = h * 0.5f - Ui.dp(getContext(), 34);
            float scale = 0.72f + 0.28f * clamp(progress / 0.35f);

            canvas.save();
            canvas.translate(cx, cy);

            // Expanding pulse halo
            float pulse = clamp((progress - 0.08f) / 0.75f);
            float rippleRadius = Ui.dp(getContext(), 54) + Ui.dp(getContext(), 48) * pulse;
            ripplePaint.setColor(((int) ((1f - pulse) * 110f) << 24) | 0x0038BDF8);
            canvas.drawCircle(0f, 0f, rippleRadius, ripplePaint);

            // Rotating rainbow-cyan orbital arc
            if (sweep != null) {
                shaderMatrix.reset();
                shaderMatrix.setRotate(progress * 420f);
                sweep.setLocalMatrix(shaderMatrix);
            }
            float orbitRadius = Ui.dp(getContext(), 56) * scale;
            orbitRect.set(-orbitRadius, -orbitRadius, orbitRadius, orbitRadius);
            canvas.drawArc(orbitRect, -90f + progress * 220f, 250f * clamp(progress / 0.55f),
                    false, orbitPaint);

            // Frosted emblem squircle
            float half = Ui.dp(getContext(), 44) * scale;
            float corner = Ui.dp(getContext(), 24) * scale;
            cardRect.set(-half, -half, half, half);
            canvas.drawRoundRect(cardRect, corner, corner, cardPaint);
            canvas.drawRoundRect(cardRect, corner, corner, borderPaint);

            // Animated V monogram stroke draw
            float strokePhase = clamp((progress - 0.06f) / 0.48f);
            if (strokePhase > 0f) {
                float gx = half * 0.44f;
                float gy = half * 0.40f;
                glyphFull.reset();
                glyphFull.moveTo(-gx, -gy);
                glyphFull.lineTo(0f, gy);
                glyphFull.lineTo(gx, -gy);
                measure.setPath(glyphFull, false);
                glyphPartial.reset();
                measure.getSegment(0f, measure.getLength() * strokePhase, glyphPartial, true);
                canvas.drawPath(glyphPartial, glyphGlowPaint);
                canvas.drawPath(glyphPartial, glyphPaint);
            }

            // Bottom progress rail under caption block
            float railY = Ui.dp(getContext(), 144);
            float railHalf = Ui.dp(getContext(), 76);
            float railH = Ui.dp(getContext(), 4);
            railRect.set(-railHalf, railY, railHalf, railY + railH);
            canvas.drawRoundRect(railRect, railH, railH, railTrackPaint);
            float fillRight = -railHalf + (railHalf * 2f) * clamp(progress / 0.94f);
            railRect.set(-railHalf, railY, fillRight, railY + railH);
            canvas.drawRoundRect(railRect, railH, railH, railFillPaint);

            canvas.restore();
        }
    }
}
