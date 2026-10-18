package com.vmore.app;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;

import java.security.MessageDigest;

/**
 * The signature of the APK that is actually installed.
 *
 * Android judges an update by this value and nothing else, so it is the one
 * thing worth checking when an APK will not install over the app that is already
 * there.  Every release note carries the fingerprint the build was signed with,
 * and Settings shows the fingerprint of what is on the phone — the two must
 * match, and when they do not, the APK was signed with a different key (or is
 * not Vmore at all).
 */
final class AppSignature {

    private AppSignature() {
    }

    /** The certificate's SHA-256 in lowercase hex, or "" when unreadable. */
    static String fingerprint(Context context) {
        try {
            PackageManager manager = context.getPackageManager();
            String packageName = context.getPackageName();
            android.content.pm.Signature[] certificates = certificates(manager, packageName);
            if (certificates == null || certificates.length == 0) {
                return "";
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(certificates[0].toByteArray());
            StringBuilder text = new StringBuilder();
            for (byte value : hash) {
                String pair = Integer.toHexString(value & 0xFF);
                if (pair.length() == 1) {
                    text.append('0');
                }
                text.append(pair);
            }
            return text.toString();
        } catch (Exception error) {
            return "";
        }
    }

    private static android.content.pm.Signature[] certificates(PackageManager manager, String packageName)
            throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageInfo info = manager.getPackageInfo(packageName,
                    PackageManager.GET_SIGNING_CERTIFICATES);
            android.content.pm.SigningInfo signing = info.signingInfo;
            if (signing == null) {
                return null;
            }
            //: A history is what an installed app has; multiple signers only
            //: happens for apps that were signed by more than one key at once.
            return signing.hasMultipleSigners()
                    ? signing.getApkContentsSigners()
                    : signing.getSigningCertificateHistory();
        }
        //noinspection deprecation
        PackageInfo info = manager.getPackageInfo(packageName, PackageManager.GET_SIGNATURES);
        //noinspection deprecation
        return info.signatures;
    }

    /** "a2c63a18 2375bd5c" — short enough for a settings row, and copyable in full. */
    static String shortForm(String fingerprint) {
        if (fingerprint == null || fingerprint.length() < 16) {
            return "";
        }
        return fingerprint.substring(0, 8) + " " + fingerprint.substring(8, 16);
    }

    /** The fingerprint in the groups people compare by eye. */
    static String grouped(String fingerprint) {
        if (fingerprint == null || fingerprint.length() < 2) {
            return "";
        }
        StringBuilder text = new StringBuilder();
        for (int index = 0; index + 1 < fingerprint.length(); index += 2) {
            if (text.length() > 0) {
                text.append(':');
            }
            text.append(fingerprint, index, index + 2);
        }
        return text.toString();
    }
}
