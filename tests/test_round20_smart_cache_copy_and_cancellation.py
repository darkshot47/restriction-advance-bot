"""Regression suite verifying all Vmore 2.3.0 features and repository invariants:

1. True download/upload cancellation & immediate partial cache file deletion.
2. Strict Cache-only storage (`getCacheDir()`), zero User Data media inflation.
3. Top-left "Smart feature" entry, permission flow, floating white circle pointer
   (drag + double-tap capture & destination paste), and colorful floating menu.
4. Destination channel/chat profile avatars + strict send-permission filtering.
5. Opening launch intro animation before revealing app UI.
6. Zero exposure of owner GitHub repository/account URLs anywhere in repo or app.
7. `tryNativeCopy` (`native_cpy`) attempted first on every link with automatic
   fallback to cache-backed mobile data download + upload when restricted.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parent.parent
ANDROID_MAIN = REPO_ROOT / "android" / "app" / "src" / "main"
JAVA_DIR = ANDROID_MAIN / "java" / "com" / "vmore" / "app"
RES_DIR = ANDROID_MAIN / "res"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_zero_owner_github_account_links_anywhere():
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache"}
    offenders = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in excluded for part in path.parts) or not path.is_file():
            continue
        if path.name == "test_round20_smart_cache_copy_and_cancellation.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"github\.com/[A-Za-z0-9_.-]+/restriction-advance-bot", text, re.I):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"Repository GitHub URL leaked in: {offenders}"
    # Also ensure no github.com URL exists anywhere in Android app sources/resources
    for path in ANDROID_MAIN.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert "github.com" not in text.lower(), f"github.com found in {path}"


def test_all_media_and_tdlib_files_live_in_cache_not_user_data():
    local_files = _read(JAVA_DIR / "LocalFiles.java")
    tg_source = _read(JAVA_DIR / "Tg.java")
    assert "context.getCacheDir()" in local_files
    assert "context.getExternalCacheDir()" in local_files
    assert "sweepLegacyUserData" in local_files
    assert "new File(cacheRoot(context), Vmore.FOLDER)" in local_files
    assert 'new File(cacheRoot(context), "tdlib")' in local_files
    assert 'new File(cacheRoot(context), "upload")' in local_files
    assert "LocalFiles.tdFilesDir(app, session)" in tg_source
    assert "LocalFiles.uploadScratchDir(app)" in tg_source
    assert "LocalFiles.chatAvatarFile(" in tg_source


def test_removing_download_cancels_active_tdlib_transfer_and_deletes_partial_file():
    tg_source = _read(JAVA_DIR / "Tg.java")
    queue_service = _read(JAVA_DIR / "QueueService.java")
    queue_activity = _read(JAVA_DIR / "QueueActivity.java")
    assert "CancelDownloadFile(fileId, true)" not in tg_source
    assert "new TdApi.CancelDownloadFile(fileId, false)" in tg_source
    assert "new TdApi.DeleteFile(fileId)" in tg_source
    assert "abortJobTransfers" in tg_source
    assert "public static void removeJob(Context context, String jobId)" in queue_service
    assert "purgeJobFiles(" in queue_service
    assert "QueueService.removeJob(this, job.id)" in queue_activity


def test_smart_feature_button_permissions_white_circle_and_colorful_menu():
    main_xml = _read(RES_DIR / "layout" / "activity_main.xml")
    strings_xml = _read(RES_DIR / "values" / "strings.xml")
    manifest = _read(ANDROID_MAIN / "AndroidManifest.xml")
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    pointer = _read(JAVA_DIR / "SmartPointerView.java")
    sheet = _read(JAVA_DIR / "SmartFeatureSheet.java")

    assert "@+id/smartFeatureButton" in main_xml
    assert '<string name="smart_button">Smart feature</string>' in strings_xml
    assert "android.permission.SYSTEM_ALERT_WINDOW" in manifest
    assert ".SmartOverlayService" in manifest
    assert "onDoubleTap" in pointer
    assert "MODE_WHITE_CIRCLE" in pointer and "MODE_MENU_ORB" in pointer
    assert "sendCapturedToRememberedDestination" in overlay
    assert "showMenuPanel" in overlay and "closeMenuPanel" in overlay
    assert "ACTION_MANAGE_OVERLAY_PERMISSION" in sheet


def test_destination_profile_avatars_and_send_permission_filtering():
    main_xml = _read(RES_DIR / "layout" / "activity_main.xml")
    picker = _read(JAVA_DIR / "ChatPickerActivity.java")
    tg_source = _read(JAVA_DIR / "Tg.java")
    ui_source = _read(JAVA_DIR / "Ui.java")

    assert "@+id/destAvatar" in main_xml
    assert "loadWritableChats" in picker
    assert "Ui.chatRow(" in picker
    assert "paintChatAvatar(" in ui_source
    assert "GetSupergroup(" in tg_source and "GetBasicGroup(" in tg_source


def test_launch_intro_animation_plays_before_app_opens():
    intro = _read(JAVA_DIR / "LaunchIntro.java")
    login = _read(JAVA_DIR / "LoginActivity.java")
    home = _read(JAVA_DIR / "MainActivity.java")
    assert "playIfNeeded(" in intro
    assert "LaunchIntro.playIfNeeded(" in login
    assert "LaunchIntro.playIfNeeded(" in home


def test_native_copy_attempted_first_with_data_download_fallback():
    queue_service = _read(JAVA_DIR / "QueueService.java")
    tg_source = _read(JAVA_DIR / "Tg.java")
    copy_pos = queue_service.index("if (tryNativeCopy(jobs, job))")
    download_pos = queue_service.index("String rawDownloadedPath = download(job);")
    assert copy_pos < download_pos, "tryNativeCopy must execute BEFORE mobile data download!"
    assert "nativeCopyBlocking(" in tg_source
    assert "new TdApi.ForwardMessages(" in tg_source


def test_upload_watch_uses_remote_uploaded_size_and_never_freezes_at_100_percent():
    tg_source = _read(JAVA_DIR / "Tg.java")
    qjob_source = _read(JAVA_DIR / "QJob.java")
    main_source = _read(JAVA_DIR / "MainActivity.java")
    assert "class UploadWatch" in tg_source
    assert "file.remote == null ? 0L : file.remote.uploadedSize" in tg_source
    assert "reported = total - 1L" in tg_source
    assert "ensureChatReady(" in tg_source
    assert "Files.createLink(" not in tg_source
    assert "Math.min(99, Format.percent(uploaded, total))" in qjob_source
    assert "QJob.UPLOADING.equals(stage)" in main_source


def test_smart_floating_menu_is_quarter_size_glitch_free_and_clean_dot_count():
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    pointer = _read(JAVA_DIR / "SmartPointerView.java")
    assert "dm.widthPixels * 0.50f" in overlay
    assert "WindowManager.LayoutParams.MATCH_PARENT" not in overlay
    assert "Jobs.get(this).size()" not in overlay
    assert "captured.size()" in overlay
    assert "ValueAnimator.INFINITE" not in pointer


def test_smart_feature_needs_no_restricted_permissions_for_play_protect():
    """Play Protect blocks sideloads that ask for Accessibility / specialUse FGS."""
    manifest = _read(ANDROID_MAIN / "AndroidManifest.xml")
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "accessibilityservice" not in manifest
    assert ".SmartAccessibilityService" not in manifest
    assert "specialUse" not in manifest
    assert "FOREGROUND_SERVICE_SPECIAL_USE" not in manifest
    assert 'android:foregroundServiceType="dataSync"' in manifest
    assert "android.permission.SYSTEM_ALERT_WINDOW" in manifest
    assert not (JAVA_DIR / "SmartAccessibilityService.java").exists()
    assert not (RES_DIR / "xml" / "smart_accessibility.xml").exists()
    sheet = _read(JAVA_DIR / "SmartFeatureSheet.java")
    assert "ACTION_ACCESSIBILITY_SETTINGS" not in sheet
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    assert "SmartAccessibilityService" not in overlay


def test_exact_file_picker_reads_telegram_servers_not_the_screen():
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    tg_source = _read(JAVA_DIR / "Tg.java")
    # Screen reading is gone; Telegram itself lists the chat's media by id.
    assert "listChatMedia(" in tg_source
    assert "new TdApi.GetChatHistory(" in tg_source
    assert "public void openPicker()" in overlay
    assert "resolveAnyChat(" in overlay
    assert "commitPickerSelection(" in overlay
    # The picker never trusts a guessed or auto-prefixed username.
    assert 'link.error = "paste a direct Telegram link (https://t.me/...) or @username"' in _read(
        JAVA_DIR / "TgLink.java")
    assert 'value.startsWith("@")' in _read(JAVA_DIR / "TgLink.java")


def test_reacting_to_a_post_captures_that_exact_post():
    tg_source = _read(JAVA_DIR / "Tg.java")
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    assert "interface SmartReactionListener" in tg_source
    assert "TdApi.UpdateMessageInteractionInfo" in tg_source
    assert "isChosen" in tg_source
    assert "setSmartReactionListener(" in overlay
    assert "onReactedMedia(" in tg_source


def test_switching_accounts_reloads_chats_and_never_reuses_old_session():
    tg_source = _read(JAVA_DIR / "Tg.java")
    overlay = _read(JAVA_DIR / "SmartOverlayService.java")
    assert "public void addStateWatcher(" in tg_source
    assert "public void removeStateWatcher(" in tg_source
    assert "Tg.STATE_NONE.equals(state)" in overlay
    assert "Tg.STATE_READY.equals(state)" in overlay
    assert "tell(STATE_NONE, null);" in tg_source
    assert "new TdApi.LoadChats(new TdApi.ChatListArchive(), limit)" in tg_source
    assert "new TdApi.GetChats(new TdApi.ChatListArchive(), limit)" in tg_source


def test_version_is_2_3_2_with_new_version_code():
    gradle = _read(REPO_ROOT / "android" / "app" / "build.gradle")
    vmore = _read(JAVA_DIR / "Vmore.java")
    assert "versionCode 19" in gradle
    assert 'versionName "2.3.2"' in gradle
    assert 'VERSION = "2.3.2"' in vmore

