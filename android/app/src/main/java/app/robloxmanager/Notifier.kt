package app.robloxmanager

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

/** Friend alerts as Android notifications (the permission to show them is asked for when alerts are switched on, on Android 13 and newer). */
object Notifier {
    const val CHANNEL = "friends"

    fun allowed(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < 33 || ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** What stops a notification from being shown, in plain words, or null when nothing does. The arguments are what the system says:
     *  whether the app may show notifications, whether they are on for the app, how important the "Friend alerts" channel is (null: not made yet), and the Do Not Disturb filter. */
    fun explain(permission: Boolean, appEnabled: Boolean, channelImportance: Int?, filter: Int): String? = when {
        !permission -> "The app is not allowed to show notifications. Allow them in the phone's settings."
        !appEnabled -> "Notifications are switched off for this app in the phone's settings."
        channelImportance == NotificationManager.IMPORTANCE_NONE -> "The \"Friend alerts\" notifications are switched off in the phone's settings."
        filter == NotificationManager.INTERRUPTION_FILTER_NONE || filter == NotificationManager.INTERRUPTION_FILTER_ALARMS ->
            "Do Not Disturb is on, so alerts may arrive silently or not be shown."
        else -> null
    }

    /** Asks the phone: [explain] with the phone's own answers. */
    fun problem(ctx: Context): String? {
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return null
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Friend alerts", NotificationManager.IMPORTANCE_DEFAULT))      // (does nothing to a channel the person already changed)
        return explain(allowed(ctx), nm.areNotificationsEnabled(), nm.getNotificationChannel(CHANNEL)?.importance, nm.currentInterruptionFilter)
    }

    /** The phone's page where this app's notifications are switched on and off. */
    fun settingsIntent(ctx: Context): Intent =
        Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, ctx.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    fun show(ctx: Context, text: String) {
        if (!allowed(ctx)) return
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Friend alerts", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = android.app.Notification.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_chat).setContentTitle("Roblox Manager").setContentText(text).setContentIntent(open).setAutoCancel(true).build()
        nm.notify(text.hashCode(), n)
    }
}
