package com.vmore.app;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
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
import android.view.animation.DecelerateInterpolator;

// Lightweight floating pointer & menu button views for Smart Feature:
// - Zero continuous idle animation (0% background GPU/CPU overhead, zero flicker)
// - Sub-pixel touch carry accumulator for silky-smooth dragging
// - Badge strictly displays only captured file count (0 = pure white circle)
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
    private final GestureDetector detector;
    private final ValueAnimator rippleAnimator;
    private final int touchSlop;

    private InteractionListener listener;
    private SweepGradient rainbowSweep;
    private int visualState = STATE_IDLE;
    private int badgeCount = 0;
    private int transferPercent = 0;
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
        badgeTextPaint.setTextSize(Ui.dp(context, 9));
        badgeTextPaint.setTypeface(Typeface.DEFAULT_BOLD);
        badgeTextPaint.setTextAlign(Paint.Align.CENTER);

        glyphPaint.setStyle(Paint.Style.STROKE);
        glyphPaint.setStrokeCap(Paint.Cap.ROUND);
        glyphPaint.setStrokeJoin(Paint.Join.ROUND);
        glyphPaint.setStrokeWidth(Ui.dp(context, 2));
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

        rippleAnimator = ValueAnimator.ofFloat(0f, 1f);
        rippleAnimator.setDuration(240L);
        rippleAnimator.setInterpolator(new DecelerateInterpolator());
        rippleAnimator.addUpdateListener(anim -> {
            tapRipple = (Float) anim.getAnimatedValue();
            invalidate();
        });
    }

    public void setInteractionListener(InteractionListener value) {
        this.listener = value;
    }

    public void setVisualState(int state, int count, int percent) {
        int cleanCount = Math.max(0, count);
        int cleanPct = Math.max(0, Math.min(100, percent));
        if (this.visualState == state
                && this.badgeCount == cleanCount
                && this.transferPercent == cleanPct) {
            return;
        }
        this.visualState = state;
        this.badgeCount = cleanCount;
        this.transferPercent = cleanPct;
        invalidate();
    }

    public void triggerRipple() {
        rippleAnimator.cancel();
        tapRipple = 0f;
        rippleAnimator.start();
    }

    @Override
    protected void onDetachedFromWindow() {
        rippleAnimator.cancel();
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
        float coreRadius = Ui.dp(getContext(), 10);
        float haloRadius = Ui.dp(getContext(), 14);

        if (tapRipple < 1f) {
            float rr = coreRadius + Ui.dp(getContext(), 9) * tapRipple;
            int alpha = (int) ((1f - tapRipple) * 200f);
            ripplePaint.setColor((alpha << 24) | 0x00FFFFFF);
            canvas.drawCircle(cx, cy, rr, ripplePaint);
        }

        outerGlowPaint.setColor(0x3D000000);
        canvas.drawCircle(cx, cy + Ui.dp(getContext(), 1), coreRadius + Ui.dp(getContext(), 2),
                outerGlowPaint);

        ringRect.set(cx - haloRadius, cy - haloRadius, cx + haloRadius, cy + haloRadius);
        ringPaint.setShader(null);
        if (visualState == STATE_SCANNING && rainbowSweep != null) {
            ringPaint.setShader(rainbowSweep);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        } else if (visualState == STATE_CAPTURED) {
            ringPaint.setColor(0xFF10B981);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        } else if (visualState == STATE_TRANSFERRING) {
            ringPaint.setColor(0x3838BDF8);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
            ringPaint.setColor(0xFF38BDF8);
            float sweepDeg = transferPercent > 0 ? Math.max(18f, transferPercent * 3.6f) : 72f;
            canvas.drawArc(ringRect, -90f, sweepDeg, false, ringPaint);
        } else if (visualState == STATE_ALERT) {
            ringPaint.setColor(0xFFF59E0B);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        } else {
            ringPaint.setColor(0x6638BDF8);
            canvas.drawCircle(cx, cy, haloRadius, ringPaint);
        }

        corePaint.setColor(0xFFFFFFFF);
        canvas.drawCircle(cx, cy, coreRadius, corePaint);
        canvas.drawCircle(cx, cy, coreRadius, strokePaint);

        dotPaint.setColor(visualState == STATE_CAPTURED ? 0xFF10B981 : 0xFF2563EB);
        canvas.drawCircle(cx, cy, Ui.dp(getContext(), 2), dotPaint);

        if (badgeCount > 0) {
            drawBadge(canvas, cx + coreRadius * 0.85f, cy - coreRadius * 0.85f, badgeCount);
        }
    }

    private void drawMenuOrb(Canvas canvas, float cx, float cy) {
        float orbRadius = Ui.dp(getContext(), 17);

        outerGlowPaint.setColor(0x44000000);
        canvas.drawCircle(cx, cy + Ui.dp(getContext(), 1), orbRadius + Ui.dp(getContext(), 1),
                outerGlowPaint);

        corePaint.setColor(0xF2121829);
        canvas.drawCircle(cx, cy, orbRadius, corePaint);

        if (rainbowSweep != null) {
            ringPaint.setShader(rainbowSweep);
        } else {
            ringPaint.setColor(0xFF38BDF8);
        }
        ringRect.set(cx - orbRadius, cy - orbRadius, cx + orbRadius, cy + orbRadius);
        canvas.drawOval(ringRect, ringPaint);

        float gx = Ui.dp(getContext(), 5);
        float gy = Ui.dp(getContext(), 5);
        canvas.drawLine(cx - gx, cy - gy, cx, cy + gy, glyphPaint);
        canvas.drawLine(cx, cy + gy, cx + gx, cy - gy, glyphPaint);

        if (badgeCount > 0) {
            drawBadge(canvas, cx + orbRadius * 0.72f, cy - orbRadius * 0.72f, badgeCount);
        }
    }

    private void drawBadge(Canvas canvas, float bx, float by, int count) {
        float r = Ui.dp(getContext(), 7);
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
                float rawX = event.getRawX();
                float rawY = event.getRawY();
                if (!dragging && Math.hypot(rawX - downRawX, rawY - downRawY) > touchSlop) {
                    dragging = true;
                }
                if (dragging && listener != null) {
                    int stepX = Math.round(rawX - lastRawX);
                    int stepY = Math.round(rawY - lastRawY);
                    if (stepX != 0 || stepY != 0) {
                        lastRawX += stepX;
                        lastRawY += stepY;
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
