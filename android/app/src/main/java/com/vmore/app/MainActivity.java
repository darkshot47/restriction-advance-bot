package com.vmore.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Switch;
import android.widget.TextView;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * The home screen: paste links, pick the chat, tap Start.
 *
 * Everything the bot used to do in a chat happens here — one link or a whole
 * batch, a public channel or a private one, straight from this phone.
 */
public class MainActivity extends Activity implements Jobs.Listener, History.Listener {

    private static final int REQUEST_DESTINATION = 101;
    private static final int REQUEST_SCAN = 102;

    private EditText linkField;
    private android.widget.ImageView destAvatar;
    private TextView destTitle;
    private View smartFeatureButton;
    private TextView smartFeatureLabel;
    private android.animation.ValueAnimator crownAnimator;
    private TextView accountText;
    private Button startButton;
    //: The three switches of the home screen, one per row, exactly as the
    //: Settings page renders them: the title gets the whole line and the
    //: switch sits on the right in its own blue.
    private Switch switchUpload;
    private Switch switchDelete;
    private Switch switchForward;
    private TextView valueQuality;
    private TextView valueFilter;
    private TextView valueSchedule;
    private View progressCard;
    private TextView progressName;
    private TextView progressStage;
    private TextView progressPercent;
    private ProgressBar progressBar;
    private Button pauseButton;
    private LinearLayout recentList;
    private android.widget.ImageView avatarView;
    private TextView profileName;
    private TextView profileUser;
    private TextView emptyText;
    private boolean forwardBatch;
    private View clipboardBanner;
    private TextView clipboardText;
    private String clipboardLink = "";

    /** Jobs waiting for a destination (the picker is open for them). */
    private final List<QJob> pending = new ArrayList<>();

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable watcher = new Runnable() {
        @Override
        public void run() {
            //: Still no session and none coming: the sign-in screen is the one
            //: that can explain why, so move there instead of pretending.
            //: Inside the Runnable `this` is the Runnable, not the screen:
            //: the activity has to be named, or Tg.get asks it for a Context
            //: and the build stops exactly here.
            if (!Tg.get(MainActivity.this).isReady()
                    && !Tg.get(MainActivity.this).starting()) {
                goToSignIn();
                return;
            }
            if (!Tg.get(MainActivity.this).isReady()) {
                //: Idempotent: rebuilds the session only when there is none, so
                //: a session TDLib closed comes back without leaving the screen.
                Tg.get(MainActivity.this).start(null);
            }
            paintLive();
            if (!avatarPainted()) {
                paintProfile();
            }
            handler.postDelayed(this, 500);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        captureShareIntent();
        //: Not "is it ready right now": a fresh process is still rebuilding the
        //: session, and this check ran before onResume could ask for one.  The
        //: screen is built either way and onResume decides where to go, so a
        //: cold start no longer flashes the sign-in screen on its way home.
        setContentView(R.layout.activity_main);
        askForNotifications();

        linkField = findViewById(R.id.linkField);
        destAvatar = findViewById(R.id.destAvatar);
        destTitle = findViewById(R.id.destTitle);
        smartFeatureButton = findViewById(R.id.smartFeatureButton);
        smartFeatureLabel = findViewById(R.id.smartFeatureLabel);
        crownAnimator = Crown.bind(this, smartFeatureButton,
                findViewById(R.id.smartFeatureCrown), smartFeatureLabel);
        accountText = findViewById(R.id.accountText);
        startButton = findViewById(R.id.startButton);
        switchUpload = findViewById(R.id.switchUpload);
        switchDelete = findViewById(R.id.switchDelete);
        switchForward = findViewById(R.id.switchForward);
        valueQuality = findViewById(R.id.valueQuality);
        valueFilter = findViewById(R.id.valueFilter);
        valueSchedule = findViewById(R.id.valueSchedule);
        Ui.tintSwitch(switchUpload);
        Ui.tintSwitch(switchDelete);
        Ui.tintSwitch(switchForward);
        progressCard = findViewById(R.id.progressCard);
        progressName = findViewById(R.id.progressName);
        progressStage = findViewById(R.id.progressStage);
        progressPercent = findViewById(R.id.progressPercent);
        progressBar = findViewById(R.id.progressBar);
        pauseButton = findViewById(R.id.pauseButton);
        recentList = findViewById(R.id.recentList);
        clipboardBanner = findViewById(R.id.clipboardBanner);
        clipboardText = findViewById(R.id.clipboardText);
        avatarView = findViewById(R.id.profileAvatar);
        profileName = findViewById(R.id.profileName);
        profileUser = findViewById(R.id.profileUser);
        emptyText = findViewById(R.id.emptyText);
        //: The header picture gets the same ring, turning slowly enough to be
        //: noticed only when looked at.
        StoryRingView profileRing = findViewById(R.id.profileRing);
        profileRing.setTurnSeconds(14f);

        smartFeatureButton.setOnClickListener(v -> SmartFeatureSheet.show(this));
        Anim.pressible(smartFeatureButton);

        findViewById(R.id.themeButton).setOnClickListener(v -> Skin.toggle(this));
        findViewById(R.id.profileBox).setOnClickListener(v ->
                startActivity(new Intent(this, SettingsActivity.class)));
        findViewById(R.id.settingsButton).setOnClickListener(v ->
                startActivity(new Intent(this, SettingsActivity.class)));
        findViewById(R.id.queueButton).setOnClickListener(v ->
                startActivity(new Intent(this, QueueActivity.class)));
        findViewById(R.id.historyButton).setOnClickListener(v ->
                startActivity(new Intent(this, HistoryActivity.class)));
        findViewById(R.id.filesButton).setOnClickListener(v ->
                startActivity(new Intent(this, FilesActivity.class)));
        findViewById(R.id.destCard).setOnClickListener(v -> pickDestination());
        findViewById(R.id.destButton).setOnClickListener(v -> pickDestination());
        findViewById(R.id.pasteButton).setOnClickListener(v -> paste());
        findViewById(R.id.clearButton).setOnClickListener(v -> linkField.setText(""));
        findViewById(R.id.scanButton).setOnClickListener(v -> scanChat());
        findViewById(R.id.viewAllButton).setOnClickListener(v ->
                startActivity(new Intent(this, HistoryActivity.class)));
        startButton.setOnClickListener(v -> start());
        //: The row is the tap target — the switch itself is not clickable, so
        //: one press never toggles twice.
        findViewById(R.id.rowUpload).setOnClickListener(v -> {
            Prefs.setAutoUpload(this, !Prefs.autoUpload(this));
            paintOptions();
        });
        findViewById(R.id.rowDelete).setOnClickListener(v -> {
            Prefs.setAutoDeleteLocal(this, !Prefs.autoDeleteLocal(this));
            paintOptions();
        });
        findViewById(R.id.rowForward).setOnClickListener(v -> {
            forwardBatch = !forwardBatch;
            paintOptions();
        });
        findViewById(R.id.rowQuality).setOnClickListener(v -> pickQuality());
        findViewById(R.id.rowFilter).setOnClickListener(v -> openFilters());
        findViewById(R.id.rowSchedule).setOnClickListener(v -> startActivity(
                new Intent(this, SettingsActivity.class)));
        findViewById(R.id.clipboardAdd).setOnClickListener(v -> {
            if (!clipboardLink.isEmpty()) {
                linkField.setText(clipboardLink);
                Anim.fadeIn(linkField, 160);
                linkField.setSelection(linkField.getText().length());
            }
        });
        findViewById(R.id.stopQueueButton).setOnClickListener(v ->
                QueueService.stopJob(this, null));
        pauseButton.setOnClickListener(v -> {
            if (Jobs.get(this).pausedAll()) {
                QueueService.resumeAll(this);
            } else {
                QueueService.pauseAll(this);
            }
            paintLive();
        });

        for (View view : new View[]{startButton, pauseButton,
                findViewById(R.id.rowUpload), findViewById(R.id.rowDelete),
                findViewById(R.id.rowForward), findViewById(R.id.rowQuality),
                findViewById(R.id.rowFilter), findViewById(R.id.rowSchedule)}) {
            Anim.pressible(view);
        }
        Anim.pageIn(findViewById(R.id.header));
        Anim.pageIn(findViewById(R.id.destCard));
        Anim.pageIn(findViewById(R.id.inputCard));
        Anim.stagger(recentList);
        LaunchIntro.playIfNeeded(this, null);
    }

    /** Android 13 and newer only show the queue row once this is allowed. */
    private void askForNotifications() {
        if (android.os.Build.VERSION.SDK_INT < 33) {
            return;
        }
        if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            return;
        }
        requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 71);
    }

    @Override
    protected void onResume() {
        super.onResume();
        //: The session is asked for first: in a fresh process it is still being
        //: rebuilt, and bouncing to the sign-in screen for those two seconds
        //: made every cold start look like a logout.
        Tg.get(this).start(null);
        boolean ready = Tg.get(this).isReady();
        if (!ready && !Tg.get(this).starting()) {
            goToSignIn();
            return;
        }
        if (Lock.guard(this)) {
            return;
        }
        takeSharedLink();
        Jobs.get(this).addListener(this);
        History.get(this).addListener(this);
        paintAccount();
        paintProfile();
        paintSmartButton();
        Skin.paintToggle(this, findViewById(R.id.themeButton));
        paintDestination();
        paintOptions();
        paintRecent();
        paintLive();
        paintClipboard();
        if (crownAnimator != null && !crownAnimator.isStarted()) {
            crownAnimator.start();
        }
        handler.post(watcher);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(watcher);
        //: The shimmer is decoration, not information: it stops with the
        //: screen so a backgrounded app never keeps an animator alive.
        if (crownAnimator != null) {
            crownAnimator.cancel();
        }
        Jobs.get(this).removeListener(this);
        History.get(this).removeListener(this);
        super.onPause();
    }

    // ------------------------------------------------------------- painting //

    /** The sign-in screen, once, from anywhere on this one. */
    private void goToSignIn() {
        handler.removeCallbacks(watcher);
        startActivity(new Intent(this, LoginActivity.class));
        finish();
    }

    private void paintAccount() {
        if (!Tg.get(this).isReady()) {
            accountText.setText(getString(R.string.login_working));
            return;
        }
        String phone = Prefs.phone(this);
        accountText.setText(phone.isEmpty() ? getString(R.string.settings_session) : phone);
    }

    /**
     * The corner block: the account name and the profile picture Telegram gave
     * us.  Both are stored on the phone, so this only reads local data — the
     * picture is downloaded exactly once, when the session comes up.
     */
    private boolean avatarPainted() {
        String path = Prefs.avatarPath(this);
        return path != null && !path.isEmpty() && new File(path).exists();
    }

    private void paintProfile() {
        String name = Prefs.accountName(this);
        String username = Prefs.accountUsername(this);
        profileName.setText(name == null || name.isEmpty()
                ? getString(R.string.home_profile_guest) : name);
        profileUser.setText(username == null || username.isEmpty() ? "" : "@" + username);
        String path = Prefs.avatarPath(this);
        android.graphics.Bitmap picture = path == null || path.isEmpty()
                ? null : android.graphics.BitmapFactory.decodeFile(path);
        if (picture != null) {
            avatarView.setPadding(0, 0, 0, 0);
            avatarView.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);
            avatarView.setImageBitmap(Ui.circle(this, picture, 42));
        } else {
            avatarView.setImageResource(R.drawable.ic_person);
            avatarView.setPadding(Ui.dp(this, 9), Ui.dp(this, 9), Ui.dp(this, 9), Ui.dp(this, 9));
        }
    }

    private void paintSmartButton() {
        if (smartFeatureLabel != null) {
            smartFeatureLabel.setText(SmartOverlayService.isRunning()
                    ? R.string.smart_button_on : R.string.smart_button);
        }
    }

    private void paintDestination() {
        long chatId = Prefs.destChatId(this);
        String title = Prefs.destTitle(this);
        if (chatId == 0L || title.isEmpty()) {
            destTitle.setText(R.string.home_no_destination);
            if (destAvatar != null) {
                destAvatar.setTag(null);
                destAvatar.setImageResource(R.drawable.ic_chat);
                destAvatar.setImageTintList(
                        android.content.res.ColorStateList.valueOf(getColor(R.color.vmore_blue)));
                destAvatar.setPadding(Ui.dp(this, 10), Ui.dp(this, 10),
                        Ui.dp(this, 10), Ui.dp(this, 10));
            }
            return;
        }
        destTitle.setText(title);
        if (destAvatar != null) {
            Tg.Chat placeholder = new Tg.Chat();
            placeholder.id = chatId;
            placeholder.title = title;
            Ui.paintChatAvatar(this, destAvatar, placeholder, 42);
            Tg.get(this).chat(chatId, new Tg.Cb<Tg.Chat>() {
                @Override
                public void ok(Tg.Chat value) {
                    if (!isFinishing() && !isDestroyed()
                            && Prefs.destChatId(MainActivity.this) == chatId) {
                        Ui.paintChatAvatar(MainActivity.this, destAvatar, value, 42);
                    }
                }

                @Override
                public void fail(String message) {
                }
            });
        }
    }

    /**
     * The option rows, painted from the stored preferences.
     *
     * A switch shows its own state, so no label has to repeat it; the three
     * chooser rows carry the value in force, and a value that is doing
     * something is set on the blue pill so it reads at a glance.
     */
    private void paintOptions() {
        switchUpload.setChecked(Prefs.autoUpload(this));
        switchDelete.setChecked(Prefs.autoDeleteLocal(this));
        switchForward.setChecked(forwardBatch);

        paintValue(valueQuality, qualityLabel(), !Prefs.SEND_FILE.equals(Prefs.sendAs(this)));

        boolean filtered = !Prefs.filterKinds(this).isEmpty()
                || Prefs.filterMinSize(this) > 0 || Prefs.filterMaxSize(this) > 0;
        paintValue(valueFilter, getString(filtered
                ? R.string.home_filter_on : R.string.filters_all), filtered);

        long at = Prefs.scheduleAt(this);
        boolean scheduled = at > System.currentTimeMillis();
        paintValue(valueSchedule, scheduled ? Format.when(at)
                : getString(R.string.home_schedule_now), scheduled);
    }

    /**
     * One value on the right of a row: plain text while it is the default, a
     * blue pill with white text the moment the option is doing something.
     */
    private void paintValue(TextView view, String text, boolean active) {
        view.setText(text);
        view.setBackgroundResource(active ? R.drawable.bg_chip_active : 0);
        view.setTextColor(getColor(active ? R.color.vmore_on_accent : R.color.vmore_text_dim));
    }

    /** File, video or photo — what the next batch is sent as. */
    private String qualityLabel() {
        String sendAs = Prefs.sendAs(this);
        if (Prefs.SEND_VIDEO.equals(sendAs)) {
            return getString(R.string.settings_send_as_video);
        }
        if (Prefs.SEND_PHOTO.equals(sendAs)) {
            return getString(R.string.settings_send_as_photo);
        }
        return getString(R.string.settings_send_as_file);
    }

    /**
     * The quality chooser: the same three words the Settings page offers, on
     * the screen the batch is actually started from.
     */
    private void pickQuality() {
        String[] labels = {getString(R.string.settings_send_as_file),
                getString(R.string.settings_send_as_video),
                getString(R.string.settings_send_as_photo)};
        String[] values = {Prefs.SEND_FILE, Prefs.SEND_VIDEO, Prefs.SEND_PHOTO};
        String current = Prefs.sendAs(this);
        int checked = 0;
        for (int index = 0; index < values.length; index++) {
            if (values[index].equals(current)) {
                checked = index;
            }
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.home_option_quality)
                .setSingleChoiceItems(labels, checked, (dialog, which) -> {
                    Prefs.setSendAs(this, values[which]);
                    dialog.dismiss();
                    paintOptions();
                    Anim.fadeIn(valueQuality, 160);
                })
                .setNegativeButton(R.string.common_cancel, null)
                .show();
    }

    /** The batch filter: which kinds are kept, and how big a file may be. */
    private void openFilters() {
        Filters.show(this, this::paintOptions);
    }

    /**
     * A link shared from another app, or the one sitting in the clipboard: both
     * land in the link box without any typing.
     */
    private void takeSharedLink() {
        String shared = Prefs.takePendingShare(this);
        if (shared != null && !shared.isEmpty()) {
            linkField.setText(shared);
            Anim.fadeIn(linkField, 200);
            Ui.toast(this, getString(R.string.home_shared_received));
        }
    }

    /**
     * A link shared from another app ("Share to Vmore") is stored right away,
     * so it survives the sign-in screen as well.
     */
    private void captureShareIntent() {
        Intent intent = getIntent();
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) {
            return;
        }
        String value = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (value != null && !value.trim().isEmpty()) {
            Prefs.setPendingShare(this, value.trim());
        }
        intent.setAction(null);
    }

    private void paintClipboard() {
        clipboardLink = "";
        android.content.ClipboardManager clipboard =
                (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard == null || !clipboard.hasPrimaryClip()
                || clipboard.getPrimaryClip() == null
                || clipboard.getPrimaryClip().getItemCount() == 0) {
            clipboardBanner.setVisibility(View.GONE);
            return;
        }
        CharSequence text = clipboard.getPrimaryClip().getItemAt(0).coerceToText(this);
        String value = text == null ? "" : text.toString().trim();
        String already = linkField.getText().toString();
        if (value.isEmpty() || value.length() > 400 || already.contains(value)) {
            clipboardBanner.setVisibility(View.GONE);
            return;
        }
        boolean looksLikeLink = value.contains("t.me/") || value.startsWith("tg://")
                || value.startsWith("@") || value.startsWith("-100");
        if (!looksLikeLink) {
            clipboardBanner.setVisibility(View.GONE);
            return;
        }
        clipboardLink = value;
        clipboardText.setText(value);
        clipboardBanner.setVisibility(View.VISIBLE);
        Anim.fadeIn(clipboardBanner, 200);
    }

    private void paintRecent() {
        recentList.removeAllViews();
        List<History.Entry> entries = History.get(this).all();
        if (entries.isEmpty()) {
            emptyText.setVisibility(View.VISIBLE);
            recentList.setVisibility(View.GONE);
            return;
        }
        emptyText.setVisibility(View.GONE);
        recentList.setVisibility(View.VISIBLE);
        int shown = Math.min(3, entries.size());
        for (int index = 0; index < shown; index++) {
            History.Entry entry = entries.get(index);
            View row = historyRow(entry);
            recentList.addView(row);
            Anim.itemIn(row, index);
        }
    }

    private View historyRow(History.Entry entry) {
        LinearLayout row = Ui.row(this, Ui.iconForKind(entry.kind),
                entry.name.isEmpty() ? "Job" : entry.name,
                historySubtitle(entry));
        row.setOnClickListener(v -> openEntry(entry));
        Anim.pressible(row);
        return row;
    }

    private String historySubtitle(History.Entry entry) {
        StringBuilder builder = new StringBuilder();
        if (entry.size > 0) {
            builder.append(Format.size(entry.size)).append(" • ");
        }
        builder.append(Format.when(entry.when));
        if (!entry.destTitle.isEmpty()) {
            builder.append(" • ").append(entry.destTitle);
        }
        if (History.STATUS_FAILED.equals(entry.status)) {
            builder.append(" • ").append(entry.error.isEmpty() ? "failed" : entry.error);
        } else if (!entry.local) {
            builder.append(" • local copy removed");
        }
        return builder.toString();
    }

    private void openEntry(History.Entry entry) {
        if (entry.local && LocalFiles.exists(entry.path)) {
            Intent intent = new Intent(this, ViewerActivity.class);
            intent.putExtra("path", entry.path);
            startActivity(intent);
            return;
        }
        Ui.toast(this, getString(R.string.viewer_missing));
    }

    private void paintLive() {
        boolean running = QueueService.Live.RUNNING.get()
                || !QueueService.Live.STAGE.isEmpty();
        QJob active = Jobs.get(this).active();
        boolean paused = Jobs.get(this).pausedAll();
        if (!running && active == null) {
            progressCard.setVisibility(View.GONE);
            return;
        }
        progressCard.setVisibility(View.VISIBLE);
        String name = QueueService.Live.NAME;
        progressName.setText(name == null || name.isEmpty()
                ? getString(R.string.home_title) : name);
        String stage = QueueService.Live.STAGE;
        String error = QueueService.Live.ERROR;
        progressStage.setText(error == null || error.isEmpty()
                ? Ui.stageLabel(stage) : Ui.stageLabel(stage) + ": " + error);
        long done = QueueService.Live.DONE.get();
        long total = QueueService.Live.TOTAL.get();
        int rawPercent = Format.percent(done, total);
        int percent = QJob.UPLOADING.equals(stage) ? Math.min(99, rawPercent) : rawPercent;
        progressBar.setProgress(total > 0 ? percent : 0);
        progressBar.setIndeterminate(total <= 0);
        StringBuilder builder = new StringBuilder();
        if (total > 0) {
            builder.append(percent).append("% • ")
                    .append(Format.size(done)).append(" / ").append(Format.size(total));
        } else if (done > 0) {
            builder.append(Format.size(done));
        }
        if (QueueService.Live.SPEED > 0
                && (QJob.DOWNLOADING.equals(stage) || QJob.UPLOADING.equals(stage))) {
            builder.append(" • ").append(Format.speed(QueueService.Live.SPEED));
            String eta = Format.eta(done, total, QueueService.Live.SPEED);
            if (!eta.isEmpty()) {
                builder.append(" • ").append(eta);
            }
        }
        if (paused) {
            builder.append(" • paused");
        }
        progressPercent.setText(builder.toString());
        pauseButton.setText(paused ? R.string.queue_resume_all : R.string.queue_pause_all);
    }

    // -------------------------------------------------------------- actions //

    private void paste() {
        android.content.ClipboardManager clipboard =
                (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard != null && clipboard.hasPrimaryClip()
                && clipboard.getPrimaryClip() != null
                && clipboard.getPrimaryClip().getItemCount() > 0) {
            CharSequence text = clipboard.getPrimaryClip().getItemAt(0).coerceToText(this);
            if (text != null) {
                linkField.setText(text.toString().trim());
                Anim.fadeIn(linkField, 160);
            }
        } else {
            Ui.toast(this, getString(R.string.home_clipboard_empty));
        }
    }

    private void start() {
        String text = linkField.getText().toString().trim();
        if (text.isEmpty()) {
            Ui.toast(this, getString(R.string.home_no_link));
            return;
        }
        List<TgLink> parsed = TgLink.parseAll(text);
        List<TgLink> usable = new ArrayList<>();
        StringBuilder notes = new StringBuilder();
        for (TgLink link : parsed) {
            if (link.valid && link.needsChatContext) {
                //: A bare "145" names a message but no chat, and a job that
                //: cannot be resolved would only fail the moment it starts.
                notes.append(link.raw).append(": ").append(getString(R.string.home_need_chat))
                        .append("\n");
            } else if (link.valid) {
                usable.add(link);
                if (!link.note.isEmpty()) {
                    notes.append(link.note).append("\n");
                }
            } else {
                notes.append(link.raw).append(": ")
                        .append(link.error.isEmpty() ? "not understood" : link.error)
                        .append("\n");
            }
        }
        if (usable.isEmpty()) {
            Ui.toast(this, "Paste a direct Telegram link (https://t.me/...) or @username");
            return;
        }
        if (!notes.toString().trim().isEmpty()) {
            Ui.toast(this, notes.toString().trim());
        }

        List<QJob> jobs = new ArrayList<>();
        String batchId = UUID.randomUUID().toString();
        String label = usable.size() == 1 ? usable.get(0).raw : usable.size() + " links";
        for (TgLink link : usable) {
            if (link.messageId <= 0) {
                //: "https://t.me/channel" or "@channel": the queue takes that
                //: chat's recent files and turns them into one job each.
                jobs.add(jobFor(link, 0L, batchId, label));
            } else if (link.isRange()) {
                for (long id = link.messageId; id <= link.endMessageId; id++) {
                    jobs.add(jobFor(link, id, batchId, label));
                }
            } else {
                jobs.add(jobFor(link, link.messageId, batchId, label));
            }
        }

        long dest = Prefs.destChatId(this);
        if (dest == 0L || Prefs.askDestination(this)) {
            pending.clear();
            pending.addAll(jobs);
            pickDestination();
            return;
        }
        applyDestination(jobs, dest, Prefs.destTitle(this));
        enqueue(jobs);
    }

    private QJob jobFor(TgLink link, long messageId, String batchId, String label) {
        QJob job = new QJob();
        job.batchId = batchId;
        job.batchLabel = label;
        job.raw = link.raw;
        job.chatId = link.privateLink ? link.privateChatId() : link.chatId;
        job.messageId = messageId;
        job.username = link.username;
        job.inviteHash = link.inviteHash;
        job.privateLink = link.privateLink;
        job.internalId = link.internalId;
        job.method = messageId <= 0 ? QJob.METHOD_SCAN
                : forwardBatch ? QJob.METHOD_FORWARD : QJob.METHOD_DOWNLOAD;
        job.sendAs = Prefs.sendAs(this);
        job.uploadAfter = Prefs.autoUpload(this);
        job.deleteLocal = Prefs.autoDeleteLocal(this);
        job.onlyKinds = Prefs.filterKinds(this);
        job.minSize = Prefs.filterMinSize(this);
        job.maxSize = Prefs.filterMaxSize(this);
        job.skipDuplicates = Prefs.skipDuplicates(this);
        return job;
    }

    private void applyDestination(List<QJob> jobs, long chatId, String title) {
        for (QJob job : jobs) {
            job.destChatId = chatId;
            job.destTitle = title == null ? "" : title;
            //: Forwarding needs the chat and the message id — never a download.
            if (job.method == null || job.method.isEmpty()) {
                job.method = QJob.METHOD_DOWNLOAD;
            }
        }
    }

    private void enqueue(List<QJob> jobs) {
        if (jobs.isEmpty()) {
            return;
        }
        Jobs.get(this).addBatch(jobs);
        QueueService.run(this);
        Ui.toast(this, jobs.size() + " " + getString(R.string.home_links_added));
        linkField.setText("");
        forwardBatch = false;
        paintOptions();
        paintLive();
        paintRecent();
    }

    private void pickDestination() {
        Intent intent = new Intent(this, ChatPickerActivity.class);
        intent.putExtra("mode", "destination");
        startActivityForResult(intent, REQUEST_DESTINATION);
    }

    private void scanChat() {
        Intent intent = new Intent(this, ChatPickerActivity.class);
        intent.putExtra("mode", "scan");
        startActivityForResult(intent, REQUEST_SCAN);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null) {
            pending.clear();
            return;
        }
        long chatId = data.getLongExtra("chat_id", 0L);
        String title = data.getStringExtra("chat_title");
        if (requestCode == REQUEST_DESTINATION) {
            if (chatId == 0L) {
                return;
            }
            if (data.getBooleanExtra("remember", false)) {
                Prefs.saveDestination(this, chatId, title);
                paintDestination();
            }
            List<QJob> jobs = new ArrayList<>(pending);
            pending.clear();
            applyDestination(jobs, chatId, title);
            enqueue(jobs);
            return;
        }
        if (requestCode == REQUEST_SCAN) {
            scanAndQueue(chatId, title);
        }
    }

    /** Take the last media messages of a chat and queue them all. */
    private void scanAndQueue(long chatId, String title) {
        long dest = Prefs.destChatId(this);
        String destTitle = Prefs.destTitle(this);
        if (dest == 0L) {
            Ui.toast(this, getString(R.string.home_need_destination));
            pickDestination();
            return;
        }
        Ui.toast(this, getString(R.string.chats_loading));
        Tg.get(this).scanChat(chatId, Vmore.SCAN_LIMIT, new Tg.Cb<List<Tg.Media>>() {
            @Override
            public void ok(List<Tg.Media> media) {
                if (media == null || media.isEmpty()) {
                    Ui.toast(MainActivity.this,
                            getString(R.string.home_no_media) + " " + title);
                    return;
                }
                List<QJob> jobs = new ArrayList<>();
                String batchId = UUID.randomUUID().toString();
                for (Tg.Media item : media) {
                    QJob job = new QJob();
                    job.batchId = batchId;
                    job.batchLabel = title;
                    job.raw = item.chatTitle.isEmpty() ? title : item.chatTitle;
                    job.chatId = item.chatId;
                    job.messageId = item.messageId;
                    job.privateLink = item.chatId < -1000000000000L;
                    job.internalId = TgLink.internalFromChatId(item.chatId);
                    job.destChatId = dest;
                    job.destTitle = destTitle;
                    job.method = forwardBatch ? QJob.METHOD_FORWARD : QJob.METHOD_DOWNLOAD;
                    job.sendAs = Prefs.sendAs(MainActivity.this);
                    job.uploadAfter = Prefs.autoUpload(MainActivity.this);
                    job.deleteLocal = Prefs.autoDeleteLocal(MainActivity.this);
                    jobs.add(job);
                }
                enqueue(jobs);
            }

            @Override
            public void fail(String message) {
                Ui.toast(MainActivity.this, message);
            }
        });
    }

    // ------------------------------------------------------------- listeners //

    @Override
    public void onJobsChanged() {
        paintLive();
    }

    @Override
    public void onHistoryChanged() {
        paintRecent();
    }

    /** Nothing here needs a file list; kept for the editor's "open latest". */
    static File newestDownload(android.content.Context context) {
        List<History.Entry> entries = History.get(context).all();
        for (History.Entry entry : entries) {
            if (entry.local && LocalFiles.exists(entry.path)) {
                return new File(entry.path);
            }
        }
        return null;
    }

    @Override
    public void onBackPressed() {
        if (linkField != null && !linkField.getText().toString().isEmpty()) {
            linkField.setText("");
            return;
        }
        super.onBackPressed();
    }
}
