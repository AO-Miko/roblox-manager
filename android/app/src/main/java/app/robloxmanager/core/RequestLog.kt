package app.robloxmanager.core

import java.io.File
import java.net.URI
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** One request: what was asked and how Roblox answered. Never the cookie, never a body, never headers. */
data class LogEntry(
    val time: Long, val account: String, val method: String, val host: String, val path: String, val query: String,
    val status: Int?, val ms: Long?, val attempt: Int, val paced: Boolean, val note: String, val rate: String,
) {
    val isProblem get() = status == null || status >= 400
}

/**
 * Every request the app sends is kept here (the newest [keep]) for the Request log screen, and optionally written to requests.log.
 * The value of anything in an address that looks like a secret is hidden, and long values are shortened.
 */
class RequestLog(private val file: File? = null, private val keep: Int = 5000) {
    private val ring = ArrayDeque<LogEntry>()
    private val _entries = MutableStateFlow<List<LogEntry>>(emptyList())
    val entries: StateFlow<List<LogEntry>> = _entries
    @Volatile var writeFile: Boolean = true
    @Volatile var total: Long = 0

    companion object {
        private val secretParam = Regex("token|code|password|secret|cookie|ticket|auth|session|api[-_]?key|(^|[-_])key$", RegexOption.IGNORE_CASE)
        private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

        fun queryText(params: Map<String, String>?, urlQuery: String?): String {
            val pairs = ArrayList<Pair<String, String>>()
            urlQuery?.split("&")?.filter { it.isNotEmpty() }?.forEach { p ->
                pairs += p.substringBefore("=") to java.net.URLDecoder.decode(p.substringAfter("=", ""), "UTF-8")
            }
            params?.forEach { (k, v) -> pairs += k to v }
            return pairs.joinToString("&") { (k, v) ->
                "$k=" + if (secretParam.containsMatchIn(k)) "***" else if (v.length <= 40) v else v.take(37) + "..."
            }
        }
    }

    fun record(
        account: String, method: String, url: String, params: Map<String, String>? = null, status: Int? = null, ms: Long? = null,
        attempt: Int = 0, paced: Boolean = false, note: String = "", rate: String = "", sent: Any? = null, answer: String? = null, contentType: String? = null,
    ): LogEntry {
        val u = URI(url)
        val e = LogEntry(System.currentTimeMillis(), account.ifEmpty { "-" }, method, u.host ?: "", u.path ?: "", queryText(params, u.rawQuery),
            status, ms, attempt, paced, note, rate)
        synchronized(ring) {
            ring.addLast(e)
            while (ring.size > keep) ring.removeFirst()
            total++
            _entries.value = ring.toList()
        }
        Debug.log?.http(e, sent, answer, contentType)          // (the app debug log: the same request with what was sent and came back, hidden)
        if (writeFile) file?.let { f ->
            try {
                val line = Redact.text(
                    "${synchronized(stamp) { stamp.format(Date(e.time)) }} acct=${e.account} $method ${e.host}${e.path}" +
                        (if (e.query.isNotEmpty()) "?${e.query}" else "") + " -> ${status ?: "no answer"}" + (if (note.isNotEmpty()) " ($note)" else "") +
                        (if (ms != null) " $ms ms" else "") + (if (paced) " paced" else "") + (if (attempt > 0) " retry#$attempt" else "") +
                        (if (rate.isNotEmpty()) " | rate: $rate" else ""),
                )
                f.parentFile?.mkdirs()
                if (f.exists() && f.length() > 1_500_000) { f.copyTo(File(f.path + ".1"), overwrite = true); f.writeText("") }
                f.appendText(line + "\n")
            } catch (_: Exception) {
            }
        }
        return e
    }

    fun clear() = synchronized(ring) { ring.clear(); _entries.value = emptyList() }

    /** (requests, changes, 429s, problems) in the last [windowMs]. */
    fun summary(windowMs: Long = 30_000, now: Long = System.currentTimeMillis()): List<Int> {
        val recent = _entries.value.filter { it.time >= now - windowMs && it.status != null }
        return listOf(recent.size, recent.count { it.method != "GET" }, recent.count { it.status == 429 }, recent.count { it.status!! >= 400 })
    }
}
