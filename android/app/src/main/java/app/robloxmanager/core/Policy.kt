package app.robloxmanager.core

import java.io.File
import java.util.Base64
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

/** Version numbers are R.B.S.F.D (see tools/version.py): compared number by number, an old three-number version counts as 1.7.0 = 1.7.0.0.0. */
object Versions {
    private val FORM = Regex("\\d+(\\.\\d+){1,4}")
    fun valid(v: String) = FORM.matches(v)
    fun key(v: String): List<Int> {
        val n = Regex("\\d+").findAll(v).map { it.value.toIntOrNull() ?: 0 }.toList().ifEmpty { listOf(0) }
        return n + List((5 - n.size).coerceAtLeast(0)) { 0 }
    }
    fun compare(a: String, b: String): Int {
        val x = key(a)
        val y = key(b)
        for (i in 0 until maxOf(x.size, y.size)) { val c = x.getOrElse(i) { 0 }.compareTo(y.getOrElse(i) { 0 }); if (c != 0) return c }
        return 0
    }
}

class PolicyList(val serial: Long, val limit: Int, val stable: List<String>, val beta: List<String>? = null)

/** How far behind this app is: [blocked] when [behind] reaches the policy's [limit] (see linux/policy.py). */
class PolicyStatus(val blocked: Boolean, val behind: Int, val limit: Int, val latest: String, val installed: String)

/**
 * Forced updates. The maintainer publishes dist/policy.json (+ .sig, signed with the release key) listing every version released to everybody ("stable") and, in the
 * file on the beta branch, every release including the betas ("beta"). An app counts the list of its own channel (the Beta channel falls back to "stable" when there is no
 * "beta" list; [useBeta]) and, having missed [limit] (2) of them, cannot be used until it is updated: a page covers the whole app. Nobody is signed out and nothing is deleted.
 * A version newer than the list is never behind. Only a valid signature is believed, a newer serial replaces an older one, the last good file is kept, and if none was ever downloaded
 * (or the server cannot be reached) nobody is locked out.
 */
class PolicyStore(
    private val file: File,
    private val trusted: ByteArray = BanStore.RELEASE_KEY,
    private val http: OkHttpClient = RobloxClient.defaultHttp().newBuilder().followRedirects(true).followSslRedirects(true).build(),
    private val baseUrl: String = BanStore.BASE_URL,
    private val useBeta: Boolean = false,
) {
    companion object {
        const val NAMESPACE = "roblox-manager-policy"
        const val DEFAULT_LIMIT = 2
        const val MAX_BYTES = 100_000L
        const val RELEASES_URL = "https://github.com/AO-Miko/roblox-manager/releases/latest"
        const val RELEASES_ALL_URL = "https://github.com/AO-Miko/roblox-manager/releases"           // (the Beta channel: the newest version may be a pre-release)
        /** The beta branch's copy of the policy (every beta release writes it there). */
        val BETA_BASE_URL = BanStore.BASE_URL.replace("/release/dist/", "/beta/dist/")

        fun parse(data: ByteArray, sig: String, trusted: ByteArray = BanStore.RELEASE_KEY): PolicyList? {
            if (!SshSig.verify(data, sig, trusted, NAMESPACE)) return null
            val d = try { AppJson.parseToJsonElement(String(data, Charsets.UTF_8)).obj } catch (_: Exception) { null } ?: return null
            val serial = d.long("serial") ?: return null
            val limit = (d.long("limit") ?: DEFAULT_LIMIT.toLong()).toInt().coerceAtLeast(1)
            fun versions(key: String): List<String>? {
                val arr = d[key] as? JsonArray ?: return null
                val list = ArrayList<String>()
                for (e: JsonElement in arr) {
                    val v = (e as? JsonPrimitive)?.content ?: throw IllegalArgumentException("not a version")
                    if (!Versions.valid(v)) throw IllegalArgumentException("not a version")
                    list.add(v)
                }
                return list
            }
            return try { PolicyList(serial, limit, versions("stable") ?: emptyList(), versions("beta")) } catch (_: IllegalArgumentException) { null }
        }
    }

    @Volatile private var cached: PolicyList? = null

    fun load(): PolicyList {
        cached?.let { return it }
        val list = try {
            val o = AppJson.parseToJsonElement(file.readText()).obj
            parse(Base64.getDecoder().decode(o?.str("data") ?: ""), o?.str("sig") ?: "", trusted)
        } catch (_: Throwable) { null }
        return (list ?: PolicyList(0, DEFAULT_LIMIT, emptyList())).also { cached = it }
    }

    fun status(installed: String): PolicyStatus = try {
        val p = load()
        val newer = (if (useBeta && p.beta != null) p.beta else p.stable).filter { Versions.compare(it, installed) > 0 }.associateBy { Versions.key(it) }          // (1.9.0.0 and 1.9.0.0.0 count once)
        val latest = newer.values.maxWithOrNull { a, b -> Versions.compare(a, b) } ?: installed
        PolicyStatus(newer.size >= p.limit, newer.size, p.limit, latest, installed)
    } catch (_: Throwable) { PolicyStatus(false, 0, DEFAULT_LIMIT, installed, installed) }

    private fun get(url: String, limit: Long): ByteArray {
        require(url.startsWith("https://"))
        Debug.execute(http, Request.Builder().url(url).header("User-Agent", RobloxClient.USER_AGENT).header("Cache-Control", "no-cache").build()).use { r ->
            if (!r.isSuccessful) error("HTTP ${r.code}")
            val b = r.body?.bytes() ?: error("empty")
            if (b.size > limit) error("too large")
            return b
        }
    }

    /** true = changed, false = no change, null = could not fetch or refused. Blocking; never throws. */
    fun refresh(): Boolean? {
        val data: ByteArray
        val sig: String
        try {
            data = get(baseUrl + "policy.json", MAX_BYTES)
            sig = String(get(baseUrl + "policy.json.sig", 20_000), Charsets.UTF_8)
        } catch (_: Throwable) {
            return null
        }
        val got = try { parse(data, sig, trusted) } catch (_: Throwable) { null } ?: return null
        val have = load()
        if (got.serial < have.serial || (got.serial == have.serial && got.limit == have.limit && got.stable == have.stable && got.beta == have.beta)) return false
        try {
            file.parentFile?.mkdirs()
            val tmp = File(file.path + ".tmp")
            tmp.writeText(AppJson.encodeToString(JsonElement.serializer(), obj("data" to Base64.getEncoder().encodeToString(data), "sig" to sig)))
            tmp.renameTo(file)
        } catch (_: Throwable) {
            return null
        }
        cached = got
        return true
    }
}
