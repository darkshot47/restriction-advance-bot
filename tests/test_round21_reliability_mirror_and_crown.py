"""Regression suite for Vmore 2.3.3:

1. Per-account destination (a chat id only exists inside one Telegram session).
2. Queue survivability: reboot receiver, flood-wait parking with a countdown,
   and the empty-file guard before an upload.
3. Auto-copy (mirror) from the account's own chat list, with filters, driven by
   a repeating alarm that is re-armed after a reboot.
4. The colourful crown "Smart feature" chip with its gradient text animation.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANDROID_MAIN = REPO_ROOT / "android" / "app" / "src" / "main"
JAVA_DIR = ANDROID_MAIN / "java" / "com" / "vmore" / "app"
RES_DIR = ANDROID_MAIN / "res"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_destination_is_remembered_per_account_not_per_phone():
    prefs = _read(JAVA_DIR / "Prefs.java")
    # the slot suffix is what keeps account 2 from inheriting account 1's chat
    assert 'KEY_DEST_ID + "_s" + activeSlot(context)' in prefs
    assert 'KEY_DEST_TITLE + "_s" + activeSlot(context)' in prefs
    # an older build's single destination is migrated to slot 1, then dropped
    assert "if (activeSlot(context) == 1)" in prefs
    assert 'store.getLong(KEY_DEST_ID, 0L)' in prefs


def test_queue_survives_a_reboot_and_resumes_only_when_it_was_running():
    manifest = _read(ANDROID_MAIN / "AndroidManifest.xml")
    boot = _read(JAVA_DIR / "BootReceiver.java")
    assert "android.permission.RECEIVE_BOOT_COMPLETED" in manifest
    assert ".BootReceiver" in manifest
    assert "android.intent.action.BOOT_COMPLETED" in manifest
    assert "android.intent.action.MY_PACKAGE_REPLACED" in manifest
    assert "Intent.ACTION_BOOT_COMPLETED" in boot
    assert "jobs.hasWork() && !jobs.pausedAll()" in boot
    assert "QueueService.run(app)" in boot
    assert "Mirror.refresh(app)" in boot


def test_flood_wait_parks_the_job_instead_of_failing_it():
    retry = _read(JAVA_DIR / "Retry.java")
    queue = _read(JAVA_DIR / "QueueService.java")
    qjob = _read(JAVA_DIR / "QJob.java")
    jobs = _read(JAVA_DIR / "Jobs.java")
    assert "static long floodSeconds(String reason)" in retry
    assert "waitOutFlood(jobs, job, flood)" in queue
    assert "job.notBefore = until;" in queue
    assert "Telegram asked to wait " in queue
    assert "public long notBefore;" in qjob
    assert 'json.put("not_before", notBefore);' in qjob
    assert "job.notBefore <= now" in jobs
    assert "public synchronized long nextDueAt()" in jobs


def test_empty_download_is_never_uploaded_as_a_broken_message():
    queue = _read(JAVA_DIR / "QueueService.java")
    assert "private boolean fileLooksEmpty(QJob job)" in queue
    assert "if (fileLooksEmpty(job))" in queue
    assert "the downloaded file arrived empty" in queue
    # the guard must sit after the file is staged and before the upload starts
    guard = queue.index("if (fileLooksEmpty(job))")
    upload = queue.index("job.stage = QJob.UPLOADING;", guard)
    assert guard < upload


def test_auto_copy_picks_chats_from_the_account_and_only_new_posts():
    mirror = _read(JAVA_DIR / "Mirror.java")
    prefs = _read(JAVA_DIR / "Prefs.java")
    picker = _read(JAVA_DIR / "ChatPickerActivity.java")
    activity = _read(JAVA_DIR / "MirrorActivity.java")
    manifest = _read(ANDROID_MAIN / "AndroidManifest.xml")

    # per-account mirror settings
    assert "static boolean mirrorEnabled(" in prefs
    assert "static void saveMirror(" in prefs
    assert "static long mirrorLastId(" in prefs

    assert "public void listChatMedia(" in _read(JAVA_DIR / "Tg.java")
    assert "media.messageId > last" in mirror
    assert "Prefs.setMirrorStart(app, newest)" in mirror
    assert "fresh.sort((a, b) -> Long.compare(a.messageId, b.messageId))" in mirror
    assert "probe.allows(media.kind, media.size)" in mirror
    assert "setInexactRepeating(" in mirror
    assert "MirrorReceiver.class" in mirror

    assert ".MirrorReceiver" in manifest
    assert ".MirrorActivity" in manifest
    assert "mirror_source" in picker
    assert "startActivityForResult(intent, request)" in activity
    assert "Prefs.setMirrorEnabled(this, checked)" in activity


def test_smart_feature_chip_is_a_colourful_animated_crown():
    layout = _read(RES_DIR / "layout" / "activity_main.xml")
    crown_svg = _read(RES_DIR / "drawable" / "ic_crown.xml")
    crown = _read(JAVA_DIR / "Crown.java")
    main = _read(JAVA_DIR / "MainActivity.java")
    strings = _read(RES_DIR / "values" / "strings.xml")

    assert 'android:id="@+id/smartFeatureCrown"' in layout
    assert 'android:id="@+id/smartFeatureLabel"' in layout
    assert '@drawable/ic_crown' in layout
    assert "<vector" in crown_svg
    assert "ic_crown" not in crown  # the drawable is referenced by its file name

    assert "LinearGradient" in crown
    assert "Shader.TileMode.MIRROR" in crown
    assert "ValueAnimator.INFINITE" in crown
    assert "crown.setRotation(" in crown
    assert "Crown.bind(this, smartFeatureButton" in main
    assert "crownAnimator.cancel();" in main
    assert '<string name="smart_button">Smart feature</string>' in strings


def test_version_is_2_3_3_with_new_version_code():
    gradle = _read(REPO_ROOT / "android" / "app" / "build.gradle")
    vmore = _read(JAVA_DIR / "Vmore.java")
    assert "versionCode 20" in gradle
    assert 'versionName "2.3.3"' in gradle
    assert 'VERSION = "2.3.3"' in vmore
