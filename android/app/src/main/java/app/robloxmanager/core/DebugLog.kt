package app.robloxmanager.core

import java.io.File
import java.io.OutputStream
import java.io.PrintStream
import java.net.URI
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One thing that happened in the app: one line, and (as [detail]) its output. Everything private is hidden before an event is made. */
data class DebugEvent(val time: Long, val level: String, val area: String, val message: String, val detail: String)

/** Hides what must never be shown or kept: cookies, tokens, passwords, codes, e-mail addresses, phone numbers, IP addresses, the accounts in use, names of people in answers. */
object Scrub {
    const val DETAIL_MAX = 6000
    const val PREVIEW_MAX = 2400
    private val cookie = Regex("(_\\|WARNING:[^;\\s\"']+|\\.ROBLOSECURITY=[^;\\s\"']+)")
    private val jwt = Regex("eyJ[A-Za-z0-9_-]{6,}\\.[A-Za-z0-9_-]{6,}\\.[A-Za-z0-9_-]*")
    private val bearer = Regex("\\b(bearer|basic)\\s+[A-Za-z0-9._~+/=-]{8,}", RegexOption.IGNORE_CASE)
    private val email = Regex("[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)+")
    private val ipv4 = Regex("(?<![\\w.])(?:(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)\\.){3}(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)(?![\\w.])")
    private val ipv6 = Regex("(?<![\\w:])(?:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?|(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4})(?![\\w:])", RegexOption.IGNORE_CASE)
    private val phone = Regex("(?<!\\w)\\+\\d[\\d ()-]{7,}\\d")
    private val opaque = Regex("(?<![\\w-])[A-Za-z0-9_+=-]{40,}(?![\\w-])")
    private const val SENSITIVE = "cookie|token|ticket|passw|secret|authoriz|session|csrf|e-?mail|phone|birth|signature|credential|api[-_]?key|private"
    private val keyValue = Regex("(?<k>[\"']?[\\w.-]*(?:$SENSITIVE)[\\w.-]*[\"']?)(?<sep>\\s*[:=]\\s*)(?<v>\\[[a-z ]*\\]|\"(?:[^\"\\\\]|\\\\.)*\"|'[^']*'|[^\\s,;&}\\]\"']+)", RegexOption.IGNORE_CASE)
    private val exact = Regex("(?<k>[\"']?\\b(?:code|pin|otp|auth|key|dob)[\"']?)(?<sep>\\s*[:=]\\s*)(?<v>\"(?:[^\"\\\\]|\\\\.)*\"|'[^']*'|\\d{5,})", RegexOption.IGNORE_CASE)
    /** Keys whose text, in an answer from Roblox, is about a person: shown as ***, whatever the value. */
    private val personalKey = Regex("^(name|displayname|username|user_?name|requested_?(user)?name|description|about|bio|body|content|text|location|ip|address|cookie|.*token.*|.*ticket.*|.*password.*|.*secret.*|authorization|.*session.*|.*csrf.*|.*email.*|.*phone.*|.*birth.*|.*signature.*|.*credential.*)$", RegexOption.IGNORE_CASE)
    private val personalText = Regex("(?<k>\"(?:name|display_?name|user_?name|requested_?(?:user)?name|description|about|bio|body|content|text|location|ip|address)\"\\s*:\\s*)(?<v>\"(?:[^\"\\\\]|\\\\.)*\"?)", RegexOption.IGNORE_CASE)
    private val names = LinkedHashSet<String>()
    private val ids = LinkedHashSet<String>()
    @Volatile var home: String = System.getProperty("user.home") ?: ""

    /** The accounts in use: their names and ids are hidden wherever they appear. */
    @Synchronized fun setIdentity(vararg people: Account?, replace: Boolean = false) {
        if (replace) { names.clear(); ids.clear() }
        for (p in people) {
            if (p == null) continue
            for (n in listOf(p.name, p.displayName)) if (n.length >= 3) names += n
            ids += p.id.toString()
        }
    }

    @Synchronized fun forgetIdentity() { names.clear(); ids.clear() }

    private fun mask(m: MatchResult): String {
        val v = m.groups["v"]!!.value
        return m.groups["k"]!!.value + m.groups["sep"]!!.value + (if (v.startsWith("\"") || v.startsWith("'")) "\"***\"" else "***")
    }

    fun text(input: String?, limit: Int = 0): String {
        return try {
            var t = input ?: ""
            t = cookie.replace(t, "[cookie]")
            if (home.length > 1) t = t.replace(home, "~")
            t = jwt.replace(t, "[token]")
            t = bearer.replace(t) { it.groupValues[1] + " ***" }
            t = keyValue.replace(t, ::mask)
            t = exact.replace(t, ::mask)
            t = email.replace(t, "[email]")
            t = ipv4.replace(t, "[ip]")
            t = ipv6.replace(t, "[ip]")
            t = phone.replace(t, "[phone]")
            t = opaque.replace(t, "[token]")
            synchronized(this) {
                for (n in names.sortedByDescending { it.length }) t = Regex("(?<![\\w])" + Regex.escape(n) + "(?![\\w])", RegexOption.IGNORE_CASE).replace(t, "<me>")
                for (i in ids) t = Regex("(?<!\\d)" + Regex.escape(i) + "(?!\\d)").replace(t, "<my id>")
            }
            if (limit > 0 && t.length > limit) t = t.take(limit) + "... [${t.length - limit} more characters]"
            t
        } catch (_: Exception) {
            "[could not be hidden safely: not shown]"
        }
    }

    private fun walk(e: JsonElement?, depth: Int = 0): JsonElement = when {
        e == null || e is JsonNull -> JsonNull
        depth > 6 -> JsonPrimitive("...")
        e is JsonObject -> JsonObject(e.entries.associate { (k, v) ->
            k to if (personalKey.matches(k)) (if (v is JsonNull || (v is JsonPrimitive && !v.isString && (v.content == "true" || v.content == "false"))) v else JsonPrimitive("***")) else walk(v, depth + 1)
        })
        e is JsonArray -> JsonArray(e.take(6).map { walk(it, depth + 1) } + (if (e.size > 6) listOf(JsonPrimitive("... ${e.size - 6} more")) else emptyList()))
        e is JsonPrimitive && e.isString -> JsonPrimitive(if (e.content.length <= 120) e.content else e.content.take(117) + "...")
        else -> e
    }

    /** A short, hidden version of something that came back or was sent (decoded json, or text): the output of a request or a task. */
    fun preview(data: Any?, limit: Int = PREVIEW_MAX): String = try {
        when (data) {
            null -> "-"
            is JsonElement -> text(AppJson.encodeToString(JsonElement.serializer(), walk(data)), limit)
            is String -> {
                val s = data.trim()
                if (s.startsWith("{") || s.startsWith("[")) {
                    val parsed = try { AppJson.parseToJsonElement(s) } catch (_: Exception) { null }
                    if (parsed != null) preview(parsed, limit) else text(personalText.replace(s.take(limit * 2)) { it.groups["k"]!!.value + "\"***\"" }, limit)
                } else text(s.take(limit * 2), limit)
            }
            else -> text(data.toString(), limit)
        }
    } catch (_: Exception) {
        "[output not shown]"
    }
}

/**
 * The app's debug log: what happens in the app, with the output (the "App debug" view of the Request log, and debug.log). The newest [keep] events are kept in memory;
 * with [writeFile] each one is also appended to the file (rotated at about 1.5 MB). Everything goes through [Scrub] before it is kept.
 */
class DebugLog(private val file: File? = null, private val keep: Int = 5000) {
    private val ring = ArrayDeque<DebugEvent>()
    private val _events = MutableStateFlow<List<DebugEvent>>(emptyList())
    val events: StateFlow<List<DebugEvent>> = _events
    @Volatile var writeFile: Boolean = true
    @Volatile var total: Long = 0
    @Volatile var minLevel: String = "debug"

    companion object {
        val LEVELS = listOf("debug", "info", "warning", "error")
        private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
        private val clock = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)

        fun clockText(t: Long): String = synchronized(clock) { clock.format(Date(t)) }

        fun line(e: DebugEvent, withDetail: Boolean = true): String =
            "${clockText(e.time)} ${e.level.uppercase().padEnd(7)} [${e.area}] ${e.message}" + if (withDetail && e.detail.isNotEmpty()) "\n    " + e.detail.replace("\n", "\n    ") else ""

        /** The events as text to copy, save or share: a header (version, system, what is hidden) and nothing private. */
        fun export(events: List<DebugEvent>, version: String): String =
            "Roblox Manager debug log (phone), exported ${synchronized(stamp) { stamp.format(Date()) }}\napp $version, Android ${android.os.Build.VERSION.RELEASE ?: "?"}\n" +
                "Cookies, tokens, passwords, codes, e-mails, phone numbers, IP addresses, names of accounts and people are hidden.\n\n" + events.joinToString("\n") { line(it) } + "\n"
    }

    fun event(area: String, message: String, level: String = "info", detail: String = ""): DebugEvent? {
        return try {
            val e = DebugEvent(System.currentTimeMillis(), if (level in LEVELS) level else "info", area, Scrub.text(message, 600).replace("\n", " "), if (detail.isEmpty()) "" else Scrub.text(detail, Scrub.DETAIL_MAX))
            synchronized(ring) {
                ring.addLast(e)
                while (ring.size > keep) ring.removeFirst()
                total++
                _events.value = ring.toList()
            }
            if (writeFile) file?.let { f ->
                try {
                    f.parentFile?.mkdirs()
                    if (f.exists() && f.length() > 1_500_000) { f.copyTo(File(f.path + ".1"), overwrite = true); f.writeText("") }
                    f.appendText("${synchronized(stamp) { stamp.format(Date(e.time)) }} ${e.level.uppercase().padEnd(7)} [${e.area}] ${e.message}" + (if (e.detail.isNotEmpty()) "\n    " + e.detail.replace("\n", "\n    ") else "") + "\n")
                } catch (_: Exception) {
                }
            }
            e
        } catch (_: Exception) {
            null
        }
    }

    /** A request to Roblox: one line, and as output what was sent and what came back. */
    fun http(e: LogEntry, sent: Any? = null, answer: String? = null, contentType: String? = null) {
        val st = e.status
        val level = if (st == null || st >= 500) "error" else if (st >= 400) "warning" else "info"
        val msg = "${e.method} ${e.host}${e.path}" + (if (e.query.isNotEmpty()) "?${e.query}" else "") + " -> ${st ?: "no answer"}" + (e.ms?.let { " ($it ms)" } ?: "") + (if (e.note.isNotEmpty()) " ${e.note}" else "")
        val parts = ArrayList<String>()
        if (sent != null) parts += "sent: " + Scrub.preview(sent, 1200)
        if (answer != null) parts += "answer: HTTP ${st ?: "-"}, ${answer.length} characters" + (contentType?.let { ", ${it.substringBefore(';')}" } ?: "") + (if (answer.isNotBlank() && (contentType == null || "json" in contentType || "text" in contentType)) "\n" + Scrub.preview(answer.take(Scrub.PREVIEW_MAX * 2)) else "")
        event("http", msg, level, parts.joinToString("\n"))
    }

    /** A download from somewhere that is not Roblox (update server, RoSeal's lists, ipwho.is, the ban and policy lists): host and path only. */
    fun net(method: String, url: String, status: Int?, size: Int = 0, error: String = "") {
        val u = try { URI(url) } catch (_: Exception) { null }
        event("net", "$method ${u?.host ?: ""}${u?.path ?: ""}" + (if (status != null) " -> $status" else " -> no answer") + (if (size > 0) ", $size bytes" else "") + (if (error.isNotEmpty()) " ($error)" else ""),
            if (status != null && status < 400) "info" else "warning")
    }

    fun clear() = synchronized(ring) { ring.clear(); _events.value = emptyList() }

    /** The kept events at [level] or above, newest last, with [area] (if given) and every word of [text] in the line or its output. */
    fun snapshot(level: String = "debug", area: String = "", text: String = ""): List<DebugEvent> {
        val floor = LEVELS.indexOf(level).coerceAtLeast(0)
        val words = text.lowercase().split(" ").filter { it.isNotEmpty() }
        return _events.value.filter { e ->
            LEVELS.indexOf(e.level) >= floor && (area.isEmpty() || e.area == area) &&
                (words.isEmpty() || "${e.area} ${e.level} ${e.message} ${e.detail}".lowercase().let { hay -> words.all { it in hay } })
        }
    }
}

/** The app's one debug log (set by Services); nothing happens before it is set (the unit tests have none). */
object Debug {
    @Volatile var log: DebugLog? = null

    fun event(area: String, message: String, level: String = "info", detail: String = "") { log?.event(area, message, level, detail) }
    fun net(method: String, url: String, status: Int?, size: Int = 0, error: String = "") { log?.net(method, url, status, size, error) }

    /** Catches uncaught errors (any thread) and what the program prints. */
    fun install(l: DebugLog) {
        log = l
        val old = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            event("crash", "uncaught ${e.javaClass.simpleName} in thread ${t.name}: ${e.message}", "error", e.stackTraceToString())
            old?.uncaughtException(t, e)
        }
        System.setOut(tee(System.out, "info"))
        System.setErr(tee(System.err, "warning"))
        event("app", "debug log started (Android ${android.os.Build.VERSION.RELEASE ?: "?"})")
    }

    /** Sends a request of a download (update server, lists, ipwho.is) and tells the log about it: host and path, the answer's code, or why there was none. */
    fun execute(http: okhttp3.OkHttpClient, req: okhttp3.Request): okhttp3.Response {
        val url = req.url.toString()
        try {
            val r = http.newCall(req).execute()
            net(req.method, url, r.code)
            return r
        } catch (e: java.io.IOException) {
            net(req.method, url, null, 0, e.javaClass.simpleName)
            throw e
        }
    }

    private fun tee(inner: PrintStream, level: String): PrintStream = PrintStream(object : OutputStream() {
        private val buf = java.io.ByteArrayOutputStream()
        override fun write(b: Int) {
            inner.write(b)
            if (b == '\n'.code) { val s = buf.toString("UTF-8").trim(); if (s.isNotEmpty()) event("output", s, level); buf.reset() } else if (buf.size() < 4000) buf.write(b)
        }
    }, true)
}
