package app.robloxmanager.core

import java.io.File
import java.time.LocalDate
import java.util.Base64
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

/** One message from the developer. All text is plain text: it is never shown as HTML. */
class Notice(val id: String, val date: String, val title: String, val body: String, val level: String, val link: String?, val channel: String, val expires: String?)

class NoticeList(val serial: Long, val items: List<Notice>)

/**
 * News from the developer: a signed list (dist/notifications.json + .sig in the update repository, namespace roblox-manager-notifications), fetched at the start and every
 * ten minutes. Only a list signed with the release key is believed, an older list is never accepted again, the last good list is kept on the phone and nothing about the
 * person is sent. Which ones were read, and which were already announced, is kept in the settings ("notices.read", "notices.seen").
 */
class NoticeStore(
    private val file: File,
    private val prefs: Prefs,
    private val trusted: ByteArray = BanStore.RELEASE_KEY,
    private val http: OkHttpClient = RobloxClient.defaultHttp().newBuilder().followRedirects(true).followSslRedirects(true).build(),
    private val baseUrl: String = BanStore.BASE_URL,
    private val today: () -> LocalDate = { LocalDate.now() },
) {
    companion object {
        const val NAMESPACE = "roblox-manager-notifications"
        const val MAX_ITEMS = 50
        const val MAX_READ = 200
        private val ID = Regex("[A-Za-z0-9._-]{1,40}")
        private val DAY = Regex("\\d{4}-\\d{2}-\\d{2}")

        /** The list if `data` is signed by the trusted key, else null. Bad entries are dropped and long text is cut, never believed as it is. */
        fun parse(data: ByteArray, sig: String, trusted: ByteArray = BanStore.RELEASE_KEY): NoticeList? {
            if (data.size > BanStore.MAX_BYTES || !SshSig.verify(data, sig, trusted, NAMESPACE)) return null
            val d = try { AppJson.parseToJsonElement(String(data, Charsets.UTF_8)).obj } catch (_: Exception) { null } ?: return null
            val serial = d.long("serial") ?: return null
            val seen = HashSet<String>()
            val out = ArrayList<Notice>()
            (d["notifications"] as? JsonArray)?.forEach { e ->
                if (out.size >= MAX_ITEMS) return@forEach
                val o = e.obj ?: return@forEach
                val id = o.str("id") ?: return@forEach
                if (!ID.matches(id) || !seen.add(id)) return@forEach
                val level = o.str("level")?.takeIf { it == "important" || it == "warning" } ?: "info"
                val link = o.str("link")?.takeIf { it.startsWith("https://") && it.length <= 300 }
                val channel = o.str("channel")?.takeIf { it == "beta" || it == "stable" } ?: "all"
                out.add(Notice(id, (o.str("date") ?: "").takeIf { DAY.matches(it) } ?: "", (o.str("title") ?: "").take(80), (o.str("body") ?: "").take(1000),
                    level, link, channel, o.str("expires")?.takeIf { DAY.matches(it) }))
            }
            return NoticeList(serial, out)
        }
    }

    @Volatile private var cached: NoticeList? = null
    @Volatile private var raw: ByteArray = ByteArray(0)

    /** The last good list from disk, checked again (so a file edited on the phone is not believed). */
    fun load(): NoticeList {
        cached?.let { return it }
        val list = try {
            val o = AppJson.parseToJsonElement(file.readText()).obj
            val bytes = Base64.getDecoder().decode(o?.str("data") ?: "")
            parse(bytes, o?.str("sig") ?: "", trusted)?.also { raw = bytes }
        } catch (_: Throwable) { null }
        return (list ?: NoticeList(0, emptyList())).also { cached = it }
    }

    /** What this phone shows: the channel is "all" or the phone's own, and the notice has not expired (it is hidden after its last day). */
    fun visible(channel: String): List<Notice> {
        val now = today().toString()
        return load().items.filter { (it.channel == "all" || it.channel == channel) && (it.expires == null || it.expires >= now) }
    }

    private fun ids(key: String): MutableSet<String> = (prefs.raw(key) as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }?.toMutableSet() ?: HashSet()

    fun isRead(id: String) = id in ids("notices.read")

    fun unreadCount(channel: String): Int { val read = ids("notices.read"); return visible(channel).count { it.id !in read } }

    private fun saveRead(read: Set<String>) {
        val exist = load().items.map { it.id }.toSet()
        val keep = read.filter { it in exist }.takeLast(MAX_READ)
        prefs.put("notices.read", keep)
    }

    fun markRead(id: String) {
        val read = ids("notices.read")
        if (id in read || load().items.none { it.id == id }) return
        read.add(id); saveRead(read)
        Debug.event("notices", "read notification '$id'")
    }

    fun markAllRead(channel: String) {
        val read = ids("notices.read")
        read.addAll(visible(channel).map { it.id }); saveRead(read)
        Debug.event("notices", "all notifications marked as read")
    }

    /** The visible notices that were never announced before (to show as phone notifications). The first time ever, nothing is announced: everything present is just remembered. */
    fun takeNew(channel: String): List<Notice> {
        val first = prefs.raw("notices.seen") == null
        val seen = ids("notices.seen")
        val fresh = visible(channel).filter { it.id !in seen }
        if (fresh.isEmpty() && !first) return emptyList()
        seen.addAll(load().items.map { it.id })
        prefs.put("notices.seen", seen.toList().takeLast(500))
        return if (first) emptyList() else fresh
    }

    private fun get(url: String, limit: Long): ByteArray {
        require(url.startsWith("https://"))
        Debug.execute(http, Request.Builder().url(url).header("User-Agent", RobloxClient.USER_AGENT).header("Cache-Control", "no-cache").build()).use { r ->
            if (!r.isSuccessful) error("HTTP ${r.code}")
            val b = r.body?.bytes() ?: error("empty")
            if (b.size > limit) error("too large")
            return b
        }
    }

    /** Downloads the list and keeps it if it is signed and not older. true = changed, false = no change, null = could not fetch or refused. Blocking. */
    fun refresh(): Boolean? {
        val data: ByteArray
        val sig: String
        try {
            data = get(baseUrl + "notifications.json", BanStore.MAX_BYTES)
            sig = String(get(baseUrl + "notifications.json.sig", 20_000), Charsets.UTF_8)
        } catch (_: Exception) {
            return null
        }
        val got = try { parse(data, sig, trusted) } catch (_: Throwable) { null } ?: return null
        val have = load()
        if (got.serial < have.serial || (got.serial == have.serial && data.contentEquals(raw))) return false
        try {
            file.parentFile?.mkdirs()
            val tmp = File(file.path + ".tmp")
            tmp.writeText(AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), obj("data" to Base64.getEncoder().encodeToString(data), "sig" to sig)))
            tmp.renameTo(file)
        } catch (_: Exception) {
            return null
        }
        cached = got
        raw = data
        return true
    }
}
