package ro.echocare.homenode

import android.content.Context

/** The one node this phone relays, by Bluetooth address (UC-15); null when none. */
object NodePrefs {
    private const val FILE = "home_node"
    private const val ADDRESS = "address"

    fun address(context: Context): String? =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(ADDRESS, null)

    fun save(context: Context, address: String?) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().apply {
            if (address == null) remove(ADDRESS) else putString(ADDRESS, address)
        }.apply()
    }
}
