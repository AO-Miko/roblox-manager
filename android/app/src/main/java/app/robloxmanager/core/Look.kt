package app.robloxmanager.core

import kotlin.math.pow
import kotlin.math.roundToInt

/** What the person chose in Settings > Looks: the theme ("dark", "light" or "system"), the accent colour and the text size in percent. */
data class LookChoice(val mode: String = Look.DEFAULT_MODE, val accent: String = Look.DEFAULT_ACCENT, val size: Int = Look.DEFAULT_SIZE) {
    companion object {
        fun load(prefs: Prefs) = LookChoice(Look.mode(prefs.str("ui.theme", Look.DEFAULT_MODE)), Look.accent(prefs.str("ui.accent", Look.DEFAULT_ACCENT)), Look.size(prefs.double("ui.textSize", 100.0).toInt()))
    }
}

/** The colours of the app: a dark and a light theme and five accent colours (the same names and values as the desktop app's theme.py). Pure arithmetic, so it is tested without a phone. */
object Look {
    const val DEFAULT_MODE = "dark"
    const val DEFAULT_ACCENT = "blue"
    const val DEFAULT_SIZE = 100
    val MODES = listOf("dark", "light", "system")
    val ACCENTS = listOf("blue", "green", "purple", "orange", "pink")
    val SIZES = listOf(90, 100, 110, 125)

    private val DARK = mapOf(
        "bg" to "#12141a", "surface" to "#1a1d25", "surface2" to "#222631", "surface3" to "#2c313e", "border" to "#2a2f3b", "border2" to "#3b4252",
        "text" to "#e8ebf1", "muted" to "#98a1b2", "faint" to "#6b7487", "success" to "#3fcf86", "warn" to "#f0b040", "danger" to "#f26b6b", "info" to "#62b4ff",
        "dangerDim" to "#3d2227", "onDim" to "#ffffff", "orange" to "#ef8a5b", "violet" to "#b59bff",
    )
    private val LIGHT = mapOf(
        "bg" to "#f3f5f9", "surface" to "#ffffff", "surface2" to "#eef1f6", "surface3" to "#e1e6ee", "border" to "#dbe0e9", "border2" to "#c3cbd8",
        "text" to "#171b24", "muted" to "#566073", "faint" to "#8d97a8", "success" to "#157a45", "warn" to "#91560a", "danger" to "#c42b2b", "info" to "#1a62c4",
        "dangerDim" to "#fbe4e4", "onDim" to "#171b24", "orange" to "#a8480f", "violet" to "#6b3fd1",
    )
    /** accent -> (fill in the dark theme, fill in the light theme). White text on a fill is always at least 4.5 : 1. */
    private val FILLS = mapOf(
        "blue" to ("#266fd8" to "#1a64e0"), "green" to ("#18814a" to "#12834a"), "purple" to ("#7650e6" to "#6a4be0"),
        "orange" to ("#b55808" to "#b85a00"), "pink" to ("#cb3779" to "#c4287a"),
    )

    fun mode(s: String?): String = if (s in MODES) s!! else DEFAULT_MODE
    fun accent(s: String?): String = if (s in ACCENTS) s!! else DEFAULT_ACCENT
    /** The size the design has that is nearest to n. */
    fun size(n: Int?): Int = if (n == null) DEFAULT_SIZE else SIZES.minByOrNull { kotlin.math.abs(it - n) }!!
    fun isDark(mode: String, systemDark: Boolean): Boolean = when (mode) { "light" -> false; "system" -> systemDark; else -> true }

    fun hex(s: String): Int = (0xFF000000L or s.removePrefix("#").toLong(16)).toInt()

    /** The colour t of the way from a to b. */
    fun mix(a: Int, b: Int, t: Double): Int {
        fun ch(shift: Int) = (((a shr shift) and 0xFF) * (1 - t) + ((b shr shift) and 0xFF) * t).roundToInt().coerceIn(0, 255)
        return (0xFF shl 24) or (ch(16) shl 16) or (ch(8) shl 8) or ch(0)
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
