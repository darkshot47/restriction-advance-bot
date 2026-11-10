"""Regression suite for Vmore 2.3.4:

1. **No internal name leaks into a chat.** Telegram takes the uploaded file name
   from the local path, so the old build's ``vmore_4838`` placeholder and the
   ``vmore_<millis>_`` upload alias both ended up as the name every recipient
   saw.  Names now come from the caption, the post's own date, or the original
   file — and a stale ``vmore_`` prefix is stripped on the way out.
2. **A profile picture survives "Clear Cache".** Pictures used to live in the
   cache, so clearing it deleted the account's photo and the owner's, and the
   header fell back to an initial until Telegram happened to send the photo
   again (the owner card waits for the owner to change it).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANDROID_MAIN = REPO_ROOT / "android" / "app" / "src" / "main"
JAVA_DIR = ANDROID_MAIN / "java" / "com" / "vmore" / "app"
TEST_DIR = REPO_ROOT / "android" / "app" / "src" / "test" / "java" / "com" / "vmore" / "app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
#  1. File names inside Telegram
# --------------------------------------------------------------------------- #

def test_media_names_come_from_the_caption_or_the_date_not_an_internal_id():
    tg = _read(JAVA_DIR / "Tg.java")
    #: The placeholder that produced "vmore_4838" is gone.
    assert '"vmore_" + media.messageId' not in tg
    assert '"vmore_" + job.messageId' not in tg
    queue = _read(JAVA_DIR / "QueueService.java")
    assert '"vmore_" + job.messageId' not in queue
    #: The caption, and then the post date, name the file instead.
    assert "Format.stemFrom(media.caption, 48)" in tg
    assert "Format.datedName(media.kind, message.date, extension)" in tg
    assert "Format.displayName(media.name," in tg
    assert "Format.displayName(job.name," in queue


def test_photos_and_voice_notes_no_longer_carry_a_placeholder_name():
    tg = _read(JAVA_DIR / "Tg.java")
    assert 'media.name = "photo.jpg"' not in tg
    assert 'media.name = "voice_note.ogg"' not in tg
    assert 'media.name = "video_note.mp4"' not in tg
    #: A kind still gets a real extension when Telegram reports no MIME type.
    assert 'return ".jpg";' in tg and 'return ".mp4";' in tg


def test_the_upload_alias_keeps_the_original_name():
    tg = _read(JAVA_DIR / "Tg.java")
    assert '"vmore_" + System.currentTimeMillis()' not in tg
    #: Uniqueness comes from a one-shot folder, so the basename Telegram reads
    #: is exactly the file's real name.
    assert 'File slot = new File(LocalFiles.uploadScratchDir(app),' in tg
    assert 'File alias = new File(slot, name);' in tg
    assert "String name = Format.displayName(source.getName(), source.getName());" in tg
    #: The whole folder is removed with the copy — no litter in the cache.
    assert 'File uploadDir = folder.getParentFile();' in tg


def test_a_stale_queued_job_is_cleaned_on_the_way_out():
    queue = _read(JAVA_DIR / "QueueService.java")
    assert 'Format.displayName(job.name, "file_" + job.messageId)' in queue


def test_the_format_helpers_are_pure_and_unit_tested():
    fmt = _read(JAVA_DIR / "Format.java")
    for helper in ("public static String stemFrom(String text, int limit)",
                   "public static String datedName(String kind, long unixSeconds, String extension)",
                   "public static String displayName(String name, String fallback)"):
        assert helper in fmt, helper
    #: No Android type may sneak into a helper the JVM tests exercise.
    assert "import android." not in fmt
    tests = _read(TEST_DIR / "FormatTest.java")
    assert "aCaptionBecomesTheFileStem" in tests
    assert "theRetiredInternalPrefixIsStrippedEverywhere" in tests
    assert "unnamedMediaGetsAReadableDatedName" in tests


def test_the_caption_stem_is_safe_for_every_phone():
    fmt = _read(JAVA_DIR / "Format.java")
    #: Reserved characters and control characters are dropped, not escaped.
    for forbidden in ("char0 == '/'", "char0 == ':'", "char0 == '?'", "char0 < 0x20"):
        assert forbidden in fmt, forbidden
    assert 'while (stem.endsWith("."))' in fmt
    assert "while (stem.startsWith(\".\"))" in fmt


# --------------------------------------------------------------------------- #
#  2. Profile pictures outlive a cache clear
# --------------------------------------------------------------------------- #

def test_profile_pictures_live_outside_the_cache():
    files = _read(JAVA_DIR / "LocalFiles.java")
    avatars = files[files.index("static File avatarsDir(Context context)"):]
    avatars = avatars[:avatars.index("static File userDataRoot(Context context)")]
    assert "userDataRoot(context)" in avatars
    assert "cacheRoot(context)" not in avatars, "a cache clear must not delete avatars"
    #: User Data root is the app's private files directory.
    assert "File dir = context.getFilesDir();" in files
    #: Only the pictures moved; the media stays under Cache so the clear frees it.
    assert 'new File(cacheRoot(context), "avatars")' in files, "the old folder is still known"
    assert "static void migrateAvatars(Context context)" in files
    assert "static File legacyAvatarsDir(Context context)" in files


def test_a_picture_from_an_older_build_is_moved_not_lost():
    files = _read(JAVA_DIR / "LocalFiles.java")
    migrate = files[files.index("static void migrateAvatars(Context context)"):]
    migrate = migrate[:migrate.index("static File legacyAvatarNamed(")]
    assert "LocalFiles.copy(child.getAbsolutePath(), moved);" in migrate
    assert "if (!moved.exists())" in migrate
    assert "child.delete();" in migrate


def test_stored_paths_are_repaired_at_startup():
    prefs = _read(JAVA_DIR / "Prefs.java")
    assert "public static void repairAvatarPaths(Context context)" in prefs
    assert "LocalFiles.avatarFile(app)" in prefs
    assert "LocalFiles.developerAvatar(app)" in prefs
    assert "LocalFiles.legacyAvatarNamed(context, newFile)" in prefs

    app = _read(JAVA_DIR / "VmoreApp.java")
    assert "LocalFiles.migrateAvatars(this);" in app
    assert "Prefs.repairAvatarPaths(this);" in app
    #: Both run before any screen can read a path.
    assert app.index("Prefs.repairAvatarPaths(this);") < app.index("registerActivityLifecycleCallbacks")


def test_a_lost_picture_is_fetched_again_even_if_its_id_is_unchanged():
    """The owner's card must refill after an old build's cache clear."""
    dev = _read(JAVA_DIR / "Developer.java")
    assert "final boolean photoMissing = profile.avatar == null || profile.avatar.isEmpty();" in dev
    assert "&& (photoMissing" in dev
    #: cached() only reports a path that is really on disk.
    assert 'new File(avatar).exists()' in dev


def test_the_login_database_was_never_in_the_cache():
    """Clearing the cache must never log the account out either."""
    tg = _read(JAVA_DIR / "Tg.java")
    assert "File dbDir = new File(app.getFilesDir(), session);" in tg


def test_version_is_current_with_a_new_version_code():
    gradle = _read(REPO_ROOT / "android" / "app" / "build.gradle")
    vmore = _read(JAVA_DIR / "Vmore.java")
    assert "versionCode 22" in gradle
    assert 'versionName "2.3.5"' in gradle
    assert 'VERSION = "2.3.5"' in vmore
