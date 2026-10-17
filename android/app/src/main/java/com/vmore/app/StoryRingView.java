package com.vmore.app;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;
import android.view.animation.LinearInterpolator;

/**
 * The story ring: a circle drawn around a profile picture or the logo, with a
 * short arc that travels around it for as long as the view is on screen.
 *
 * The owner asked for the ring Telegram shows around a profile with an active
 * story, and for one animation that never ends.  This is that animation, and it
 * is deliberately quiet: a thin ring, one bright arc, no bounce and no colour
 * outside the white, blue and black palette.
 *
 * The arc stops when the view leaves the window, so a screen in the background
 * costs nothing.
 */
public class StoryRingView extends View {

    private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint arc = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private final float stroke;

    private ValueAnimator animator;
    private float angle = -90f;
    private float sweep = 64f;
    /** Seconds for one full turn; zero draws a still ring. */
    private float turnSeconds;
    private boolean spinning;

    public StoryRingView(Context context) {
        this(context, null);
    }

    public StoryRingView(Context context, AttributeSet attrs) {
        super(context, attrs);
        float density = context.getResources().getDisplayMetrics().density;
        stroke = Math.max(2f, 2.4f * density);
        ring.setStyle(Paint.Style.STROKE);
        ring.setStrokeWidth(stroke);
        ring.setColor(context.getColor(R.color.vmore_blue_soft));
        arc.setStyle(Paint.Style.STROKE);
        arc.setStrokeWidth(stroke);
        arc.setStrokeCap(Paint.Cap.ROUND);
        arc.setColor(context.getColor(R.color.vmore_blue));
    }

    /** Sets the speed: 0 keeps the ring still, anything else spins forever. */
    public void setTurnSeconds(float seconds) {
        turnSeconds = Math.max(0f, seconds);
        sweep = turnSeconds == 0f ? 360f : 64f;
        if (turnSeconds == 0f) {
            stop();
            angle = -90f;
            invalidate();
            return;
        }
        if (isAttachedToWindow() && getWindowVisibility() == VISIBLE) {
            start();
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float inset = stroke / 2f + 1f;
        oval.set(inset, inset, getWidth() - inset, getHeight() - inset);
        if (sweep >= 359f) {
            arc.setStyle(Paint.Style.STROKE);
            canvas.drawOval(oval, arc);
            return;
        }
        canvas.drawOval(oval, ring);
        canvas.drawArc(oval, angle, sweep, false, arc);
    }

    private void start() {
        if (spinning || turnSeconds <= 0f || getWidth() == 0) {
            return;
        }
        spinning = true;
        animator = ValueAnimator.ofFloat(0f, 360f);
        animator.setDuration((long) (turnSeconds * 1000f));
        animator.setRepeatCount(ValueAnimator.INFINITE);
        animator.setInterpolator(new LinearInterpolator());
        animator.addUpdateListener(value -> {
            angle = -90f + (Float) value.getAnimatedValue();
            invalidate();
        });
        animator.start();
    }

    private void stop() {
        spinning = false;
        if (animator != null) {
            animator.cancel();
            animator = null;
        }
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (getWindowVisibility() == VISIBLE) {
            start();
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        stop();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onWindowVisibilityChanged(int visibility) {
        super.onWindowVisibilityChanged(visibility);
        if (visibility == VISIBLE) {
            start();
        } else {
            stop();
        }
    }

    @Override
    protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
        super.onSizeChanged(width, height, oldWidth, oldHeight);
        if (!spinning) {
            start();
        }
    }
}
