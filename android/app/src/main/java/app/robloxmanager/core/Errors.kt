package app.robloxmanager.core

import kotlin.coroutines.cancellation.CancellationException

/** Roblox said no (or could not be reached: status 0). str() is safe to show: it never contains the cookie. */
open class RobloxException(val status: Int, message: String, val code: Int? = null, val local: Boolean = false) : Exception(message) {
    override fun toString() = "HTTP $status: $message"
}

/** The account changed while a request was waiting or in flight: its answer must never be used. */
class StaleAccount : CancellationException("The account changed")

/** Removes anything that looks like the sign-in cookie from a text before it is logged or shown. */
object Redact {
    private val secret = Regex("(_\\|WARNING:[^;\\s]+|\\.ROBLOSECURITY=[^;\\s]+)")
    fun text(t: String?): String = secret.replace(t ?: "", "[cookie removed]")
}
