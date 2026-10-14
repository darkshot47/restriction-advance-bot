package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * Everything Vmore has on the phone, in one place.
 *
 * The list is built from the app's own folder plus any file the history still
 * points at, so a download that was kept (delete-local switched off) shows up
 * here as well.  Search, three sort orders, and a selection mode that can upload,
 * share, delete or open a whole group at once.
 */
public class FilesActivity extends Activity {

    private static final String SORT_DATE = "date";
    private static final String SORT_NAME = "name";
    private static final String SORT_SIZE = "size";

    private LinearLayout box;
    private EditText search;
    private String sort = SORT_DATE;
    private String query = "";
    private final List<File> selected = new ArrayList<>();
    private boolean selecting;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_files);
        box = findViewById(R.id.filesBox);
        if (findViewById(R.id.backButton) != null) {
            findViewById(R.id.backButton).setOnClickListener(v -> finish());
        }
        Anim.pageIn(findViewById(R.id.screenHeader));
        render();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
        render();
    }

    // ------------------------------------------------------------- painting //

    private void render() {
        box.removeAllViews();
        selected.clear();
        selecting = false;

        List<File> files = files();
        addSearch();
        addSortChips(files.size());
        addActions();

        if (files.isEmpty()) {
            TextView empty = Ui.subtitle(this, getString(R.string.files_empty));
            empty.setPadding(0, Ui.dp(this, 12), 0, 0);
            box.addView(empty);
            return;
        }
        box.addView(Ui.divider(this));
        int index = 0;
        for (File file : files) {
            box.addView(fileRow(file, index));
            index++;
        }
        Anim.stagger(box);
    }

    private void addSearch() {
        search = new EditText(this);
        search.setHint(R.string.files_search_hint);
        search.setText(query);
        search.setSingleLine(true);
        search.setBackgroundResource(R.drawable.bg_field);
        search.setTextColor(getColor(R.color.vmore_text));
        search.setHintTextColor(getColor(R.color.vmore_text_faint));
        search.setPadding(Ui.dp(this, 14), Ui.dp(this, 12), Ui.dp(this, 14), Ui.dp(this, 12));
        search.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence text, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence text, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable text) {
                String value = text.toString().trim().toLowerCase(Locale.US);
                if (!value.equals(query)) {
                    query = value;
                    render();
                }
            }
        });
        box.addView(search);
    }

    private void addSortChips(int count) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 4));
        row.addView(Ui.chip(this, getString(R.string.files_sort_date), SORT_DATE.equals(sort),
                v -> {
                    sort = SORT_DATE;
                    render();
                }));
        row.addView(Ui.chip(this, getString(R.string.files_sort_name), SORT_NAME.equals(sort),
                v -> {
                    sort = SORT_NAME;
                    render();
                }));
        row.addView(Ui.chip(this, getString(R.string.files_sort_size), SORT_SIZE.equals(sort),
                v -> {
                    sort = SORT_SIZE;
                    render();
                }));
        box.addView(row);
        TextView summary = Ui.subtitle(this, count + " " + getString(R.string.files_count));
        summary.setPadding(0, Ui.dp(this, 2), 0, Ui.dp(this, 6));
        box.addView(summary);
    }

    private void addActions() {
        if (selected.isEmpty()) {
            return;
        }
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 6));
        row.addView(Ui.chip(this, getString(R.string.files_upload), true, v -> uploadSelected()));
        row.addView(Ui.chip(this, getString(R.string.files_share), false, v -> shareSelected()));
        row.addView(Ui.chip(this, getString(R.string.common_delete), false,
                v -> confirmDelete()));
        row.addView(Ui.chip(this, getString(R.string.files_clear), false, v -> {
            selected.clear();
            render();
        }));
        box.addView(row);
        TextView hint = Ui.subtitle(this, selected.size() + " " + getString(R.string.files_selected));
        hint.setPadding(0, 0, 0, Ui.dp(this, 6));
        box.addView(hint);
    }

    private View fileRow(File file, int index) {
        boolean marked = selected.contains(file);
        View row = Ui.row(this, iconFor(file), file.getName(), line(file));
        if (marked) {
            row.setBackgroundResource(R.drawable.bg_card);
        }
        row.setOnClickListener(v -> {
            if (selecting) {
                toggle(file);
            } else {
                open(file);
            }
        });
        row.setOnLongClickListener(v -> {
            selecting = true;
            toggle(file);
            return true;
        });
        Anim.pressible(row);
        Anim.itemIn(row, index);
        return row;
    }

    private void toggle(File file) {
        if (selected.contains(file)) {
            selected.remove(file);
        } else {
            selected.add(file);
        }
        render();
    }

    private void open(File file) {
        if (MediaUtils.isText(file) || MediaUtils.isVideo(file) || MediaUtils.isAudio(file)
                || MediaUtils.isImage(file)) {
            Intent intent = new Intent(this, ViewerActivity.class);
            intent.putExtra("path", file.getAbsolutePath());
            startActivity(intent);
            return;
        }
        Intent intent = new Intent(this, EditorActivity.class);
        intent.putExtra("path", file.getAbsolutePath());
        startActivity(intent);
    }

    // -------------------------------------------------------------- actions //

    private void uploadSelected() {
        if (selected.isEmpty()) {
            return;
        }
        long dest = Prefs.destChatId(this);
        if (dest == 0L) {
            Ui.toast(this, getString(R.string.home_need_destination));
            return;
        }
        int queued = 0;
        for (File file : selected) {
            QJob job = jobFor(file, dest);
            Jobs.get(this).add(job);
            queued++;
        }
        QueueService.run(this);
        Ui.toast(this, queued + " " + getString(R.string.files_queued));
        selected.clear();
        render();
    }

    private QJob jobFor(File file, long dest) {
        QJob job = new QJob();
        job.batchId = java.util.UUID.randomUUID().toString();
        job.batchLabel = getString(R.string.files_title);
        job.raw = file.getName();
        job.method = QJob.METHOD_DOWNLOAD;
        job.uploadAfter = true;
        job.deleteLocal = Prefs.autoDeleteLocal(this);
        job.sendAs = Prefs.sendAs(this);
        job.destChatId = dest;
        job.destTitle = Prefs.destTitle(this);
        job.name = file.getName();
        job.path = file.getAbsolutePath();
        job.size = file.length();
        job.done = file.length();
        job.kind = kindOf(file);
        job.stage = QJob.QUEUED;
        //: The bytes are already here, so the engine only has to upload them.
        job.onlyKinds = "";
        return job;
    }

    private void shareSelected() {
        if (selected.isEmpty()) {
            return;
        }
        Intent intent = new Intent(Intent.ACTION_SEND_MULTIPLE);
        intent.setType("*/*");
        ArrayList<android.net.Uri> uris = new ArrayList<>();
        for (File file : selected) {
            uris.add(VmoreFiles.uriFor(this, file));
        }
        intent.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivity(Intent.createChooser(intent, getString(R.string.files_share)));
        } catch (Exception error) {
            Ui.toast(this, "Nothing on this phone can share that");
        }
    }

    private void confirmDelete() {
        final List<File> files = new ArrayList<>(selected);
        Ui.confirm(this, getString(R.string.common_delete),
                files.size() + " " + getString(R.string.files_delete_confirm),
                getString(R.string.common_delete), () -> {
                    for (File file : files) {
                        String path = file.getAbsolutePath();
                        LocalFiles.delete(path);
                        History.get(this).markLocalGone(path);
                    }
                    Ui.toast(this, files.size() + " " + getString(R.string.files_deleted));
                    selected.clear();
                    render();
                });
    }

    // ---------------------------------------------------------------- files //

    private List<File> files() {
        List<File> found = new ArrayList<>();
        File[] inFolder = LocalFiles.downloadsDir(this).listFiles();
        if (inFolder != null) {
            for (File file : inFolder) {
                if (file.isFile() && file.length() > 0) {
                    found.add(file);
                }
            }
        }
        for (History.Entry entry : History.get(this).all()) {
            if (entry.local && entry.path != null && !entry.path.isEmpty()) {
                File file = new File(entry.path);
                if (file.isFile() && !found.contains(file)) {
                    found.add(file);
                }
            }
        }
        if (!query.isEmpty()) {
            List<File> kept = new ArrayList<>();
            for (File file : found) {
                if (file.getName().toLowerCase(Locale.US).contains(query)) {
                    kept.add(file);
                }
            }
            found = kept;
        }
        final String order = sort;
        Collections.sort(found, (left, right) -> {
            if (SORT_NAME.equals(order)) {
                return left.getName().compareToIgnoreCase(right.getName());
            }
            if (SORT_SIZE.equals(order)) {
                return Long.compare(right.length(), left.length());
            }
            return Long.compare(right.lastModified(), left.lastModified());
        });
        return found;
    }

    private static int iconFor(File file) {
        if (MediaUtils.isVideo(file)) {
            return R.drawable.ic_play;
        }
        if (MediaUtils.isImage(file)) {
            return R.drawable.ic_image;
        }
        if (MediaUtils.isAudio(file)) {
            return R.drawable.ic_speed;
        }
        return R.drawable.ic_folder;
    }

    private static String kindOf(File file) {
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

    private static String line(File file) {
        return Format.size(file.length()) + " \u2022 " + Format.when(file.lastModified());
    }
}
