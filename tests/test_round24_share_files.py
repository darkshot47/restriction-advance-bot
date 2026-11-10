"""Regression suite for Vmore 2.3.5 - "Share to Vmore" for real files.

The gap this closes: until now Vmore could only send what it had downloaded
from Telegram.  Its only share filter was ``text/plain``, so no gallery, mail or
recorder app even offered Vmore, and a photo from the camera had no way into a
chat at all.  The tests below pin the pieces that make the new path work and,
just as important, the things that must not change:

* the manifest accepts files (single and multiple) without losing text links;
* a shared file keeps the name its owner gave it, never a name Vmore invents;
* the copy is made inside Cache, one folder per share, and is deleted after the
  upload (or when the sheet is cancelled) so a share is not a second library;
* the queue uploads it with no download and no forward step, records it in
  history, and reports it like any other upload;
* a share that arrives before sign-in waits on disk instead of being lost;
* the version moved to 2.3.5 / versionCode 22.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANDROID_MAIN = REPO_ROOT / "android" / "app" / "src" / "main"
JAVA_DIR = ANDROID_MAIN / "java" / "com" / "vmore" / "app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _manifest() -> str:
    return _read(ANDROID_MAIN / "AndroidManifest.xml")


# --------------------------------------------------------------------------- #
#  1. Other apps can actually share a file into Vmore
# --------------------------------------------------------------------------- #

def test_the_manifest_accepts_single_and_multiple_file_shares():
    manifest = _manifest()
    assert 'android.intent.action.SEND_MULTIPLE' in manifest
    #: One- and many-file shares both land on the home screen.
    assert manifest.count('android:mimeType="*/*"') >= 2
    #: A link shared as text keeps working exactly as before.
    assert 'android:mimeType="text/plain"' in manifest


def test_the_intake_reads_both_extras_and_ignores_repeats():
    intake = _read(JAVA_DIR / "ShareIntake.java")
    assert "intent.getParcelableExtra(Intent.EXTRA_STREAM)" in intake
    assert "intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)" in intake
    #: Some apps put the same uri in both extras; it must arrive once.
    assert "Set<Uri> unique = new LinkedHashSet<>();" in intake
    assert "unique.add(single)" in intake


def test_the_home_screen_copies_the_share_off_the_main_thread():
    home = _read(JAVA_DIR / "MainActivity.java")
    assert "captureSharedFiles(getIntent());" in home
    assert "private void captureSharedFiles(Intent intent)" in home
    assert 'new Thread(() -> {' in home
    #: The same intent must not be copied twice after a rotation.
    assert "intent.removeExtra(Intent.EXTRA_STREAM);" in home


# --------------------------------------------------------------------------- #
#  2. The file keeps the name it already had
# --------------------------------------------------------------------------- #

def test_a_shared_file_keeps_its_real_name():
    intake = _read(JAVA_DIR / "ShareIntake.java")
    #: The name the sharing app declared wins, extension included.
    assert "OpenableColumns.DISPLAY_NAME" in intake
    assert "Format.displayName(display," in intake
    #: A nameless stream still gets a readable, dated name - not an id.
    assert "Format.datedName(kind, 0L," in intake
    assert "vmore_" not in intake
    #: Two gallery files called IMG_0001.jpg do not overwrite each other.
    assert 'candidate = stem + "-" + copy + suffix;' in intake


def test_the_kind_and_extension_come_from_the_sharing_app():
    intake = _read(JAVA_DIR / "ShareIntake.java")
    assert 'type.startsWith("image/")' in intake
    assert 'type.startsWith("video/")' in intake
    assert 'type.startsWith("audio/")' in intake
    assert "MimeTypeMap.getSingleton()" in intake
    #: A document keeps a document's name: no invented .jpg for a PDF.
    assert 'return "document";' in intake


def test_two_gigabytes_and_fifty_files_are_the_ceilings():
    intake = _read(JAVA_DIR / "ShareIntake.java")
    assert "static final long MAX_BYTES = 2L * 1024L * 1024L * 1024L;" in intake
    assert "static final int MAX_FILES = 50;" in intake
    #: The phone's free space is checked before a copy is started.
    assert "freeBytes(folder) < declared + 8L * 1024L * 1024L" in intake


# --------------------------------------------------------------------------- #
#  3. The copy is a one-shot, not a second library
# --------------------------------------------------------------------------- #

def test_shared_copies_live_in_the_cache_and_are_swept():
    files = _read(JAVA_DIR / "LocalFiles.java")
    assert 'new File(cacheRoot(context), "share")' in files
    assert "static File shareInbox(Context context, long stamp)" in files
    cleanup = _read(JAVA_DIR / "Cleanup.java")
    assert "sweepFolder(LocalFiles.shareRoot(app), inUse, freed, false);" in cleanup


def test_the_copy_is_deleted_when_the_upload_lands_or_the_sheet_is_cancelled():
    queue = _read(JAVA_DIR / "QueueService.java")
    assert "private void dropSharedCopy(QJob job)" in queue
    assert "LocalFiles.shareRoot(this)" in queue
    intake = _read(JAVA_DIR / "ShareIntake.java")
    assert "static void discard(List<Item> items)" in intake
    home = _read(JAVA_DIR / "MainActivity.java")
    assert "ShareIntake.discard(ShareIntake.decode(Prefs.shareBatch(this)));" in home


# --------------------------------------------------------------------------- #
#  4. It travels through the queue like everything else
# --------------------------------------------------------------------------- #

def test_the_queue_uploads_a_shared_file_without_downloading_it():
    job = _read(JAVA_DIR / "QJob.java")
    assert 'public static final String METHOD_UPLOAD = "upload";' in job
    queue = _read(JAVA_DIR / "QueueService.java")
    #: The upload path is taken before anything resolves or downloads.
    assert "if (QJob.METHOD_UPLOAD.equals(job.method)) {" in queue
    assert queue.index("QJob.METHOD_UPLOAD.equals(job.method)") < queue.index(
        "QJob.METHOD_SCAN.equals(job.method)")
    assert "private void uploadSharedFile(Jobs jobs, QJob job)" in queue
    #: One real send, the same one every other upload uses.
    assert "Tg.get(this).sendBlocking(job," in queue
    #: Progress, history and the finish note are recorded for it too.
    assert "Live.STAGE = QJob.UPLOADING;" in queue
    assert "History.STATUS_UPLOADED, job.raw, \"\", \"\");" in queue
    assert "markFinished(job);" in queue


def test_a_missing_shared_file_is_not_retried_four_times():
    queue = _read(JAVA_DIR / "QueueService.java")
    assert '"the shared file was not found on the phone"' in queue


def test_the_sheet_shows_the_real_names_and_sends_where_the_user_says():
    home = _read(JAVA_DIR / "MainActivity.java")
    assert "private void showShareSheet(String problem)" in home
    assert "private void sendSharedFiles(List<ShareIntake.Item> items, String caption)" in home
    assert "job.method = QJob.METHOD_UPLOAD;" in home
    assert "job.path = item.path;" in home
    #: A PDF is never re-typed as a picture by the send-as setting.
    assert '"document".equals(item.kind)' in home
    #: The sheet comes back after the chat picker, caption included.
    assert "showShareSheet(\"\")" in home
    assert "shareCaptionDraft" in home


def test_a_share_that_arrives_before_sign_in_is_not_lost():
    prefs = _read(JAVA_DIR / "Prefs.java")
    assert "public static String shareBatch(Context context)" in prefs
    assert "public static void setShareBatch(Context context, String json)" in prefs
    intake = _read(JAVA_DIR / "ShareIntake.java")
    assert "static String encode(List<Item> items)" in intake
    assert "static List<Item> decode(String json)" in intake
    home = _read(JAVA_DIR / "MainActivity.java")
    #: The home screen offers the waiting batch again on every resume.
    assert 'showShareSheet("");' in home
    assert "if (!Tg.get(this).isReady()) {" in home


def test_version_is_2_3_5_with_a_new_version_code():
    gradle = _read(REPO_ROOT / "android" / "app" / "build.gradle")
    vmore = _read(JAVA_DIR / "Vmore.java")
    assert "versionCode 22" in gradle
    assert 'versionName "2.3.5"' in gradle
    assert 'VERSION = "2.3.5"' in vmore
