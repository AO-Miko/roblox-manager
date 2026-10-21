package app.robloxmanager.core

import java.net.URI

/** Raised instead of sending: Roblox's own numbers say this route is used up for longer than this request may wait. */
class LocalLimit(route: String, limit: Int, window: Int?, waitMs: Long) :
    RobloxException(429, "Roblox allows only $limit of these${window?.let { " per $it s" } ?: ""} ($route); the next one is allowed in ${waitMs / 1000} s", local = true)

/**
 * Every answer from Roblox says how many requests a route allows (x-ratelimit-limit), how many are left (-remaining) and when the
 * count starts over (-reset). This keeps that per route, so each route is used right up to its limit and never past it, and spreads the
 * allowance over the time that is left instead of using it all at once.
 */
class RateTable(private val now: () -> Long = { System.currentTimeMillis() }) {
    class Route(
        var limit: Int, var left: Int, var resetAt: Long, var window: Int?, var seen: Long,
        var nextOk: Long = 0, var minGap: Long = 0, var lastSent: Long = 0,
    )

    data class Snapshot(val route: String, val limit: Int?, val window: Int?, val left: Int?, val resetInMs: Long, val seen: Long)

    private val lock = Any()
    private val routes = LinkedHashMap<String, Route>()

    companion object {
        const val UNKNOWN = 1_000_000
        var HIDDEN_WAIT_MS = 10_000L      // a 429 although the headers said plenty was left: a hidden limit; wait at least this long
        var HIDDEN_GAP_MS = 5_500L        // the first gap between requests on such a route (doubled by every further refusal)
        var HIDDEN_FLOOR_MS = 4_000L      // the gap never drops below this afterwards
        var NOTIFY_AFTER_MS = 5_000L      // only waits longer than this are announced

        fun key(method: String, url: String): String {
            val u = URI(url)
            return "${method.uppercase()} ${u.host}${u.path.replace(Regex("/[0-9]+"), "/{n}")}"
        }
    }

    fun known(key: String) = synchronized(lock) { routes.containsKey(key) }

    fun clear() = synchronized(lock) { routes.clear() }

    fun waitLeftMs(key: String): Long = synchronized(lock) {
        val st = routes[key] ?: return 0
        if (st.left <= 0) maxOf(0, st.resetAt - now()) else 0
    }

    /**
     * Wait until one more request on this route is allowed, and reserve it. If the route is used up and its reset is further away than
     * [maxWaitMs], [LocalLimit] is thrown at once instead of making the caller wait.
     * [burst] is the share of the limit that may be used back to back first; a batch of changes uses 0 so it runs evenly from the start.
     */
    suspend fun gate(
        key: String, sleep: suspend (Long) -> Unit, maxWaitMs: Long? = null, notify: ((Long) -> Unit)? = null, burst: Double = 0.0,
    ) {
        var told = false
        while (true) {
            var wait: Long
            synchronized(lock) {
                val st = routes[key] ?: return
                val t = now()
                val hold = if (st.minGap > 0) st.lastSent + st.minGap - t else 0L
                if (hold > 0) {
                    wait = hold
                } else {
                    if (t >= st.resetAt) {                                    // a new window: full allowance again
                        st.left = st.limit
                        st.resetAt = t + (st.window ?: 1) * 1000L
                        st.nextOk = 0
                    }
                    val remaining = maxOf(0L, st.resetAt - t)
                    if (st.left > 0) {
                        val used = st.limit - st.left
                        val free = (st.limit * burst).toInt()
                        val gapWait = if (used >= free) st.nextOk - t else 0L
                        if (gapWait <= 0) {
                            st.left -= 1
                            st.lastSent = t
                            st.nextOk = t + if (used + 1 >= free) remaining / (st.left + 1) else 0L
                            return
                        }
                        wait = if (maxWaitMs == null) gapWait else minOf(gapWait, maxWaitMs)
                    } else {
                        wait = st.resetAt - t + 200
                        if (maxWaitMs != null && wait > maxWaitMs) {
                            throw LocalLimit(key.substringAfter(' '), st.limit, st.window, wait)
                        }
                    }
                }
            }
            if (notify != null && wait > NOTIFY_AFTER_MS && !told) {
                told = true
                notify(wait)
            }
            sleep(wait)
        }
    }

    /** Read the limit headers (and a 429) of an answer. Returns a short text for the log. */
    fun learn(key: String, headers: Map<String, String>, status: Int, attempt: Int, minWaitMs: Long): String {
        val h = headers.mapKeys { it.key.lowercase() }
        val rem = h["x-ratelimit-remaining"]?.trim()?.toIntOrNull()
        val rst = h["x-ratelimit-reset"]?.trim()?.toDoubleOrNull()
        val limText = h["x-ratelimit-limit"] ?: ""
        val lim = Regex("^\\s*(\\d+)").find(limText)?.groupValues?.get(1)?.toInt()
        val window = Regex(";\\s*w=(\\d+)").find(limText)?.groupValues?.get(1)?.toInt()
        val t = now()
        var text = ""
        synchronized(lock) {
            var st = routes[key]
            if (st == null && (rem != null || status == 429)) {
                st = Route(lim ?: UNKNOWN, UNKNOWN, 0, null, t)
                routes[key] = st
            }
            if (st == null) return ""
            st.seen = t
            if (lim != null) st.limit = lim
            if (window != null) st.window = window
            if (rem != null && rst != null) {
                st.left = rem
                st.resetAt = t + (rst * 1000).toLong()
                text = "$rem of ${lim ?: "?"} left, resets in ${rst.toLong()} s"
            }
            val hidden = status == 429 && rem != null && rem > 0
            if (status == 429) {
                var wait = maxOf(((h["retry-after"]?.toDoubleOrNull() ?: 0.0) * 1000).toLong(), ((rst ?: 0.0) * 1000).toLong())
                if (rst == null) wait = maxOf(wait, minWaitMs * (attempt + 1))
                if (hidden) {                                              // refused although the headers say plenty is left
                    wait = maxOf(wait, HIDDEN_WAIT_MS)
                    st.minGap = minOf(maxOf(st.minGap * 2, HIDDEN_GAP_MS), 30_000)
                    text += (if (text.isEmpty()) "" else "; ") + "hidden limit: keeping ${st.minGap / 1000} s between requests"
                }
                st.left = 0
                st.resetAt = t + minOf(wait, 60_000) + 500                   // Roblox's latest word beats our own estimate
                text += (if (text.isEmpty()) "" else "; ") + "limited: wait ${minOf(wait, 60_000) / 1000} s"
            } else if (st.minGap > 0) {
                st.minGap = maxOf((st.minGap * 0.95).toLong(), HIDDEN_FLOOR_MS)   // a success: loosen the gap again, slowly (never to nothing)
            }
        }
        return text
    }

    fun snapshot(): List<Snapshot> = synchronized(lock) {
        val t = now()
        routes.map { (k, st) ->
            val active = t < st.resetAt
            Snapshot(
                k, if (st.limit < UNKNOWN) st.limit else null, st.window,
                if (active && st.left < UNKNOWN) st.left else if (st.limit < UNKNOWN) st.limit else null,
                if (active) st.resetAt - t else 0, st.seen,
            )
        }.sortedBy { it.route }
    }
}
