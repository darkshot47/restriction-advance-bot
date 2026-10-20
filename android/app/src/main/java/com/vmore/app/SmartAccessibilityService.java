package com.vmore.app;

import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.Context;
import android.graphics.Rect;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

// Multi-window accessibility reader used exclusively when the user double-taps
// Vmore's floating white circle pointer over a file or chat on screen.
public class SmartAccessibilityService extends AccessibilityService {

    public static final class ScreenTarget {
        public String packageName = "";
        public String headerTitle = "";
        public boolean looksLikeChatList;
        public final List<String> targetLines = new ArrayList<>();
        public final List<String> siblingAnchorLines = new ArrayList<>();
        public int cellOffsetFromAnchor;
        public int cellIndexFromBottom;
        public boolean hasComposerBar;
    }

    private static final class CellBox {
        final Rect bounds;
        final List<String> lines;

        CellBox(Rect bounds, List<String> lines) {
            this.bounds = bounds;
            this.lines = lines;
        }
    }

    private static volatile SmartAccessibilityService instance;

    public static boolean isRunning() {
        return instance != null;
    }

    public static boolean isEnabled(Context context) {
        if (instance != null) {
            return true;
        }
        if (context == null) {
            return false;
        }
        try {
            ComponentName expected = new ComponentName(context, SmartAccessibilityService.class);
            String raw = Settings.Secure.getString(
                    context.getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (raw == null || raw.isEmpty()) {
                return false;
            }
            TextUtils.SimpleStringSplitter splitter = new TextUtils.SimpleStringSplitter(':');
            splitter.setString(raw);
            while (splitter.hasNext()) {
                ComponentName enabled = ComponentName.unflattenFromString(splitter.next());
                if (expected.equals(enabled)) {
                    return true;
                }
            }
        } catch (Throwable ignored) {
        }
        return false;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Passive only: screen inspection runs strictly when the user double-taps
        // the Vmore white pointer circle, consuming zero background CPU or battery.
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public void onDestroy() {
        if (instance == this) {
            instance = null;
        }
        super.onDestroy();
    }

    /**
     * Inspects the app window directly beneath {@code (rawX, rawY)}, skipping
     * Vmore's own floating overlay windows so the pointer circle never blocks
     * the underlying Telegram message bubble or chat row.
     */
    public static ScreenTarget inspectAt(int rawX, int rawY) {
        SmartAccessibilityService service = instance;
        if (service == null) {
            return null;
        }
        DisplayMetrics dm = service.getResources().getDisplayMetrics();
        int screenW = Math.max(1, dm.widthPixels);
        int screenH = Math.max(1, dm.heightPixels);
        String ownPkg = service.getPackageName();

        AccessibilityNodeInfo chosenRoot = null;
        try {
            List<AccessibilityWindowInfo> windows = service.getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo win : windows) {
                    if (win == null
                            || win.getType() != AccessibilityWindowInfo.TYPE_APPLICATION) {
                        continue;
                    }
                    Rect winRect = new Rect();
                    win.getBoundsInScreen(winRect);
                    if (!winRect.contains(rawX, rawY)) {
                        continue;
                    }
                    AccessibilityNodeInfo root = win.getRoot();
                    if (root == null) {
                        continue;
                    }
                    CharSequence pkg = root.getPackageName();
                    if (pkg != null && ownPkg.contentEquals(pkg)) {
                        continue;
                    }
                    chosenRoot = root;
                    break;
                }
            }
            if (chosenRoot == null) {
                AccessibilityNodeInfo active = service.getRootInActiveWindow();
                if (active != null && (active.getPackageName() == null
                        || !ownPkg.contentEquals(active.getPackageName()))) {
                    chosenRoot = active;
                }
            }
            if (chosenRoot == null) {
                return null;
            }
            return parseWindow(chosenRoot, rawX, rawY, screenW, screenH);
        } catch (Throwable error) {
            return null;
        }
    }

    private static ScreenTarget parseWindow(AccessibilityNodeInfo root, int rawX, int rawY,
                                            int screenW, int screenH) {
        ScreenTarget target = new ScreenTarget();
        if (root.getPackageName() != null) {
            target.packageName = root.getPackageName().toString();
        }
        int headerBandBottom = (int) (screenH * 0.165f);
        int composerBandTop = (int) (screenH * 0.84f);

        List<String> headerCandidates = new ArrayList<>();
        List<CellBox> visibleCells = new ArrayList<>();
        AccessibilityNodeInfo deepestHit = findDeepestHit(root, rawX, rawY);

        scanTree(root, screenW, screenH, headerBandBottom, composerBandTop,
                headerCandidates, visibleCells, target);

        target.headerTitle = pickBestHeaderTitle(headerCandidates);

        // Extract text lines from the tapped cell container (walking upward from deepestHit)
        AccessibilityNodeInfo cellNode = findCellContainer(deepestHit, screenW, screenH);
        Rect hitBounds = new Rect();
        if (cellNode != null) {
            cellNode.getBoundsInScreen(hitBounds);
            collectNodeTexts(cellNode, target.targetLines);
        } else if (deepestHit != null) {
            deepestHit.getBoundsInScreen(hitBounds);
            collectNodeTexts(deepestHit, target.targetLines);
        }

        // Also include overlapping cell boxes in case Telegram paints text on sibling custom views
        for (CellBox box : visibleCells) {
            if (box.bounds.contains(rawX, rawY)) {
                for (String line : box.lines) {
                    if (!target.targetLines.contains(line)) {
                        target.targetLines.add(line);
                    }
                }
            }
        }

        // Sort message/row cells top-to-bottom so we know relative rank & anchor offsets
        visibleCells.sort(Comparator.comparingInt(a -> a.bounds.centerY()));
        int hitCellIndex = -1;
        int bestDist = Integer.MAX_VALUE;
        for (int i = 0; i < visibleCells.size(); i++) {
            CellBox cell = visibleCells.get(i);
            int d = Math.abs(cell.bounds.centerY() - rawY);
            if (cell.bounds.contains(rawX, rawY) || d < bestDist) {
                bestDist = d;
                hitCellIndex = i;
                if (cell.bounds.contains(rawX, rawY)) {
                    break;
                }
            }
        }

        if (hitCellIndex >= 0 && !visibleCells.isEmpty()) {
            //Newest messages sit at the bottom in Telegram chats (index 0 = bottom-most)
            target.cellIndexFromBottom = Math.max(0, (visibleCells.size() - 1) - hitCellIndex);
            // Find nearest sibling bubble with rich text to serve as anchor when tapping a pure photo/video
            for (int delta = 1; delta <= 4; delta++) {
                int[] neighbors = new int[]{hitCellIndex + delta, hitCellIndex - delta};
                for (int idx : neighbors) {
                    if (idx >= 0 && idx < visibleCells.size()) {
                        List<String> candidateLines = visibleCells.get(idx).lines;
                        String q = SmartMatcher.extractSearchQuery(candidateLines);
                        if (q.length() >= 4) {
                            target.siblingAnchorLines.addAll(candidateLines);
                            // In newest-first history ordering: lower Y (smaller idx) = older = positive index delta
                            target.cellOffsetFromAnchor = idx - hitCellIndex;
                            delta = 99;
                            break;
                        }
                    }
                }
            }
        }

        target.looksLikeChatList = !target.hasComposerBar
                && (target.headerTitle.isEmpty() || isGenericHomeTitle(target.headerTitle))
                && visibleCells.size() >= 3;
        return target;
    }

    private static void scanTree(AccessibilityNodeInfo node, int screenW, int screenH,
                                 int headerBottom, int composerTop,
                                 List<String> headers, List<CellBox> cells,
                                 ScreenTarget target) {
        if (node == null || !node.isVisibleToUser()) {
            return;
        }
        Rect r = new Rect();
        node.getBoundsInScreen(r);
        String cls = node.getClassName() == null ? "" : node.getClassName().toString();
        if (cls.contains("EditText") && r.top >= composerTop) {
            target.hasComposerBar = true;
        }
        String text = ownLabel(node);
        if (!text.isEmpty() && r.bottom <= headerBottom && r.top >= 0
                && r.left > (int) (screenW * 0.08f) && r.left < (int) (screenW * 0.72f)) {
            headers.add(text);
        }
        // Message bubble or chat-list row cell container
        int h = r.height();
        int w = r.width();
        if (r.top >= headerBottom - 16 && r.bottom <= composerTop + 48
                && h >= (int) (screenH * 0.042f) && h <= (int) (screenH * 0.78f)
                && w >= (int) (screenW * 0.28f)) {
            List<String> lines = new ArrayList<>();
            collectNodeTexts(node, lines);
            if (!lines.isEmpty() && isLeafCellContainer(node, screenH)) {
                cells.add(new CellBox(new Rect(r), lines));
            }
        }
        int count = node.getChildCount();
        for (int i = 0; i < count; i++) {
            scanTree(node.getChild(i), screenW, screenH, headerBottom, composerTop,
                    headers, cells, target);
        }
    }

    private static boolean isLeafCellContainer(AccessibilityNodeInfo node, int screenH) {
        int childLarge = 0;
        int n = node.getChildCount();
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo c = node.getChild(i);
            if (c == null || !c.isVisibleToUser()) {
                continue;
            }
            Rect cr = new Rect();
            c.getBoundsInScreen(cr);
            if (cr.height() >= (int) (screenH * 0.06f)) {
                childLarge++;
            }
        }
        return childLarge <= 1;
    }

    private static AccessibilityNodeInfo findDeepestHit(AccessibilityNodeInfo node, int x, int y) {
        if (node == null || !node.isVisibleToUser()) {
            return null;
        }
        Rect r = new Rect();
        node.getBoundsInScreen(r);
        if (!r.contains(x, y)) {
            return null;
        }
        int n = node.getChildCount();
        for (int i = n - 1; i >= 0; i--) {
            AccessibilityNodeInfo deeper = findDeepestHit(node.getChild(i), x, y);
            if (deeper != null) {
                return deeper;
            }
        }
        return node;
    }

    private static AccessibilityNodeInfo findCellContainer(AccessibilityNodeInfo leaf,
                                                           int screenW, int screenH) {
        AccessibilityNodeInfo cursor = leaf;
        AccessibilityNodeInfo best = leaf;
        int guard = 0;
        while (cursor != null && guard++ < 10) {
            Rect r = new Rect();
            cursor.getBoundsInScreen(r);
            if (r.height() >= (int) (screenH * 0.80f)) {
                break;
            }
            best = cursor;
            cursor = cursor.getParent();
        }
        return best;
    }

    private static void collectNodeTexts(AccessibilityNodeInfo node, List<String> out) {
        if (node == null || !node.isVisibleToUser()) {
            return;
        }
        String label = ownLabel(node);
        if (!label.isEmpty() && !out.contains(label)) {
            out.add(label);
        }
        int count = node.getChildCount();
        for (int i = 0; i < count; i++) {
            collectNodeTexts(node.getChild(i), out);
        }
    }

    private static String ownLabel(AccessibilityNodeInfo node) {
        StringBuilder sb = new StringBuilder();
        if (node.getText() != null && node.getText().length() > 0) {
            sb.append(node.getText().toString().trim());
        }
        if (node.getContentDescription() != null && node.getContentDescription().length() > 0) {
            String desc = node.getContentDescription().toString().trim();
            if (!desc.isEmpty() && !sb.toString().contains(desc)) {
                if (sb.length() > 0) {
                    sb.append('\n');
                }
                sb.append(desc);
            }
        }
        return sb.toString().trim();
    }

    private static String pickBestHeaderTitle(List<String> candidates) {
        for (String line : candidates) {
            for (String piece : line.split("\\n")) {
                String clean = piece.trim();
                if (clean.length() < 2) {
                    continue;
                }
                if (SmartMatcher.isSubtitleNoise(clean)) {
                    continue;
                }
                if (!SmartMatcher.extractClockTimes(clean).isEmpty() && clean.length() <= 9) {
                    continue;
                }
                return clean;
            }
        }
        return "";
    }

    private static boolean isGenericHomeTitle(String header) {
        String norm = SmartMatcher.normalizeTitle(header);
        return "telegram".equals(norm) || "telegram x".equals(norm)
                || "plus messenger".equals(norm) || "nekogram".equals(norm)
                || "chats".equals(norm) || "all chats".equals(norm);
    }
}
