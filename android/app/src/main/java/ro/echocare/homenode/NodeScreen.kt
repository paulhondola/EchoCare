package ro.echocare.homenode

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.ParcelUuid
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.util.Locale
import ro.echocare.R
import ro.echocare.home.HomeScaffold
import ro.echocare.ui.Banner
import ro.echocare.ui.FieldRow
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/** One node found by the scan: its address and its advertised name. */
data class FoundNode(val address: String, val name: String?)

/** What the room state reads as on the senior's phone (P26); unknown values show as they are. */
val ROOM_STATE_LABELS = mapOf(
    "ok" to R.string.room_ok,
    "cold_soon" to R.string.room_cold_soon,
    "cold" to R.string.room_cold,
    "hot_soon" to R.string.room_hot_soon,
    "hot" to R.string.room_hot
)

/**
 * „Conectează senzorul din casă” (UC-15): scans for boxes advertising the EchoCare service,
 * lists them by the last four characters of their address (printed on the box), and relays the
 * chosen one. Once connected it shows the room and offers to forget the box.
 */
@Composable
fun NodeScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    var allowed by remember { mutableStateOf(NodeService.bluetoothAllowed(context)) }
    var saved by remember { mutableStateOf(NodePrefs.address(context)) }
    val status by NodeService.status.collectAsState()
    val ask = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { allowed = NodeService.bluetoothAllowed(context) }

    HomeScaffold(stringResource(R.string.node_title), onBack = onBack, menu = {}) {
        Column(
            Modifier
                .verticalScroll(rememberScrollState())
                .fillMaxWidth()
                .wrapContentWidth(Alignment.CenterHorizontally)
                .widthIn(max = 600.dp)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            when {
                !allowed -> {
                    Text(stringResource(R.string.node_permission))
                    SnButton(stringResource(R.string.node_allow), {
                        ask.launch(
                            arrayOf(
                                Manifest.permission.BLUETOOTH_SCAN,
                                Manifest.permission.BLUETOOTH_CONNECT
                            )
                        )
                    }, Modifier.fillMaxWidth(), kind = Kind.Link)
                }
                saved != null -> Connected(saved!!, status) {
                    NodeService.stop(context)
                    NodePrefs.save(context, null)
                    saved = null
                }
                else -> Scan(context) { found ->
                    bond(context, found.address)
                    NodePrefs.save(context, found.address)
                    saved = found.address
                    NodeService.start(context)
                }
            }
        }
    }
}

@Composable
private fun Connected(address: String, status: NodeService.Status?, onForget: () -> Unit) {
    val connected = status?.connected == true
    Banner(
        stringResource(if (connected) R.string.node_connected else R.string.node_connecting),
        if (connected) Tone.Verde else Tone.Muted
    )
    FieldRow(stringResource(R.string.node_box)) { Text(boxLabel(address)) }
    status?.temperature?.let {
        FieldRow(stringResource(R.string.node_room)) {
            Text(String.format(Locale.forLanguageTag("ro"), "%.1f °C", it))
        }
    }
    status?.roomState?.let { state ->
        FieldRow(stringResource(R.string.node_room_state)) {
            Text(ROOM_STATE_LABELS[state]?.let { stringResource(it) } ?: state)
        }
    }
    SectionLabel(stringResource(R.string.node_other), Modifier.padding(top = 16.dp))
    Text(stringResource(R.string.node_forget_hint), color = Palette.FgMuted)
    SnButton(
        stringResource(R.string.node_forget),
        onForget,
        Modifier.fillMaxWidth(),
        kind = Kind.Outline
    )
}

@SuppressLint("MissingPermission") // asked for by NodeScreen before this is shown
@Composable
private fun Scan(context: Context, onPick: (FoundNode) -> Unit) {
    val found = remember { mutableStateListOf<FoundNode>() }
    var scanning by remember { mutableStateOf(true) }
    DisposableEffect(Unit) {
        val scanner = context.getSystemService(BluetoothManager::class.java)
            ?.adapter?.bluetoothLeScanner
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val node = FoundNode(result.device.address, result.scanRecord?.deviceName)
                if (found.none { it.address == node.address }) found.add(node)
            }

            override fun onScanFailed(errorCode: Int) {
                scanning = false
            }
        }
        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(NodeUuids.SERVICE)).build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        if (scanner == null) scanning = false else scanner.startScan(listOf(filter), settings, callback)
        onDispose { scanner?.stopScan(callback) }
    }
    Text(stringResource(R.string.node_scan_hint))
    if (found.isEmpty()) {
        Text(
            stringResource(if (scanning) R.string.node_scanning else R.string.node_none),
            color = Palette.FgMuted
        )
    }
    found.forEach { node ->
        SnButton(
            stringResource(R.string.node_pick, node.name ?: "Ecou", boxLabel(node.address)),
            { onPick(node) },
            Modifier.fillMaxWidth()
        )
    }
}

/** Bonds with the node, as P20 asks; a node that refuses bonding is still relayed. */
@SuppressLint("MissingPermission")
private fun bond(context: Context, address: String) {
    runCatching {
        context.getSystemService(BluetoothManager::class.java)?.adapter
            ?.getRemoteDevice(address)?.createBond()
    }
}
