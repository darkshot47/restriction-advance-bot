package com.vmore.app;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Floating overlay service for Vmore's Smart Feature:
// - Floating colorful Vmore menu orb (single-tap opens/closes colorful menu)
// - Small precision white circle pointer (drag onto any file + double-tap to
//   capture; move to any writable destination channel/chat + double-tap to paste)
// - Live step-by-step floating status banner right on top of Telegram
public class SmartOverlayService extends Service implements Jobs.Listener {

    public static final String ACTION_START = "com.vmore.app.SMART_START";
    public static final String ACTION_SHOW_MENU = "com.vmore.app.SMART_MENU";
    public static final String ACTION_STOP = "com.vmore.app.SMART_STOP";

    private static volatile SmartOverlayService current;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<Tg.Media> captured = new ArrayList<>();
    private final List<Tg.Chat> writableChats = new ArrayList<>();

    private WindowManager wm;
    private SmartPointerView whiteCircle;
    private WindowManager.LayoutParams whiteParams;
    private SmartPointerView menuOrb;
    private WindowManager.LayoutParams orbParams;
    private FrameLayout bannerRoot;
    private TextView bannerBadge;
    private TextView bannerText;
    private FrameLayout menuScrim;
    private AuroraDrawable menuAurora;

    // Live views inside the colorful floating menu
    private TextView menuStepText;
    private LinearLayout menuGuideBox;
    private LinearLayout menuCapturedList;
    private LinearLayout menuLiveTransferBox;
    private LinearLayout menuDestList;
    private Button togglePointerBtn;

    private boolean pointerVisible = true;
    private boolean guideExpanded = false;
    private boolean resolvingTap = false;
    private String lastAnnouncedStage = "";

    private final Runnable hideBannerTask = () -> {
        if (bannerRoot != null) {
            bannerRoot.animate().alpha(0f).setDuration(220L)
                    .withEndAction(() -> {
                        if (bannerRoot != null) {
                            bannerRoot.setVisibility(View.GONE);
                        }
                    }).start();
        }
    };

    private final Runnable liveTicker = new Runnable() {
        @Override
        public void run() {
            syncLiveTransferUi();
            handler.postDelayed(this, 600L);
        }
    };

    public static boolean isRunning() {
        return current != null;
    }

    public static boolean canDrawOverlays(Context context) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || Settings.canDrawOverlays(context);
    }

    public static void start(Context context, boolean openMenuImmediately) {
        if (context == null || !canDrawOverlays(context)) {
            return;
        }
        Intent intent = new Intent(context, SmartOverlayService.class);
        intent.setAction(openMenuImmediately ? ACTION_SHOW_MENU : ACTION_START);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Throwable ignored) {
        }
    }

    public static void stop(Context context) {
        if (context == null) {
            return;
        }
        SmartOverlayService active = current;
        if (active != null) {
            active.shutdownCleanly();
            return;
        }
        try {
            context.stopService(new Intent(context, SmartOverlayService.class));
        } catch (Throwable ignored) {
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        current = this;
        Notifications.ensureChannels(this);
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        startForegroundSafely(getString(R.string.smart_step_ready));
        Jobs.get(this).addListener(this);
        mountOverlays();
        refreshWritableDestinations();
        handler.post(liveTicker);
        announceStep("STEP 1 OF 2", getString(R.string.smart_step_ready), 0xFF38BDF8, 5200L);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            shutdownCleanly();
            return START_NOT_STICKY;
        }
        startForegroundSafely(currentStepSummary());
        if (!canDrawOverlays(this)) {
            shutdownCleanly();
            return START_NOT_STICKY;
        }
        mountOverlays();
        if (ACTION_SHOW_MENU.equals(action)) {
            showMenuPanel();
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        Jobs.get(this).removeListener(this);
        removeAllWindows();
        if (current == this) {
            current = null;
        }
        Notifications.cancelSmart(this);
        super.onDestroy();
    }

    public void shutdownCleanly() {
        removeAllWindows();
        try {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } catch (Throwable ignored) {
        }
        Notifications.cancelSmart(this);
        stopSelf();
    }

    private void startForegroundSafely(String statusLine) {
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(Notifications.ID_SMART,
                        Notifications.smart(this, statusLine),
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            } else {
                startForeground(Notifications.ID_SMART,
                        Notifications.smart(this, statusLine));
            }
        } catch (Throwable ignored) {
        }
    }

    // --------------------------------------------------------- overlay mount //

    private int overlayWindowType() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
    }

    private void mountOverlays() {
        if (wm == null) {
            return;
        }
        DisplayMetrics dm = getResources().getDisplayMetrics();

        // 1. Floating top step-by-step banner toast
        if (bannerRoot == null) {
            bannerRoot = buildBannerView();
            WindowManager.LayoutParams bp = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.WRAP_CONTENT,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT);
            bp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
            bp.y = Ui.dp(this, 44);
            bannerRoot.setVisibility(View.GONE);
            safeAddView(bannerRoot, bp);
        }

        // 2. Small precision white circle pointer
        if (whiteCircle == null) {
            int size = Ui.dp(this, 38);
            whiteCircle = new SmartPointerView(this, SmartPointerView.MODE_WHITE_CIRCLE);
            whiteParams = new WindowManager.LayoutParams(
                    size, size,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                    PixelFormat.TRANSLUCENT);
            whiteParams.gravity = Gravity.TOP | Gravity.START;
            whiteParams.x = (dm.widthPixels - size) / 2;
            whiteParams.y = (int) (dm.heightPixels * 0.44f);
            whiteCircle.setInteractionListener(new SmartPointerView.InteractionListener() {
                @Override
                public void onMoveBy(int dx, int dy) {
                    whiteParams.x = clamp(whiteParams.x + dx, 0, dm.widthPixels - size);
                    whiteParams.y = clamp(whiteParams.y + dy, Ui.dp(SmartOverlayService.this, 24),
                            dm.heightPixels - size);
                    safeUpdateView(whiteCircle, whiteParams);
                }

                @Override
                public void onDragFinished() {
                }

                @Override
                public void onSingleTap() {
                    if (captured.isEmpty()) {
                        announceStep("HOW TO CAPTURE",
                                "Place this white circle directly on a file in Telegram and double-tap it.",
                                0xFF38BDF8, 3400L);
                    } else {
                        announceStep(captured.size() + " READY TO PASTE",
                                "Open any writable channel or chat and double-tap to paste there, or tap the colorful Vmore orb.",
                                0xFF10B981, 3600L);
                    }
                }

                @Override
                public void onDoubleTap(int centerRawX, int centerRawY) {
                    handleWhiteCircleDoubleTap(centerRawX, centerRawY);
                }
            });
            safeAddView(whiteCircle, whiteParams);
        }

        // 3. Floating colorful Vmore menu orb on screen edge
        if (menuOrb == null) {
            int orbSize = Ui.dp(this, 50);
            menuOrb = new SmartPointerView(this, SmartPointerView.MODE_MENU_ORB);
            orbParams = new WindowManager.LayoutParams(
                    orbSize, orbSize,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                    PixelFormat.TRANSLUCENT);
            orbParams.gravity = Gravity.TOP | Gravity.START;
            orbParams.x = Ui.dp(this, 10);
            orbParams.y = (int) (dm.heightPixels * 0.28f);
            menuOrb.setInteractionListener(new SmartPointerView.InteractionListener() {
                @Override
                public void onMoveBy(int dx, int dy) {
                    orbParams.x = clamp(orbParams.x + dx, 0, dm.widthPixels - orbSize);
                    orbParams.y = clamp(orbParams.y + dy, Ui.dp(SmartOverlayService.this, 32),
                            dm.heightPixels - orbSize);
                    safeUpdateView(menuOrb, orbParams);
                }

                @Override
                public void onDragFinished() {
                    // Gently snap colorful orb to left or right edge so it stays tidy
                    orbParams.x = orbParams.x + orbSize / 2 < dm.widthPixels / 2
                            ? Ui.dp(SmartOverlayService.this, 8)
                            : dm.widthPixels - orbSize - Ui.dp(SmartOverlayService.this, 8);
                    safeUpdateView(menuOrb, orbParams);
                }

                @Override
                public void onSingleTap() {
                    toggleMenuPanel();
                }

                @Override
                public void onDoubleTap(int centerRawX, int centerRawY) {
                    toggleMenuPanel();
                }
            });
            safeAddView(menuOrb, orbParams);
        }
    }

    // ------------------------------------------ double-tap smart engine ---- //

    private void handleWhiteCircleDoubleTap(final int rawX, final int rawY) {
        if (resolvingTap) {
            return;
        }
        if (!SmartAccessibilityService.isEnabled(this)
                || !SmartAccessibilityService.isRunning()) {
            setPointerState(SmartPointerView.STATE_ALERT);
            announceStep("ENABLE SCREEN READER",
                    "Tap Allow on Screen file and chat reader once so Vmore can see the file or chat under the circle.",
                    0xFFF59E0B, 5200L);
            showMenuPanel();
            return;
        }
        if (!Tg.get(this).isReady()) {
            Tg.get(this).start(null);
            setPointerState(SmartPointerView.STATE_SCANNING);
            announceStep("CONNECTING SESSION",
                    "Waking your signed-in Telegram session… double-tap once more in a second.",
                    0xFF38BDF8, 3800L);
            return;
        }

        resolvingTap = true;
        setPointerState(SmartPointerView.STATE_SCANNING);
        announceStep("SCANNING TARGET", getString(R.string.smart_step_reading),
                0xFF818CF8, 3500L);

        final SmartAccessibilityService.ScreenTarget screen =
                SmartAccessibilityService.inspectAt(rawX, rawY);
        if (screen == null) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            announceStep("NOTHING DETECTED",
                    "Open Telegram with a chat or file visible under the white circle, then double-tap.",
                    0xFFF59E0B, 4200L);
            return;
        }

        // Case A: User double-tapped a chat row directly in Telegram's main chat list!
        if (screen.looksLikeChatList && !screen.targetLines.isEmpty()) {
            resolveChatRowTap(screen);
            return;
        }

        // Case B: User is inside an opened chat/channel (headerTitle identifies it)
        String chatQuery = !screen.headerTitle.isEmpty()
                ? screen.headerTitle
                : firstTitleCandidate(screen.targetLines);
        if (chatQuery.isEmpty()) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            announceStep("MOVE CIRCLE CLOSER",
                    "Keep the chat header visible at the top of Telegram and place the circle right on the file or chat.",
                    0xFFF59E0B, 4500L);
            return;
        }

        Tg.get(this).findChatsMatching(chatQuery, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> matches) {
                if (matches == null || matches.isEmpty()) {
                    resolvingTap = false;
                    restoreIdleOrCapturedState();
                    announceStep("CHAT NOT MATCHED",
                            "Could not find \"" + shortStr(chatQuery, 28)
                                    + "\" in your signed-in Vmore account.",
                            0xFFF59E0B, 4500L);
                    return;
                }
                final Tg.Chat matchedChat = matches.get(0);
                // Decide whether this double-tap captures another file or pastes into destination:
                // - If basket is empty -> capture file under pointer!
                // - If basket already holds files AND user moved into a DIFFERENT chat (or tapped empty chat space / composer area) -> PASTE into matchedChat!
                // - If basket holds files AND user is STILL inside the same source chat tapping another media item -> add to batch!
                boolean sameAsLastSource = !captured.isEmpty()
                        && captured.get(captured.size() - 1).chatId == matchedChat.id;
                boolean looksLikeMediaBubble = hasMediaHints(screen.targetLines);

                if (!captured.isEmpty() && (!sameAsLastSource || !looksLikeMediaBubble)) {
                    resolvingTap = false;
                    pasteCapturedIntoChat(matchedChat);
                    return;
                }

                // Capture media message under the white circle inside matchedChat!
                Tg.get(SmartOverlayService.this).matchMediaInChat(
                        matchedChat.id,
                        screen.targetLines,
                        screen.siblingAnchorLines,
                        screen.cellOffsetFromAnchor,
                        screen.cellIndexFromBottom,
                        new Tg.Cb<Tg.Media>() {
                            @Override
                            public void ok(Tg.Media media) {
                                resolvingTap = false;
                                onMediaCaptured(media, matchedChat);
                            }

                            @Override
                            public void fail(String message) {
                                resolvingTap = false;
                                if (!captured.isEmpty() && matchedChat.canSend) {
                                    pasteCapturedIntoChat(matchedChat);
                                    return;
                                }
                                restoreIdleOrCapturedState();
                                announceStep("NO FILE UNDER CIRCLE",
                                        message, 0xFFF59E0B, 4600L);
                            }
                        });
            }

            @Override
            public void fail(String message) {
                resolvingTap = false;
                restoreIdleOrCapturedState();
                announceStep("SESSION BUSY", message, 0xFFF59E0B, 4200L);
            }
        });
    }

    private void resolveChatRowTap(final SmartAccessibilityService.ScreenTarget screen) {
        String rowTitle = firstTitleCandidate(screen.targetLines);
        if (rowTitle.isEmpty()) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            announceStep("PLACE ON CHAT OR FILE",
                    "Open a chat to grab a file first, or place the circle right on a destination chat name.",
                    0xFFF59E0B, 4200L);
            return;
        }
        Tg.get(this).findChatsMatching(rowTitle, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> matches) {
                resolvingTap = false;
                if (matches == null || matches.isEmpty()) {
                    restoreIdleOrCapturedState();
                    announceStep("CHAT NOT FOUND",
                            "Open the chat first so Telegram loads it, then double-tap.",
                            0xFFF59E0B, 4200L);
                    return;
                }
                Tg.Chat chat = matches.get(0);
                if (!captured.isEmpty()) {
                    pasteCapturedIntoChat(chat);
                } else {
                    restoreIdleOrCapturedState();
                    announceStep("OPEN CHAT TO PICK FILE",
                            "Open \"" + shortStr(chat.title, 26)
                                    + "\", place the white circle on the file you want, and double-tap.",
                            0xFF38BDF8, 4500L);
                }
            }

            @Override
            public void fail(String message) {
                resolvingTap = false;
                restoreIdleOrCapturedState();
                announceStep("ERROR", message, 0xFFF59E0B, 4000L);
            }
        });
    }

    private void onMediaCaptured(Tg.Media media, Tg.Chat sourceChat) {
        for (Tg.Media existing : captured) {
            if (existing.chatId == media.chatId && existing.messageId == media.messageId) {
                restoreIdleOrCapturedState();
                announceStep("ALREADY IN BASKET (" + captured.size() + ")",
                        shortStr(media.name, 30)
                                + " is already selected. Open your destination channel/chat and double-tap to paste!",
                        0xFF10B981, 4600L);
                return;
            }
        }
        if (media.chatTitle == null || media.chatTitle.isEmpty()) {
            media.chatTitle = sourceChat.title;
        }
        captured.add(media);
        restoreIdleOrCapturedState();
        String sizeLabel = media.size > 0 ? " (" + Format.size(media.size) + ")" : "";
        String stepBadge = captured.size() == 1
                ? "STEP 1 DONE • FILE ADDED"
                : captured.size() + " FILES ADDED";
        String msg = "Found " + shortStr(media.name, 28) + sizeLabel
                + " in " + shortStr(media.chatTitle, 22)
                + ". Now open any writable channel/chat and double-tap to paste!";
        startForegroundSafely(msg);
        announceStep(stepBadge, msg, 0xFF10B981, 5600L);
        refreshMenuContents();
    }

    private void pasteCapturedIntoChat(Tg.Chat destination) {
        if (destination == null) {
            return;
        }
        if (!destination.canSend) {
            setPointerState(SmartPointerView.STATE_ALERT);
            handler.postDelayed(this::restoreIdleOrCapturedState, 1200L);
            announceStep("NO SEND PERMISSION",
                    "You cannot post in \"" + shortStr(destination.title, 28)
                            + "\". Open a channel or chat where you have send permission.",
                    0xFFEF4444, 5200L);
            return;
        }
        if (captured.isEmpty()) {
            announceStep("SELECT A FILE FIRST",
                    getString(R.string.smart_step_ready), 0xFF38BDF8, 4200L);
            return;
        }

        List<QJob> batch = new ArrayList<>();
        String batchId = UUID.randomUUID().toString();
        for (Tg.Media item : captured) {
            QJob job = new QJob();
            job.batchId = batchId;
            job.batchLabel = "Smart transfer";
            job.raw = item.chatTitle.isEmpty() ? item.name : item.chatTitle + " / " + item.name;
            job.chatId = item.chatId;
            job.messageId = item.messageId;
            job.fileId = item.fileId;
            job.name = item.name;
            job.kind = item.kind;
            job.size = item.size;
            job.caption = item.caption;
            job.durationSec = item.durationSec;
            job.width = item.width;
            job.height = item.height;
            job.protectedContent = item.protectedContent;
            job.destChatId = destination.id;
            job.destTitle = destination.title;
            job.method = QJob.METHOD_DOWNLOAD;
            job.sendAs = Prefs.sendAs(this);
            job.uploadAfter = true;
            job.deleteLocal = Prefs.autoDeleteLocal(this);
            job.stage = QJob.QUEUED;
            batch.add(job);
        }
        int count = batch.size();
        captured.clear();
        Prefs.saveDestination(this, destination.id, destination.title);
        Jobs.get(this).addBatch(batch);
        QueueService.run(this);

        setPointerState(SmartPointerView.STATE_TRANSFERRING);
        String msg = "Pasting " + (count == 1 ? "file" : count + " files")
                + " into " + shortStr(destination.title, 26)
                + " — trying instant zero-data copy first…";
        startForegroundSafely(msg);
        announceStep("STEP 2 • TRANSFER STARTED", msg, 0xFF38BDF8, 5200L);
        refreshMenuContents();
    }

    // ----------------------------------------- floating step banner UI ----- //

    private FrameLayout buildBannerView() {
        FrameLayout outer = new FrameLayout(this);
        outer.setPadding(Ui.dp(this, 14), 0, Ui.dp(this, 14), 0);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable bg = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xF210172A, 0xF21E1B4B, 0xF20F172A});
        bg.setCornerRadius(Ui.dp(this, 18));
        bg.setStroke(Ui.dp(this, 1), 0x6638BDF8);
        card.setBackground(bg);
        card.setPadding(Ui.dp(this, 14), Ui.dp(this, 10), Ui.dp(this, 14), Ui.dp(this, 11));

        bannerBadge = new TextView(this);
        bannerBadge.setTextSize(10.5f);
        bannerBadge.setTypeface(Typeface.DEFAULT_BOLD);
        bannerBadge.setLetterSpacing(0.08f);
        bannerBadge.setTextColor(0xFF38BDF8);
        card.addView(bannerBadge);

        bannerText = new TextView(this);
        bannerText.setTextSize(13f);
        bannerText.setTextColor(Color.WHITE);
        bannerText.setLineSpacing(0f, 1.15f);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tp.topMargin = Ui.dp(this, 3);
        bannerText.setLayoutParams(tp);
        card.addView(bannerText);

        card.setOnClickListener(v -> hideBannerTask.run());
        outer.addView(card, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return outer;
    }

    private void announceStep(String badge, String message, int accentColor, long durationMs) {
        handler.post(() -> {
            if (bannerRoot == null || bannerBadge == null || bannerText == null) {
                return;
            }
            handler.removeCallbacks(hideBannerTask);
            bannerBadge.setText(badge);
            bannerBadge.setTextColor(accentColor);
            bannerText.setText(message);
            if (bannerRoot.getVisibility() != View.VISIBLE) {
                bannerRoot.setAlpha(0f);
                bannerRoot.setVisibility(View.VISIBLE);
            }
            bannerRoot.animate().alpha(1f).setDuration(180L).start();
            handler.postDelayed(hideBannerTask, durationMs);
        });
    }

    // -------------------------------------- colorful interactive menu ------ //

    public void toggleMenuPanel() {
        if (menuScrim != null) {
            closeMenuPanel();
        } else {
            showMenuPanel();
        }
    }

    public void showMenuPanel() {
        if (wm == null || menuScrim != null) {
            refreshMenuContents();
            return;
        }
        refreshWritableDestinations();
        menuScrim = new FrameLayout(this);
        menuScrim.setBackgroundColor(0x99050811);
        menuScrim.setPadding(Ui.dp(this, 16), Ui.dp(this, 44),
                Ui.dp(this, 16), Ui.dp(this, 32));
        menuScrim.setOnClickListener(v -> closeMenuPanel());

        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        FrameLayout.LayoutParams scrollLp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER);

        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setClickable(true);
        GradientDrawable panelBg = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0xFA111827, 0xFA0F172A});
        panelBg.setCornerRadius(Ui.dp(this, 24));
        panelBg.setStroke(Ui.dp(this, 1), 0x55818CF8);
        panel.setBackground(panelBg);
        panel.setPadding(Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16));

        // Colorful Aurora Hero Header inside Menu
        menuAurora = new AuroraDrawable(getResources().getDisplayMetrics().density);
        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setBackground(menuAurora);
        hero.setPadding(Ui.dp(this, 16), Ui.dp(this, 14), Ui.dp(this, 14), Ui.dp(this, 14));

        LinearLayout topRow = new LinearLayout(this);
        topRow.setOrientation(LinearLayout.HORIZONTAL);
        topRow.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = new TextView(this);
        title.setText(R.string.smart_setup_title);
        title.setTextColor(Color.WHITE);
        title.setTextSize(19f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        topRow.addView(title, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button closeBtn = pillButton(getString(R.string.common_close), 0x33FFFFFF, Color.WHITE);
        closeBtn.setOnClickListener(v -> closeMenuPanel());
        topRow.addView(closeBtn);
        hero.addView(topRow);

        menuStepText = new TextView(this);
        menuStepText.setTextColor(0xFFE0E7FF);
        menuStepText.setTextSize(13f);
        menuStepText.setLineSpacing(0f, 1.15f);
        LinearLayout.LayoutParams stLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        stLp.topMargin = Ui.dp(this, 8);
        menuStepText.setLayoutParams(stLp);
        hero.addView(menuStepText);

        LinearLayout heroActions = new LinearLayout(this);
        heroActions.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams haLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        haLp.topMargin = Ui.dp(this, 12);
        heroActions.setLayoutParams(haLp);

        Button howBtn = pillButton("Step-by-step guide", 0x3838BDF8, 0xFFBAE6FD);
        howBtn.setOnClickListener(v -> {
            guideExpanded = !guideExpanded;
            menuGuideBox.setVisibility(guideExpanded ? View.VISIBLE : View.GONE);
        });
        heroActions.addView(howBtn);

        View spacer = new View(this);
        heroActions.addView(spacer, new LinearLayout.LayoutParams(Ui.dp(this, 8), 1));

        togglePointerBtn = pillButton(pointerVisible ? "Hide circle" : "Show circle",
                0x38818CF8, 0xFFE0E7FF);
        togglePointerBtn.setOnClickListener(v -> togglePointerVisibility());
        heroActions.addView(togglePointerBtn);

        hero.addView(heroActions);
        panel.addView(hero);
        menuAurora.start();

        // Expandable step-by-step walkthrough
        menuGuideBox = new LinearLayout(this);
        menuGuideBox.setOrientation(LinearLayout.VERTICAL);
        menuGuideBox.setVisibility(guideExpanded ? View.VISIBLE : View.GONE);
        GradientDrawable guideBg = roundedCard(0xFF172033, 0x4438BDF8, 16);
        menuGuideBox.setBackground(guideBg);
        menuGuideBox.setPadding(Ui.dp(this, 14), Ui.dp(this, 12),
                Ui.dp(this, 14), Ui.dp(this, 12));
        LinearLayout.LayoutParams gbLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        gbLp.topMargin = Ui.dp(this, 12);
        menuGuideBox.setLayoutParams(gbLp);
        TextView guideText = new TextView(this);
        guideText.setText(R.string.smart_guide_steps);
        guideText.setTextColor(0xFFCBD5E1);
        guideText.setTextSize(12.5f);
        guideText.setLineSpacing(0f, 1.18f);
        menuGuideBox.addView(guideText);
        panel.addView(menuGuideBox);

        // Accessibility permission prompt right inside menu if not yet granted
        if (!SmartAccessibilityService.isEnabled(this)) {
            LinearLayout permCard = new LinearLayout(this);
            permCard.setOrientation(LinearLayout.VERTICAL);
            permCard.setBackground(roundedCard(0xFF2B1F12, 0x88F59E0B, 16));
            permCard.setPadding(Ui.dp(this, 14), Ui.dp(this, 12),
                    Ui.dp(this, 14), Ui.dp(this, 12));
            LinearLayout.LayoutParams pLp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            pLp.topMargin = Ui.dp(this, 12);
            permCard.setLayoutParams(pLp);

            TextView permLabel = new TextView(this);
            permLabel.setText(R.string.smart_perm_access_hint);
            permLabel.setTextColor(0xFFFDE68A);
            permLabel.setTextSize(12.5f);
            permCard.addView(permLabel);

            Button enableBtn = pillButton(getString(R.string.smart_perm_grant),
                    0xFFF59E0B, 0xFF0F172A);
            LinearLayout.LayoutParams ebLp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            ebLp.topMargin = Ui.dp(this, 8);
            enableBtn.setLayoutParams(ebLp);
            enableBtn.setOnClickListener(v -> {
                closeMenuPanel();
                Intent s = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
                s.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(s);
            });
            permCard.addView(enableBtn);
            panel.addView(permCard);
        }

        // Dynamic sections
        menuLiveTransferBox = new LinearLayout(this);
        menuLiveTransferBox.setOrientation(LinearLayout.VERTICAL);
        panel.addView(menuLiveTransferBox);

        menuCapturedList = new LinearLayout(this);
        menuCapturedList.setOrientation(LinearLayout.VERTICAL);
        panel.addView(menuCapturedList);

        menuDestList = new LinearLayout(this);
        menuDestList.setOrientation(LinearLayout.VERTICAL);
        panel.addView(menuDestList);

        // Bottom control bar: Open Vmore + Turn Off Smart Feature
        LinearLayout bottomRow = new LinearLayout(this);
        bottomRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams brLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        brLp.topMargin = Ui.dp(this, 14);
        bottomRow.setLayoutParams(brLp);

        Button openAppBtn = pillButton("Open Vmore", 0xFF1E293B, 0xFFE2E8F0);
        openAppBtn.setOnClickListener(v -> {
            closeMenuPanel();
            Intent open = new Intent(this, MainActivity.class);
            open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(open);
        });
        bottomRow.addView(openAppBtn, new LinearLayout.LayoutParams(
                0, Ui.dp(this, 42), 1f));

        View gap = new View(this);
        bottomRow.addView(gap, new LinearLayout.LayoutParams(Ui.dp(this, 10), 1));

        Button turnOffBtn = pillButton(getString(R.string.smart_stop), 0xFFDC2626, Color.WHITE);
        turnOffBtn.setOnClickListener(v -> shutdownCleanly());
        bottomRow.addView(turnOffBtn, new LinearLayout.LayoutParams(
                0, Ui.dp(this, 42), 1f));

        panel.addView(bottomRow);
        scroll.addView(panel);
        menuScrim.addView(scroll, scrollLp);

        WindowManager.LayoutParams mp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                overlayWindowType(),
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        mp.gravity = Gravity.CENTER;
        safeAddView(menuScrim, mp);
        refreshMenuContents();
    }

    public void closeMenuPanel() {
        if (menuAurora != null) {
            menuAurora.stop();
            menuAurora = null;
        }
        if (menuScrim != null) {
            safeRemoveView(menuScrim);
            menuScrim = null;
        }
        menuStepText = null;
        menuGuideBox = null;
        menuCapturedList = null;
        menuLiveTransferBox = null;
        menuDestList = null;
        togglePointerBtn = null;
    }

    private void togglePointerVisibility() {
        pointerVisible = !pointerVisible;
        if (whiteCircle != null) {
            whiteCircle.setVisibility(pointerVisible ? View.VISIBLE : View.GONE);
        }
        if (togglePointerBtn != null) {
            togglePointerBtn.setText(pointerVisible ? "Hide circle" : "Show circle");
        }
    }

    private void refreshWritableDestinations() {
        if (!Tg.get(this).isReady()) {
            return;
        }
        Tg.get(this).loadWritableChats(40, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> value) {
                writableChats.clear();
                if (value != null) {
                    writableChats.addAll(value);
                }
                refreshMenuContents();
            }

            @Override
            public void fail(String message) {
            }
        });
    }

    private void refreshMenuContents() {
        if (menuScrim == null) {
            return;
        }
        if (menuStepText != null) {
            menuStepText.setText(currentStepSummary());
        }

        // Captured files basket
        menuCapturedList.removeAllViews();
        menuCapturedList.addView(sectionHeading(
                captured.isEmpty() ? "CAPTURED FILES (NONE YET)"
                        : "CAPTURED FILES (" + captured.size() + " READY)"));
        if (captured.isEmpty()) {
            TextView empty = smallNote(
                    "Drag the white circle onto any Telegram video, photo, audio or file and double-tap it.");
            menuCapturedList.addView(empty);
        } else {
            for (Tg.Media item : captured) {
                TextView row = new TextView(this);
                String sz = item.size > 0 ? " • " + Format.size(item.size) : "";
                row.setText(item.name + sz + " (" + item.chatTitle + ")");
                row.setTextColor(0xFFECFDF5);
                row.setTextSize(13f);
                row.setBackground(roundedCard(0xFF064E3B, 0x6610B981, 12));
                row.setPadding(Ui.dp(this, 12), Ui.dp(this, 9), Ui.dp(this, 12), Ui.dp(this, 9));
                LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                lp.bottomMargin = Ui.dp(this, 6);
                row.setLayoutParams(lp);
                menuCapturedList.addView(row);
            }
            Button clearBasket = pillButton("Clear captured files", 0xFF334155, Color.WHITE);
            clearBasket.setOnClickListener(v -> {
                captured.clear();
                restoreIdleOrCapturedState();
                refreshMenuContents();
            });
            menuCapturedList.addView(clearBasket);
        }

        // Writable destinations with real circular profile photos
        menuDestList.removeAllViews();
        menuDestList.addView(sectionHeading(
                captured.isEmpty()
                        ? "WRITABLE DESTINATION CHATS (PROFILE PHOTOS)"
                        : "TAP A CHANNEL OR CHAT BELOW TO PASTE NOW"));
        if (writableChats.isEmpty()) {
            menuDestList.addView(smallNote(
                    "Sign in and open chats where you have permission to post messages."));
        } else {
            int max = Math.min(8, writableChats.size());
            for (int i = 0; i < max; i++) {
                final Tg.Chat chat = writableChats.get(i);
                LinearLayout row = buildOverlayChatRow(chat);
                row.setOnClickListener(v -> {
                    if (!captured.isEmpty()) {
                        closeMenuPanel();
                        pasteCapturedIntoChat(chat);
                    } else {
                        Prefs.saveDestination(SmartOverlayService.this, chat.id, chat.title);
                        announceStep("DEFAULT DESTINATION SET",
                                "Default destination set to " + chat.title, 0xFF10B981, 3000L);
                        refreshMenuContents();
                    }
                });
                menuDestList.addView(row);
            }
        }
        syncLiveTransferUi();
    }

    private LinearLayout buildOverlayChatRow(Tg.Chat chat) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        boolean isDefault = chat.id == Prefs.destChatId(this);
        row.setBackground(roundedCard(isDefault ? 0xFF1E293B : 0xFF151E2E,
                isDefault ? 0x8838BDF8 : 0x3394A3B8, 14));
        row.setPadding(Ui.dp(this, 10), Ui.dp(this, 8), Ui.dp(this, 12), Ui.dp(this, 8));
        LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        rlp.bottomMargin = Ui.dp(this, 6);
        row.setLayoutParams(rlp);

        ImageView avatar = new ImageView(this);
        int px = Ui.dp(this, 36);
        row.addView(avatar, new LinearLayout.LayoutParams(px, px));
        Ui.paintChatAvatar(this, avatar, chat, 36);

        LinearLayout textCol = new LinearLayout(this);
        textCol.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        tlp.leftMargin = Ui.dp(this, 10);
        textCol.setLayoutParams(tlp);

        TextView name = new TextView(this);
        name.setText(chat.title);
        name.setTextColor(Color.WHITE);
        name.setTextSize(13.5f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setSingleLine(true);
        name.setEllipsize(TextUtils.TruncateAt.END);
        textCol.addView(name);

        TextView sub = new TextView(this);
        sub.setText(chat.type + (isDefault ? " • active destination" : " • can send"));
        sub.setTextColor(0xFF94A3B8);
        sub.setTextSize(11.5f);
        textCol.addView(sub);

        row.addView(textCol);
        return row;
    }

    private void syncLiveTransferUi() {
        QJob active = Jobs.get(this).active();
        boolean running = QueueService.Live.RUNNING.get() || active != null;
        if (running) {
            long done = QueueService.Live.DONE.get();
            long total = QueueService.Live.TOTAL.get();
            int pct = Format.percent(done, total);
            setPointerVisual(SmartPointerView.STATE_TRANSFERRING,
                    Math.max(captured.size(), Jobs.get(this).size()), pct);
            String stage = QueueService.Live.STAGE;
            if (!stage.isEmpty() && !stage.equals(lastAnnouncedStage)) {
                lastAnnouncedStage = stage;
                announceStep("LIVE TRANSFER • " + Ui.stageLabel(stage).toUpperCase(),
                        shortStr(QueueService.Live.NAME, 36), 0xFF38BDF8, 2800L);
            }
        } else {
            if (!lastAnnouncedStage.isEmpty()) {
                lastAnnouncedStage = "";
                announceStep("TRANSFER COMPLETE",
                        getString(R.string.smart_step_done), 0xFF10B981, 4000L);
                startForegroundSafely(currentStepSummary());
            }
            if (!resolvingTap) {
                restoreIdleOrCapturedState();
            }
        }

        if (menuLiveTransferBox == null) {
            return;
        }
        menuLiveTransferBox.removeAllViews();
        List<QJob> allJobs = Jobs.get(this).all();
        if (allJobs.isEmpty() && !running) {
            return;
        }
        menuLiveTransferBox.addView(sectionHeading("ACTIVE TRANSFERS & CANCEL CONTROLS"));
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(roundedCard(0xFF172554, 0x8838BDF8, 16));
        card.setPadding(Ui.dp(this, 12), Ui.dp(this, 10), Ui.dp(this, 12), Ui.dp(this, 10));

        final QJob primary = active != null ? active
                : (!allJobs.isEmpty() ? allJobs.get(0) : null);
        String jobTitle = !QueueService.Live.NAME.isEmpty() ? QueueService.Live.NAME
                : (primary != null ? primary.title() : "Transfer queue");
        String stageText = Ui.stageLabel(QueueService.Live.STAGE.isEmpty() && primary != null
                ? primary.stage : QueueService.Live.STAGE);
        long done = QueueService.Live.DONE.get();
        long total = QueueService.Live.TOTAL.get();
        int pct = Format.percent(done, total);

        TextView label = new TextView(this);
        label.setText(jobTitle + " • " + stageText
                + (total > 0 ? " (" + pct + "%)" : ""));
        label.setTextColor(Color.WHITE);
        label.setTextSize(13f);
        label.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(label);

        ProgressBar bar = new ProgressBar(this, null,
                android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setIndeterminate(total <= 0);
        bar.setProgress(pct);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 8));
        blp.topMargin = Ui.dp(this, 8);
        blp.bottomMargin = Ui.dp(this, 10);
        bar.setLayoutParams(blp);
        card.addView(bar);

        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.HORIZONTAL);
        boolean paused = Jobs.get(this).pausedAll();
        Button pauseBtn = pillButton(paused ? "Resume" : "Pause", 0xFF2563EB, Color.WHITE);
        pauseBtn.setOnClickListener(v -> {
            if (Jobs.get(this).pausedAll()) {
                QueueService.resumeAll(this);
            } else {
                QueueService.pauseAll(this);
            }
            syncLiveTransferUi();
        });
        controls.addView(pauseBtn);

        View cgap = new View(this);
        controls.addView(cgap, new LinearLayout.LayoutParams(Ui.dp(this, 8), 1));

        Button cancelCurrent = pillButton("Cancel & delete file", 0xFFDC2626, Color.WHITE);
        cancelCurrent.setOnClickListener(v -> {
            if (primary != null) {
                QueueService.removeJob(this, primary.id);
            } else {
                QueueService.stopJob(this, null);
            }
            announceStep("TRANSFER CANCELLED",
                    "Download stopped immediately and partial cache file deleted.",
                    0xFFEF4444, 3600L);
            refreshMenuContents();
        });
        controls.addView(cancelCurrent);

        card.addView(controls);
        menuLiveTransferBox.addView(card);
    }

    @Override
    public void onJobsChanged() {
        handler.post(this::syncLiveTransferUi);
    }

    // --------------------------------------------------------- small utils //

    private String currentStepSummary() {
        if (!captured.isEmpty()) {
            return captured.size() + " file(s) ready — open any writable chat and double-tap to paste.";
        }
        return getString(R.string.smart_step_ready);
    }

    private void setPointerState(int state) {
        setPointerVisual(state, captured.size(), 0);
    }

    private void restoreIdleOrCapturedState() {
        int state = captured.isEmpty()
                ? SmartPointerView.STATE_IDLE : SmartPointerView.STATE_CAPTURED;
        setPointerVisual(state, captured.size(), 0);
    }

    private void setPointerVisual(int state, int count, int pct) {
        if (whiteCircle != null) {
            whiteCircle.setVisualState(state, count, pct);
        }
        if (menuOrb != null) {
            menuOrb.setVisualState(state, count, pct);
        }
    }

    private TextView sectionHeading(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(0xFF93C5FD);
        view.setTextSize(11f);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setLetterSpacing(0.06f);
        view.setPadding(0, Ui.dp(this, 14), 0, Ui.dp(this, 6));
        return view;
    }

    private TextView smallNote(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(0xFF94A3B8);
        view.setTextSize(12.5f);
        return view;
    }

    private Button pillButton(String label, int bgColor, int fgColor) {
        Button btn = new Button(this);
        btn.setText(label);
        btn.setAllCaps(false);
        btn.setTextSize(12.5f);
        btn.setTypeface(Typeface.DEFAULT_BOLD);
        btn.setTextColor(fgColor);
        btn.setStateListAnimator(null);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(bgColor);
        bg.setCornerRadius(Ui.dp(this, 999));
        btn.setBackground(bg);
        btn.setPadding(Ui.dp(this, 14), Ui.dp(this, 6), Ui.dp(this, 14), Ui.dp(this, 6));
        return btn;
    }

    private GradientDrawable roundedCard(int fill, int stroke, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(Ui.dp(this, radiusDp));
        d.setStroke(Ui.dp(this, 1), stroke);
        return d;
    }

    private static boolean hasMediaHints(List<String> lines) {
        if (lines == null || lines.isEmpty()) {
            return true;
        }
        if (SmartMatcher.extractSizeBytes(lines) > 0 || SmartMatcher.extractDurationSec(lines) > 0) {
            return true;
        }
        for (String line : lines) {
            String l = line.toLowerCase();
            if (l.contains("photo") || l.contains("video") || l.contains("gif")
                    || l.contains("audio") || l.contains("voice") || l.contains("file")
                    || l.contains(".mp4") || l.contains(".mkv") || l.contains(".pdf")
                    || l.contains(".zip") || l.contains(".apk") || l.contains(".mp3")) {
                return true;
            }
        }
        return !lines.isEmpty();
    }

    private static String firstTitleCandidate(List<String> lines) {
        if (lines == null) {
            return "";
        }
        for (String line : lines) {
            for (String piece : line.split("\\n")) {
                String c = piece.trim();
                if (c.length() >= 2 && !SmartMatcher.isSubtitleNoise(c)
                        && SmartMatcher.extractClockTimes(c).isEmpty()) {
                    return c;
                }
            }
        }
        return "";
    }

    private static String shortStr(String s, int max) {
        if (s == null) {
            return "";
        }
        String one = Format.oneLine(s);
        return one.length() <= max ? one : one.substring(0, max) + "…";
    }

    private static int clamp(int val, int min, int max) {
        return Math.max(min, Math.min(Math.max(min, max), val));
    }

    private void safeAddView(View view, WindowManager.LayoutParams params) {
        try {
            if (wm != null && view.getParent() == null) {
                wm.addView(view, params);
            }
        } catch (Throwable ignored) {
        }
    }

    private void safeUpdateView(View view, WindowManager.LayoutParams params) {
        try {
            if (wm != null && view.getParent() != null) {
                wm.updateViewLayout(view, params);
            }
        } catch (Throwable ignored) {
        }
    }

    private void safeRemoveView(View view) {
        try {
            if (wm != null && view != null && view.getParent() != null) {
                wm.removeView(view);
            }
        } catch (Throwable ignored) {
        }
    }

    private void removeAllWindows() {
        closeMenuPanel();
        safeRemoveView(whiteCircle);
        whiteCircle = null;
        safeRemoveView(menuOrb);
        menuOrb = null;
        safeRemoveView(bannerRoot);
        bannerRoot = null;
    }
}
