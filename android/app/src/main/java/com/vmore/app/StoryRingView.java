package com.vmore.app;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.SweepGradient;
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

    /** The colours of the developer card's ring, in the order they travel. */
    private static final int[] STORY_COLOURS = {
            0xFF60A5FA, 0xFF8B5CF6, 0xFF22D3EE, 0xFFF472B6, 0xFFF59E0B, 0xFF60A5FA,
    };

    private ValueAnimator animator;
    private float angle = -90f;
    private float sweep = 64f;
    private boolean rainbow;
    private SweepGradient rainbowShader;
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

    /** A multicolour ring, used only by the developer card. */
    public void setRainbow(boolean value) {
        rainbow = value;
        if (!rainbow) {
            arc.setShader(null);
        } else {
            buildRainbow();
        }
        invalidate();
    }

    /** The quiet track colour, changed on the dark developer card. */
    public void setTrackColor(int color) {
        ring.setColor(color);
        invalidate();
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
            if (rainbow && rainbowShader != null) {
                arc.setShader(rainbowShader);
            }
            canvas.drawOval(oval, arc);
            return;
        }
        canvas.drawOval(oval, ring);
        if (rainbow && rainbowShader != null) {
            arc.setShader(rainbowShader);
        }
        canvas.drawArc(oval, angle, sweep, false, arc);
    }

    /** The sweep shader is built once the view has a size. */
    private void buildRainbow() {
        if (getWidth() == 0 || getHeight() == 0) {
            return;
        }
        rainbowShader = new SweepGradient(getWidth() / 2f, getHeight() / 2f,
                STORY_COLOURS, null);
        invalidate();
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
        if (rainbow) {
            buildRainbow();
        }
        if (!spinning) {
            start();
        }
    }
}
