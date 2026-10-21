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
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Compact glitch-free Smart Feature overlay service:
// - Floating colorful Vmore button opens a compact ~1/4-screen floating mini popup
//   right beside the button (never a full-screen blocking dialog)
// - Crisp white pointer circle displays ONLY captured file count (0 = clean white dot)
// - Live progress & cancel controls update strictly in-place with zero view rebuilds
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

    // Compact ~1/4-screen floating mini popup card + static child references
    private FrameLayout menuPopup;
    private WindowManager.LayoutParams menuParams;
    private TextView menuStepText;
    private TextView menuGuideText;
    private LinearLayout menuPermBox;
    private LinearLayout menuLiveCard;
    private TextView menuLiveLabel;
    private ProgressBar menuLiveBar;
    private Button menuCancelBtn;
    private Button menuClearBtn;
    private TextView menuDestActiveLabel;
    private LinearLayout menuAvatarStrip;
    private Button togglePointerBtn;

    private boolean pointerVisible = true;
    private boolean guideExpanded = false;
    private boolean resolvingTap = false;
    private String lastAnnouncedStage = "";
    private String lastStepRendered = "";
    private String lastLiveLabelRendered = "";

    private final Runnable hideBannerTask = () -> {
        if (bannerRoot != null) {
            bannerRoot.animate().alpha(0f).setDuration(160L)
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
            handler.postDelayed(this, 650L);
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
        announceStep("SMART READY", "Double-tap any file with white dot", 0xFF38BDF8, 3200L);
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

        // 1. Compact non-touchable top pill toast (never blocks screen touches)
        if (bannerRoot == null) {
            bannerRoot = buildBannerView();
            WindowManager.LayoutParams bp = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.WRAP_CONTENT,
                    WindowManager.LayoutParams.WRAP_CONTENT,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                            | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                    PixelFormat.TRANSLUCENT);
            bp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
            bp.y = Ui.dp(this, 42);
            bannerRoot.setVisibility(View.GONE);
            safeAddView(bannerRoot, bp);
        }

        // 2. Small crisp white circle pointer
        if (whiteCircle == null) {
            final int size = Ui.dp(this, 34);
            whiteCircle = new SmartPointerView(this, SmartPointerView.MODE_WHITE_CIRCLE);
            whiteParams = new WindowManager.LayoutParams(
                    size, size,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                    PixelFormat.TRANSLUCENT);
            whiteParams.gravity = Gravity.TOP | Gravity.START;
            whiteParams.x = (dm.widthPixels - size) / 2;
            whiteParams.y = (int) (dm.heightPixels * 0.44f);
            whiteCircle.setInteractionListener(new SmartPointerView.InteractionListener() {
                @Override
                public void onMoveBy(int dx, int dy) {
                    int nx = clamp(whiteParams.x + dx, 0, dm.widthPixels - size);
                    int ny = clamp(whiteParams.y + dy, Ui.dp(SmartOverlayService.this, 24),
                            dm.heightPixels - size);
                    if (nx != whiteParams.x || ny != whiteParams.y) {
                        whiteParams.x = nx;
                        whiteParams.y = ny;
                        safeUpdateView(whiteCircle, whiteParams);
                    }
                }

                @Override
                public void onDragFinished() {
                }

                @Override
                public void onSingleTap() {
                    if (captured.isEmpty()) {
                        announceStep("STEP 1",
                                "Place white dot on any file and double-tap",
                                0xFF38BDF8, 2400L);
                    } else {
                        announceStep(captured.size() + " IN DOT",
                                "Open target channel and double-tap to send",
                                0xFF10B981, 2600L);
                    }
                }

                @Override
                public void onDoubleTap(int centerRawX, int centerRawY) {
                    handleWhiteCircleDoubleTap(centerRawX, centerRawY);
                }
            });
            safeAddView(whiteCircle, whiteParams);
        }

        // 3. Compact floating colorful Vmore menu orb
        if (menuOrb == null) {
            final int orbSize = Ui.dp(this, 42);
            menuOrb = new SmartPointerView(this, SmartPointerView.MODE_MENU_ORB);
            orbParams = new WindowManager.LayoutParams(
                    orbSize, orbSize,
                    overlayWindowType(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                    PixelFormat.TRANSLUCENT);
            orbParams.gravity = Gravity.TOP | Gravity.START;
            orbParams.x = Ui.dp(this, 8);
            orbParams.y = (int) (dm.heightPixels * 0.28f);
            menuOrb.setInteractionListener(new SmartPointerView.InteractionListener() {
                @Override
                public void onMoveBy(int dx, int dy) {
                    int nx = clamp(orbParams.x + dx, 0, dm.widthPixels - orbSize);
                    int ny = clamp(orbParams.y + dy, Ui.dp(SmartOverlayService.this, 28),
                            dm.heightPixels - orbSize);
                    if (nx != orbParams.x || ny != orbParams.y) {
                        orbParams.x = nx;
                        orbParams.y = ny;
                        safeUpdateView(menuOrb, orbParams);
                        repositionMenuNearOrb();
                    }
                }

                @Override
                public void onDragFinished() {
                    orbParams.x = orbParams.x + orbSize / 2 < dm.widthPixels / 2
                            ? Ui.dp(SmartOverlayService.this, 8)
                            : dm.widthPixels - orbSize - Ui.dp(SmartOverlayService.this, 8);
                    safeUpdateView(menuOrb, orbParams);
                    repositionMenuNearOrb();
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
            announceStep("ALLOW READER",
                    "Tap Allow in the mini menu once",
                    0xFFF59E0B, 3600L);
            showMenuPanel();
            return;
        }
        if (!Tg.get(this).isReady()) {
            Tg.get(this).start(null);
            setPointerState(SmartPointerView.STATE_SCANNING);
            announceStep("CONNECTING",
                    "Waking session — double-tap again in 1s",
                    0xFF38BDF8, 2800L);
            return;
        }

        resolvingTap = true;
        setPointerState(SmartPointerView.STATE_SCANNING);

        final SmartAccessibilityService.ScreenTarget screen =
                SmartAccessibilityService.inspectAt(rawX, rawY);
        if (screen == null) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            announceStep("TRY AGAIN",
                    "Place white dot right on a Telegram post or channel",
                    0xFFF59E0B, 2800L);
            return;
        }

        if (screen.looksLikeChatList && !screen.targetLines.isEmpty()) {
            resolveChatRowTap(screen);
            return;
        }

        String chatQuery = !screen.headerTitle.isEmpty()
                ? screen.headerTitle
                : firstTitleCandidate(screen.targetLines);
        if (chatQuery.isEmpty()) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            announceStep("MOVE DOT",
                    "Keep channel title visible and tap on the file",
                    0xFFF59E0B, 3000L);
            return;
        }

        Tg.get(this).findChatsMatching(chatQuery, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> matches) {
                if (matches == null || matches.isEmpty()) {
                    resolvingTap = false;
                    restoreIdleOrCapturedState();
                    announceStep("NOT FOUND",
                            "Open \"" + shortStr(chatQuery, 20) + "\" in your signed-in account",
                            0xFFF59E0B, 3200L);
                    return;
                }
                final Tg.Chat matchedChat = matches.get(0);
                boolean sameAsLastSource = !captured.isEmpty()
                        && captured.get(captured.size() - 1).chatId == matchedChat.id;
                boolean looksLikeMediaBubble = hasMediaHints(screen.targetLines);

                if (!captured.isEmpty() && (!sameAsLastSource || !looksLikeMediaBubble)) {
                    resolvingTap = false;
                    pasteCapturedIntoChat(matchedChat);
                    return;
                }

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
                                announceStep("NO FILE", shortStr(message, 34), 0xFFF59E0B, 3000L);
                            }
                        });
            }

            @Override
            public void fail(String message) {
                resolvingTap = false;
                restoreIdleOrCapturedState();
                announceStep("BUSY", shortStr(message, 32), 0xFFF59E0B, 2800L);
            }
        });
    }

    private void resolveChatRowTap(final SmartAccessibilityService.ScreenTarget screen) {
        String rowTitle = firstTitleCandidate(screen.targetLines);
        if (rowTitle.isEmpty()) {
            resolvingTap = false;
            restoreIdleOrCapturedState();
            return;
        }
        Tg.get(this).findChatsMatching(rowTitle, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> matches) {
                resolvingTap = false;
                if (matches == null || matches.isEmpty()) {
                    restoreIdleOrCapturedState();
                    announceStep("OPEN CHAT",
                            "Open the channel first, then double-tap",
                            0xFFF59E0B, 2800L);
                    return;
                }
                Tg.Chat chat = matches.get(0);
                if (!captured.isEmpty()) {
                    pasteCapturedIntoChat(chat);
                } else {
                    restoreIdleOrCapturedState();
                    announceStep("OPEN CHAT",
                            "Open \"" + shortStr(chat.title, 20) + "\" to pick a file",
                            0xFF38BDF8, 2800L);
                }
            }

            @Override
            public void fail(String message) {
                resolvingTap = false;
                restoreIdleOrCapturedState();
            }
        });
    }

    private void onMediaCaptured(Tg.Media media, Tg.Chat sourceChat) {
        for (Tg.Media existing : captured) {
            if (existing.chatId == media.chatId && existing.messageId == media.messageId) {
                restoreIdleOrCapturedState();
                announceStep("READY (" + captured.size() + ")",
                        "Open target channel and double-tap to paste",
                        0xFF10B981, 2800L);
                return;
            }
        }
        if (media.chatTitle == null || media.chatTitle.isEmpty()) {
            media.chatTitle = sourceChat.title;
        }
        captured.add(media);
        restoreIdleOrCapturedState();
        String msg = shortStr(media.name, 22) + " -> open channel & double-tap";
        startForegroundSafely(msg);
        announceStep("ADDED (" + captured.size() + ")", msg, 0xFF10B981, 3200L);
        syncLiveTransferUi();
    }

    private void pasteCapturedIntoChat(Tg.Chat destination) {
        if (destination == null) {
            return;
        }
        if (!destination.canSend) {
            setPointerState(SmartPointerView.STATE_ALERT);
            handler.postDelayed(this::restoreIdleOrCapturedState, 1100L);
            announceStep("NO POST ACCESS",
                    "Cannot send to \"" + shortStr(destination.title, 22) + "\"",
                    0xFFEF4444, 3400L);
            return;
        }
        if (captured.isEmpty()) {
            announceStep("PICK FILE FIRST",
                    "Double-tap any file first", 0xFF38BDF8, 2600L);
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
            job.remoteFileId = item.remoteFileId;
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
        captured.clear();
        Prefs.saveDestination(this, destination.id, destination.title);
        Jobs.get(this).addBatch(batch);
        QueueService.run(this);

        // White dot badge immediately resets to 0 (clean white circle, no stale queue count)
        setPointerVisual(SmartPointerView.STATE_TRANSFERRING, 0, 2);
        String msg = "Sending to " + shortStr(destination.title, 20);
        startForegroundSafely(msg);
        announceStep("SENDING", msg, 0xFF38BDF8, 3000L);
        renderDestinationAvatars();
        syncLiveTransferUi();
    }

    // ----------------------------------------- compact floating pill toast - //

    private FrameLayout buildBannerView() {
        FrameLayout outer = new FrameLayout(this);

        LinearLayout pill = new LinearLayout(this);
        pill.setOrientation(LinearLayout.HORIZONTAL);
        pill.setGravity(Gravity.CENTER_VERTICAL);
        GradientDrawable bg = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{0xEE0F172A, 0xEE1E1B4B});
        bg.setCornerRadius(Ui.dp(this, 999));
        bg.setStroke(Ui.dp(this, 1), 0x6638BDF8);
        pill.setBackground(bg);
        pill.setPadding(Ui.dp(this, 11), Ui.dp(this, 6), Ui.dp(this, 12), Ui.dp(this, 6));

        bannerBadge = new TextView(this);
        bannerBadge.setTextSize(10f);
        bannerBadge.setTypeface(Typeface.DEFAULT_BOLD);
        bannerBadge.setTextColor(0xFF38BDF8);
        pill.addView(bannerBadge);

        bannerText = new TextView(this);
        bannerText.setTextSize(11.5f);
        bannerText.setTextColor(Color.WHITE);
        bannerText.setSingleLine(true);
        bannerText.setEllipsize(TextUtils.TruncateAt.END);
        bannerText.setMaxWidth(Ui.dp(this, 230));
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tp.leftMargin = Ui.dp(this, 7);
        bannerText.setLayoutParams(tp);
        pill.addView(bannerText);

        outer.addView(pill, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
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
                bannerRoot.animate().alpha(1f).setDuration(140L).start();
            } else {
                bannerRoot.setAlpha(1f);
            }
            handler.postDelayed(hideBannerTask, durationMs);
        });
    }

    // ---------------------- compact ~1/4-screen floating mini popup -------- //

    public void toggleMenuPanel() {
        if (menuPopup != null) {
            closeMenuPanel();
        } else {
            showMenuPanel();
        }
    }

    public void showMenuPanel() {
        if (wm == null) {
            return;
        }
        if (menuPopup != null) {
            renderDestinationAvatars();
            syncLiveTransferUi();
            return;
        }
        refreshWritableDestinations();
        DisplayMetrics dm = getResources().getDisplayMetrics();
        int popupWidth = Math.min((int) (dm.widthPixels * 0.50f), Ui.dp(this, 198));
        popupWidth = Math.max(popupWidth, Ui.dp(this, 176));

        menuPopup = new FrameLayout(this) {
            @Override
            public boolean onTouchEvent(MotionEvent event) {
                if (event != null && event.getActionMasked() == MotionEvent.ACTION_OUTSIDE) {
                    closeMenuPanel();
                    return true;
                }
                return super.onTouchEvent(event);
            }
        };

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable cardBg = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0xF7111827, 0xF70F172A});
        cardBg.setCornerRadius(Ui.dp(this, 16));
        cardBg.setStroke(Ui.dp(this, 1), 0x66818CF8);
        card.setBackground(cardBg);
        card.setPadding(Ui.dp(this, 9), Ui.dp(this, 8), Ui.dp(this, 9), Ui.dp(this, 9));

        // 1. Compact colorful gradient header with [?] and [×] close button
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        GradientDrawable headerBg = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{0xFF4F46E5, 0xFF0284C7, 0xFF0D9488});
        headerBg.setCornerRadius(Ui.dp(this, 11));
        header.setBackground(headerBg);
        header.setPadding(Ui.dp(this, 9), Ui.dp(this, 6), Ui.dp(this, 6), Ui.dp(this, 6));

        TextView title = new TextView(this);
        title.setText("Vmore Smart");
        title.setTextColor(Color.WHITE);
        title.setTextSize(12f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setSingleLine(true);
        header.addView(title, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button helpBtn = miniChip("?", 0x36FFFFFF, Color.WHITE);
        helpBtn.setOnClickListener(v -> {
            guideExpanded = !guideExpanded;
            if (menuGuideText != null) {
                menuGuideText.setVisibility(guideExpanded ? View.VISIBLE : View.GONE);
            }
        });
        header.addView(helpBtn);

        View hGap = new View(this);
        header.addView(hGap, new LinearLayout.LayoutParams(Ui.dp(this, 4), 1));

        Button closeBtn = miniChip("×", 0x44000000, Color.WHITE);
        closeBtn.setContentDescription(getString(R.string.common_close));
        closeBtn.setOnClickListener(v -> closeMenuPanel());
        header.addView(closeBtn);
        card.addView(header);

        // Collapsible short guide (hidden by default so popup stays compact 1/4 size)
        menuGuideText = new TextView(this);
        menuGuideText.setText("1. Drag white dot on file & double-tap\n2. Open channel & double-tap to send");
        menuGuideText.setTextColor(0xFFBAE6FD);
        menuGuideText.setTextSize(10.5f);
        menuGuideText.setLineSpacing(0f, 1.12f);
        menuGuideText.setPadding(Ui.dp(this, 4), Ui.dp(this, 6), Ui.dp(this, 4), Ui.dp(this, 2));
        menuGuideText.setVisibility(guideExpanded ? View.VISIBLE : View.GONE);
        card.addView(menuGuideText);

        // Accessibility permission row (only visible when reader permission is missing)
        menuPermBox = new LinearLayout(this);
        menuPermBox.setOrientation(LinearLayout.VERTICAL);
        menuPermBox.setPadding(0, Ui.dp(this, 6), 0, 0);
        Button enableBtn = miniActionButton("Allow Screen Reader", 0xFFF59E0B, 0xFF0F172A);
        enableBtn.setOnClickListener(v -> {
            closeMenuPanel();
            Intent s = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            s.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(s);
        });
        menuPermBox.addView(enableBtn, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 28)));
        menuPermBox.setVisibility(SmartAccessibilityService.isEnabled(this)
                ? View.GONE : View.VISIBLE);
        card.addView(menuPermBox);

        // 2. Status row + Clear chip when files are in dot
        LinearLayout statusRow = new LinearLayout(this);
        statusRow.setOrientation(LinearLayout.HORIZONTAL);
        statusRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams srlp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        srlp.topMargin = Ui.dp(this, 6);
        statusRow.setLayoutParams(srlp);

        menuStepText = new TextView(this);
        menuStepText.setTextColor(0xFFE2E8F0);
        menuStepText.setTextSize(10.5f);
        menuStepText.setSingleLine(true);
        menuStepText.setEllipsize(TextUtils.TruncateAt.END);
        statusRow.addView(menuStepText, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        menuClearBtn = miniChip("Clear", 0xFF334155, Color.WHITE);
        menuClearBtn.setVisibility(View.GONE);
        menuClearBtn.setOnClickListener(v -> {
            captured.clear();
            restoreIdleOrCapturedState();
            syncLiveTransferUi();
        });
        statusRow.addView(menuClearBtn);
        card.addView(statusRow);

        // 3. Pre-allocated in-place live progress + Cancel card (NEVER recreated on tick)
        menuLiveCard = new LinearLayout(this);
        menuLiveCard.setOrientation(LinearLayout.VERTICAL);
        menuLiveCard.setBackground(roundedCard(0xFF172554, 0x7738BDF8, 10));
        menuLiveCard.setPadding(Ui.dp(this, 8), Ui.dp(this, 6), Ui.dp(this, 8), Ui.dp(this, 6));
        LinearLayout.LayoutParams lclp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lclp.topMargin = Ui.dp(this, 6);
        menuLiveCard.setLayoutParams(lclp);

        menuLiveLabel = new TextView(this);
        menuLiveLabel.setTextColor(Color.WHITE);
        menuLiveLabel.setTextSize(10.5f);
        menuLiveLabel.setTypeface(Typeface.DEFAULT_BOLD);
        menuLiveLabel.setSingleLine(true);
        menuLiveLabel.setEllipsize(TextUtils.TruncateAt.END);
        menuLiveCard.addView(menuLiveLabel);

        menuLiveBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        menuLiveBar.setMax(100);
        LinearLayout.LayoutParams barLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 5));
        barLp.topMargin = Ui.dp(this, 5);
        barLp.bottomMargin = Ui.dp(this, 6);
        menuLiveBar.setLayoutParams(barLp);
        menuLiveCard.addView(menuLiveBar);

        menuCancelBtn = miniActionButton("Cancel & Delete", 0xFFDC2626, Color.WHITE);
        menuCancelBtn.setOnClickListener(v -> cancelCurrentTransfer());
        menuLiveCard.addView(menuCancelBtn, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 26)));
        menuLiveCard.setVisibility(View.GONE);
        card.addView(menuLiveCard);

        // 4. Compact horizontal channel avatar selector
        menuDestActiveLabel = new TextView(this);
        menuDestActiveLabel.setTextColor(0xFF93C5FD);
        menuDestActiveLabel.setTextSize(10f);
        menuDestActiveLabel.setTypeface(Typeface.DEFAULT_BOLD);
        menuDestActiveLabel.setSingleLine(true);
        menuDestActiveLabel.setEllipsize(TextUtils.TruncateAt.END);
        menuDestActiveLabel.setPadding(0, Ui.dp(this, 7), 0, Ui.dp(this, 4));
        card.addView(menuDestActiveLabel);

        HorizontalScrollView hScroll = new HorizontalScrollView(this);
        hScroll.setHorizontalScrollBarEnabled(false);
        menuAvatarStrip = new LinearLayout(this);
        menuAvatarStrip.setOrientation(LinearLayout.HORIZONTAL);
        menuAvatarStrip.setGravity(Gravity.CENTER_VERTICAL);
        hScroll.addView(menuAvatarStrip);
        card.addView(hScroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        // 5. Compact 2-button footer: Hide/Show Dot + Off
        LinearLayout bottomRow = new LinearLayout(this);
        bottomRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams brLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        brLp.topMargin = Ui.dp(this, 8);
        bottomRow.setLayoutParams(brLp);

        togglePointerBtn = miniActionButton(pointerVisible ? "Hide Dot" : "Show Dot",
                0xFF1E293B, 0xFFE2E8F0);
        togglePointerBtn.setOnClickListener(v -> togglePointerVisibility());
        bottomRow.addView(togglePointerBtn, new LinearLayout.LayoutParams(
                0, Ui.dp(this, 28), 1f));

        View bGap = new View(this);
        bottomRow.addView(bGap, new LinearLayout.LayoutParams(Ui.dp(this, 6), 1));

        Button offBtn = miniActionButton("Off", 0xFFDC2626, Color.WHITE);
        offBtn.setOnClickListener(v -> shutdownCleanly());
        bottomRow.addView(offBtn, new LinearLayout.LayoutParams(
                Ui.dp(this, 56), Ui.dp(this, 28)));

        card.addView(bottomRow);
        menuPopup.addView(card, new FrameLayout.LayoutParams(
                popupWidth, ViewGroup.LayoutParams.WRAP_CONTENT));

        menuParams = new WindowManager.LayoutParams(
                popupWidth,
                WindowManager.LayoutParams.WRAP_CONTENT,
                overlayWindowType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH
                        | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                PixelFormat.TRANSLUCENT);
        menuParams.gravity = Gravity.TOP | Gravity.START;
        computeMenuPosition(menuParams, popupWidth);

        lastStepRendered = "";
        lastLiveLabelRendered = "";
        safeAddView(menuPopup, menuParams);
        renderDestinationAvatars();
        syncLiveTransferUi();
    }

    private void computeMenuPosition(WindowManager.LayoutParams lp, int popupWidth) {
        DisplayMetrics dm = getResources().getDisplayMetrics();
        int orbSize = Ui.dp(this, 42);
        int margin = Ui.dp(this, 8);
        int ox = orbParams != null ? orbParams.x : margin;
        int oy = orbParams != null ? orbParams.y : (int) (dm.heightPixels * 0.28f);
        boolean onLeftHalf = ox + orbSize / 2 < dm.widthPixels / 2;
        int targetX = onLeftHalf
                ? ox + orbSize + Ui.dp(this, 6)
                : ox - popupWidth - Ui.dp(this, 6);
        lp.x = clamp(targetX, margin, dm.widthPixels - popupWidth - margin);
        lp.y = clamp(oy - Ui.dp(this, 8), Ui.dp(this, 36),
                Math.max(Ui.dp(this, 36), dm.heightPixels - Ui.dp(this, 250)));
    }

    private void repositionMenuNearOrb() {
        if (menuPopup != null && menuParams != null) {
            computeMenuPosition(menuParams, menuParams.width);
            safeUpdateView(menuPopup, menuParams);
        }
    }

    public void closeMenuPanel() {
        if (menuPopup != null) {
            safeRemoveView(menuPopup);
            menuPopup = null;
        }
        menuParams = null;
        menuStepText = null;
        menuGuideText = null;
        menuPermBox = null;
        menuLiveCard = null;
        menuLiveLabel = null;
        menuLiveBar = null;
        menuCancelBtn = null;
        menuClearBtn = null;
        menuDestActiveLabel = null;
        menuAvatarStrip = null;
        togglePointerBtn = null;
    }

    private void cancelCurrentTransfer() {
        String activeId = QueueService.Live.JOB_ID;
        if (activeId != null && !activeId.isEmpty()) {
            QueueService.removeJob(this, activeId);
        } else {
            QJob active = Jobs.get(this).active();
            if (active != null) {
                QueueService.removeJob(this, active.id);
            } else {
                QueueService.stopJob(this, null);
            }
        }
        announceStep("CANCELLED", "Stopped and cleared cache file", 0xFFEF4444, 2600L);
        syncLiveTransferUi();
    }

    private void togglePointerVisibility() {
        pointerVisible = !pointerVisible;
        if (whiteCircle != null) {
            whiteCircle.setVisibility(pointerVisible ? View.VISIBLE : View.GONE);
        }
        if (togglePointerBtn != null) {
            togglePointerBtn.setText(pointerVisible ? "Hide Dot" : "Show Dot");
        }
    }

    private void refreshWritableDestinations() {
        if (!Tg.get(this).isReady()) {
            return;
        }
        Tg.get(this).loadWritableChats(30, new Tg.Cb<List<Tg.Chat>>() {
            @Override
            public void ok(List<Tg.Chat> value) {
                writableChats.clear();
                if (value != null) {
                    writableChats.addAll(value);
                }
                renderDestinationAvatars();
            }

            @Override
            public void fail(String message) {
            }
        });
    }

    private void renderDestinationAvatars() {
        if (menuAvatarStrip == null || menuDestActiveLabel == null) {
            return;
        }
        long currentDestId = Prefs.destChatId(this);
        String destTitle = Prefs.destTitle(this);
        menuDestActiveLabel.setText(destTitle == null || destTitle.isEmpty()
                ? "Channel: tap avatar below"
                : "To: " + shortStr(destTitle, 22));

        menuAvatarStrip.removeAllViews();
        int max = Math.min(10, writableChats.size());
        for (int i = 0; i < max; i++) {
            final Tg.Chat chat = writableChats.get(i);
            boolean selected = chat.id == currentDestId;
            FrameLayout holder = new FrameLayout(this);
            int ringPx = Ui.dp(this, 34);
            int imgPx = Ui.dp(this, 28);
            GradientDrawable ring = new GradientDrawable();
            ring.setShape(GradientDrawable.OVAL);
            ring.setColor(selected ? 0x3310B981 : 0x1AFFFFFF);
            ring.setStroke(Ui.dp(this, selected ? 2 : 1),
                    selected ? 0xFF10B981 : 0x3394A3B8);
            holder.setBackground(ring);

            ImageView avatar = new ImageView(this);
            FrameLayout.LayoutParams alp = new FrameLayout.LayoutParams(
                    imgPx, imgPx, Gravity.CENTER);
            holder.addView(avatar, alp);
            Ui.paintChatAvatar(this, avatar, chat, 28);

            holder.setContentDescription(chat.title);
            holder.setOnClickListener(v -> {
                if (!captured.isEmpty()) {
                    closeMenuPanel();
                    pasteCapturedIntoChat(chat);
                } else {
                    Prefs.saveDestination(SmartOverlayService.this, chat.id, chat.title);
                    announceStep("CHANNEL SET", shortStr(chat.title, 22), 0xFF10B981, 2200L);
                    renderDestinationAvatars();
                }
            });

            LinearLayout.LayoutParams hlp = new LinearLayout.LayoutParams(ringPx, ringPx);
            hlp.rightMargin = Ui.dp(this, 6);
            menuAvatarStrip.addView(holder, hlp);
        }
    }

    private void syncLiveTransferUi() {
        boolean running = QueueService.Live.RUNNING.get();
        String stage = QueueService.Live.STAGE == null ? "" : QueueService.Live.STAGE;
        long done = QueueService.Live.DONE.get();
        long total = QueueService.Live.TOTAL.get();
        int rawPct = Format.percent(done, total);
        int pct = QJob.UPLOADING.equals(stage) ? Math.min(99, rawPct) : rawPct;

        if (running && !stage.isEmpty()) {
            // Badge shows strictly captured file count only (0 when empty).
            setPointerVisual(SmartPointerView.STATE_TRANSFERRING, captured.size(), pct);
            if (!stage.equals(lastAnnouncedStage)) {
                lastAnnouncedStage = stage;
                announceStep(Ui.stageLabel(stage).toUpperCase(),
                        shortStr(QueueService.Live.NAME, 24), 0xFF38BDF8, 2200L);
            }
        } else {
            if (!lastAnnouncedStage.isEmpty()) {
                lastAnnouncedStage = "";
                announceStep("DONE", "Sent successfully", 0xFF10B981, 2600L);
                startForegroundSafely(currentStepSummary());
            }
            if (!resolvingTap) {
                restoreIdleOrCapturedState();
            }
        }

        if (menuPopup == null) {
            return;
        }
        if (menuPermBox != null) {
            int want = SmartAccessibilityService.isEnabled(this) ? View.GONE : View.VISIBLE;
            if (menuPermBox.getVisibility() != want) {
                menuPermBox.setVisibility(want);
            }
        }
        if (menuClearBtn != null) {
            int wantClear = captured.isEmpty() ? View.GONE : View.VISIBLE;
            if (menuClearBtn.getVisibility() != wantClear) {
                menuClearBtn.setVisibility(wantClear);
            }
        }
        if (menuStepText != null) {
            String step = compactStepLine();
            if (!step.equals(lastStepRendered)) {
                lastStepRendered = step;
                menuStepText.setText(step);
            }
        }
        if (menuLiveCard != null && menuLiveLabel != null && menuLiveBar != null) {
            if (!running || stage.isEmpty()) {
                if (menuLiveCard.getVisibility() != View.GONE) {
                    menuLiveCard.setVisibility(View.GONE);
                    lastLiveLabelRendered = "";
                }
            } else {
                if (menuLiveCard.getVisibility() != View.VISIBLE) {
                    menuLiveCard.setVisibility(View.VISIBLE);
                }
                double speed = QueueService.Live.SPEED;
                String speedPart = speed > 1024 ? " • " + Format.speed(speed) : "";
                String stageText = Ui.stageLabel(stage);
                String line = stageText
                        + (total > 0 ? " " + pct + "%" : "")
                        + speedPart;
                if (!line.equals(lastLiveLabelRendered)) {
                    lastLiveLabelRendered = line;
                    menuLiveLabel.setText(line);
                }
                boolean indeterminate = total <= 0 || QJob.COPYING.equals(stage)
                        || QJob.RESOLVING.equals(stage);
                if (menuLiveBar.isIndeterminate() != indeterminate) {
                    menuLiveBar.setIndeterminate(indeterminate);
                }
                if (!indeterminate && menuLiveBar.getProgress() != pct) {
                    menuLiveBar.setProgress(pct);
                }
            }
        }
    }

    @Override
    public void onJobsChanged() {
        handler.post(this::syncLiveTransferUi);
    }

    // --------------------------------------------------------- small utils //

    private String compactStepLine() {
        if (!captured.isEmpty()) {
            return captured.size() + " file in dot -> open channel";
        }
        return "Ready • double-tap file";
    }

    private String currentStepSummary() {
        if (!captured.isEmpty()) {
            return captured.size() + " file(s) ready — open channel and double-tap to send.";
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
        int dotCount = Math.max(0, count);
        if (whiteCircle != null) {
            whiteCircle.setVisualState(state, dotCount, pct);
        }
        if (menuOrb != null) {
            menuOrb.setVisualState(state, dotCount, pct);
        }
    }

    private Button miniChip(String label, int bgColor, int fgColor) {
        Button btn = new Button(this);
        btn.setText(label);
        btn.setAllCaps(false);
        btn.setTextSize(11f);
        btn.setTypeface(Typeface.DEFAULT_BOLD);
        btn.setTextColor(fgColor);
        btn.setMinWidth(0);
        btn.setMinimumWidth(0);
        btn.setMinHeight(0);
        btn.setMinimumHeight(0);
        btn.setStateListAnimator(null);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(bgColor);
        bg.setCornerRadius(Ui.dp(this, 999));
        btn.setBackground(bg);
        btn.setPadding(Ui.dp(this, 8), Ui.dp(this, 3), Ui.dp(this, 8), Ui.dp(this, 3));
        return btn;
    }

    private Button miniActionButton(String label, int bgColor, int fgColor) {
        Button btn = new Button(this);
        btn.setText(label);
        btn.setAllCaps(false);
        btn.setTextSize(10.5f);
        btn.setTypeface(Typeface.DEFAULT_BOLD);
        btn.setTextColor(fgColor);
        btn.setMinWidth(0);
        btn.setMinimumWidth(0);
        btn.setMinHeight(0);
        btn.setMinimumHeight(0);
        btn.setStateListAnimator(null);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(bgColor);
        bg.setCornerRadius(Ui.dp(this, 9));
        btn.setBackground(bg);
        btn.setPadding(Ui.dp(this, 6), 0, Ui.dp(this, 6), 0);
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
