package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.ImageView;
import android.widget.MediaController;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;

/**
 * Viewer for whatever was downloaded: video player, image, PDF (handed to the
 * system viewer) or text — plus **Save to device**.
 *
 * The app ships no third-party player: {@link VideoView} plays everything the
 * phone supports, and documents open in the phone's own app.
 */
public class ViewerActivity extends Activity {

    private File file;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_viewer);
        String path = getIntent().getStringExtra("path");
        file = path == null ? null : new File(path);
        TextView title = findViewById(R.id.viewerTitle);
        if (file == null || !file.exists()) {
            title.setText("That file is gone");
            return;
        }
        title.setText(file.getName() + " • " + Notifications.human(file.length()));

        findViewById(R.id.saveDeviceButton).setOnClickListener(v -> save());
        findViewById(R.id.openExternalButton).setOnClickListener(v -> openExternally());
        findViewById(R.id.shareButton).setOnClickListener(v -> share());
        findViewById(R.id.editButton).setOnClickListener(v -> {
            Intent intent = new Intent(this, EditorActivity.class);
            intent.putExtra("path", file.getAbsolutePath());
            startActivity(intent);
        });

        if (MediaUtils.isVideo(file)) {
            play();
        } else if (MediaUtils.isImage(file)) {
            showImage();
        } else if (MediaUtils.isText(file)) {
            showText();
        } else {
            showFallback(MediaUtils.isPdf(file)
                    ? "PDF — open it with your phone's viewer."
                    : "This file type opens in another app.");
        }
    }

    private void play() {
        VideoView video = findViewById(R.id.videoView);
        video.setVisibility(View.VISIBLE);
        video.setVideoPath(file.getAbsolutePath());
        MediaController controller = new MediaController(this);
        controller.setAnchorView(video);
        video.setMediaController(controller);
        video.start();
    }

    private void showImage() {
        ImageView image = findViewById(R.id.imageView);
        image.setVisibility(View.VISIBLE);
        image.setImageBitmap(BitmapFactory.decodeFile(file.getAbsolutePath()));
    }

    private void showText() {
        TextView text = findViewById(R.id.textView);
        text.setVisibility(View.VISIBLE);
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(file)))) {
            String line;
            int lines = 0;
            while ((line = reader.readLine()) != null && lines < 5000) {
                builder.append(line).append('\n');
                lines++;
            }
        } catch (Exception exc) {
            builder.append("Could not read the file: ").append(exc.getMessage());
        }
        text.setText(builder.toString());
    }

    private void showFallback(String message) {
        TextView text = findViewById(R.id.textView);
        text.setVisibility(View.VISIBLE);
        text.setText(message + "\n\nTap 📤 Open in another app.");
    }

    private void save() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
                && checkSelfPermission("android.permission.WRITE_EXTERNAL_STORAGE")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.WRITE_EXTERNAL_STORAGE"}, 602);
            Toast.makeText(this, "Allow storage access, then tap Save again",
                    Toast.LENGTH_LONG).show();
            return;
        }
        try {
            String where = MediaUtils.saveToDevice(this, file);
            Toast.makeText(this, "Saved to " + where, Toast.LENGTH_LONG).show();
        } catch (Exception exc) {
            Toast.makeText(this, "Could not save: " + exc.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    /**
     * Hand the file to another app.
     *
     * The URI comes from {@link VmoreFiles}: since Android 7 a {@code file://}
     * URI in an Intent throws {@code FileUriExposedException}, so the app shares
     * a {@code content://} URI (with a read grant) instead.
     */
    private void openExternally() {
        try {
            Uri uri = VmoreFiles.uriFor(this, file);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, MediaUtils.mimeOf(file));
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception exc) {
            Toast.makeText(this, "No app can open this file", Toast.LENGTH_LONG).show();
        }
    }

    private void share() {
        try {
            Uri uri = VmoreFiles.uriFor(this, file);
            Intent intent = new Intent(Intent.ACTION_SEND);
            intent.setType(MediaUtils.mimeOf(file));
            intent.putExtra(Intent.EXTRA_STREAM, uri);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(intent, "Share"));
        } catch (Exception exc) {
            Toast.makeText(this, "Sharing is not available", Toast.LENGTH_LONG).show();
        }
    }
}
