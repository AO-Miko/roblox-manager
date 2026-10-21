package app.robloxmanager.core

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChangelogTest {
    @Test fun readsTheShippedLog() {
        val f = File("src/main/assets/changelog.json")
        val e = Changelog.parse(f.readText())
        assertTrue(e.size >= 3)
        assertTrue(e.all { it.date.isNotEmpty() && it.changes.isNotEmpty() })
    }

    @Test fun badInputGivesAnEmptyList() {
        assertEquals(emptyList<ChangelogEntry>(), Changelog.parse("{nope"))
        assertEquals(emptyList<ChangelogEntry>(), Changelog.parse("{}"))
    }

    @Test fun oddEntriesAreSkipped() {
        val e = Changelog.parse("""[{"version":"2.0.0","changes":["a","  "]},{"nope":1},"text",{"version":" "}]""")
        assertEquals(1, e.size)
        assertEquals(listOf("a"), e[0].changes)
        assertEquals("", e[0].date)
    }
}
