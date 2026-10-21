package app.robloxmanager

import app.robloxmanager.ui.ALL
import app.robloxmanager.ui.BOTTOM
import app.robloxmanager.ui.IN_MORE
import app.robloxmanager.ui.MORE
import app.robloxmanager.ui.matchHits
import app.robloxmanager.ui.searchHits
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NavTest {
    private val hits = searchHits()
    private val adminHits = searchHits(admin = true)

    @Test fun everyPageIsReachableFromTheBottomBarOrMore() {
        val reachable = BOTTOM.map { it.id } + IN_MORE.map { it.id }
        assertTrue(ALL.all { it.id in reachable })
        assertTrue(MORE in BOTTOM)
    }

    @Test fun descriptiveWordsFindThePage() {
        assertEquals("Money", matchHits(hits, "robux").first().title)
        assertEquals("VIP servers", matchHits(hits, "private").first().title)
        assertEquals("Request log", matchHits(hits, "rate limit").first { it.where == "page" }.title)
    }

    @Test fun subPagesCarryTheirNumber() {
        val blocked = matchHits(hits, "blocked").first { it.title == "Blocked" }
        assertEquals("people", blocked.jump.dest)
        assertEquals(4, blocked.jump.sub)
        assertEquals(1, matchHits(hits, "updates").first { it.title == "Updates" }.jump.sub)
    }

    @Test fun titleThatStartsWithTheQueryComesFirst() {
        assertEquals("Groups", matchHits(hits, "gro").first().title)
    }

    @Test fun staffListIsForEverybodyAndAdminOnlyForAdmins() {
        assertEquals("Staff List", matchHits(hits, "staff").first().title)
        assertTrue(matchHits(hits, "ban").none { it.title == "Admin" })
        assertEquals("Admin", matchHits(adminHits, "unban").first().title)
    }

    @Test fun emptyQueryShowsEverythingAndNonsenseShowsNothing() {
        assertEquals(hits.size, matchHits(hits, "  ").size)
        assertTrue(matchHits(hits, "zzzqq").isEmpty())
    }
}
