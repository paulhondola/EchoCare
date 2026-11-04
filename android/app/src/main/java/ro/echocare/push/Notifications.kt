package ro.echocare.push

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import ro.echocare.MainActivity
import ro.echocare.R

/** The alerts channel, high importance so an alert sounds and shows on top (03 §7). */
fun createAlertChannel(context: Context) {
    val channel = NotificationChannel(
        ALERT_CHANNEL,
        context.getString(R.string.alerts_channel),
        NotificationManager.IMPORTANCE_HIGH
    ).apply { description = context.getString(R.string.alerts_channel_description) }
    context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
}

fun notificationsAllowed(context: Context): Boolean = ContextCompat.checkSelfPermission(
    context,
    Manifest.permission.POST_NOTIFICATIONS
) == PackageManager.PERMISSION_GRANTED

/**
 * An alert that arrived while the app was in front, where Firebase hands it to the app instead of
 * the tray. It looks like the tray's own and opens the app with the same extras (04 §6).
 */
fun showAlert(context: Context, data: Map<String, String>) {
    if (!notificationsAllowed(context)) return
    val extras = data.filterKeys { it in PUSH_KEYS }
    val intent = Intent(context, MainActivity::class.java).apply {
        flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        extras.forEach { (key, value) -> putExtra(key, value) }
    }
    val open = PendingIntent.getActivity(
        context,
        // One per senior or incident, so a second alert does not take over the first one's extras
        extras.hashCode(),
        intent,
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )
    val notification = NotificationCompat.Builder(context, ALERT_CHANNEL)
        .setSmallIcon(R.drawable.ic_notification)
        .setContentTitle(context.getString(R.string.alert_title))
        .setContentText(context.getString(R.string.alert_text))
        .setPriority(NotificationCompat.PRIORITY_HIGH)
        .setCategory(NotificationCompat.CATEGORY_MESSAGE)
        .setAutoCancel(true)
        .setContentIntent(open)
        .build()
    try {
        // Tagged by senior: a later alert about the same senior replaces the earlier one
        NotificationManagerCompat.from(context).notify(extras["senior_id"], 1, notification)
    } catch (e: SecurityException) {
        // The permission was taken back between the check and the post
    }
}
