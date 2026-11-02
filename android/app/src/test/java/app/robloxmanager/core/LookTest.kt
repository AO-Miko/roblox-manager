package app.robloxmanager.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class LookTest {
    private fun prefs() = Prefs(File.createTempFile("prefs", ".json").also { it.delete(); it.deleteOnExit() })

    @Test fun everyColourIsReadableInBothThemesAndWithEveryAccent() {
        val low = ArrayList<String>()
        for (dark in listOf(true, false)) for (accent in Look.ACCENTS) {
            val p = Look.palette(dark, accent)
            val label = (if (dark) "dark " else "light ") + accent
            fun c(name: String) = p.getValue(name)
            fun need(text: String, on: String, min: Double) { val r = Look.contrast(c(text), c(on)); if (r < min) low.add("$label: $text on $on = ${"%.1f".format(r)}") }
            for (s in listOf("bg", "surface", "surface2", "surface3")) for (t in listOf("text", "muted")) need(t, s, 4.5)
            for (s in listOf("bg", "surface", "surface2")) for (t in listOf("success", "warn", "danger", "info", "orange", "violet", "accent")) need(t, s, 4.5)
            for (fill in listOf("fill", "fillHover")) need("onAccent", fill, 4.5)
            need("onDim", "accentDim", 7.0)
            need("danger", "dangerDim", 4.5)
        }
        assertTrue(low.toString(), low.isEmpty())
    }

    @Test fun contrastOfBlackOnWhiteIs21() {
        assertEquals(21.0, Look.contrast(Look.hex("#000000"), Look.hex("#ffffff")), 0.01)
        assertEquals(1.0, Look.contrast(Look.hex("#336699"), Look.hex("#336699")), 0.0)
    }

    @Test fun theDarkAndTheLightThemeAreDifferentAndAccentsChangeTheFill() {
        assertNotEquals(Look.palette(true, "blue")["bg"], Look.palette(false, "blue")["bg"])
        assertEquals(Look.palette(true, "blue").keys, Look.palette(false, "blue").keys)
        assertEquals(Look.ACCENTS.size, Look.ACCENTS.map { Look.palette(true, it)["fill"] }.toSet().size)
        assertEquals(Look.palette(true, "blue"), Look.palette(true, "no such accent"))          // an unknown accent is the default one
    }

    @Test fun choicesAreCheckedAndRoundedToWhatTheDesignHas() {
        assertEquals("dark", Look.mode("neon")); assertEquals("dark", Look.mode(null)); assertEquals("light", Look.mode("light"))
        assertEquals("blue", Look.accent("beige")); assertEquals("pink", Look.accent("pink"))
        assertEquals(110, Look.size(112)); assertEquals(125, Look.size(500)); assertEquals(90, Look.size(1)); assertEquals(100, Look.size(null))
        assertTrue(Look.isDark("dark", false)); assertTrue(!Look.isDark("light", true)); assertTrue(Look.isDark("system", true)); assertTrue(!Look.isDark("system", false))
    }

    @Test fun theChoiceIsKeptInTheSettings() {
        val p = prefs()
        assertEquals(LookChoice("dark", "blue", 100), LookChoice.load(p))
        p.put("ui.theme", "light"); p.put("ui.accent", "green"); p.put("ui.textSize", 125.0)
        assertEquals(LookChoice("light", "green", 125), LookChoice.load(p))
        p.put("ui.theme", "garbage"); p.put("ui.textSize", 7.0)
        assertEquals(LookChoice("dark", "green", 90), LookChoice.load(p))
    }

    @Test fun theLookIsInABackupAndComesBackCleaned() {
        val p = prefs()
        p.put("ui.theme", "light"); p.put("ui.accent", "purple"); p.put("ui.textSize", 110.0)
        val d = Backup.build(p, "v", "t")
        assertEquals(setOf("ui.theme", "ui.accent", "ui.textSize"), d.obj("settings")!!.keys)
        val q = prefs()
        val (s, _, _) = Backup.restore(q, d)
        assertEquals(3, s)
        assertEquals(LookChoice("light", "purple", 110), LookChoice.load(q))
        val hostile = Backup.read("""{"app":"roblox-manager","format":1,"settings":{"ui.theme":"<script>","ui.accent":"red","ui.textSize":"999"}}""")
        val r = prefs()
        assertEquals(0, Backup.restore(r, hostile).first)
        assertEquals(LookChoice(), LookChoice.load(r))
    }
}
