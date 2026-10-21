package app.robloxmanager.core

import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** A person as the screens show them. */
data class Person(
    val id: Long, val name: String = "", val displayName: String = "", val verified: Boolean = false, val extra: String = "",
) {
    val title get() = displayName.ifEmpty { name }.ifEmpty { "User $id" }
    val handle get() = if (name.isNotEmpty()) "@$name" else ""
}

/** Names saved between runs so a list never asks Roblox for the same person twice. Kept in a small json file (no secrets in it). */
class NameCache(private val file: File? = null) {
    private val map = HashMap<Long, Person>()
    private var dirty = 0

    init {
        try {
            file?.takeIf { it.exists() }?.let { f ->
                AppJson.parseToJsonElement(f.readText()).obj?.forEach { (k, v) ->
                    val o = v.obj ?: return@forEach
                    map[k.toLong()] = Person(k.toLong(), o.str("n") ?: "", o.str("d") ?: "", o.bool("v") ?: false)
                }
            }
        } catch (_: Exception) {
        }
    }

    @Synchronized fun get(id: Long): Person? = map[id]
    @Synchronized fun put(p: Person) {
        if (p.name.isEmpty()) return
        map[p.id] = p
        if (++dirty >= 50) save()
    }

    @Synchronized fun save() {
        dirty = 0
        try {
            val f = file ?: return
            f.parentFile?.mkdirs()
            val o = JsonObject(map.entries.associate { (k, p) -> k.toString() to obj("n" to p.name, "d" to p.displayName, "v" to p.verified) })
            f.writeText(AppJson.encodeToString(JsonElement.serializer(), o))
        } catch (_: Exception) {
        }
    }
}

/**
 * The Roblox calls the screens use. A change (unfriend, leave, switch on ...) is always one call here, so the client's pacing applies.
 * [hasRobux] style answers are trees; this class turns them into the few fields the screens need.
 */
class RobloxApi(val client: RobloxClient, val names: NameCache = NameCache()) {
    companion object {
        const val PROFILES = "https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles"
    }

    val me: Long get() = client.userId ?: throw RobloxException(401, "Not signed in", local = true)

    suspend fun login(): JsonObject {
        val u = client.get("https://users.roblox.com/v1/users/authenticated", retries = 1).json.obj ?: throw RobloxException(401, "Not signed in")
        client.user = u
        return u
    }

    /** Follows nextPageCursor to the end (or [maxPages]). */
    suspend fun paged(url: String, params: Map<String, String> = emptyMap(), limit: Int = 100, maxPages: Int = 50, onPage: ((List<JsonObject>) -> Unit)? = null): List<JsonObject> {
        val q = HashMap(params)
        q.putIfAbsent("limit", limit.toString())
        val out = ArrayList<JsonObject>()
        repeat(maxPages) {
            val d = client.get(url, q).json
            val page = d.items()
            out += page
            onPage?.invoke(page)
            val cur = d.obj?.str("nextPageCursor")
            if (cur.isNullOrEmpty()) return out
            q["cursor"] = cur
        }
        return out
    }

    // ---------------- names
    suspend fun users(ids: List<Long>): List<Person> {
        val found = HashMap<Long, Person>()
        val todo = ids.distinct().filter { id -> names.get(id)?.also { found[id] = it } == null }
        for (chunk in todo.chunked(100)) {
            val d = client.post("https://users.roblox.com/v1/users", obj("userIds" to chunk, "excludeBannedUsers" to false)).json.items()
            for (o in d) {
                val p = Person(o.long("id") ?: continue, o.str("name") ?: "", o.str("displayName") ?: "", o.bool("hasVerifiedBadge") ?: false)
                names.put(p); found[p.id] = p
            }
        }
        return ids.distinct().mapNotNull { found[it] }
    }

    /** Names for many ids, fast: the profile route takes 200 ids and reports its limit honestly; the older route is the fallback. */
    suspend fun lookupNames(ids: List<Long>, onChunk: ((List<Person>) -> Unit)? = null): List<Person> {
        val found = HashMap<Long, Person>()
        val todo = ids.distinct().filter { id -> names.get(id)?.also { found[id] = it } == null }
        for (chunk in todo.chunked(200)) {
            val got = ArrayList<Person>()
            try {
                val d = client.post(PROFILES, obj("userIds" to chunk, "fields" to listOf("names.username", "names.displayName", "isVerified"))).json.obj
                for (p in d?.arr("profileDetails").orEmpty()) {
                    val o = p.obj ?: continue
                    val n = o.obj("names")
                    val un = n?.str("username")
                    val id = o.long("userId")
                    if (id != null && !un.isNullOrEmpty()) got += Person(id, un, n.str("displayName") ?: un, o.bool("isVerified") ?: false)
                }
            } catch (e: RobloxException) {
                if (e.status == 401 || e.status == 403 || e.local) throw e
            }
            if (got.size < chunk.size / 2) {
                val have = got.map { it.id }.toSet()
                got += users(chunk.filter { it !in have })
            }
            got.forEach { names.put(it); found[it.id] = it }
            onChunk?.invoke(got)
        }
        names.save()
        return ids.distinct().mapNotNull { found[it] }
    }

    private fun fill(items: List<JsonObject>, extra: (JsonObject) -> String = { "" }): List<Person> = items.mapNotNull { o ->
        val id = o.long("id") ?: o.long("userId") ?: return@mapNotNull null
        val c = names.get(id)
        Person(id, o.str("name")?.takeIf { it.isNotEmpty() } ?: c?.name ?: "", o.str("displayName")?.takeIf { it.isNotEmpty() } ?: c?.displayName ?: "",
            o.bool("hasVerifiedBadge") ?: c?.verified ?: false, extra(o))
    }

    // ---------------- people
    suspend fun friends(): List<Person> {
        val items = client.get("https://friends.roblox.com/v1/users/$me/friends").json.items()
        val ids = items.mapNotNull { it.long("id") }
        val info = if (ids.isEmpty()) emptyMap() else lookupNames(ids).associateBy { it.id }
        return items.mapNotNull { f ->
            val id = f.long("id") ?: return@mapNotNull null
            val u = info[id]
            Person(id, u?.name ?: f.str("name") ?: "", u?.displayName ?: f.str("displayName") ?: u?.name ?: "", u?.verified ?: f.bool("hasVerifiedBadge") ?: false)
        }
    }

    suspend fun friendRequests(onPage: ((List<Person>) -> Unit)? = null): List<Person> =
        fill(paged("https://friends.roblox.com/v1/my/friends/requests", onPage = onPage?.let { cb -> { p -> cb(fill(p)) } }))

    suspend fun friendRequestCount(): Int = client.get("https://friends.roblox.com/v1/user/friend-requests/count").json.obj?.int("count") ?: 0
    suspend fun followers(): List<Person> = fill(paged("https://friends.roblox.com/v1/users/$me/followers"))
    suspend fun followings(): List<Person> = fill(paged("https://friends.roblox.com/v1/users/$me/followings"))

    suspend fun blocked(): List<Person> {
        val tries = listOf(
            "https://apis.roblox.com/user-blocking-api/v1/users/me/blocked-users",
            "https://accountsettings.roblox.com/v1/users/get-detailed-blocked-users",
            "https://accountsettings.roblox.com/v1/users/blocked-users",
        )
        var last: RobloxException? = null
        for (u in tries) {
            val d = try { client.get(u, retries = 1).json } catch (e: RobloxException) {
                last = e
                if (e.status == 401 || e.status == 403) throw e
                continue
            }
            val list: JsonArray = d.obj?.arr("blockedUsers") ?: d.obj?.arr("data") ?: d.obj?.arr("users") ?: (d as? JsonArray) ?: JsonArray(emptyList())
            val out = list.mapNotNull { it.obj }.mapNotNull { b ->
                val id = b.long("userId") ?: b.long("id") ?: return@mapNotNull null
                Person(id, b.str("name") ?: b.str("username") ?: "", b.str("displayName") ?: "")
            }
            val missing = out.filter { it.name.isEmpty() }.map { it.id }
            val info = if (missing.isEmpty()) emptyMap() else lookupNames(missing).associateBy { it.id }
            return out.map { if (it.name.isEmpty()) info[it.id] ?: it else it }
        }
        throw RobloxException(last?.status ?: 0, "Roblox did not return your blocked list (it may have moved it)")
    }

    suspend fun acceptRequest(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/accept-friend-request")
    suspend fun declineRequest(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/decline-friend-request")
    suspend fun declineAllRequests() = client.post("https://friends.roblox.com/v1/user/friend-requests/decline-all")
    suspend fun sendRequest(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/request-friendship", obj("friendshipOriginSourceType" to "UserProfile"))
    suspend fun unfriend(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/unfriend")
    suspend fun follow(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/follow")
    suspend fun unfollow(id: Long) = client.post("https://friends.roblox.com/v1/users/$id/unfollow")
    suspend fun block(id: Long) = client.post("https://apis.roblox.com/user-blocking-api/v1/users/$id/block-user")
    suspend fun unblock(id: Long) = client.post("https://apis.roblox.com/user-blocking-api/v1/users/$id/unblock-user")

    suspend fun search(text: String): List<Person> {
        val t = text.trim()
        val out = ArrayList<Person>()
        val seen = HashSet<Long>()
        fun add(o: JsonObject?) {
            val id = o?.long("id") ?: return
            if (seen.add(id)) out += Person(id, o.str("name") ?: "", o.str("displayName") ?: "", o.bool("hasVerifiedBadge") ?: false)
        }
        if (t.isNotEmpty() && t.all { it.isDigit() }) try { add(client.get("https://users.roblox.com/v1/users/$t", auth = false).json.obj) } catch (_: RobloxException) { }
        else if (t.isNotEmpty()) add(client.post("https://users.roblox.com/v1/usernames/users", obj("usernames" to listOf(t), "excludeBannedUsers" to false)).json.items().firstOrNull())
        try {
            client.get("https://users.roblox.com/v1/users/search", mapOf("keyword" to t, "limit" to "25"), auth = false).json.items().forEach { add(it) }
        } catch (_: RobloxException) { }
        return out
    }

    /** Headshot urls (public pictures). */
    suspend fun headshots(ids: List<Long>, size: String = "150x150"): Map<Long, String> {
        val out = HashMap<Long, String>()
        for (c in ids.distinct().chunked(100)) {
            try {
                val d = client.get("https://thumbnails.roblox.com/v1/users/avatar-headshot",
                    mapOf("userIds" to c.joinToString(","), "size" to size, "format" to "Png", "isCircular" to "true"), auth = false).json
                d.items().forEach { t -> val id = t.long("targetId"); val u = t.str("imageUrl"); if (id != null && !u.isNullOrEmpty()) out[id] = u }
            } catch (_: RobloxException) { }
        }
        return out
    }

    /** A user's public profile: name, displayName, description, created. */
    suspend fun profile(id: Long): JsonObject? = client.get("https://users.roblox.com/v1/users/$id").json.obj

    suspend fun counts(id: Long): Map<String, Int?> = listOf("friends" to "friends", "followers" to "followers", "following" to "followings").associate { (k, part) ->
        k to try { client.get("https://friends.roblox.com/v1/users/$id/$part/count", auth = false).json.obj?.int("count") } catch (_: RobloxException) { null }
    }

    suspend fun robux(): Long? = client.get("https://economy.roblox.com/v1/user/currency").json.obj?.long("robux")
    suspend fun hasPremium(): Boolean = (client.get("https://premiumfeatures.roblox.com/v1/users/$me/validate-membership", retries = 1).json as? JsonPrimitive)?.content == "true"

    // ---------------- groups
    data class Group(val id: Long, val name: String, val role: String, val rank: Int, val members: Int?, val owned: Boolean, val created: String? = null)

    suspend fun myGroups(): List<Group> {
        val d = client.get("https://groups.roblox.com/v1/users/$me/groups/roles").json.items()
        return d.mapNotNull { e ->
            val g = e.obj("group") ?: return@mapNotNull null
            val r = e.obj("role")
            Group(g.long("id") ?: return@mapNotNull null, g.str("name") ?: "", r?.str("name") ?: "", r?.int("rank") ?: 0, g.int("memberCount"),
                g.obj("owner")?.long("userId") == me || (r?.int("rank") ?: 0) == 255)
        }
    }

    suspend fun groupsCreated(ids: List<Long>): Map<Long, String?> {
        val out = HashMap<Long, String?>()
        for (c in ids.chunked(100)) {
            val d = client.get("https://groups.roblox.com/v2/groups", mapOf("groupIds" to c.joinToString(",")), auth = false).json.items()
            d.forEach { g -> g.long("id")?.let { out[it] = g.str("created") } }
        }
        return out
    }

    suspend fun leaveGroup(id: Long) = client.delete("https://groups.roblox.com/v1/groups/$id/users/$me")

    // ---------------- VIP servers
    suspend fun myPrivateServers(maxPages: Int = 10): List<JsonObject> {
        val combos = listOf("vip-servers" to "MyPrivateServers", "vip-servers" to null, "private-servers" to "MyPrivateServers", "private-servers" to null)
        var last: RobloxException? = null
        for ((path, tab) in combos) {
            val params = HashMap<String, String>().apply { put("itemsPerPage", "25"); if (tab != null) put("privateServersTab", tab) }
            val items = ArrayList<JsonObject>()
            var cursor: String? = null
            try {
                repeat(maxPages) {
                    val q = HashMap(params)
                    if (cursor != null) q["cursor"] = cursor!!
                    val d = client.get("https://games.roblox.com/v1/$path/my-private-servers", q).json
                    items += d.items()
                    cursor = d.obj?.str("nextPageCursor")
                    if (cursor.isNullOrEmpty()) return items
                }
                return items
            } catch (e: RobloxException) {
                last = e
                if (e.status == 401 || e.status == 403) throw e
            }
        }
        throw last ?: RobloxException(0, "could not list your private servers")
    }

    suspend fun vipServer(id: Long, retries: Int = 3): JsonObject? = client.get("https://games.roblox.com/v1/vip-servers/$id", retries = retries).json.obj
    suspend fun updateVip(id: Long, fields: JsonObject) = client.patch("https://games.roblox.com/v1/vip-servers/$id", fields)
    suspend fun renewVip(id: Long, price: Int) = client.patch("https://games.roblox.com/v1/vip-servers/$id/subscription", obj("active" to true, "price" to price))
    suspend fun setVipActive(id: Long, active: Boolean) = updateVip(id, obj("active" to active))
    suspend fun cancelVipRenewal(id: Long) = client.patch("https://games.roblox.com/v1/vip-servers/$id/subscription", obj("active" to false))

    suspend fun placeNames(ids: List<Long>): Map<Long, String> {
        val out = HashMap<Long, String>()
        for (c in ids.distinct().chunked(50)) {
            val d = try { client.get("https://games.roblox.com/v1/games/multiget-place-details", mapOf("placeIds" to c.joinToString("&placeIds="))).json } catch (_: RobloxException) { continue }
            val list = (d as? JsonArray)?.mapNotNull { it.obj } ?: d.items()
            list.forEach { p -> val id = p.long("placeId") ?: p.long("id"); if (id != null) out[id] = p.str("name") ?: p.str("sourceName") ?: "" }
        }
        return out
    }

    // ---------------- money
    suspend fun pendingTotal(): Long = client.get("https://economy.roblox.com/v2/users/$me/transaction-totals",
        mapOf("timeFrame" to "Month", "transactionType" to "summary"), retries = 1).json.obj?.long("pendingRobuxTotal") ?: 0L

    suspend fun transactionTotals(frame: String = "Month"): JsonObject? = client.get("https://economy.roblox.com/v2/users/$me/transaction-totals",
        mapOf("timeFrame" to frame, "transactionType" to "summary")).json.obj

    /** Your newest transactions of one kind (Sale, Purchase, GroupPayout ...), newest first. */
    suspend fun transactions(kind: String, maxPages: Int = 3): List<JsonObject> {
        val items = ArrayList<JsonObject>()
        var cursor: String? = null
        repeat(maxPages) {
            val q = hashMapOf("transactionType" to kind, "limit" to "100", "sortOrder" to "Desc")
            if (cursor != null) q["cursor"] = cursor!!
            val d = client.get("https://economy.roblox.com/v2/users/$me/transactions", q, retries = 1).json
            items += d.items()
            cursor = d.obj?.str("nextPageCursor")
            if (cursor.isNullOrEmpty()) return items
        }
        return items
    }

    suspend fun emailStatus(): Pair<String, Boolean> {
        val d = client.get("https://accountsettings.roblox.com/v1/email").json.obj
        return (d?.str("emailAddress") ?: "") to (d?.bool("verified") ?: false)
    }
}
