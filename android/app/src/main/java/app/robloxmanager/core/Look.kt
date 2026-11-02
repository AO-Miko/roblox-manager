package app.robloxmanager.core

import kotlin.math.pow
import kotlin.math.roundToInt

/** What the person chose in Settings > Looks: the theme ("dark", "light" or "system"), the accent colour and the text size in percent. */
data class LookChoice(val mode: String = Look.DEFAULT_MODE, val accent: String = Look.DEFAULT_ACCENT, val size: Int = Look.DEFAULT_SIZE) {
    companion object {
        fun load(prefs: Prefs) = LookChoice(Look.mode(prefs.str("ui.theme", Look.DEFAULT_MODE)), Look.accent(prefs.str("ui.accent", Look.DEFAULT_ACCENT)), Look.size(prefs.double("ui.textSize", 100.0).toInt()))
    }
}

/** The colours of the app ("Ink and paper"): a dark and a light theme and five accent colours (the same names and values as the desktop app's theme.py). Pure arithmetic, so it is tested without a phone. */
object Look {
    const val DEFAULT_MODE = "dark"
    const val DEFAULT_ACCENT = "ember"
    const val DEFAULT_SIZE = 100
    val MODES = listOf("dark", "light", "system")
    val ACCENTS = listOf("ember", "teal", "iris", "gold", "rose")
    val SIZES = listOf(90, 100, 110, 125)

    private val DARK = mapOf(
        "bg" to "#0d0d0f", "surface" to "#151518", "surface2" to "#1d1d21", "surface3" to "#28282d", "border" to "#26262b", "border2" to "#3a3a41",
        "text" to "#f4f1ea", "muted" to "#aaa69d", "faint" to "#7d7a73", "success" to "#5fd38d", "warn" to "#f2b84b", "danger" to "#ff7a70", "info" to "#7cb8ff",
        "dangerDim" to "#3a1d1c", "onDim" to "#ffffff", "orange" to "#f08a5d", "violet" to "#b9a3ff",
    )
    private val LIGHT = mapOf(
        "bg" to "#f5f2ea", "surface" to "#fbfaf6", "surface2" to "#ece8dd", "surface3" to "#ddd8ca", "border" to "#e0dbcd", "border2" to "#c4bead",
        "text" to "#1a1814", "muted" to "#5a564c", "faint" to "#8c877a", "success" to "#17733f", "warn" to "#8a5100", "danger" to "#b42318", "info" to "#1a5cb8",
        "dangerDim" to "#fbe3df", "onDim" to "#1a1814", "orange" to "#a03d0a", "violet" to "#6a3dc9",
    )
    /** accent -> (fill in the dark theme, fill in the light theme). White text on a fill is always at least 4.5 : 1. */
    private val FILLS = mapOf(
        "ember" to ("#c2410c" to "#b93a08"), "teal" to ("#0f766e" to "#0d6e66"), "iris" to ("#5b4bd8" to "#5040c8"),
        "gold" to ("#a16207" to "#8f5706"), "rose" to ("#be123c" to "#b01036"),
    )

    fun mode(s: String?): String = if (s in MODES) s!! else DEFAULT_MODE
    fun accent(s: String?): String = if (s in ACCENTS) s!! else DEFAULT_ACCENT
    /** The size the design has that is nearest to n. */
    fun size(n: Int?): Int = if (n == null) DEFAULT_SIZE else SIZES.minByOrNull { kotlin.math.abs(it - n) }!!
    fun isDark(mode: String, systemDark: Boolean): Boolean = when (mode) { "light" -> false; "system" -> systemDark; else -> true }

    fun hex(s: String): Int = (0xFF000000L or s.removePrefix("#").toLong(16)).toInt()

    /** The colour t of the way from a to b. */
    fun mix(a: Int, b: Int, t: Double): Int {
        fun ch(shift: Int): Int {
            val from = ((a shr shift) and 0xFF).toDouble()
            val to = ((b shr shift) and 0xFF).toDouble()
            return ((from * (1.0 - t)) + (to * t)).roundToInt().coerceIn(0, 255)
        }
        val alpha = 0xFF shl 24
        val red = ch(16) shl 16
        val green = ch(8) shl 8
        return alpha or red or green or ch(0)
    }

    fun luminance(c: Int): Double {
        fun f(shift: Int): Double { val v = ((c shr shift) and 0xFF) / 255.0; return if (v <= 0.03928) v / 12.92 else ((v + 0.055) / 1.055).pow(2.4) }
        return 0.2126 * f(16) + 0.7152 * f(8) + 0.0722 * f(0)
    }

    /** WCAG contrast ratio of two colours (1 to 21); text wants 4.5 or more. */
    fun contrast(a: Int, b: Int): Double {
        val la = luminance(a); val lb = luminance(b)
        return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
    }

    /** Every colour of a theme with an accent colour, as 0xAARRGGBB. */
    fun palette(dark: Boolean, name: String): Map<String, Int> {
        val p = (if (dark) DARK else LIGHT).mapValues { hex(it.value) }.toMutableMap()
        val pair = FILLS[accent(name)]!!
        val fill = hex(if (dark) pair.first else pair.second)
        val white = hex("#ffffff"); val black = hex("#000000")
        p["fill"] = fill                                                    // buttons, the selected switch: white text on it
        p["fillHover"] = mix(fill, black, 0.10)
        p["accentDim"] = mix(fill, p["bg"]!!, if (dark) 0.72 else 0.84)      // the selected item in a bar or list
        p["accent"] = if (dark) mix(fill, white, 0.38) else mix(fill, black, 0.10)     // the accent as a colour for icons, links and text on a surface
        p["onAccent"] = white
        return p
    }
}
