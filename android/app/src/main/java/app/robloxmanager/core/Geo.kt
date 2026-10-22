package app.robloxmanager.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/** Where a Roblox server is: the public address of a server (from Roblox's join answer) is looked up on ipwho.is, which says which city it is in.
 *  Only the address of a Roblox server is sent to ipwho.is (never a name, a cookie or an account); answers are kept 30 days by the first three numbers of the
 *  address, because Roblox puts a whole block of addresses in one data centre. Looking up is always started by the person (the Locate button). */
data class Place(val city: String, val region: String, val country: String, val cc: String, val lat: Double, val lon: Double) {
    val label get() = listOf(city, country.ifEmpty { cc }).filter { it.isNotEmpty() }.joinToString(", ").ifEmpty { "Unknown" }
}

class GeoException(message: String) : Exception(message)

object Geo {
    const val TTL_MS = 30L * 24 * 3600 * 1000
    const val MAX_CACHED = 500
    const val MAX_ANSWER = 20_000L
    const val FIELDS = "success,country,country_code,region,city,latitude,longitude"

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

    /** ipwho.is's answer -> a place, or null when it does not look right. */
    fun clean(d: JsonElement?): Place? {
        val o = d.obj ?: return null
        if (o.bool("success") == false) return null
        fun num(k: String) = (o[k] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toDoubleOrNull()
        val lat = num("latitude") ?: return null
        val lon = num("longitude") ?: return null
        if (lat !in -90.0..90.0 || lon !in -180.0..180.0) return null
        return Place((o.str("city") ?: "").take(60), (o.str("region") ?: "").take(60), (o.str("country") ?: "").take(60), (o.str("country_code") ?: "").take(2).uppercase(),
            Math.round(lat * 1000) / 1000.0, Math.round(lon * 1000) / 1000.0)
    }

    /** A place from what was kept in the file, checked the same way as a fresh answer. */
    fun fromKept(o: JsonObject): Place? = clean(JsonObject(mapOf("success" to JsonPrimitive(true), "city" to (o["city"] ?: JsonPrimitive("")), "region" to (o["region"] ?: JsonPrimitive("")),
        "country" to (o["country"] ?: JsonPrimitive("")), "country_code" to (o["cc"] ?: JsonPrimitive("")), "latitude" to (o["lat"] ?: JsonPrimitive("x")), "longitude" to (o["lon"] ?: JsonPrimitive("x")))))

    /** Asks ipwho.is over https, without any cookie, never following a redirect, reading at most [MAX_ANSWER] bytes. */
    fun httpFetch(http: OkHttpClient = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false).callTimeout(10, TimeUnit.SECONDS).build()): suspend (String) -> JsonElement? = { ip ->
        withContext(Dispatchers.IO) {
            try {
                http.newCall(Request.Builder().url("https://ipwho.is/$ip?fields=$FIELDS").header("User-Agent", "RobloxManager").build()).execute().use { r ->
                    if (!r.isSuccessful) throw GeoException("The location service answered ${r.code}")
                    val src = r.body!!.source()
                    src.request(MAX_ANSWER + 1)
                    if (src.buffer.size > MAX_ANSWER) throw GeoException("The answer was too big")
                    AppJson.parseToJsonElement(src.buffer.readUtf8())
                }
            } catch (e: GeoException) {
                throw e
            } catch (e: java.io.IOException) {
                throw GeoException("The location service could not be reached")
            } catch (e: IllegalArgumentException) {
                throw GeoException("The location service gave an answer that could not be read")
            }
        }
    }
}

/** The places of addresses, with the answers kept in a file (by block of addresses). [fetch] asks the service for one address. */
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

    suspend fun lookup(address: String): Place {
        val ip = Geo.publicIpv4(address) ?: throw GeoException("That is not a public address")
        val key = Geo.blockOf(ip)
        val cache = read()
        val hit = cache[key]
        if (hit != null && now() - (hit.long("t") ?: 0) < Geo.TTL_MS) Geo.fromKept(hit)?.let { return it }
        val place = Geo.clean(fetch(ip)) ?: throw GeoException("The location service did not know that address")
        write(cache + (key to obj("city" to place.city, "region" to place.region, "country" to place.country, "cc" to place.cc, "lat" to place.lat, "lon" to place.lon, "t" to now())))
        return place
    }
}

/** The public address of one public server, from Roblox's join answer (the call the website makes when Play is pressed; nothing is joined).
 *  Only the address is taken out of the answer: its tickets are never kept or logged. Needs the sign-in. The first answers may say "not ready", so it asks again a few times. */
suspend fun RobloxApi.serverAddress(placeId: Long, jobId: String, tries: Int = 4, waitMs: Long = 1500): String {
    if (!Games.validCode(jobId)) throw IllegalArgumentException("odd server id")
    for (k in 0 until tries) {
        val d = client.post("https://gamejoin.roblox.com/v1/join-game-instance",
            obj("placeId" to placeId, "isTeleport" to false, "gameId" to jobId, "gameJoinAttemptId" to java.util.UUID.randomUUID().toString())).json.obj
        var script: JsonObject? = d?.obj("joinScript")
        if (script == null) d?.str("joinScript")?.let { s -> script = try { AppJson.parseToJsonElement(s).obj } catch (_: Exception) { null } }
        script?.let { sc ->
            sc.arr("UdmuxEndpoints")?.forEach { e -> e.obj?.str("Address")?.let { a -> Geo.publicIpv4(a)?.let { return it } } }
            throw RobloxException(0, "Roblox did not give a public address for this server", local = true)
        }
        if (k + 1 < tries) delay(waitMs)
    }
    throw RobloxException(0, "Roblox did not give this server's address (it may be full or just closed)", local = true)
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
            val flat = (r as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content?.toDoubleOrNull() } ?: return@mapNotNull null
            (0 until flat.size / 2).map { i -> Pair(flat[i * 2] / scale, flat[i * 2 + 1] / scale) }
        } ?: emptyList()
    } catch (_: Exception) { emptyList() }

    /** The located servers, one entry per place: (place, server ids). */
    fun groupPlaces(servers: List<ServerInfo>, places: Map<String, Place>): List<Pair<Place, List<String>>> =
        servers.mapNotNull { s -> places[s.id]?.let { it to s.id } }.groupBy({ it.first.lat to it.first.lon }, { it }).values.map { l -> l[0].first to l.map { it.second } }
}
