package com.vmore.app;

import android.content.Context;

import java.io.File;

/**
 * The person behind Vmore, as the signed-in account sees them.
 *
 * The owner asked for his own profile at the end of Settings — his picture, his
 * name, his bio and a button that opens a direct chat — and for it to be shown
 * from the user's own session rather than from a copy baked into the APK.  So
 * the profile is read through {@link Tg#userProfile} once per visit, and what
 * came back is kept on the phone: the card paints instantly from that copy and
 * quietly updates when Telegram answers.
 *
 * The fallback values are used only until the first answer arrives (or when the
 * phone is offline), so the card is never empty.
 */
final class Developer {

    /** The handle whose profile the card shows. */
    static final String USERNAME = Vmore.DEVELOPER;

    /** Shown until Telegram answers with the real name. */
    static final String DISPLAY_NAME = "Xyr Developer";

    /** Shown until Telegram answers with the real bio. */
    static final String FALLBACK_BIO =
            "Building and maintaining Vmore. Write for help, an idea or a bug report.";

    /** One reading of the profile. */
    static final class Profile {
        String name = DISPLAY_NAME;
        String username = USERNAME;
        String bio = FALLBACK_BIO;
        /** Absolute path of the picture on this phone, or "". */
        String avatar = "";
    }

    private Developer() {
    }

    static String webUrl() {
        return "https://t.me/" + USERNAME;
    }

    /** tg:// opens the app; the https link is the fallback when it cannot. */
    static String deepLink() {
        return "tg://resolve?domain=" + USERNAME;
    }

    /** The last reading saved on the phone, ready before any network call. */
    static Profile cached(Context context) {
        Profile profile = new Profile();
        String name = Prefs.developerName(context);
        String bio = Prefs.developerBio(context);
        if (name != null && !name.isEmpty()) {
            profile.name = name;
        }
        if (bio != null && !bio.isEmpty()) {
            profile.bio = bio;
        }
        String avatar = Prefs.developerAvatar(context);
        if (avatar != null && !avatar.isEmpty() && new File(avatar).exists()) {
            profile.avatar = avatar;
        }
        return profile;
    }

    /**
     * Asks Telegram for the profile and saves what it answers.
     *
     * The picture is downloaded only when the account's picture changed, so a
     * second visit costs one profile read and no bytes.
     */
    static void refresh(final Context context, final Tg.Cb<Profile> done) {
        Tg.get(context).userProfile(USERNAME, new Tg.Cb<Tg.Profile>() {
            @Override
            public void ok(Tg.Profile value) {
                final Profile profile = cached(context);
                if (value.name != null && !value.name.isEmpty()) {
                    profile.name = value.name;
                }
                if (value.username != null && !value.username.isEmpty()) {
                    profile.username = value.username;
                }
                if (value.bio != null && !value.bio.isEmpty()) {
                    profile.bio = value.bio;
                }
                final boolean photoChanged = value.photoFileId != 0
                        && value.photoFileId != Prefs.developerAvatarFile(context);
                if (!photoChanged) {
                    Prefs.saveDeveloper(context, profile.name, profile.bio,
                            profile.avatar, value.photoFileId == 0
                                    ? Prefs.developerAvatarFile(context) : value.photoFileId);
                    done.ok(profile);
                    return;
                }
                if (value.photoPath != null && !value.photoPath.isEmpty()) {
                    profile.avatar = save(context, value.photoPath, value.photoFileId);
                    Prefs.saveDeveloper(context, profile.name, profile.bio,
                            profile.avatar, value.photoFileId);
                    done.ok(profile);
                    return;
                }
                Tg.get(context).downloadFile(value.photoFileId, null, new Tg.Cb<Integer>() {
                    @Override
                    public void ok(Integer fileId) {
                        String path = Tg.get(context).localPath(fileId);
                        if (path != null && !path.isEmpty()) {
                            profile.avatar = save(context, path, value.photoFileId);
                        }
                        //: The picture is on the phone now; the download watch
                        //: has no reason to stay registered.
                        Tg.get(context).releaseDownload(fileId);
                        Prefs.saveDeveloper(context, profile.name, profile.bio,
                                profile.avatar, value.photoFileId);
                        done.ok(profile);
                    }

                    @Override
                    public void fail(String message) {
                        //: A missing picture is not worth an error on screen;
                        //: the card keeps the initial it already shows.
                        Prefs.saveDeveloper(context, profile.name, profile.bio,
                                profile.avatar, Prefs.developerAvatarFile(context));
                        done.ok(profile);
                    }
                });
            }

            @Override
            public void fail(String message) {
                done.fail(message);
            }
        });
    }

    /** Copies the picture into app storage under a stable name. */
    private static String save(Context context, String sourcePath, int fileId) {
        File copied = LocalFiles.copy(sourcePath, LocalFiles.developerAvatar(context));
        if (copied != null) {
            Prefs.saveDeveloper(context, Prefs.developerName(context),
                    Prefs.developerBio(context), copied.getAbsolutePath(), fileId);
            return copied.getAbsolutePath();
        }
        return "";
    }
}
