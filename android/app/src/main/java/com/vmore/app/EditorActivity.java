package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.BitmapFactory;
import android.provider.MediaStore;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.File;

/**
 * Caption, thumbnail and trim — then the upload goes out with the user's own
 * Telegram session, straight to the chosen chat.
 */
public class EditorActivity extends Activity {

    private static final int PICK_IMAGE = 501;
    private static final int PICK_CHAT = 502;

    private File file;
    private File thumbnail;
    private EditText captionField;
    private TextView fileLabel;
    private TextView trimLabel;
    private TextView destLabel;
    private SeekBar startBar;
    private SeekBar endBar;
    private ProgressBar progress;
    private LinearLayout trimBox;
    private ImageView thumbPreview;
    private long durationMs;
    private boolean trimming;
    private long destChatId;
    private String destTitle = "";
    private String sendAs = Prefs.SEND_FILE;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_editor);

        String path = getIntent().getStringExtra("path");
        file = path == null ? null : new File(path);
        if (file == null || !file.exists()) {
            Ui.toast(this, getString(R.string.viewer_missing));
            finish();
            return;
        }

        captionField = findViewById(R.id.captionField);
        fileLabel = findViewById(R.id.fileLabel);
        trimLabel = findViewById(R.id.trimLabel);
        destLabel = findViewById(R.id.destLabel);
        startBar = findViewById(R.id.startBar);
        endBar = findViewById(R.id.endBar);
        progress = findViewById(R.id.uploadProgress);
        trimBox = findViewById(R.id.trimBox);
        thumbPreview = findViewById(R.id.thumbPreview);

        destChatId = Prefs.destChatId(this);
        destTitle = Prefs.destTitle(this);
        if (destChatId == 0L) {
            destTitle = getString(R.string.home_no_destination);
        }
        destLabel.setText(destTitle);

        sendAs = Prefs.sendAs(this);
        findViewById(R.id.qualityFile).setOnClickListener(v -> setQuality(Prefs.SEND_FILE));
        findViewById(R.id.qualityVideo).setOnClickListener(v -> setQuality(Prefs.SEND_VIDEO));
        findViewById(R.id.qualityPhoto).setOnClickListener(v -> setQuality(Prefs.SEND_PHOTO));

        String template = Prefs.captionTemplate(this);
        captionField.setText(template == null || template.isEmpty()
                ? Format.withoutExtension(file.getName()) : template);

        fileLabel.setText(file.getName() + " • " + Format.size(file.length()));

        findViewById(R.id.backButton).setOnClickListener(v -> finish());
        findViewById(R.id.captionFromName).setOnClickListener(v ->
                captionField.setText(Format.withoutExtension(file.getName())));
        findViewById(R.id.pickThumb).setOnClickListener(v -> pickThumbnail());
        findViewById(R.id.grabThumb).setOnClickListener(v -> grabThumbnail());
        findViewById(R.id.uploadButton).setOnClickListener(v -> upload());
        findViewById(R.id.previewButton).setOnClickListener(v -> {
            Intent intent = new Intent(this, ViewerActivity.class);
            intent.putExtra("path", file.getAbsolutePath());
            startActivity(intent);
        });
        findViewById(R.id.destRow).setOnClickListener(v -> pickChat());
        findViewById(R.id.trimSwitch).setOnClickListener(v -> toggleTrim());
        paintQuality();

        for (View view : new View[]{findViewById(R.id.uploadButton),
                findViewById(R.id.previewButton), findViewById(R.id.pickThumb),
                findViewById(R.id.grabThumb)}) {
            Anim.pressible(view);
        }
        Anim.pageIn(findViewById(R.id.editorHeader));

        long[] meta = MediaUtils.videoMeta(file);
        durationMs = meta[0];
        boolean video = MediaUtils.isVideo(file) && MediaUtils.canTrim(file) && durationMs > 0;
        trimBox.setVisibility(video ? View.VISIBLE : View.GONE);
        if (video) {
            setupTrim();
        }
    }

    // -------------------------------------------------------------- quality //

    private void paintQuality() {
        Button file = findViewById(R.id.qualityFile);
        Button video = findViewById(R.id.qualityVideo);
        Button photo = findViewById(R.id.qualityPhoto);
        file.setBackgroundResource(Prefs.SEND_FILE.equals(sendAs)
                ? R.drawable.bg_chip_active : R.drawable.bg_chip);
        video.setBackgroundResource(Prefs.SEND_VIDEO.equals(sendAs)
                ? R.drawable.bg_chip_active : R.drawable.bg_chip);
        photo.setBackgroundResource(Prefs.SEND_PHOTO.equals(sendAs)
                ? R.drawable.bg_chip_active : R.drawable.bg_chip);
    }

    private void setQuality(String value) {
        sendAs = value;
        //: The choice is remembered, so the next upload starts from it too.
        Prefs.setSendAs(this, value);
        paintQuality();
    }

    // ----------------------------------------------------------------- trim //

    private void setupTrim() {
        startBar.setMax((int) durationMs);
        endBar.setMax((int) durationMs);
        endBar.setProgress((int) durationMs);
        paintTrim();
        SeekBar.OnSeekBarChangeListener listener = new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                if (startBar.getProgress() > endBar.getProgress() - 500) {
                    if (bar == startBar) {
                        startBar.setProgress(Math.max(0, endBar.getProgress() - 500));
                    } else {
                        endBar.setProgress(startBar.getProgress() + 500);
                    }
                }
                paintTrim();
            }

            @Override
            public void onStartTrackingTouch(SeekBar bar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar bar) {
            }
        };
        startBar.setOnSeekBarChangeListener(listener);
        endBar.setOnSeekBarChangeListener(listener);
    }

    private void paintTrim() {
        trimLabel.setText(Format.duration(startBar.getProgress()) + " - "
                + Format.duration(endBar.getProgress()) + " • "
                + getString(trimming ? R.string.editor_trim_on : R.string.editor_trim_off));
    }

    private void toggleTrim() {
        if (durationMs <= 0) {
            return;
        }
        trimming = !trimming;
        paintTrim();
    }

    // ------------------------------------------------------------ thumbnail //

    private void pickThumbnail() {
        //: Picking straight from the gallery keeps the chooser to images; no
        //: mime pattern is needed for that.
        Intent intent = new Intent(Intent.ACTION_PICK,
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
        startActivityForResult(intent, PICK_IMAGE);
    }

    private void grabThumbnail() {
        if (!MediaUtils.isVideo(file)) {
            Ui.toast(this, getString(R.string.editor_need_video));
            return;
        }
        File target = new File(getCacheDir(), "cover.jpg");
        File result = MediaUtils.thumbnailFor(file, target);
        if (result == null) {
            Ui.toast(this, getString(R.string.editor_thumb_failed));
            return;
        }
        thumbnail = result;
        thumbPreview.setImageBitmap(BitmapFactory.decodeFile(result.getAbsolutePath()));
        thumbPreview.setVisibility(View.VISIBLE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_CHAT && resultCode == RESULT_OK && data != null) {
            destChatId = data.getLongExtra("chat_id", destChatId);
            destTitle = data.getStringExtra("chat_title");
            if (data.getBooleanExtra("remember", false) && destChatId != 0L) {
                Prefs.saveDestination(this, destChatId, destTitle);
            }
            destLabel.setText(destTitle == null || destTitle.isEmpty()
                    ? getString(R.string.home_no_destination) : destTitle);
            return;
        }
        if (requestCode == PICK_IMAGE && resultCode == RESULT_OK && data != null
                && data.getData() != null) {
            try {
                File copy = new File(getCacheDir(), "picked_image");
                java.io.InputStream in = getContentResolver().openInputStream(data.getData());
                try (java.io.OutputStream out = new java.io.FileOutputStream(copy)) {
                    byte[] buffer = new byte[64 * 1024];
                    int read;
                    while (in != null && (read = in.read(buffer)) > 0) {
                        out.write(buffer, 0, read);
                    }
                }
                File target = MediaUtils.thumbnailOf(copy, new File(getCacheDir(), "cover.jpg"));
                if (target == null) {
                    Ui.toast(this, getString(R.string.editor_image_failed));
                    return;
                }
                thumbnail = target;
                thumbPreview.setImageBitmap(BitmapFactory.decodeFile(target.getAbsolutePath()));
                thumbPreview.setVisibility(View.VISIBLE);
            } catch (Exception error) {
                Ui.toast(this, getString(R.string.editor_image_failed));
            }
        }
    }

    // --------------------------------------------------------------- upload //

    private void pickChat() {
        Intent intent = new Intent(this, ChatPickerActivity.class);
        intent.putExtra("mode", "destination");
        startActivityForResult(intent, PICK_CHAT);
    }

    private void upload() {
        if (destChatId == 0L) {
            Ui.toast(this, getString(R.string.home_need_destination));
            pickChat();
            return;
        }
        progress.setVisibility(View.VISIBLE);
        final String caption = captionField.getText().toString();
        final long[] meta = MediaUtils.videoMeta(file);
        final String kind = mediaKind();
        new Thread(() -> {
            File toSend = file;
            if (trimming && durationMs > 0) {
                File target = new File(getCacheDir(),
                        Format.withoutExtension(file.getName()) + "_trim"
                                + file.getName().substring(
                                Format.withoutExtension(file.getName()).length()));
                try {
                    toSend = MediaUtils.trim(file, target, startBar.getProgress(),
                            endBar.getProgress());
                } catch (Exception error) {
                    runOnUiThread(() -> {
                        progress.setVisibility(View.GONE);
                        Ui.toast(this, getString(R.string.editor_trim_failed)
                                + " " + error.getMessage());
                    });
                    return;
                }
            }
            final File sending = toSend;
            final String cover = thumbnail == null || !thumbnail.exists()
                    ? null : thumbnail.getAbsolutePath();
            runOnUiThread(() -> Tg.get(this).sendMedia(destChatId, sending.getAbsolutePath(),
                    kind, caption, meta[0] / 1000, (int) meta[1], (int) meta[2],
                    sendAs, cover, (done, total) -> runOnUiThread(() -> {
                        progress.setMax(100);
                        progress.setProgress(Format.percent(done, total));
                    }), new Tg.Cb<Long>() {
                @Override
                public void ok(Long value) {
                    finishUpload(sending, caption);
                }

                @Override
                public void fail(String message) {
                    progress.setVisibility(View.GONE);
                    History.get(EditorActivity.this).record(file.getName(), kind, file.length(),
                            destChatId, destTitle, History.STATUS_FAILED, "", message, file.getAbsolutePath());
                    Ui.toast(EditorActivity.this, message);
                }
            }));
        }, "vmore-editor-upload").start();
    }

    private String mediaKind() {
        if (MediaUtils.isVideo(file)) {
            return "video";
        }
        if (MediaUtils.isImage(file)) {
            return "photo";
        }
        if (MediaUtils.isAudio(file)) {
            return "audio";
        }
        return "document";
    }

    private void finishUpload(File sent, String caption) {
        progress.setVisibility(View.GONE);
        History history = History.get(this);
        boolean delete = Prefs.autoDeleteLocal(this);
        history.record(file.getName(), mediaKind(), sent.length(), destChatId, destTitle,
                History.STATUS_UPLOADED, "", "", delete ? "" : sent.getAbsolutePath());
        if (delete && sent.getAbsolutePath().equals(file.getAbsolutePath())) {
            LocalFiles.delete(file.getAbsolutePath());
            history.markLocalGone(file.getAbsolutePath());
        }
        Ui.toast(this, getString(R.string.editor_uploaded) + " " + destTitle);
        finish();
    }
}
