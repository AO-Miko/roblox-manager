package app.robloxmanager.core

import java.net.URI
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** One game as the home page and the search describe it (the fields differ a little between them), in one shape. */
data class GameCard(
    val universeId: Long, val placeId: Long?, val name: String, val playing: Long, val up: Long, val down: Long,
    val creator: String = "", val verified: Boolean = false, val age: String = "", val genre: String = "",
)

/** A row of Roblox's own home page (Top Trending, Up-and-Coming ...). */
data class GameSort(val id: String, val name: String, val games: List<GameCard>)

/** What the page of a game shows (the details Roblox gives for a universe). */
data class GameDetails(
    val name: String, val description: String, val creator: String, val creatorVerified: Boolean, val playing: Long, val visits: Long, val favorites: Long?,
    val maxPlayers: Int?, val created: String, val updated: String, val genre: String, val placeId: Long?,
)

data class GroupHit(val id: Long, val name: String, val members: Long, val description: String)

/** One public server of a game. */
data class ServerInfo(val id: String, val playing: Int, val max: Int, val ping: Int?, val fps: Int?)

/** A friend who is in a game right now, and which server they are in. */
data class FriendGame(val id: Long, val name: String, val displayName: String, val place: Long, val job: String?, val universe: Long?, val game: String)

object Games {
    const val ROW_LIMIT = 16
    const val ROWS_LIMIT = 8

    /** A card from one entry of the home page or the search; null for ads (sponsored entries are not games) and for entries without an id. */
    fun card(o: JsonObject?): GameCard? {
        if (o == null || o.bool("isSponsored") == true) return null
        val uid = o.long("universeId") ?: o.long("id") ?: return null
        return GameCard(
            uid, o.long("rootPlaceId") ?: o.long("placeId"), o.str("name") ?: "", o.long("playerCount") ?: o.long("playing") ?: 0,
            o.long("totalUpVotes") ?: 0, o.long("totalDownVotes") ?: 0, o.str("creatorName") ?: "", o.bool("creatorHasVerifiedBadge") ?: false,
            o.str("ageRecommendationDisplayName") ?: "", o.str("genreL1") ?: "",
        )
    }

    fun parseSorts(d: JsonElement?): List<GameSort> {
        val sorts = d.obj?.arr("sorts") ?: return emptyList()
        return sorts.mapNotNull { s ->
            val o = s.obj ?: return@mapNotNull null
            if (o.str("contentType") != "Games") return@mapNotNull null
            val cards = o.arr("games")?.mapNotNull { card(it.obj) } ?: emptyList()
            if (cards.isEmpty()) null else GameSort(o.str("sortId") ?: "", o.str("sortDisplayName") ?: o.str("sortId") ?: "", cards)
        }
    }

    /** (the games, the token of the next page or "") of a search. */
    fun parseSearch(d: JsonElement?): Pair<List<GameCard>, String> {
        val o = d.obj ?: return emptyList<GameCard>() to ""
        val cards = ArrayList<GameCard>()
        o.arr("searchResults")?.forEach { g ->
            val group = g.obj ?: return@forEach
            if (group.str("contentGroupType") == "Game") group.arr("contents")?.forEach { c -> card(c.obj)?.let { cards += it } }
        }
        return cards to (o.str("nextPageToken") ?: "")
    }

    fun parseDetails(o: JsonObject?): GameDetails? {
        if (o == null) return null
        val cr = o.obj("creator")
        return GameDetails(
            o.str("name") ?: "", o.str("description") ?: "", cr?.str("name") ?: "", cr?.bool("hasVerifiedBadge") ?: false, o.long("playing") ?: 0, o.long("visits") ?: 0,
            o.long("favoritedCount"), o.int("maxPlayers"), o.str("created") ?: "", o.str("updated") ?: "", o.str("genre_l1") ?: o.str("genre") ?: "", o.long("rootPlaceId"),
        )
    }

    /** The friends who are in a game (presence type 2, with a place) out of Roblox's presence answer. */
    fun friendGames(presence: JsonElement?, friends: Map<Long, Person>): List<FriendGame> = presence.obj?.arr("userPresences")?.mapNotNull { e ->
        val p = e.obj ?: return@mapNotNull null
        val place = p.long("rootPlaceId") ?: p.long("placeId") ?: return@mapNotNull null
        if (p.int("userPresenceType") != 2) return@mapNotNull null
        val id = p.long("userId") ?: return@mapNotNull null
        val f = friends[id]
        FriendGame(id, f?.name ?: "", f?.displayName ?: "", place, p.str("gameId")?.takeIf { validCode(it) }, p.long("universeId"), p.str("lastLocation") ?: "")
    } ?: emptyList()

    /** How the loaded servers can be ordered on the phone: key -> label. Roblox does not say how long a server has been running, so that is not one of them. */
    val SERVER_ORDERS = listOf("roblox" to "Roblox's order", "ping" to "Lowest ping", "fps" to "Highest FPS", "most" to "Most players", "fewest" to "Fewest players")

    /** The servers in the order asked for. A server without a ping or FPS value goes last; ties keep Roblox's order (the sort is stable). */
    fun sortServers(servers: List<ServerInfo>, mode: String): List<ServerInfo> = when (mode) {
        "ping" -> servers.sortedWith(compareBy<ServerInfo> { it.ping == null }.thenBy { it.ping ?: 0 })
        "fps" -> servers.sortedWith(compareBy<ServerInfo> { it.fps == null }.thenByDescending { it.fps ?: 0 })
        "most" -> servers.sortedByDescending { it.playing }
        "fewest" -> servers.sortedBy { it.playing }
        else -> servers
    }

    /** Whole percent of the votes that are likes, or null when nobody voted. */
    fun likePercent(up: Long, down: Long): Int? = if (up + down <= 0) null else Math.round(100.0 * up / (up + down)).toInt()

    /** 18,769 -> 18.8K; 4,753,429,786 -> 4.8B */
    fun short(n: Long): String {
        for ((limit, suffix) in listOf(1_000_000_000L to "B", 1_000_000L to "M", 1_000L to "K")) {
            if (n >= limit) {
                val v = n.toDouble() / limit
                return (if (v < 100) "%.1f".format(java.util.Locale.US, v).trimEnd('0').trimEnd('.') else "%.0f".format(java.util.Locale.US, v)) + suffix
            }
        }
        return n.toString()
    }

    /** The address that makes the Roblox app start and join: a game (place id) or a private/VIP server (place id + link code). */
    fun launcherUrl(placeId: Long, linkCode: String? = null, jobId: String? = null): String {
        if (!linkCode.isNullOrEmpty() && !validCode(linkCode)) throw IllegalArgumentException("the join code does not look like a join code")
        if (linkCode.isNullOrEmpty() && !jobId.isNullOrEmpty() && !validCode(jobId)) throw IllegalArgumentException("the server id does not look like a server id")
        return "roblox://experiences/start?placeId=$placeId" + if (!linkCode.isNullOrEmpty()) "&linkCode=$linkCode" else if (!jobId.isNullOrEmpty()) "&gameInstanceId=$jobId" else ""
    }

    private val CODE = Regex("[A-Za-z0-9_-]{1,64}")

    /** A private server link code only if it looks like one (letters, digits, - and _): it goes into a link that starts the Roblox app. */
    fun validCode(code: String?): Boolean = code != null && CODE.matches(code)

    fun pageUrl(placeId: Long?): String = if (placeId != null) "https://www.roblox.com/games/$placeId" else "https://www.roblox.com/discover"

    /** (place id, private server link code) read from a roblox.com join link such as https://www.roblox.com/games/123?privateServerLinkCode=ABC. */
    fun linkParts(url: String?): Pair<Long?, String?> = try {
        val u = URI(url ?: "")
        val code = (u.rawQuery ?: "").split("&").map { it.split("=", limit = 2) }.firstOrNull { it[0] == "privateServerLinkCode" && it.size == 2 }?.get(1)?.takeIf { validCode(it) }
        val place = Regex("/games/(\\d+)").find(u.path ?: "")?.groupValues?.get(1)?.toLongOrNull()
        place to code
    } catch (_: Exception) {
        null to null
    }
}

/** The games you looked at lately, kept on the phone (the 'Recently viewed' row). */
object RecentGames {
    const val KEY = "recentGames"
    const val LIMIT = 20

    fun load(prefs: Prefs): List<GameCard> = try {
        (prefs.raw(KEY) as? kotlinx.serialization.json.JsonArray)?.mapNotNull { e ->
            val o = e.obj ?: return@mapNotNull null
            val uid = o.long("u") ?: return@mapNotNull null
            GameCard(uid, o.long("p"), (o.str("n") ?: return@mapNotNull null).take(120), o.long("c") ?: 0, o.long("up") ?: 0, o.long("down") ?: 0, (o.str("by") ?: "").take(60), o.bool("v") ?: false, o.str("a") ?: "", o.str("g") ?: "")
        }?.take(LIMIT) ?: emptyList()
    } catch (_: Exception) { emptyList() }

    /** Put a game first (it moves up if it was there already). Returns the new list. */
    fun add(prefs: Prefs, card: GameCard): List<GameCard> {
        val items = listOf(card) + load(prefs).filter { it.universeId != card.universeId }
        try {
            prefs.put(KEY, kotlinx.serialization.json.JsonArray(items.take(LIMIT).map { c ->
                obj("u" to c.universeId, "p" to c.placeId, "n" to c.name, "c" to c.playing, "up" to c.up, "down" to c.down, "by" to c.creator, "v" to c.verified, "a" to c.age, "g" to c.genre)
            }))
        } catch (_: Exception) { }
        return items.take(LIMIT)
    }
}

// ---------------------------------------------------------------- the calls (public data: no sign-in needed)
suspend fun RobloxApi.discoverSorts(sessionId: String): List<GameSort> =
    Games.parseSorts(client.get("https://apis.roblox.com/explore-api/v1/get-sorts", mapOf("sessionId" to sessionId, "device" to "phone", "country" to "all"), auth = false).json)

suspend fun RobloxApi.searchGames(text: String, sessionId: String, token: String = ""): Pair<List<GameCard>, String> {
    val q = HashMap<String, String>().apply { put("searchQuery", text); put("sessionId", sessionId); put("pageType", "all"); if (token.isNotEmpty()) put("pageToken", token) }
    return Games.parseSearch(client.get("https://apis.roblox.com/search-api/omni-search", q, auth = false).json)
}

suspend fun RobloxApi.searchGroups(text: String): List<GroupHit> =
    client.get("https://groups.roblox.com/v1/groups/search", mapOf("keyword" to text, "limit" to "10"), auth = false).json.items().mapNotNull { g ->
        val id = g.long("id") ?: return@mapNotNull null
        GroupHit(id, g.str("name") ?: "", g.long("memberCount") ?: 0, g.str("description") ?: "")
    }

suspend fun RobloxApi.gameDetails(universeId: Long): GameDetails? =
    Games.parseDetails(client.get("https://games.roblox.com/v1/games", mapOf("universeIds" to universeId.toString()), auth = false).json.items().firstOrNull())

suspend fun RobloxApi.gameVotes(universeId: Long): Pair<Long, Long>? =
    client.get("https://games.roblox.com/v1/games/votes", mapOf("universeIds" to universeId.toString()), auth = false).json.items().firstOrNull()?.let { (it.long("upVotes") ?: 0) to (it.long("downVotes") ?: 0) }

suspend fun RobloxApi.gameFavorites(universeId: Long): Long? =
    client.get("https://games.roblox.com/v1/games/$universeId/favorites/count", auth = false).json.obj?.long("favoritesCount")

/** {universe id: picture url}, 100 per request. */
suspend fun RobloxApi.gameIcons(ids: List<Long>, size: String = "150x150"): Map<Long, String> {
    val out = HashMap<Long, String>()
    for (c in ids.distinct().chunked(100)) {
        try {
            client.get("https://thumbnails.roblox.com/v1/games/icons", mapOf("universeIds" to c.joinToString(","), "size" to size, "format" to "Png", "isCircular" to "false"), auth = false)
                .json.items().forEach { t -> val id = t.long("targetId"); val u = t.str("imageUrl"); if (id != null && !u.isNullOrEmpty()) out[id] = u }
        } catch (_: RobloxException) { }
    }
    return out
}

suspend fun RobloxApi.gameCover(universeId: Long): String =
    client.get("https://thumbnails.roblox.com/v1/games/multiget/thumbnails", mapOf("universeIds" to universeId.toString(), "size" to "768x432", "format" to "Png", "count" to "1", "isCircular" to "false"), auth = false)
        .json.items().firstNotNullOfOrNull { g -> g.arr("thumbnails")?.firstNotNullOfOrNull { it.obj?.str("imageUrl")?.takeIf { u -> u.isNotEmpty() } } } ?: ""

/** (the public servers, the next cursor): fewest players first ("Asc") or most ("Desc"); only servers with room. */
suspend fun RobloxApi.gameServers(placeId: Long, sort: String = "Asc", cursor: String = "", limit: Int = 50): Pair<List<ServerInfo>, String> {
    val q = hashMapOf("sortOrder" to sort, "limit" to limit.toString(), "excludeFullGames" to "true")
    if (cursor.isNotEmpty()) q["cursor"] = cursor
    val d = client.get("https://games.roblox.com/v1/games/$placeId/servers/Public", q, auth = false).json
    val servers = d.items().mapNotNull { s ->
        val id = s.str("id")?.takeIf { Games.validCode(it) } ?: return@mapNotNull null
        ServerInfo(id, s.int("playing") ?: 0, s.int("maxPlayers") ?: 0, s.long("ping")?.toInt(), s.long("fps")?.toInt())
    }
    return servers to (d.obj?.str("nextPageCursor") ?: "")
}

suspend fun RobloxApi.favoriteState(universeId: Long): Boolean = client.get("https://games.roblox.com/v1/games/$universeId/favorites").json.obj?.bool("isFavorited") ?: false

suspend fun RobloxApi.setFavorite(universeId: Long, on: Boolean) { client.post("https://games.roblox.com/v1/games/$universeId/favorites", obj("isFavorited" to on)) }

/** The account's favorite games (as far as its privacy settings show them). */
suspend fun RobloxApi.favoriteGames(userId: Long): List<GameCard> =
    client.get("https://games.roblox.com/v2/users/$userId/favorite/games", mapOf("limit" to "50", "sortOrder" to "Desc"), auth = false).json.items().mapNotNull { g ->
        val id = g.long("id") ?: return@mapNotNull null
        GameCard(id, g.obj("rootPlace")?.long("id"), g.str("name") ?: "", 0, 0, 0, g.obj("creator")?.str("name") ?: "")
    }

/** The friends who are in a game right now (friends, then their presence, 100 at a time). */
suspend fun RobloxApi.friendsInGames(): List<FriendGame> {
    val friends = friends().associateBy { it.id }
    val out = ArrayList<FriendGame>()
    for (chunk in friends.keys.toList().chunked(100)) out += Games.friendGames(client.post("https://presence.roblox.com/v1/presence/users", obj("userIds" to chunk)).json, friends)
    return out
}
