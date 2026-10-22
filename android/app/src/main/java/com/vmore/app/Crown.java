package com.vmore.app;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.LinearGradient;
import android.graphics.Shader;
import android.text.TextPaint;
import android.view.View;
import android.widget.ImageView;
import android.widget.TextView;

/**
 * The colourful "Smart feature" mark: a king's crown that breathes and a label
 * whose colour slides across it.
 *
 * Both animations are deliberately tiny: they only redraw two small views, they
 * stop with the screen, and they never touch the floating overlay windows, so a
 * shimmering chip can never cost the smoothness the overlay was fixed for.
 */
final class Crown {

    private static final int[] COLOURS = {
            0xFFFDE68A, 0xFFF59E0B, 0xFFF472B6, 0xFFA78BFA, 0xFF38BDF8, 0xFF34D399,
    };

    private Crown() {
    }

    /** Binds the crown and the gradient label, and starts the gentle animation. */
    static ValueAnimator bind(Context context, View chip, ImageView crown, TextView label) {
        if (chip == null || crown == null || label == null) {
            return null;
        }
        float density = context.getResources().getDisplayMetrics().density;
        paintText(label, 0f);

        //: One animator drives both: the crown rocks a little and the gradient
        //: slides across the letters, so the two movements stay in step.
        ValueAnimator animator = ValueAnimator.ofFloat(0f, 1f);
        animator.setDuration(2600L);
        animator.setRepeatCount(ValueAnimator.INFINITE);
        animator.setRepeatMode(ValueAnimator.RESTART);
        animator.addUpdateListener(animation -> {
            float t = (float) animation.getAnimatedValue();
            crown.setRotation((float) Math.sin(t * Math.PI * 2.0) * 7f);
            crown.setScaleX(1f + (float) Math.sin(t * Math.PI * 2.0) * 0.05f);
            crown.setScaleY(1f - (float) Math.sin(t * Math.PI * 2.0) * 0.05f);
            paintText(label, t * density * 40f);
        });
        chip.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener() {
            @Override
            public void onViewAttachedToWindow(View view) {
                if (!animator.isStarted()) {
                    animator.start();
                }
            }

            @Override
            public void onViewDetachedFromWindow(View view) {
                animator.cancel();
            }
        });
        animator.start();
        return animator;
    }

    /**
     * Gives the text one gradient that spans its own width.
     *
     * The shader is rebuilt only when the view is measured or the offset moves,
     * which is what keeps the shimmer free of allocations in the draw path.
     */
    static void paintText(TextView label, float offset) {
        if (label == null) {
            return;
        }
        TextPaint paint = label.getPaint();
        float width = Math.max(1f, (float) label.getWidth());
        if (width <= 1f) {
            width = label.getPaint().measureText(String.valueOf(label.getText()));
        }
        float span = Math.max(width, paint.getTextSize() * 3f);
        paint.setShader(new LinearGradient(
                -span + offset, 0f,
                offset, paint.getTextSize(),
                COLOURS, null, Shader.TileMode.MIRROR));
        label.invalidate();
    }

    /** Repaints the label once it has a real width (the first layout pass). */
    static void refresh(TextView label) {
        paintText(label, 0f);
    }
}
