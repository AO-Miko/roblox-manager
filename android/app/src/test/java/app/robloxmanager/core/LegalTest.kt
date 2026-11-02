package app.robloxmanager.core

import java.io.File
import org.junit.Test
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue

class LegalTest {
    private fun prefs() = Prefs(File.createTempFile("legal", ".json").also { it.delete(); it.deleteOnExit() })

    @Test fun nobody_has_accepted_on_a_new_phone() {
        val p = prefs()
        assertFalse(Legal.accepted(p, 1)); assertFalse(Legal.accepted(p, 2))
    }

    @Test fun each_account_is_remembered_on_its_own() {
        val p = prefs()
        Legal.accept(p, 1)
        assertTrue(Legal.accepted(p, 1)); assertFalse(Legal.accepted(p, 2))
        Legal.accept(p, 2)
        assertTrue(Legal.accepted(p, 1)); assertTrue(Legal.accepted(p, 2))
    }

    @Test fun taking_one_back_asks_only_that_account_again() {
        val p = prefs()
        Legal.accept(p, 1); Legal.accept(p, 2)
        Legal.forget(p, 1)
        assertFalse(Legal.accepted(p, 1)); assertTrue(Legal.accepted(p, 2))
    }

    @Test fun an_acceptance_of_an_older_text_does_not_count() {
        val p = prefs()
        p.put("legal.5", "2020-01-01")
        assertFalse(Legal.accepted(p, 5))
    }
}
