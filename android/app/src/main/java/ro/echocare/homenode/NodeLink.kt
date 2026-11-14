package ro.echocare.homenode

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.content.Context
import android.util.Log
import java.util.UUID
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull

/**
 * The phone's GATT client for one home node (04 §3). Android runs one GATT operation at a time,
 * so every operation waits for its callback under one lock. `autoConnect` keeps reconnecting
 * after the node goes out of range, which is what P20 expects of the phone.
 *
 * Bluetooth permissions are checked by the screen and the service before this is made.
 */
@SuppressLint("MissingPermission")
class NodeLink(
    private val context: Context,
    private val address: String,
    private val listener: Listener
) : BluetoothGattCallback() {
    interface Listener {
        fun onConnected(connected: Boolean)
        fun onNotified(characteristic: UUID, text: String)
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val ops = Mutex()
    private var pending: CompletableDeferred<Int>? = null
    private var gatt: BluetoothGatt? = null

    @Volatile var connected = false
        private set

    fun connect() {
        val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter ?: return
        val device = adapter.getRemoteDevice(address)
        gatt = device.connectGatt(context, true, this, BluetoothDevice.TRANSPORT_LE)
    }

    fun close() {
        scope.cancel()
        gatt?.close()
        gatt = null
        connected = false
    }

    /** Writes a small text to one of the node's characteristics; false when it did not go. */
    suspend fun write(characteristic: UUID, text: String): Boolean {
        val g = gatt ?: return false
        val char = g.getService(NodeUuids.SERVICE)?.getCharacteristic(characteristic) ?: return false
        return run {
            g.writeCharacteristic(
                char,
                text.toByteArray(),
                BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            ) == BluetoothStatusCodes.SUCCESS
        } == BluetoothGatt.GATT_SUCCESS
    }

    private suspend fun run(start: () -> Boolean): Int = ops.withLock {
        val done = CompletableDeferred<Int>()
        pending = done
        if (!start()) return@withLock -1
        withTimeoutOrNull(OP_TIMEOUT_MS) { done.await() } ?: -1
    }

    private suspend fun setUp(g: BluetoothGatt) {
        run { g.requestMtu(MTU) } // a fall's 37-point scan needs more than 20 bytes
        if (run { g.discoverServices() } != BluetoothGatt.GATT_SUCCESS) {
            Log.w(TAG, "no services on $address")
            return
        }
        val service = g.getService(NodeUuids.SERVICE) ?: run {
            Log.w(TAG, "$address is not an EchoCare node")
            return
        }
        for (uuid in NodeUuids.NOTIFIED) {
            val char = service.getCharacteristic(uuid) ?: continue
            g.setCharacteristicNotification(char, true)
            val cccd = char.getDescriptor(NodeUuids.CCCD) ?: continue
            run {
                g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) ==
                    BluetoothStatusCodes.SUCCESS
            }
        }
        connected = true
        listener.onConnected(true)
    }

    override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
        if (newState == BluetoothProfile.STATE_CONNECTED) {
            scope.launch { setUp(g) }
        } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
            connected = false
            pending?.complete(-1)
            listener.onConnected(false)
        }
    }

    override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) {
        pending?.complete(status)
    }

    override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
        pending?.complete(status)
    }

    override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
        pending?.complete(status)
    }

    override fun onCharacteristicWrite(
        g: BluetoothGatt,
        c: BluetoothGattCharacteristic,
        status: Int
    ) {
        pending?.complete(status)
    }

    override fun onCharacteristicChanged(
        g: BluetoothGatt,
        c: BluetoothGattCharacteristic,
        value: ByteArray
    ) {
        listener.onNotified(c.uuid, value.decodeToString())
    }

    private companion object {
        const val TAG = "NodeLink"
        const val MTU = 185
        const val OP_TIMEOUT_MS = 5000L
    }
}
