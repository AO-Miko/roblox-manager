package app.robloxmanager.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/** Where a Roblox server is, and how long it has been running. Roblox's join answer gives the id of the server's data centre, its public address and the time it started.
 *  Two services can say where that is, and each is used only if the person agreed to it (Settings): RoSeal's public list of Roblox data centres (data.roseal.live: one plain
 *  download, nothing about the person or the server is sent), and ipwho.is (the server's public address is sent, nothing else). What they said is kept on the phone: by data
 *  centre for 30 days, and for ipwho.is by the first three numbers of the address (Roblox puts a whole block of addresses in one data centre).
 *  Looking up is always started by the person (the "Location and uptime" button). */
data class Place(val city: String, val region: String, val country: String, val cc: String, val lat: Double, val lon: Double) {
    val label get() = listOf(city, country.ifEmpty { cc }).filter { it.isNotEmpty() }.joinToString(", ").ifEmpty { "Unknown" }
}

/** What Roblox's join answer says about one server. */
data class ServerFacts(val address: String, val startedMs: Long?, val dc: Long?, val placeVersion: Long?)

class GeoException(message: String) : Exception(message)

object Geo {
    const val TTL_MS = 30L * 24 * 3600 * 1000
    const val MAX_CACHED = 500
    const val MAX_ANSWER = 20_000L
    const val FIELDS = "success,country,country_code,region,city,latitude,longitude"
    val JOIN_RETRY = setOf(0, 2, 22)             // the statuses of a join answer that mean "ask again"

    /** The address as text when it is a public IPv4 address (the only kind that is ever looked up), else null. */
    fun publicIpv4(text: String?): String? {
        val parts = text?.trim()?.split(".") ?: return null
        if (parts.size != 4 || parts.any { it.isEmpty() || it.length > 3 || !it.all(Char::isDigit) }) return null
        val o = parts.map { it.toInt() }
        if (o.any { it > 255 }) return null
        val (a, b, c) = o
        val reserved = a == 0 || a == 10 || a == 127 || a >= 224 || (a == 100 && b in 64..127) || (a == 169 && b == 254) || (a == 172 && b in 16..31) ||
            (a == 192 && b == 168) || (a == 192 && b == 0 && c in 0..2) || (a == 198 && b in 18..19) || (a == 198 && b == 51 && c == 100) || (a == 203 && b == 0 && c == 113)
        return if (reserved) null else o.joinToString(".")
    }

    /** '128.116.44.33' -> '128.116.44' */
    fun blockOf(ip: String) = ip.split(".").take(3).joinToString(".")

    private fun round3(v: Double) = Math.round(v * 1000) / 1000.0

    /** ipwho.is's answer -> a place, or null when it does not look right. */
    fun clean(d: JsonElement?): Place? {
        val o = d.obj ?: return null
        if (o.bool("success") == false) return null
        fun num(k: String) = (o[k] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toDoubleOrNull()
        val lat = num("latitude") ?: return null
        val lon = num("longitude") ?: return null
        if (lat !in -90.0..90.0 || lon !in -180.0..180.0) return null
        return Place((o.str("city") ?: "").take(60), (o.str("region") ?: "").take(60), (o.str("country") ?: "").take(60), (o.str("country_code") ?: "").take(2).uppercase(), round3(lat), round3(lon))
    }

    /** A place from what was kept in the file, checked the same way as a fresh answer. */
    fun fromKept(o: JsonObject): Place? = clean(JsonObject(mapOf("success" to JsonPrimitive(true), "city" to (o["city"] ?: JsonPrimitive("")), "region" to (o["region"] ?: JsonPrimitive("")),
        "country" to (o["country"] ?: JsonPrimitive("")), "country_code" to (o["cc"] ?: JsonPrimitive("")), "latitude" to (o["lat"] ?: JsonPrimitive("x")), "longitude" to (o["lon"] ?: JsonPrimitive("x")))))

    fun placeJson(p: Place, t: Long) = obj("city" to p.city, "region" to p.region, "country" to p.country, "cc" to p.cc, "lat" to p.lat, "lon" to p.lon, "t" to t)

    /** The few values wanted from a join script (names as Roblox sends them, or in camelCase). */
    fun joinFacts(script: JsonObject, nowMs: Long = System.currentTimeMillis()): ServerFacts {
        fun pick(a: String, b: String): JsonElement? = script[a] ?: script[b]
        var address: String? = null
        for ((key, alt) in listOf("UdmuxEndpoints" to "udmuxEndpoints", "ServerConnections" to "serverConnections")) {
            for (e in pick(key, alt).arr.orEmpty()) {
                val o = e.obj ?: continue
                val a = publicIpv4(o.str("Address") ?: o.str("address"))
                if (a != null) { address = a; break }
            }
            if (address != null) break
        }
        if (address == null) throw RobloxException(0, "Roblox did not give a public address for this server", local = true)
        fun whole(e: JsonElement?): Long? = (e as? JsonPrimitive)?.takeIf { !it.isString }?.let { it.longOrNull ?: it.content.toDoubleOrNull()?.toLong() }?.takeIf { it > 0 }
        val started = whole(pick("ServerClaimedTime", "serverClaimedTime"))?.takeIf { it in 946_684_800_001..(nowMs + 86_400_000) }
        return ServerFacts(address, started, whole(pick("DataCenterId", "dataCenterId")), whole(pick("PlaceVersion", "placeVersion")))
    }

    private suspend fun fetchJson(http: OkHttpClient, url: String, max: Long): JsonElement? = withContext(Dispatchers.IO) {
        try {
            http.newCall(Request.Builder().url(url).header("User-Agent", "RobloxManager").build()).execute().use { r ->
                if (!r.isSuccessful) throw GeoException("The service answered ${r.code}")
                val src = r.body!!.source()
                src.request(max + 1)
                if (src.buffer.size > max) throw GeoException("The answer was too big")
                AppJson.parseToJsonElement(src.buffer.readUtf8())
            }
        } catch (e: GeoException) {
            throw e
        } catch (e: java.io.IOException) {
            throw GeoException("The service could not be reached")
        } catch (e: IllegalArgumentException) {
            throw GeoException("The service gave an answer that could not be read")
        }
    }

    private fun plainClient() = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false).callTimeout(10, TimeUnit.SECONDS).build()

    /** Asks ipwho.is over https about one address: no cookie, no redirect, a small answer. */
    fun httpFetch(http: OkHttpClient = plainClient()): suspend (String) -> JsonElement? = { ip -> fetchJson(http, "https://ipwho.is/$ip?fields=$FIELDS", MAX_ANSWER) }

    /** Downloads RoSeal's list of data centres: a plain GET, no cookie, no redirect. */
    fun rosealFetch(http: OkHttpClient = plainClient(), max: Long = RoSeal.MAX_BYTES): suspend (String) -> JsonElement? = { url -> fetchJson(http, url, max) }
}

/** One group of data centres of RoSeal's list, with the city they are in. */
data class DcGroup(val ids: Set<Long>, val place: Place)

object RoSeal {
    const val URL = "https://data.roseal.live/v2/grouped-datacenters.json"
    const val TTL_MS = 6L * 3600 * 1000
    const val MAX_BYTES = 200_000L

    /** RoSeal's list -> the well-formed groups only (positions come as text there). */
    fun parseGroups(d: JsonElement?): List<DcGroup> = (d as? JsonArray)?.take(200)?.mapNotNull { g ->
        val o = g.obj ?: return@mapNotNull null
        val loc = o.obj("location") ?: return@mapNotNull null
        val ll = loc.arr("latLong")?.mapNotNull { (it as? JsonPrimitive)?.content?.toDoubleOrNull() } ?: return@mapNotNull null
        if (ll.size != 2 || ll[0] !in -90.0..90.0 || ll[1] !in -180.0..180.0) return@mapNotNull null
        val ids = o.arr("dataCenterIds")?.take(2000)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> !p.isString }?.longOrNull }?.toSet().orEmpty()
        if (ids.isEmpty()) null else DcGroup(ids, Place((loc.str("city") ?: "").take(60), (loc.str("region") ?: "").take(60), "", (loc.str("country") ?: "").take(2).uppercase(),
            Math.round(ll[0] * 1000) / 1000.0, Math.round(ll[1] * 1000) / 1000.0))
    } ?: emptyList()
}

/** RoSeal's list of data centres, kept 6 hours in a file. [fetch] downloads it. */
class RoSealList(private val file: File, private val fetch: suspend (String) -> JsonElement?, private val now: () -> Long = { System.currentTimeMillis() }) {
    suspend fun groups(): List<DcGroup> {
        val kept = try { AppJson.parseToJsonElement(file.readText()).obj } catch (_: Exception) { null }
        val old = RoSeal.parseGroups(kept?.get("groups"))
        if (old.isNotEmpty() && now() - (kept?.long("t") ?: 0) < RoSeal.TTL_MS) return old
        val data = try { fetch(RoSeal.URL) } catch (e: GeoException) { if (old.isNotEmpty()) return old else throw GeoException("RoSeal's list of data centres could not be downloaded") }
        val groups = RoSeal.parseGroups(data)
        if (groups.isEmpty()) { if (old.isNotEmpty()) return old; throw GeoException("RoSeal's list of data centres did not look right") }
        try { file.parentFile?.mkdirs(); file.writeText(AppJson.encodeToString(JsonElement.serializer(), obj("t" to now(), "groups" to data))) } catch (_: Exception) { }
        return groups
    }

    suspend fun placeFor(dc: Long): Place? = groups().firstOrNull { dc in it.ids }?.place
}

/** The places of servers, with the answers kept in a file (by data centre, and for ipwho.is by block of addresses). [fetch] asks ipwho.is about one address. */
class GeoBook(private val file: File, private val fetch: suspend (String) -> JsonElement?, private val now: () -> Long = { System.currentTimeMillis() }) {
    private fun read(): Map<String, JsonObject> = try {
        AppJson.parseToJsonElement(file.readText()).obj?.entries?.mapNotNull { (k, v) -> v.obj?.let { k to it } }?.toMap() ?: emptyMap()
    } catch (_: Exception) { emptyMap() }

    private fun write(m: Map<String, JsonObject>) {
        try {
            val keep = m.entries.sortedByDescending { it.value.long("t") ?: 0 }.take(Geo.MAX_CACHED).associate { it.key to it.value }
            file.parentFile?.mkdirs()
            file.writeText(AppJson.encodeToString(JsonElement.serializer(), JsonObject(keep)))
        } catch (_: Exception) { }
    }

    /** The place of a public address, by ipwho.is (the answer is kept by block of addresses). */
    suspend fun lookup(address: String): Place {
        val ip = Geo.publicIpv4(address) ?: throw GeoException("That is not a public address")
        val key = Geo.blockOf(ip)
        val cache = read()
        val hit = cache[key]
        if (hit != null && now() - (hit.long("t") ?: 0) < Geo.TTL_MS) Geo.fromKept(hit)?.let { return it }
        val place = Geo.clean(fetch(ip)) ?: throw GeoException("The location service did not know that address")
        write(cache + (key to Geo.placeJson(place, now())))
        return place
    }

    /** The place of a server: kept answers first, then RoSeal's list, then ipwho.is, each only if allowed. GeoException says in plain words why a place could not be found. */
    suspend fun resolve(info: ServerFacts, useRoseal: Boolean, useIpwho: Boolean, roseal: RoSealList): Place {
        val dc = info.dc
        val key = "dc:$dc"
        if (dc != null) read()[key]?.let { hit -> if (now() - (hit.long("t") ?: 0) < Geo.TTL_MS) Geo.fromKept(hit)?.let { return it } }
        if (!useRoseal && !useIpwho) throw GeoException("Server locations are switched off in Settings")
        val why = ArrayList<String>()
        var place: Place? = null
        if (useRoseal) {
            if (dc == null) why += "RoSeal's list cannot place a server without its data centre id"
            else try {
                place = roseal.placeFor(dc)
                if (place == null) why += "RoSeal's list does not know this data centre"
            } catch (e: GeoException) { why += e.message ?: "RoSeal's list could not be used" }
        }
        if (place == null && useIpwho) place = lookup(info.address)
        if (place == null) throw GeoException(why.joinToString(". ") + if (!useIpwho) " (and ipwho.is is switched off in Settings)" else "")
        if (dc != null) write(read() + (key to Geo.placeJson(place, now())))
        return place
    }
}

/** What Roblox's join answer says about one public server (the call the website makes when Play is pressed; nothing is joined). Only the values in [ServerFacts] are taken out of
 *  the answer: its tickets are never kept or logged. Needs the sign-in. The first answers may say "not ready", so it asks again a few times. */
suspend fun RobloxApi.serverInfo(placeId: Long, jobId: String, tries: Int = 8, waitMs: Long = 1250): ServerFacts {
    if (!Games.validCode(jobId)) throw IllegalArgumentException("odd server id")
    var status: Int? = null
    for (k in 0 until tries) {
        val d = client.post("https://gamejoin.roblox.com/v1/join-game-instance",
            obj("placeId" to placeId, "isTeleport" to false, "gameId" to jobId, "gameJoinAttemptId" to java.util.UUID.randomUUID().toString())).json.obj
        var script: JsonObject? = d?.obj("joinScript")
        if (script == null) d?.str("joinScript")?.let { s -> script = try { AppJson.parseToJsonElement(s).obj } catch (_: Exception) { null } }
        script?.let { return Geo.joinFacts(it) }
        status = d?.int("status")
        if (status in Geo.JOIN_RETRY && k + 1 < tries) { delay(waitMs); continue }
        break
    }
    if (status == null || status in Geo.JOIN_RETRY) throw RobloxException(0, "Roblox is still getting this server ready (it may be full or just closed)", local = true)
    throw RobloxException(0, "Roblox would not let this server be looked at (status $status)", local = true)
}

// ======================================================================== the world map's data

object WorldMap {
    /** Longitude and latitude -> a point on a w x h picture (every degree takes the same room, so the map is twice as wide as high). */
    fun project(lat: Double, lon: Double, w: Float, h: Float): Pair<Float, Float> = Pair(((lon + 180.0) / 360.0 * w).toFloat(), ((90.0 - lat) / 180.0 * h).toFloat())

    /** The rings of the land from world_land.json: each ring as longitude/latitude pairs (empty when the text cannot be read, so the dots still show). */
    fun parseLand(text: String): List<List<Pair<Double, Double>>> = try {
        val d = AppJson.parseToJsonElement(text).obj
        val scale = (d?.int("scale") ?: 10).toDouble()
        d?.arr("rings")?.mapNotNull { r ->
            val flat = (r as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content?.toDoubleOrNull() } ?: return@mapNotNull null
            (0 until flat.size / 2).map { i -> Pair(flat[i * 2] / scale, flat[i * 2 + 1] / scale) }
        } ?: emptyList()
    } catch (_: Exception) { emptyList() }

    /** The located servers, one entry per place: (place, server ids). */
    fun groupPlaces(servers: List<ServerInfo>, places: Map<String, Place>): List<Pair<Place, List<String>>> =
        servers.mapNotNull { s -> places[s.id]?.let { it to s.id } }.groupBy({ it.first.lat to it.first.lon }, { it }).values.map { l -> l[0].first to l.map { it.second } }
}
