package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.MediaPlayer;
import android.media.PlaybackParams;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/**
 * The player.
 *
 * Videos and audio play here — with speed control from 0.25x to 3x, seeking,
 * fullscreen and background playback — photos open with a zoom, text files are
 * shown inline and anything else is handed to the phone's own app.
 */
public class ViewerActivity extends Activity {

    private File file;
    private MediaPlayer player;
    private SurfaceView surface;
    private ImageView image;
    private ScrollView textScroll;
    private TextView textView;
    private LinearLayout controls;
    private LinearLayout fallback;
    private Button playButton;
    private Button speedButton;
    private SeekBar seekBar;
    private TextView timeText;
    private TextView titleText;
    private boolean prepared;
    private boolean controlsVisible = true;
    private boolean fullscreen;
    private float speed = 1f;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            paintPosition();
            handler.postDelayed(this, 400);
        }
    };
    private final Runnable hider = new Runnable() {
        @Override
        public void run() {
            if (player != null && player.isPlaying()) {
                setControls(false);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_viewer);

        String path = getIntent().getStringExtra("path");
        file = path == null ? null : new File(path);

        titleText = findViewById(R.id.viewerTitle);
        surface = findViewById(R.id.videoSurface);
        image = findViewById(R.id.imageView);
        textScroll = findViewById(R.id.textScroll);
        textView = findViewById(R.id.textView);
        controls = findViewById(R.id.controls);
        fallback = findViewById(R.id.fallbackBox);
        //: The player keeps its dark stage in both skins, so its own labels
        //: are painted with the on-accent whites.
        ((TextView) findViewById(R.id.fallbackText))
                .setTextColor(getColor(R.color.vmore_on_accent_dim));
        playButton = findViewById(R.id.playButton);
        speedButton = findViewById(R.id.speedButton);
        seekBar = findViewById(R.id.seekBar);
        timeText = findViewById(R.id.timeText);

        findViewById(R.id.backButton).setOnClickListener(v -> finish());
        findViewById(R.id.editButton).setOnClickListener(v -> openEditor());
        findViewById(R.id.uploadButton).setOnClickListener(v -> openEditor());
        findViewById(R.id.saveButton).setOnClickListener(v -> saveToDevice());
        findViewById(R.id.shareButton).setOnClickListener(v -> share());
        findViewById(R.id.openExternalButton).setOnClickListener(v -> openExternally());
        findViewById(R.id.fullscreenButton).setOnClickListener(v -> toggleFullscreen());
        playButton.setOnClickListener(v -> togglePlay());
        speedButton.setOnClickListener(v -> cycleSpeed());

        Anim.pageIn(controls);
        for (View view : new View[]{playButton, speedButton, findViewById(R.id.editButton),
                findViewById(R.id.uploadButton), findViewById(R.id.saveButton),
                findViewById(R.id.shareButton), findViewById(R.id.backButton)}) {
            Anim.pressible(view);
        }

        if (file == null || !file.exists()) {
            titleText.setText(R.string.viewer_missing);
            controls.setVisibility(View.GONE);
            fallback.setVisibility(View.VISIBLE);
            return;
        }
        titleText.setText(file.getName() + " • " + Format.size(file.length()));
        if (Prefs.keepScreenOn(this)) {
            getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }

        speed = Prefs.playbackSpeed(this);
        speedButton.setText(Vmore.speedLabel(speed));

        if (MediaUtils.isVideo(file)) {
            setupVideo();
        } else if (MediaUtils.isAudio(file)) {
            setupAudio();
        } else if (MediaUtils.isImage(file)) {
            showImage();
        } else if (MediaUtils.isText(file)) {
            showText();
        } else {
            showFallback();
        }
    }

    // --------------------------------------------------------------- players //

    private void setupVideo() {
        surface.setVisibility(View.VISIBLE);
        controls.setVisibility(View.VISIBLE);
        surface.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override
            public void surfaceCreated(SurfaceHolder holder) {
                startPlayer(holder);
            }

            @Override
            public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
            }

            @Override
            public void surfaceDestroyed(SurfaceHolder holder) {
                if (player != null) {
                    player.setDisplay(null);
                }
            }
        });
        View surfaceView = surface;
        surfaceView.setOnClickListener(v -> setControls(!controlsVisible));
    }

    private void setupAudio() {
        controls.setVisibility(View.VISIBLE);
        surface.setVisibility(View.GONE);
        fallback.setVisibility(View.GONE);
        image.setVisibility(View.VISIBLE);
        image.setImageResource(R.drawable.ic_speed);
        image.setImageTintList(android.content.res.ColorStateList.valueOf(
                getColor(R.color.vmore_on_accent)));
        startPlayer(null);
    }

    private void startPlayer(SurfaceHolder holder) {
        try {
            if (player == null) {
                player = new MediaPlayer();
                player.setDataSource(file.getAbsolutePath());
                if (holder != null) {
                    player.setDisplay(holder);
                }
                player.setOnPreparedListener(mp -> {
                    prepared = true;
                    seekBar.setMax(Math.max(1, mp.getDuration()));
                    applySpeed();
                    seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                        @Override
                        public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                            if (fromUser) {
                                mp.seekTo(progress);
                                paintPosition();
                            }
                        }

                        @Override
                        public void onStartTrackingTouch(SeekBar bar) {
                        }

                        @Override
                        public void onStopTrackingTouch(SeekBar bar) {
                        }
                    });
                    playButton.setText("");
                    playButton.setCompoundDrawablesWithIntrinsicBounds(
                            R.drawable.ic_pause, 0, 0, 0);
                    mp.start();
                    handler.post(ticker);
                    handler.postDelayed(hider, 3500);
                });
                player.setOnCompletionListener(mp -> {
                    playButton.setCompoundDrawablesWithIntrinsicBounds(
                            R.drawable.ic_play, 0, 0, 0);
                    setControls(true);
                });
                player.setOnErrorListener((mp, what, extra) -> {
                    Ui.toast(this, "This phone cannot play that file");
                    showFallback();
                    return true;
                });
                player.prepareAsync();
            } else if (holder != null) {
                player.setDisplay(holder);
            }
        } catch (Exception error) {
            Ui.toast(this, "This phone cannot play that file");
            showFallback();
        }
    }

    private void togglePlay() {
        if (player == null || !prepared) {
            return;
        }
        if (player.isPlaying()) {
            player.pause();
            playButton.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_play, 0, 0, 0);
            setControls(true);
        } else {
            player.start();
            applySpeed();
            playButton.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_pause, 0, 0, 0);
            handler.removeCallbacks(hider);
            handler.postDelayed(hider, 3500);
        }
    }

    /** Speed up or slow down: 0.25x … 3x, remembered for the next video. */
    private void cycleSpeed() {
        int index = 0;
        for (int position = 0; position < Vmore.SPEEDS.length; position++) {
            if (Math.abs(Vmore.SPEEDS[position] - speed) < 0.01f) {
                index = position;
                break;
            }
        }
        index = (index + 1) % Vmore.SPEEDS.length;
        speed = Vmore.SPEEDS[index];
        Prefs.setPlaybackSpeed(this, speed);
        speedButton.setText(Vmore.speedLabel(speed));
        applySpeed();
        Anim.fadeIn(speedButton, 120);
    }

    private void applySpeed() {
        if (player == null || !prepared) {
            return;
        }
        try {
            PlaybackParams params = player.getPlaybackParams();
            params.setSpeed(speed);
            player.setPlaybackParams(params);
        } catch (Exception ignored) {
            //: Some files answer with an illegal-state error; playback simply
            //: continues at the previous speed.
        }
    }

    private void paintPosition() {
        if (player == null || !prepared) {
            return;
        }
        try {
            int position = player.getCurrentPosition();
            seekBar.setProgress(position);
            timeText.setText(Format.duration(position) + " / "
                    + Format.duration(player.getDuration()));
        } catch (Exception ignored) {
        }
    }

    private void setControls(boolean visible) {
        controlsVisible = visible;
        if (visible) {
            controls.setVisibility(View.VISIBLE);
            Anim.fadeIn(controls, 160);
            handler.removeCallbacks(hider);
            handler.postDelayed(hider, 3500);
        } else {
            handler.removeCallbacks(hider);
            controls.animate().alpha(0f).setDuration(180).withEndAction(() ->
                    controls.setVisibility(View.GONE)).start();
        }
    }

    private void toggleFullscreen() {
        fullscreen = !fullscreen;
        if (fullscreen) {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION);
            setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
            setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        }
    }

    // ------------------------------------------------------- other file kinds //

    private void showImage() {
        image.setVisibility(View.VISIBLE);
        Bitmap bitmap = decode(file);
        if (bitmap == null) {
            showFallback();
            return;
        }
        image.setImageBitmap(bitmap);
        image.setOnClickListener(v -> {
            boolean zoomed = image.getScaleX() > 1.05f;
            image.animate().scaleX(zoomed ? 1f : 2f).scaleY(zoomed ? 1f : 2f)
                    .setDuration(220).start();
        });
    }

    private Bitmap decode(File source) {
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(source.getAbsolutePath(), bounds);
            int sample = 1;
            int longest = Math.max(bounds.outWidth, bounds.outHeight);
            while (longest / sample > 2200) {
                sample *= 2;
            }
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = sample;
            return BitmapFactory.decodeFile(source.getAbsolutePath(), options);
        } catch (Exception error) {
            return null;
        }
    }

    private void showText() {
        textScroll.setVisibility(View.VISIBLE);
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            int lines = 0;
            while ((line = reader.readLine()) != null && lines < 4000) {
                builder.append(line).append('\n');
                lines++;
            }
        } catch (Exception error) {
            builder.append("Could not read this file: ").append(error.getMessage());
        }
        textView.setText(builder.toString());
    }

    private void showFallback() {
        fallback.setVisibility(View.VISIBLE);
        surface.setVisibility(View.GONE);
        image.setVisibility(View.GONE);
        textScroll.setVisibility(View.GONE);
        controls.setVisibility(View.GONE);
        TextView label = findViewById(R.id.fallbackText);
        label.setText(MediaUtils.isPdf(file)
                ? "This is a PDF. Open it with your phone's viewer."
                : "This file type opens in another app.");
    }

    // ---------------------------------------------------------------- actions //

    private void openEditor() {
        if (file == null || !file.exists()) {
            Ui.toast(this, getString(R.string.viewer_missing));
            return;
        }
        Intent intent = new Intent(this, EditorActivity.class);
        intent.putExtra("path", file.getAbsolutePath());
        startActivity(intent);
    }

    private void openExternally() {
        if (file == null || !file.exists()) {
            return;
        }
        try {
            Uri uri = VmoreFiles.uriFor(this, file);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, MediaUtils.mimeOf(file));
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(intent);
        } catch (Exception error) {
            Ui.toast(this, "No app on this phone opens that file");
        }
    }

    private void share() {
        if (file == null || !file.exists()) {
            return;
        }
        try {
            Uri uri = VmoreFiles.uriFor(this, file);
            Intent intent = new Intent(Intent.ACTION_SEND);
            intent.setType(MediaUtils.mimeOf(file));
            intent.putExtra(Intent.EXTRA_STREAM, uri);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(intent, getString(R.string.viewer_share)));
        } catch (Exception error) {
            Ui.toast(this, "Sharing is not available");
        }
    }

    private void saveToDevice() {
        if (file == null || !file.exists()) {
            return;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
                && checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.WRITE_EXTERNAL_STORAGE},
                    602);
            Ui.toast(this, "Allow storage access, then tap Save again");
            return;
        }
        try {
            String where = MediaUtils.saveToDevice(this, file);
            Ui.toast(this, getString(R.string.viewer_saved) + " " + where);
        } catch (Exception error) {
            Ui.toast(this, "Could not save: " + error.getMessage());
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (player != null && player.isPlaying()) {
            player.pause();
            playButton.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_play, 0, 0, 0);
        }
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (player != null) {
            try {
                player.release();
            } catch (Exception ignored) {
            }
            player = null;
        }
        super.onDestroy();
    }
}
