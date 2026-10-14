package com.vmore.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

/**
 * The phone's own state: the network the queue may use, and whether it is
 * allowed to keep working in the background.
 *
 * The queue asks {@link #blocker} before every job and simply waits when the
 * answer is not empty, so "only on Wi-Fi" and "only while charging" are real
 * rules rather than a first-job check.
 */
final class Net {

    private Net() {
    }

    /** True on Wi-Fi (or on a phone where there is no Wi-Fi radio at all). */
    static boolean onWifi(Context context) {
        ConnectivityManager manager =
                (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) {
            return true;
        }
        Network network = manager.getActiveNetwork();
        if (network == null) {
            return false;
        }
        NetworkCapabilities caps = manager.getNetworkCapabilities(network);
        if (caps == null) {
            return false;
        }
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
            return true;
        }
        return false;
    }

    static boolean online(Context context) {
        ConnectivityManager manager =
                (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) {
            return true;
        }
        Network network = manager.getActiveNetwork();
        NetworkCapabilities caps = network == null ? null
                : manager.getNetworkCapabilities(network);
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    static boolean charging(Context context) {
        Intent intent = context.registerReceiver(null,
                new android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (intent == null) {
            return true;
        }
        int status = intent.getIntExtra(android.os.BatteryManager.EXTRA_STATUS, -1);
        return status == android.os.BatteryManager.BATTERY_STATUS_CHARGING
                || status == android.os.BatteryManager.BATTERY_STATUS_FULL;
    }

    /**
     * The reason the queue should wait right now, in the user's words, or an
     * empty string when it may go ahead.
     */
    static String blocker(Context context) {
        if (!online(context)) {
            return "waiting for a connection";
        }
        if (Prefs.wifiOnly(context) && !onWifi(context)) {
            return "waiting for Wi-Fi";
        }
        if (Prefs.chargingOnly(context) && !charging(context)) {
            return "waiting for the charger";
        }
        return "";
    }

    /** The same answer for the scheduler, before the first job starts. */
    static String scheduleBlocker(Context context) {
        long at = Prefs.scheduleAt(context);
        if (at <= 0L) {
            return "";
        }
        long now = System.currentTimeMillis();
        if (at <= now) {
            if (Prefs.scheduleDaily(context)) {
                long next = at + 24L * 60L * 60L * 1000L;
                while (next <= now) {
                    next += 24L * 60L * 60L * 1000L;
                }
                Prefs.setScheduleAt(context, next);
                return "";
            }
            Prefs.setScheduleAt(context, 0L);
            return "";
        }
        return "starts at " + Format.when(at);
    }

    // ------------------------------------------------------- battery saver //

    /** True when Android is allowed to freeze Vmore in the background. */
    static boolean batteryRestricted(Context context) {
        PowerManager power = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        if (power == null) {
            return false;
        }
        String packageName = context.getPackageName();
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                && !power.isIgnoringBatteryOptimizations(packageName);
    }

    /** The one system dialog that keeps a long queue alive. */
    static void askForBatteryFreedom(Activity activity) {
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            intent.setData(Uri.parse("package:" + activity.getPackageName()));
            activity.startActivity(intent);
        } catch (Exception error) {
            try {
                activity.startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            } catch (Exception ignored) {
                Ui.toast(activity, "Android settings could not be opened");
            }
        }
    }
}
