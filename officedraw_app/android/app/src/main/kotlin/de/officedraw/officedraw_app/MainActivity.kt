package de.officedraw.officedraw_app

import android.os.SystemClock
import android.util.Log
import android.view.KeyEvent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var penChannel: MethodChannel? = null
    private var lastToggle = 0L

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        penChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "officedraw/pen")
    }

    // Pens like the HONOR Magic-Pencil report their double tap as a key press from a
    // Bluetooth "keyboard" that belongs to the pen. Android 14 also has stylus button key codes.
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (!isPenKey(event)) return super.dispatchKeyEvent(event)
        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
            Log.d(TAG, "pen key ${event.keyCode} from ${event.device?.name}")
            val now = SystemClock.uptimeMillis()
            // One double tap may send several keys; treat them as a single toggle.
            if (now - lastToggle > DEBOUNCE_MS) {
                lastToggle = now
                penChannel?.invokeMethod("doubleTap", null)
            }
        }
        return true
    }

    private fun isPenKey(event: KeyEvent): Boolean {
        if (event.keyCode in STYLUS_BUTTON_KEYS) return true
        val name = event.device?.name ?: return false
        return name.contains("pencil", ignoreCase = true) || name.contains("stylus", ignoreCase = true)
    }

    companion object {
        private const val TAG = "OfficeDrawPen"
        private const val DEBOUNCE_MS = 400L
        // KEYCODE_STYLUS_BUTTON_PRIMARY, _SECONDARY, _TERTIARY, _TAIL (API 34)
        private val STYLUS_BUTTON_KEYS = setOf(308, 309, 310, 311)
    }
}
