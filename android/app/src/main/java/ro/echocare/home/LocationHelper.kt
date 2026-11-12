package ro.echocare.home

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.core.content.ContextCompat

/**
 * The phone's last known location, attached to the events we post (UC-09 §5, 04 §3). Null when the
 * senior has not allowed location, no provider has a fix yet, or Play Services is unavailable.
 *
 * shortcut: LocationManager.getLastKnownLocation is best-effort — may be stale by minutes.
 * Upgrade to FusedLocationProviderClient (+ play-services-location dep) when staleness matters.
 */
@Suppress("MissingPermission") // We guard with checkSelfPermission on the same line
fun lastKnownLocation(context: Context): Location? {
    if (ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.ACCESS_COARSE_LOCATION
        ) != PackageManager.PERMISSION_GRANTED
    ) {
        return null
    }
    val lm = context.getSystemService(LocationManager::class.java) ?: return null
    return lm.allProviders
        .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
        .maxByOrNull { it.time }
}
