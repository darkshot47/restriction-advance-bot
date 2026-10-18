package com.vmore.app;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;

/**
 * The motion language of the app.
 *
 * Every screen slides its content in, every list staggers its rows, and every
 * button answers a touch with a small scale — as the owner asked, each page
 * moves.
 */
final class Anim {

    private Anim() {
    }

    /** Content slides up and fades in when a screen appears. */
    static void pageIn(View root) {
        if (root == null) {
            return;
        }
        root.setAlpha(0f);
        root.setTranslationY(Ui.dp(root.getContext(), 14));
        root.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(280)
                .setInterpolator(new DecelerateInterpolator())
                .start();
    }

    /** Rows appear one after another instead of all at once. */
    static void stagger(ViewGroup list) {
        if (list == null) {
            return;
        }
        int count = Math.min(list.getChildCount(), 12);
        for (int index = 0; index < count; index++) {
            View child = list.getChildAt(index);
            child.setAlpha(0f);
            child.setTranslationY(Ui.dp(child.getContext(), 18));
            child.animate()
                    .alpha(1f)
                    .translationY(0f)
                    .setStartDelay(index * 35L)
                    .setDuration(240)
                    .setInterpolator(new DecelerateInterpolator())
                    .start();
        }
    }

    /** One new row (a live list that grows while the user watches). */
    static void itemIn(View row, int index) {
        if (row == null) {
            return;
        }
        row.setAlpha(0f);
        row.setTranslationY(Ui.dp(row.getContext(), 16));
        row.animate()
                .alpha(1f)
                .translationY(0f)
                .setStartDelay(Math.min(index, 10) * 30L)
                .setDuration(230)
                .setInterpolator(new DecelerateInterpolator())
                .start();
    }

    static void fadeIn(View view, long duration) {
        if (view == null) {
            return;
        }
        view.setAlpha(0f);
        view.animate().alpha(1f).setDuration(duration).start();
    }

    static void fadeOut(View view, long duration) {
        if (view == null) {
            return;
        }
        view.animate().alpha(0f).setDuration(duration).start();
    }

    static void slideUp(View view) {
        if (view == null) {
            return;
        }
        view.animate().translationY(0f).alpha(1f).setDuration(220).start();
    }

    /** Buttons shrink slightly under the finger — every tappable thing does. */
    static void pressible(View view) {
        if (view == null) {
            return;
        }
        view.setOnTouchListener((target, event) -> {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    target.animate().scaleX(0.97f).scaleY(0.97f).setDuration(90).start();
                    break;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    target.animate().scaleX(1f).scaleY(1f).setDuration(120).start();
                    break;
                default:
                    break;
            }
            return false;
        });
    }

    /** A progress bar that breathes while a job is running. */
    static ObjectAnimator pulse(View view) {
        if (view == null) {
            return null;
        }
        ObjectAnimator animator = ObjectAnimator.ofFloat(view, "alpha", 1f, 0.55f);
        animator.setDuration(900);
        animator.setRepeatMode(ValueAnimator.REVERSE);
        animator.setRepeatCount(ValueAnimator.INFINITE);
        animator.start();
        return animator;
    }
}
