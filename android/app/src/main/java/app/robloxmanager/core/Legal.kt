package app.robloxmanager.core

/**
 * The Terms of use and the Privacy policy: which version of them each account accepted on this phone.
 * Every account is asked once, at its first sign-in, and again when the texts change (VERSION is the "Last updated" date of
 * TERMS.md and PRIVACY.md; a desktop test keeps them equal). Without the acceptance that account is signed out.
 */
object Legal {
    const val VERSION = "2026-11-02"
    const val TERMS_URL = "https://github.com/AO-Miko/roblox-manager/blob/main/TERMS.md"
    const val PRIVACY_URL = "https://github.com/AO-Miko/roblox-manager/blob/main/PRIVACY.md"

    private fun key(id: Long) = "legal.$id"

    fun accepted(prefs: Prefs, id: Long) = prefs.str(key(id), "") == VERSION

    fun accept(prefs: Prefs, id: Long) = prefs.put(key(id), VERSION)

    /** Takes one account's acceptance back: it is asked again at its next sign-in. */
    fun forget(prefs: Prefs, id: Long) = prefs.put(key(id), "")
}
