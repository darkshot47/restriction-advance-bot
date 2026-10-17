package com.vmore.app;

import android.animation.ValueAnimator;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RadialGradient;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;
import android.view.animation.LinearInterpolator;

/**
 * The moving colour behind the developer card.
 *
 * The owner asked for a card that is alive: colours that travel, not a still
 * picture.  Five soft clouds of colour drift on their own paths behind the
 * name, a band of light crosses the card every few seconds and small dots rise
 * slowly, all inside the same rounded rectangle the other cards use.  It is
 * deliberately slow, and a dark wash keeps the white text the first thing read.
 *
 * This is a drawable rather than a view so it can be set as the card's own
 * background: the card keeps sizing itself from the profile inside it, and the
 * drawing simply follows those bounds.
 */
final class AuroraDrawable extends Drawable {

    private static final int BASE_TOP = 0xFF0A1024;
    private static final int BASE_BOTTOM = 0xFF111A38;
    private static final int[] CLOUDS = {
            0xFF2563EB, // blue
            0xFF7C3AED, // violet
            0xFF06B6D4, // cyan
            0xFFDB2777, // rose
            0xFFF59E0B, // amber
    };
    private static final int DOTS = 26;

    private final Paint base = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint cloud = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint scrim = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint shine = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint dot = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint border = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path clip = new Path();
    private final RectF bounds = new RectF();
    private final Matrix matrix = new Matrix();
    private final Shader[] cloudShaders = new Shader[CLOUDS.length];

    private final float radius;
    private final float stroke;

    private Shader shineShader;
    private Shader borderShader;
    private ValueAnimator animator;
    private float phase;
    private boolean running;

    private final float[] dotX = new float[DOTS];
    private final float[] dotY = new float[DOTS];
    private final float[] dotSpeed = new float[DOTS];
    private final float[] dotSize = new float[DOTS];
    private final float[] dotAlpha = new float[DOTS];

    AuroraDrawable(float density) {
        radius = 18f * density;
        stroke = Math.max(1.2f, 1.4f * density);
        scrim.setColor(0x40081024);
        dot.setColor(0xFFFFFFFF);
        border.setStyle(Paint.Style.STROKE);
        border.setStrokeWidth(stroke);

        //: A fixed, evenly spread pattern: a random one would look different
        //: every time the page is rebuilt.
        for (int index = 0; index < DOTS; index++) {
            dotX[index] = ((index * 37) % 100) / 100f;
            dotY[index] = ((index * 61) % 100) / 100f;
            dotSpeed[index] = 0.030f + ((index * 13) % 17) / 1000f;
            dotSize[index] = 0.9f + ((index * 7) % 11) / 10f;
            dotAlpha[index] = 20f + ((index * 23) % 60);
        }
    }

    @Override
    protected void onBoundsChange(Rect rect) {
        super.onBoundsChange(rect);
        bounds.set(rect);
        if (rect.width() <= 0 || rect.height() <= 0) {
            return;
        }
        float w = rect.width();
        float h = rect.height();
        base.setShader(new LinearGradient(0, 0, w, h, BASE_TOP, BASE_BOTTOM, Shader.TileMode.CLAMP));

        float cloudRadius = Math.max(w, h) * 0.62f;
        for (int index = 0; index < CLOUDS.length; index++) {
            cloudShaders[index] = new RadialGradient(0, 0, cloudRadius,
                    new int[]{withAlpha(CLOUDS[index], 150), withAlpha(CLOUDS[index], 0)},
                    new float[]{0f, 1f}, Shader.TileMode.CLAMP);
        }
        shineShader = new LinearGradient(0, 0, w, h * 0.4f,
                new int[]{0x00FFFFFF, 0x1FFFFFFF, 0x00FFFFFF},
                new float[]{0f, 0.5f, 1f}, Shader.TileMode.CLAMP);
        shine.setShader(shineShader);
        borderShader = new LinearGradient(0, 0, w, h,
                new int[]{0xCC60A5FA, 0xCC8B5CF6, 0xCC22D3EE, 0xCCF472B6, 0xCC60A5FA},
                null, Shader.TileMode.CLAMP);
        border.setShader(borderShader);

        clip.reset();
        clip.addRoundRect(bounds, radius, radius, Path.Direction.CW);
        invalidateSelf();
    }

    @Override
    public void draw(Canvas canvas) {
        if (bounds.width() <= 0 || bounds.height() <= 0) {
            return;
        }
        int save = canvas.save();
        canvas.clipPath(clip);
        canvas.drawRect(bounds, base);

        float centreX = bounds.centerX();
        float centreY = bounds.centerY();
        float orbitX = bounds.width() * 0.34f;
        float orbitY = bounds.height() * 0.30f;
        for (int index = 0; index < CLOUDS.length; index++) {
            double angle = phase * Math.PI * 2 * (index % 2 == 0 ? 1 : -1)
                    + index * (Math.PI * 2 / CLOUDS.length);
            float x = centreX + (float) Math.cos(angle) * orbitX * (index == 4 ? 0.55f : 1f);
            float y = centreY + (float) Math.sin(angle * 1.3f) * orbitY;
            cloud.setShader(cloudShaders[index]);
            matrix.setTranslate(x, y);
            cloudShaders[index].setLocalMatrix(matrix);
            canvas.drawRect(bounds, cloud);
        }

        //: The dark wash is what keeps the white name, bio and button easy to
        //: read over whichever colour happens to be under them.
        canvas.drawRect(bounds, scrim);

        if (shineShader != null) {
            matrix.setTranslate((phase * 2.4f - 1.2f) * bounds.width() * 1.8f, 0);
            shineShader.setLocalMatrix(matrix);
            canvas.drawRect(bounds, shine);
        }

        for (int index = 0; index < DOTS; index++) {
            float y = (dotY[index] - phase * dotSpeed[index] * 9f) % 1f;
            if (y < 0f) {
                y += 1f;
            }
            float x = dotX[index] + 0.012f * (float) Math.sin(phase * Math.PI * 2 + index);
            dot.setAlpha((int) dotAlpha[index]);
            canvas.drawCircle(bounds.left + x * bounds.width(),
                    bounds.top + y * bounds.height(), dotSize[index], dot);
        }

        RectF edge = new RectF(bounds);
        edge.inset(stroke / 2f, stroke / 2f);
        canvas.drawRoundRect(edge, radius, radius, border);
        canvas.restoreToCount(save);
    }

    private static int withAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }

    /** Runs the animation; safe to call more than once. */
    void start() {
        if (running) {
            return;
        }
        running = true;
        animator = ValueAnimator.ofFloat(0f, 1f);
        animator.setDuration(11000L);
        animator.setRepeatCount(ValueAnimator.INFINITE);
        animator.setInterpolator(new LinearInterpolator());
        animator.addUpdateListener(value -> {
            phase = (Float) value.getAnimatedValue();
            invalidateSelf();
        });
        animator.start();
    }

    /** Stops the animation when the screen is not the one in front. */
    void stop() {
        running = false;
        if (animator != null) {
            animator.cancel();
            animator = null;
        }
    }

    @Override
    public void setAlpha(int alpha) {
        //: The colours are already chosen with their own alpha; the card uses
        //: Anim.stagger on the whole view when the page opens.
    }

    @Override
    public void setColorFilter(ColorFilter filter) {
        //: No filter is applied to this drawing.
    }

    @Override
    public int getOpacity() {
        return PixelFormat.TRANSLUCENT;
    }
}
