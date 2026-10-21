package app.robloxmanager.core

import java.io.File
import java.util.Base64
import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * Who is on the staff: the signed role list (dist/roles.json + .sig, same release key as the ban list), five roles one above the other:
 * owner (5) > co-owner (4) > senior-admin (3) > admin (2) > trusted-friend (1). From admin up an account also gets the Admin page.
 * Everybody sees the Staff List. The rules of who may ban whom are the same as on the PC (docs/ADMIN.md); bans are published from a PC.
 */
object Roles {
    class Role(val key: String, val rank: Int, val label: String)

    val ORDER = listOf(Role("owner", 5, "Owner"), Role("co-owner", 4, "Co-owner"), Role("senior-admin", 3, "Senior admin"), Role("admin", 2, "Admin"), Role("trusted-friend", 1, "Trusted friend"))
    const val MODERATOR = 2          // the lowest rank with the Admin page and the power to ban

    fun normalize(s: String) = s.trim().lowercase().replace(' ', '-').replace('_', '-')
    fun byKey(key: String?): Role? = ORDER.firstOrNull { it.key == key }
    fun label(rank: Int) = ORDER.firstOrNull { it.rank == rank }?.label ?: ""
}

class RoleList(val serial: Long, val roles: Map<Long, String>)

class RoleStore(
    private val file: File,
    private val trusted: ByteArray = BanStore.RELEASE_KEY,
    private val http: OkHttpClient = RobloxClient.defaultHttp().newBuilder().followRedirects(true).followSslRedirects(true).build(),
    private val baseUrl: String = BanStore.BASE_URL,
) {
    companion object {
        const val NAMESPACE = "roblox-manager-roles"
        const val MAX_BYTES = 100_000L

        /** The list if it is signed by the trusted key; unknown roles are dropped, a bad entry refuses the whole list. */
        fun parse(data: ByteArray, sig: String, trusted: ByteArray = BanStore.RELEASE_KEY): RoleList? {
            if (!SshSig.verify(data, sig, trusted, NAMESPACE)) return null
            val d: JsonObject = try { AppJson.parseToJsonElement(String(data, Charsets.UTF_8)).obj } catch (_: Exception) { null } ?: return null
            val serial = d.long("serial") ?: return null
            val out = HashMap<Long, String>()
            val r = d["roles"] as? JsonObject ?: return RoleList(serial, out)
            for ((k, v) in r) {
                val id = k.toLongOrNull() ?: return null
                val role = Roles.normalize((v as? kotlinx.serialization.json.JsonPrimitive)?.content ?: return null)
                if (Roles.byKey(role) != null) out[id] = role
            }
            return RoleList(serial, out)
        }
    }

    @Volatile private var cached: RoleList? = null

    fun load(): RoleList {
        cached?.let { return it }
        val list = try {
            val o = AppJson.parseToJsonElement(file.readText()).obj
            parse(Base64.getDecoder().decode(o?.str("data") ?: ""), o?.str("sig") ?: "", trusted)
        } catch (_: Throwable) { null }
        return (list ?: RoleList(0, emptyMap())).also { cached = it }
    }

    fun roleOf(userId: Long): Roles.Role? = try { Roles.byKey(load().roles[userId]) } catch (_: Throwable) { null }
    fun rankOf(userId: Long): Int = roleOf(userId)?.rank ?: 0

    /** (user id, role) from the highest role down, then by id. */
    fun staff(): List<Pair<Long, Roles.Role>> = try {
        load().roles.mapNotNull { (id, r) -> Roles.byKey(r)?.let { id to it } }.sortedWith(compareBy({ -it.second.rank }, { it.first }))
    } catch (_: Throwable) { emptyList() }

    private fun get(url: String, limit: Long): ByteArray {
        require(url.startsWith("https://"))
        http.newCall(Request.Builder().url(url).header("User-Agent", RobloxClient.USER_AGENT).header("Cache-Control", "no-cache").build()).execute().use { r ->
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
            data = get(baseUrl + "roles.json", MAX_BYTES)
            sig = String(get(baseUrl + "roles.json.sig", 20_000), Charsets.UTF_8)
        } catch (_: Throwable) {
            return null
        }
        val got = try { parse(data, sig, trusted) } catch (_: Throwable) { null } ?: return null
        val have = load()
        if (got.serial < have.serial || (got.serial == have.serial && got.roles == have.roles)) return false
        try {
            file.parentFile?.mkdirs()
            val tmp = File(file.path + ".tmp")
            tmp.writeText(AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), obj("data" to Base64.getEncoder().encodeToString(data), "sig" to sig)))
            tmp.renameTo(file)
        } catch (_: Throwable) {
            return null
        }
        cached = got
        return true
    }
}
