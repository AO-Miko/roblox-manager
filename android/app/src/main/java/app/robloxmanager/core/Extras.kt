package app.robloxmanager.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// ======================================================================== friend alerts

/** Where a friend was at one look: 0 offline, 1 online, 2 in a game, 3 in Studio. */
data class Seen(val kind: Int, val place: Long?, val game: String)

object AlertRules {
    const val INTERVAL_MS = 90_000L          // how often the watched friends are looked at (one request for up to 100 people)
    const val MAX_WATCHED = 200
    const val OFFLINE = 0; const val ONLINE = 1; const val IN_GAME = 2; const val IN_STUDIO = 3

    /** Roblox's presence answer -> where each friend is. Broken entries are dropped, odd types count as offline. */
    fun snapshot(presence: JsonElement?): Map<Long, Seen> {
        val out = HashMap<Long, Seen>()
        presence.obj?.arr("userPresences")?.forEach { e ->
            val p = e.obj ?: return@forEach
            val id = p.long("userId") ?: return@forEach
            val kind = p.int("userPresenceType")?.takeIf { it in 0..3 } ?: 0
            out[id] = Seen(kind, p.long("rootPlaceId") ?: p.long("placeId"), (p.str("lastLocation") ?: "").take(80))
        }
        return out
    }

    /** What is new between two looks: (user id, text). A friend that was not in the earlier look is only learned about, never reported. */
    fun news(prev: Map<Long, Seen>, now: Map<Long, Seen>, names: Map<Long, String>, online: Boolean = true, ingame: Boolean = true): List<Pair<Long, String>> {
        val out = ArrayList<Pair<Long, String>>()
        for ((id, s) in now) {
            val before = prev[id] ?: continue
            val who = names[id]?.takeIf { it.isNotEmpty() } ?: "User $id"
            when {
                s.kind == IN_GAME && ingame && (before.kind != IN_GAME || before.place != s.place) -> out += id to "$who joined ${s.game.ifEmpty { "a game" }}"
                online && before.kind == OFFLINE && s.kind != OFFLINE -> out += id to "$who is online"
            }
        }
        return out
    }
}

/** The alert choices and the watched friends, kept in the phone's settings. The watch list is per account. */
class AlertSettings(private val prefs: Prefs) {
    var enabled: Boolean
        get() = prefs.bool("alerts.enabled", false)
        set(v) = prefs.put("alerts.enabled", v)
    var online: Boolean
        get() = prefs.bool("alerts.online", true)
        set(v) = prefs.put("alerts.online", v)
    var ingame: Boolean
        get() = prefs.bool("alerts.ingame", true)
        set(v) = prefs.put("alerts.ingame", v)

    fun watched(account: Long): Map<Long, String> = clean(prefs.raw("alerts.watch"))[account] ?: emptyMap()

    fun setWatched(account: Long, friends: Map<Long, String>) {
        val all = clean(prefs.raw("alerts.watch")).toMutableMap()
        all[account] = friends.entries.take(AlertRules.MAX_WATCHED).associate { it.key to it.value.take(60) }
        prefs.put("alerts.watch", toJson(all))
    }

    companion object {
        /** {"account id": {"friend id": "name"}} from anything read from disk or a backup: wrong shapes are dropped, sizes limited. */
        fun clean(raw: JsonElement?): Map<Long, Map<Long, String>> {
            val out = LinkedHashMap<Long, Map<Long, String>>()
            raw.obj?.entries?.take(50)?.forEach { (acc, friends) ->
                val a = acc.toLongOrNull() ?: return@forEach
                val f = friends.obj ?: return@forEach
                out[a] = f.entries.take(AlertRules.MAX_WATCHED).mapNotNull { (id, n) -> id.toLongOrNull()?.let { it to ((n as? JsonPrimitive)?.content ?: "").take(60) } }.toMap()
            }
            return out
        }

        fun toJson(all: Map<Long, Map<Long, String>>): JsonObject = JsonObject(all.entries.associate { (a, f) -> a.toString() to JsonObject(f.entries.associate { (id, n) -> id.toString() to JsonPrimitive(n) }) })
    }
}

suspend fun RobloxApi.presence(ids: List<Long>): JsonElement? {
    val users = ArrayList<JsonElement>()
    for (c in ids.distinct().chunked(100)) client.post("https://presence.roblox.com/v1/presence/users", obj("userIds" to c)).json.obj?.arr("userPresences")?.let { users.addAll(it) }
    return JsonObject(mapOf("userPresences" to JsonArray(users)))
}

// ======================================================================== join requests of all groups

data class JoinRequest(val gid: Long, val group: String, val id: Long, val username: String, val display: String, val created: String?) {
    val key get() = "$gid:$id"
    val title get() = display.ifEmpty { username }.ifEmpty { "User $id" }
}

object JoinRequests {
    const val PAGES_PER_GROUP = 2

    fun mayAnswer(membership: JsonElement?): Boolean =
        membership.obj?.obj("permissions")?.obj("groupMembershipPermissions")?.bool("inviteMembers") == true

    fun parse(gid: Long, group: String, page: JsonElement?): List<JoinRequest> = page.items().mapNotNull { r ->
        val u = r.obj("requester") ?: return@mapNotNull null
        JoinRequest(gid, group, u.long("userId") ?: return@mapNotNull null, u.str("username") ?: "", u.str("displayName") ?: "", r.str("created"))
    }
}

/** (the requests, how many groups you may answer in, the groups that could not be checked) */
data class JoinScan(val requests: List<JoinRequest>, val checked: Int, val failed: List<String>)

suspend fun RobloxApi.joinRequestsOfAll(groups: List<RobloxApi.Group>, progress: (Int) -> Unit = {}): JoinScan {
    val rows = ArrayList<JoinRequest>()
    val failed = ArrayList<String>()
    var checked = 0
    for ((k, g) in groups.withIndex()) {
        progress(k)
        try {
            if (!JoinRequests.mayAnswer(client.get("https://groups.roblox.com/v1/groups/${g.id}/membership").json)) continue
            checked++
            var cursor: String? = null
            for (page in 1..JoinRequests.PAGES_PER_GROUP) {
                val q = hashMapOf("limit" to "100", "sortOrder" to "Asc")
                if (cursor != null) q["cursor"] = cursor!!
                val d = client.get("https://groups.roblox.com/v1/groups/${g.id}/join-requests", q).json
                rows += JoinRequests.parse(g.id, g.name, d)
                cursor = d.obj?.str("nextPageCursor")?.takeIf { it.isNotEmpty() }
                if (cursor == null) break
            }
        } catch (e: kotlin.coroutines.cancellation.CancellationException) {
            throw e
        } catch (e: RobloxException) {
            if (e.status == 401) throw e
            failed += "${g.name}: ${e.message}"
        }
    }
    return JoinScan(rows, checked, failed)
}

suspend fun RobloxApi.answerJoinRequests(gid: Long, userIds: List<Long>, accept: Boolean) {
    val url = "https://groups.roblox.com/v1/groups/$gid/join-requests"
    if (accept) client.post(url, obj("UserIds" to userIds)) else client.delete(url, obj("UserIds" to userIds))
}

// ======================================================================== backup

class BackupException(message: String) : Exception(message)

/** A backup of what is yours in the app: the settings, the friend alerts and the recently viewed games, and (if asked) a copy of your lists.
 *  Sign-ins are never in it. Restoring changes nothing on Roblox. */
object Backup {
    const val APP = "roblox-manager"
    const val FORMAT = 1
    const val MAX_BYTES = 5_000_000
    /** The settings that go into a backup and come back from one: name -> kind. Nothing else is ever read from or written to a backup. */
    val KEYS = mapOf("readBurst" to "double", "logToFile" to "bool", "alerts.enabled" to "bool", "alerts.online" to "bool", "alerts.ingame" to "bool",
        "ui.theme" to "theme", "ui.accent" to "accent", "ui.textSize" to "size")

    fun build(prefs: Prefs, version: String, created: String, account: Person? = null, friends: List<Person>? = null, followers: List<Person>? = null,
              following: List<Person>? = null, groups: List<RobloxApi.Group>? = null): JsonObject {
        val m = LinkedHashMap<String, JsonElement>()
        m["app"] = JsonPrimitive(APP); m["format"] = JsonPrimitive(FORMAT); m["version"] = JsonPrimitive(version); m["created"] = JsonPrimitive(created)
        m["settings"] = JsonObject(KEYS.keys.mapNotNull { k -> prefs.raw(k)?.let { k to it } }.toMap())
        m["alerts"] = AlertSettings.toJson(AlertSettings.clean(prefs.raw("alerts.watch")))
        m["recent_games"] = prefs.raw(RecentGames.KEY) as? JsonArray ?: JsonArray(emptyList())
        if (account != null) m["account"] = obj("id" to account.id, "name" to account.name, "displayName" to account.displayName)
        fun people(l: List<Person>) = JsonArray(l.map { obj("id" to it.id, "name" to it.name.take(40), "displayName" to it.displayName.take(60)) })
        friends?.let { m["friends"] = people(it) }
        followers?.let { m["followers"] = people(it) }
        following?.let { m["following"] = people(it) }
        groups?.let { l -> m["groups"] = JsonArray(l.map { obj("id" to it.id, "name" to it.name.take(100), "role" to it.role.take(60), "rank" to it.rank) }) }
        return JsonObject(m)
    }

    fun read(text: String): JsonObject {
        if (text.length > MAX_BYTES) throw BackupException("That file is too big to be a backup of this app.")
        val d = try { AppJson.parseToJsonElement(text).obj } catch (_: Exception) { throw BackupException("That file is not a backup of this app (it is not valid JSON).") }
        if (d == null || d.str("app") != APP) throw BackupException("That file is not a backup of this app.")
        val f = d.int("format") ?: throw BackupException("That backup has no version number.")
        if (f < 1) throw BackupException("That backup has no version number.")
        if (f > FORMAT) throw BackupException("That backup was made by a newer version of the app. Update the app first.")
        return d
    }

    /** Puts the settings, alerts and recent games back; returns (settings, watched friends, games). */
    fun restore(prefs: Prefs, d: JsonObject): Triple<Int, Int, Int> {
        var s = 0
        d.obj("settings")?.let { st ->
            for ((k, kind) in KEYS) {
                val v = st[k] as? JsonPrimitive ?: continue
                when (kind) {
                    "bool" -> v.content.toBooleanStrictOrNull()?.let { prefs.put(k, it); s++ }
                    "double" -> v.content.toDoubleOrNull()?.takeIf { it in 0.0..1.0 }?.let { prefs.put(k, it); s++ }
                    "theme" -> v.content.takeIf { it in Look.MODES }?.let { prefs.put(k, it); s++ }
                    "accent" -> v.content.takeIf { it in Look.ACCENTS }?.let { prefs.put(k, it); s++ }
                    "size" -> v.content.toDoubleOrNull()?.toInt()?.takeIf { it in Look.SIZES }?.let { prefs.put(k, it.toDouble()); s++ }
                }
            }
        }
        var w = 0
        if (d["alerts"] != null) {
            val clean = AlertSettings.clean(d["alerts"])
            prefs.put("alerts.watch", AlertSettings.toJson(clean))
            w = clean.values.sumOf { it.size }
        }
        var g = 0
        d.arr("recent_games")?.let { arr ->
            val keep = arr.mapNotNull { e ->
                val o = e.obj ?: return@mapNotNull null
                if (o.long("u") == null || o.str("n") == null) null else o
            }.take(RecentGames.LIMIT)
            prefs.put(RecentGames.KEY, JsonArray(keep))
            g = keep.size
        }
        return Triple(s, w, g)
    }
}
