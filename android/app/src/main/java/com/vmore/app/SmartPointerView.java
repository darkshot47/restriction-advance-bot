package com.vmore.app;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.SweepGradient;
import android.graphics.Typeface;
import android.os.Build;
import android.view.GestureDetector;
import android.view.HapticFeedbackConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.animation.LinearInterpolator;

// Custom floating views for Smart Feature:
// 1) Small precision white circle pointer supporting drag + double-tap capture/paste.
// 2) Colorful floating orb button that toggles the full Smart Feature control menu.
public final class SmartPointerView extends View {

    public static final int MODE_WHITE_CIRCLE = 0;
    public static final int MODE_MENU_ORB = 1;

    public static final int STATE_IDLE = 0;
    public static final int STATE_SCANNING = 1;
    public static final int STATE_CAPTURED = 2;
    public static final int STATE_TRANSFERRING = 3;
    public static final int STATE_ALERT = 4;

    public interface InteractionListener {
        void onMoveBy(int dx, int dy);

        void onDragFinished();

        void onSingleTap();

        void onDoubleTap(int centerRawX, int centerRawY);
    }

    private final int mode;
    private final Paint outerGlowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ringPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint corePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint strokePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint dotPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ripplePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint badgePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint badgeTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glyphPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF ringRect = new RectF();
    private final Matrix sweepMatrix = new Matrix();
    private final GestureDetector detector;
    private final ValueAnimator spinner;
    private final int touchSlop;

    private InteractionListener listener;
    private SweepGradient rainbowSweep;
    private int visualState = STATE_IDLE;
    private int badgeCount = 0;
    private int transferPercent = 0;
    private float angle = 0f;
    private float tapRipple = 1f;

    private float downRawX;
    private float downRawY;
    private float lastRawX;
    private float lastRawY;
    private boolean dragging;

    public SmartPointerView(Context context, int viewMode) {
        super(context);
        this.mode = viewMode;
        this.touchSlop = ViewConfiguration.get(context).getScaledTouchSlop();

        ringPaint.setStyle(Paint.Style.STROKE);
        ringPaint.setStrokeCap(Paint.Cap.ROUND);
        ringPaint.setStrokeWidth(Ui.dp(context, mode == MODE_WHITE_CIRCLE ? 2 : 3));

        strokePaint.setStyle(Paint.Style.STROKE);
        strokePaint.setStrokeWidth(Ui.dp(context, 1));
        strokePaint.setColor(0x550F172A);

        ripplePaint.setStyle(Paint.Style.STROKE);
        ripplePaint.setStrokeWidth(Ui.dp(context, 2));

        badgePaint.setColor(0xFF10B981);
        badgeTextPaint.setColor(Color.WHITE);
        badgeTextPaint.setTextSize(Ui.dp(context, 10));
        badgeTextPaint.setTypeface(Typeface.DEFAULT_BOLD);
        badgeTextPaint.setTextAlign(Paint.Align.CENTER);

        glyphPaint.setStyle(Paint.Style.STROKE);
        glyphPaint.setStrokeCap(Paint.Cap.ROUND);
        glyphPaint.setStrokeJoin(Paint.Join.ROUND);
        glyphPaint.setStrokeWidth(Ui.dp(context, 3));
        glyphPaint.setColor(Color.WHITE);

        detector = new GestureDetector(context, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onSingleTapConfirmed(MotionEvent e) {
                if (listener != null) {
                    performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
                    listener.onSingleTap();
                }
                return true;
            }

            @Override
            public boolean onDoubleTap(MotionEvent e) {
                triggerRipple();
                performHapticFeedback(Build.VERSION.SDK_INT >= 27
                        ? HapticFeedbackConstants.KEYBOARD_TAP
                        : HapticFeedbackConstants.LONG_PRESS);
                if (listener != null) {
                    int[] loc = new int[2];
                    getLocationOnScreen(loc);
                    int cx = loc[0] + getWidth() / 2;
                    int cy = loc[1] + getHeight() / 2;
                    listener.onDoubleTap(cx, cy);
                }
                return true;
            }
        });

        spinner = ValueAnimator.ofFloat(0f, 360f);
        spinner.setDuration(2600L);
        spinner.setRepeatCount(ValueAnimator.INFINITE);
        spinner.setInterpolator(new LinearInterpolator());
        spinner.addUpdateListener(anim -> {
            angle = (Float) anim.getAnimatedValue();
            if (tapRipple < 1f) {
                tapRipple = Math.min(1f, tapRipple + 0.07f);
            }
            invalidate();
        });
    }

    public void setInteractionListener(InteractionListener value) {
        this.listener = value;
    }

    public void setVisualState(int state, int count, int percent) {
        this.visualState = state;
        this.badgeCount = Math.max(0, count);
        this.transferPercent = Math.max(0, Math.min(100, percent));
        invalidate();
    }

    public void triggerRipple() {
        tapRipple = 0f;
        invalidate();
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (!spinner.isRunning()) {
            spinner.start();
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        spinner.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        rainbowSweep = new SweepGradient(w * 0.5f, h * 0.5f,
                new int[]{0xFF38BDF8, 0xFF818CF8, 0xFFC084FC, 0xFFF472B6, 0xFF34D399, 0xFF38BDF8},
                null);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float cx = getWidth() * 0.5f;
        float cy = getHeight() * 0.5f;
        if (cx <= 0f || cy <= 0f) {
            return;
        }
        if (mode == MODE_MENU_ORB) {
            drawMenuOrb(canvas, cx, cy);
        } else {
            drawWhiteCirclePointer(canvas, cx, cy);
        }
    }

    private void drawWhiteCirclePointer(Canvas canvas, float cx, float cy) {
        float coreRadius = Ui.dp(getContext(), 11);
        float haloRadius = Ui.dp(getContext(), 16);

        // Double-tap shockwave ripple
        if (tapRipple < 1f) {
            float rr = coreRadius + Ui.dp(getContext(), 10) * tapRipple;
            int alpha = (int) ((1f - tapRipple) * 210f);
            ripplePaint.setColor((alpha << 24) | 0x00FFFFFF);
            canvas.drawCircle(cx, cy, rr, ripplePaint);
        }

        // Subtle dark contrast shadow halo so white circle pops on pure white backgrounds too
        outerGlowPaint.setColor(0x40000000);
        canvas.drawCircle(cx, cy + Ui.dp(getContext(), 1), coreRadius + Ui.dp(getContext(), 2),
                outerGlowPaint);

        // State ring around the crisp white circle
        ringRect.set(cx - haloRadius, cy - haloRadius, cx + haloRadius, cy + haloRadius);
        ringPaint.setShader(null);
        if (visualState == STATE_SCANNING && rainbowSweep != null) {
            sweepMatrix.reset();
            sweepMatrix.setRotate(angle * 2.2f, cx, cy);
            rainbowSweep.setLocalMatrix(sweepMatrix);
            ringPaint.setShader(rainbowSweep);
            canvas.drawArc(ringRect, angle * 2f, 270f, false, ringPaint);
        } else if (visualState == STATE_CAPTURED) {
            ringPaint.setColor(0xFF10B981);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        } else if (visualState == STATE_TRANSFERRING) {
            ringPaint.setColor(0x4438BDF8);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
            ringPaint.setColor(0xFF38BDF8);
            float sweepDeg = transferPercent > 0 ? (transferPercent * 3.6f) : 120f;
            float startDeg = transferPercent > 0 ? -90f : angle * 1.8f;
            canvas.drawArc(ringRect, startDeg, sweepDeg, false, ringPaint);
        } else if (visualState == STATE_ALERT) {
            ringPaint.setColor(0xFFF59E0B);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        } else {
            ringPaint.setColor(0x8838BDF8);
            canvas.drawArc(ringRect, angle, 200f, false, ringPaint);
        }

        // Pure crisp white circle body
        corePaint.setColor(0xFFFFFFFF);
        canvas.drawCircle(cx, cy, coreRadius, corePaint);
        canvas.drawCircle(cx, cy, coreRadius, strokePaint);

        // Precision center target dot
        dotPaint.setColor(visualState == STATE_CAPTURED ? 0xFF10B981 : 0xFF2563EB);
        canvas.drawCircle(cx, cy, Ui.dp(getContext(), 2), dotPaint);

        if (badgeCount > 0) {
            drawBadge(canvas, cx + coreRadius * 0.85f, cy - coreRadius * 0.85f, badgeCount);
        }
    }

    private void drawMenuOrb(Canvas canvas, float cx, float cy) {
        float orbRadius = Ui.dp(getContext(), 21);

        outerGlowPaint.setColor(0x48000000);
        canvas.drawCircle(cx, cy + Ui.dp(getContext(), 2), orbRadius + Ui.dp(getContext(), 1),
                outerGlowPaint);

        corePaint.setColor(0xF2121829);
        canvas.drawCircle(cx, cy, orbRadius, corePaint);

        if (rainbowSweep != null) {
            sweepMatrix.reset();
            sweepMatrix.setRotate(angle, cx, cy);
            rainbowSweep.setLocalMatrix(sweepMatrix);
            ringPaint.setShader(rainbowSweep);
        } else {
            ringPaint.setColor(0xFF38BDF8);
        }
        ringRect.set(cx - orbRadius, cy - orbRadius, cx + orbRadius, cy + orbRadius);
        canvas.drawOval(ringRect, ringPaint);

        // Crisp V emblem inside colorful orb
        float gx = Ui.dp(getContext(), 6);
        float gy = Ui.dp(getContext(), 6);
        canvas.drawLine(cx - gx, cy - gy, cx, cy + gy, glyphPaint);
        canvas.drawLine(cx, cy + gy, cx + gx, cy - gy, glyphPaint);

        if (badgeCount > 0) {
            drawBadge(canvas, cx + orbRadius * 0.72f, cy - orbRadius * 0.72f, badgeCount);
        }
    }

    private void drawBadge(Canvas canvas, float bx, float by, int count) {
        float r = Ui.dp(getContext(), 8);
        canvas.drawCircle(bx, by, r, badgePaint);
        String text = count > 9 ? "9+" : String.valueOf(count);
        Paint.FontMetrics fm = badgeTextPaint.getFontMetrics();
        float baseline = by - (fm.ascent + fm.descent) * 0.5f;
        canvas.drawText(text, bx, baseline, badgeTextPaint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        detector.onTouchEvent(event);
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downRawX = event.getRawX();
                downRawY = event.getRawY();
                lastRawX = downRawX;
                lastRawY = downRawY;
                dragging = false;
                return true;
            case MotionEvent.ACTION_MOVE:
                float totalDx = event.getRawX() - downRawX;
                float totalDy = event.getRawY() - downRawY;
                if (!dragging && Math.hypot(totalDx, totalDy) > touchSlop) {
                    dragging = true;
                }
                if (dragging && listener != null) {
                    int stepX = Math.round(event.getRawX() - lastRawX);
                    int stepY = Math.round(event.getRawY() - lastRawY);
                    if (stepX != 0 || stepY != 0) {
                        lastRawX = event.getRawX();
                        lastRawY = event.getRawY();
                        listener.onMoveBy(stepX, stepY);
                    }
                }
                return true;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                if (dragging) {
                    dragging = false;
                    if (listener != null) {
                        listener.onDragFinished();
                    }
                }
                return true;
            default:
                return super.onTouchEvent(event);
        }
    }
}
