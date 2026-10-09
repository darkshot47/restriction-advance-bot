package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import org.drinkless.tdlib.TdApi;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/**
 * The editing tools that appear after a private download: change the **caption**,
 * set a **thumbnail** and **trim the video from the front or the back** — then
 * upload the result, which goes out through the user's own Telegram session.
 */
public class EditorActivity extends Activity {

    private static final int PICK_IMAGE = 501;

    private File file;
    private EditText captionField;
    private TextView fileLabel;
    private TextView trimLabel;
    private SeekBar startBar;
    private SeekBar endBar;
    private TextView trimSwitch;
    private ProgressBar progress;
    private Button uploadButton;
    private File thumbnail;
    private long durationMs = 0;
    private boolean trimming = false;
    /** Where the file came from — lets an untouched file be re-sent server-side. */
    private String link;
    /** The download job id (the server may still hold the very same bytes). */
    private String jobId;
    /** Direct-mode origin of the file (chat/message), for the zero-byte forward. */
    private long tdChatId;
    private long tdMessageId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_editor);
        String path = getIntent().getStringExtra("path");
        file = path == null ? null : new File(path);
        if (file == null || !file.exists()) {
            toast("Nothing to edit");
            finish();
            return;
        }
        link = getIntent().getStringExtra("link");
        jobId = getIntent().getStringExtra("jobId");
        if (link == null || link.isEmpty()) {
            //: Every download lands in the history with its link and its job id —
            //: find this file's entry so an unedited upload costs no new bytes.
            for (LocalStore.Item item : LocalStore.all(this)) {
                if (item.path != null && item.path.equals(path)) {
                    link = item.link;
                    jobId = item.kind;
                    break;
                }
            }
        }
        if (jobId != null && jobId.startsWith("td:")) {
            //: Direct downloads remember the source message — the key to a
            //: zero-byte re-send (ForwardMessages) from the phone itself.
            String[] parts = jobId.split(":");
            if (parts.length == 3) {
                try {
                    tdChatId = Long.parseLong(parts[1]);
                    tdMessageId = Long.parseLong(parts[2]);
                } catch (NumberFormatException ignored) {
                }
            }
        }
        captionField = findViewById(R.id.captionField);
        fileLabel = findViewById(R.id.fileLabel);
        trimLabel = findViewById(R.id.trimLabel);
        startBar = findViewById(R.id.startBar);
        endBar = findViewById(R.id.endBar);
        trimSwitch = findViewById(R.id.trimSwitch);
        progress = findViewById(R.id.uploadProgress);
        uploadButton = findViewById(R.id.uploadButton);

        fileLabel.setText(file.getName() + " • " + Notifications.human(file.length()));
        captionField.setText(Prefs.lastCaption(this));

        findViewById(R.id.captionFromFile).setOnClickListener(v ->
                captionField.setText(stripExtension(file.getName())));

        findViewById(R.id.pickThumb).setOnClickListener(v -> pickThumbnail());
        findViewById(R.id.grabThumb).setOnClickListener(v -> grabThumbnail());
        findViewById(R.id.uploadButton).setOnClickListener(v -> upload());
        findViewById(R.id.viewButton).setOnClickListener(v -> {
            Intent intent = new Intent(this, ViewerActivity.class);
            intent.putExtra("path", file.getAbsolutePath());
            startActivity(intent);
        });
        findViewById(R.id.trimSwitch).setOnClickListener(v -> toggleTrim());

        long[] meta = MediaUtils.videoMeta(file);
        durationMs = meta[0];
        boolean video = MediaUtils.isVideo(file) && MediaUtils.canTrim(file) && durationMs > 0;
        findViewById(R.id.trimBox).setVisibility(video ? View.VISIBLE : View.GONE);
        if (video) {
            setupTrim();
        } else if (MediaUtils.isVideo(file)) {
            findViewById(R.id.trimBox).setVisibility(View.VISIBLE);
            findViewById(R.id.trimSwitch).setEnabled(false);
            trimLabel.setText("Trimming works on MP4 videos (this file is "
                    + MediaUtils.extension(file.getName()) + ").");
        }
        String existing = Prefs.thumbnailPath(this);
        if (existing != null && !existing.isEmpty() && new File(existing).exists()) {
            thumbnail = new File(existing);
            showThumbnail(thumbnail);
        }
    }

    // ------------------------------------------------------------- caption //

    private String stripExtension(String name) {
        int dot = name.lastIndexOf('.');
        return dot <= 0 ? name : name.substring(0, dot);
    }

    // ----------------------------------------------------------- thumbnail //

    private void pickThumbnail() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.setType("image/*");
        startActivityForResult(intent, PICK_IMAGE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_IMAGE || resultCode != RESULT_OK || data == null
                || data.getData() == null) {
            return;
        }
        try (InputStream in = getContentResolver().openInputStream(data.getData())) {
            if (in == null) {
                toast("Could not read that image");
                return;
            }
            File target = new File(getCacheDir(), "thumb_edit.jpg");
            try (FileOutputStream out = new FileOutputStream(target)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) > 0) {
                    out.write(buffer, 0, read);
                }
            }
            thumbnail = target;
            Prefs.setThumbnailPath(this, target.getAbsolutePath());
            showThumbnail(target);
            toast("Thumbnail set");
        } catch (Exception exc) {
            toast("Could not read that image");
        }
    }

    private void grabThumbnail() {
        if (!MediaUtils.isVideo(file)) {
            toast("Thumbnails come from videos");
            return;
        }
        File target = new File(getCacheDir(), "thumb_frame.jpg");
        File grabbed = MediaUtils.thumbnailFrom(file, target);
        if (grabbed == null) {
            toast("Could not grab a frame");
            return;
        }
        thumbnail = grabbed;
        Prefs.setThumbnailPath(this, grabbed.getAbsolutePath());
        showThumbnail(grabbed);
        toast("Thumbnail taken from the video");
    }

    private void showThumbnail(File source) {
        ImageView view = findViewById(R.id.thumbPreview);
        Bitmap bitmap = BitmapFactory.decodeFile(source.getAbsolutePath());
        if (bitmap != null) {
            view.setImageBitmap(bitmap);
            view.setVisibility(View.VISIBLE);
        }
    }

    // ---------------------------------------------------------------- trim //

    private void setupTrim() {
        startBar.setMax(1000);
        endBar.setMax(1000);
        endBar.setProgress(1000);
        SeekBar.OnSeekBarChangeListener listener = new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int value, boolean fromUser) {
                if (startBar.getProgress() > endBar.getProgress() - 10) {
                    if (seekBar == startBar) {
                        endBar.setProgress(Math.min(1000, startBar.getProgress() + 10));
                    } else {
                        startBar.setProgress(Math.max(0, endBar.getProgress() - 10));
                    }
                }
                paintTrim();
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
            }
        };
        startBar.setOnSeekBarChangeListener(listener);
        endBar.setOnSeekBarChangeListener(listener);
        paintTrim();
        Prefs.setTrimEnabled(this, Prefs.trimEnabled(this));
        paintTrimSwitch();
    }

    private void paintTrim() {
        long start = startMs();
        long end = endMs();
        trimLabel.setText("Front cut: " + time(start) + " • Back cut: " + time(end)
                + "  (new length " + time(end - start) + ")");
    }

    private void paintTrimSwitch() {
        trimSwitch.setText(trimming ? "Trim: ON — tap to upload the full video"
                : "Trim: OFF — tap to cut it here");
        startBar.setEnabled(trimming);
        endBar.setEnabled(trimming);
    }

    private void toggleTrim() {
        trimming = !trimming;
        Prefs.setTrimEnabled(this, trimming);
        paintTrimSwitch();
    }

    private long startMs() {
        return durationMs * startBar.getProgress() / 1000;
    }

    private long endMs() {
        long end = durationMs * endBar.getProgress() / 1000;
        return end <= 0 ? durationMs : end;
    }

    private String time(long ms) {
        long total = ms / 1000;
        return String.format(java.util.Locale.US, "%02d:%02d", total / 60, total % 60);
    }

    // -------------------------------------------------------------- upload //

    private void upload() {
        uploadButton.setEnabled(false);
        progress.setVisibility(View.VISIBLE);
        progress.setIndeterminate(true);

        new Thread(() -> {
            File toUpload = file;
            String note = null;
            try {
                if (trimming && MediaUtils.canTrim(file)) {
                    File trimmed = new File(getCacheDir(), "trimmed_"
                            + System.currentTimeMillis() + ".mp4");
                    MediaUtils.trim(file, trimmed, startMs(), endMs());
                    toUpload = trimmed;
                    note = "trimmed " + time(startMs()) + " → " + time(endMs());
                }
            } catch (Exception exc) {
                final File original = file;
                runOnUiThread(() -> {
                    progress.setVisibility(View.GONE);
                    uploadButton.setEnabled(true);
                    toast("Trim failed (" + exc.getMessage() + ") — uploading the original");
                });
                toUpload = file;
                note = null;
            }
            doUpload(toUpload, note, toUpload != file);
        }).start();
    }

    private void doUpload(File toUpload, String note, boolean bytesChanged) {
        String caption = captionField.getText().toString();
        String kind = uploadKind(toUpload);
        long[] meta = MediaUtils.isVideo(toUpload) || MediaUtils.isAudio(toUpload)
                ? MediaUtils.videoMeta(toUpload) : new long[]{0, 0, 0};
        if (TdDirect.get(this).isReady()) {
            //: Direct mode wins whenever it can run: the bytes ride phone ↔
            //: Telegram straight, so the host's bill is literally zero.
            directUpload(toUpload, caption, kind, meta, bytesChanged);
            return;
        }
        if (!bytesChanged && link != null && !link.isEmpty() && commitUpload(caption, kind)) {
            return;
        }
        byteUpload(toUpload, note, caption, kind, meta);
    }

    /** Direct-mode upload: zero-byte forward when untouched, otherwise the
     *  phone ships the (new) bytes itself.  The server never sees a byte. */
    private void directUpload(final File toUpload, final String caption, final String kind,
                              final long[] meta, boolean bytesChanged) {
        runOnUiThread(() -> {
            progress.setIndeterminate(true);
            fileLabel.setText("⏳ Sending straight from this phone…");
        });
        TdDirect direct = TdDirect.get(this);
        if (!bytesChanged && tdMessageId != 0 && (caption == null || caption.trim().isEmpty())) {
            direct.forwardToBot(tdChatId, tdMessageId, new TdDirect.ResultCallback() {
                @Override
                public void onOk(TdApi.Object object) {
                    directUploadDone(true);
                }

                @Override
                public void onError(String message) {
                    runOnUiThread(() -> toast("Zero-byte re-send refused — uploading directly…"));
                    directSendBytes(toUpload, caption, kind, meta);
                }
            });
            return;
        }
        directSendBytes(toUpload, caption, kind, meta);
    }

    private void directSendBytes(File toUpload, String caption, String kind, long[] meta) {
        final long length = toUpload.length();
        TdDirect.get(this).sendMediaToBot(toUpload.getAbsolutePath(), kind, caption,
                (int) (meta[0] / 1000), (int) meta[1], (int) meta[2],
                (done, total) -> runOnUiThread(() -> {
                    long shown = total > 0 ? total : length;
                    progress.setIndeterminate(false);
                    progress.setMax(1000);
                    progress.setProgress(shown > 0
                            ? (int) Math.min(1000, done * 1000 / shown) : 0);
                    fileLabel.setText("⬆️ Uploading " + Notifications.human(done)
                            + (shown > 0 ? " / " + Notifications.human(shown) : ""));
                }),
                new TdDirect.ResultCallback() {
                    @Override
                    public void onOk(TdApi.Object object) {
                        directUploadDone(false);
                    }

                    @Override
                    public void onError(String message) {
                        runOnUiThread(() -> {
                            progress.setVisibility(View.GONE);
                            uploadButton.setEnabled(true);
                            toast("Upload failed: " + message);
                        });
                    }
                });
    }

    private void directUploadDone(boolean zeroBytes) {
        Prefs.setLastCaption(this, captionField.getText().toString());
        runOnUiThread(() -> {
            progress.setVisibility(View.GONE);
            uploadButton.setEnabled(true);
            fileLabel.setText(zeroBytes
                    ? "✅ Sent — zero new bytes spent"
                    : "✅ Uploaded from this phone");
            new AlertDialog.Builder(this)
                    .setTitle("Uploaded")
                    .setMessage(zeroBytes
                            ? "Telegram moved your file on its own servers — neither your "
                              + "phone nor the host moved the bytes again."
                            : "Your phone sent the file straight to Telegram — the server "
                              + "spent nothing at all on it.")
                    .setPositiveButton("OK", null)
                    .show();
        });
    }

    /**
     * The zero-transfer commit: the phone ships only the caption (and maybe a
     * thumbnail); the server re-sends the file it already has — by Telegram's
     * own copy mechanics when possible, so neither phone nor host moves the
     * media bytes again.
     *
     * @return true when the re-send was handled (success or a login demand);
     *         false when the server needs the real bytes after all.
     */
    private boolean commitUpload(String caption, String kind) {
        runOnUiThread(() -> fileLabel.setText("⏳ Asking Telegram to re-send it…"));
        JSONObject body = null;
        try {
            body = Api.uploadMeta(Prefs.baseUrl(this), Prefs.token(this), link, jobId,
                    caption, thumbnail, kind, file.getName());
        } catch (Exception ignored) {
        }
        if (body != null && body.optBoolean("ok", false)) {
            Prefs.setLastCaption(this, caption);
            final String via = body.optString("via", "");
            runOnUiThread(() -> {
                progress.setVisibility(View.GONE);
                uploadButton.setEnabled(true);
                fileLabel.setText("✅ Uploaded — no new bytes spent");
                new AlertDialog.Builder(this)
                        .setTitle("Uploaded")
                        .setMessage("copy".equals(via) || "reference".equals(via)
                                ? "Telegram re-sent the file on its own servers — "
                                  + "neither your phone nor the host moved the bytes again."
                                : "The server re-sent its own copy through your Telegram "
                                  + "account — your phone uploaded nothing.")
                        .setPositiveButton("OK", null)
                        .show();
            });
            return true;
        }
        if (body != null && body.optBoolean("needs_login", false)) {
            //: The byte upload would hit the same missing session — say it now.
            final String error = body.optString("error", "log in again");
            runOnUiThread(() -> {
                progress.setVisibility(View.GONE);
                uploadButton.setEnabled(true);
                toast(error);
            });
            return true;
        }
        runOnUiThread(() -> toast("The server couldn't re-send it — sending the file itself…"));
        return false;
    }

    private void byteUpload(File toUpload, String note, String caption, String kind,
                            long[] meta) {
        try {
            JSONObject body = Api.upload(Prefs.baseUrl(this), Prefs.token(this), toUpload,
                    caption, thumbnail, kind, toUpload.getName(), meta[0], (int) meta[1],
                    (int) meta[2], (sent, total) -> {
                        runOnUiThread(() -> {
                            progress.setIndeterminate(total <= 0);
                            progress.setMax(1000);
                            progress.setProgress(total > 0
                                    ? (int) Math.min(1000, sent * 1000 / total) : 0);
                            fileLabel.setText("⬆️ Uploading " + Notifications.human(sent)
                                    + (total > 0 ? " / " + Notifications.human(total) : ""));
                        });
                        return true;
                    });
            Prefs.setLastCaption(this, caption);
            runOnUiThread(() -> {
                progress.setVisibility(View.GONE);
                uploadButton.setEnabled(true);
                boolean ok = body.optBoolean("ok", false);
                fileLabel.setText(ok
                        ? "✅ Uploaded" + (note == null ? "" : " (" + note + ")")
                        : "⚠️ " + body.optString("error", "upload failed"));
                new AlertDialog.Builder(this)
                        .setTitle(ok ? "Uploaded" : "Upload failed")
                        .setMessage(ok
                                ? "Your file went back through your own Telegram account — "
                                  + "open the chat with the bot to see it."
                                : body.optString("error", "unknown error"))
                        .setPositiveButton("OK", null)
                        .show();
            });
        } catch (Exception exc) {
            runOnUiThread(() -> {
                progress.setVisibility(View.GONE);
                uploadButton.setEnabled(true);
                toast("Upload failed: " + exc.getMessage());
            });
        }
    }

    private String uploadKind(File target) {
        if (MediaUtils.isVideo(target)) {
            return "video";
        }
        if (MediaUtils.isImage(target)) {
            return "photo";
        }
        if (MediaUtils.isAudio(target)) {
            return "audio";
        }
        return "document";
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }
}
