package app.robloxmanager.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.io.File
import java.time.Instant
import java.time.ZoneOffset

/** What you and another person have in common, from Roblox's profile insights. */
data class Insight(val mutual: List<Person>, val friendsSinceMs: Long?, val playedTogether: Boolean)
data class VoiceState(val enabled: Boolean, val eligible: Boolean, val optedIn: Boolean, val banned: Boolean, val bannedUntil: String?, val verified: Boolean)
data class AgeState(val verified: Boolean, val age: Int?)
data class DevExState(val eligibleRobux: Long?, val updated: String?, val minCashOut: Long?, val canCashOut: Boolean?, val suspended: Boolean?, val atRisk: Boolean?)
data class WikiLink(val label: String, val url: String)

object Features {
    /** Roblox's profile insights -> {user id: what is shared}. Broken entries are dropped; a person with nothing in common is there with empty values. */
    fun parseInsights(d: JsonElement?): Map<Long, Insight> {
        val out = LinkedHashMap<Long, Insight>()
        d.obj?.arr("userInsights")?.forEach { e ->
            val o = e.obj ?: return@forEach
            val id = o.long("targetUser") ?: return@forEach
            val mutual = ArrayList<Person>()
            var since: Long? = null
            var played = false
            o.arr("profileInsights")?.forEach { i ->
                val ins = i.obj ?: return@forEach
                ins.obj("mutualFriendInsight")?.obj("mutualFriends")?.entries?.take(500)?.forEach { (k, v) ->
                    val m = v.obj ?: return@forEach
                    k.toLongOrNull()?.let { mutual += Person(it, (m.str("username") ?: "").take(40), (m.str("displayName") ?: "").take(60)) }
                }
                ins.obj("friendshipAgeInsight")?.obj("friendsSinceDateTime")?.long("seconds")?.takeIf { it > 0 }?.let { since = it * 1000 }
                if (ins.obj("offlineFrequentsInsight")?.bool("havePlayedTogether") == true) played = true
            }
            out[id] = Insight(mutual, since, played)
        }
        return out
    }

    /** "5 years, 7 months" / "under a month": how long ago a time was. */
    fun yearsText(ms: Long, nowMs: Long = System.currentTimeMillis()): String {
        val then = Instant.ofEpochMilli(ms).atZone(ZoneOffset.UTC)
        val now = Instant.ofEpochMilli(nowMs).atZone(ZoneOffset.UTC)
        val months = maxOf(0, (now.year - then.year) * 12 + now.monthValue - then.monthValue - (if (now.dayOfMonth < then.dayOfMonth) 1 else 0))
        val y = months / 12; val m = months % 12
        val parts = listOfNotNull(if (y > 0) "$y year${if (y != 1) "s" else ""}" else null, if (m > 0) "$m month${if (m != 1) "s" else ""}" else null)
        return parts.joinToString(", ").ifEmpty { "under a month" }
    }

    /** The text of the "you and ..." window: friends since, played together, the shared friends. Plain text (a name from Roblox is never read as markup). */
    fun describe(info: Insight?, name: String, nowMs: Long = System.currentTimeMillis()): String {
        if (info == null) return "Roblox gave nothing about you and $name."
        val lines = ArrayList<String>()
        if (info.friendsSinceMs != null) lines += "Friends since ${Instant.ofEpochMilli(info.friendsSinceMs).atZone(ZoneOffset.UTC).toLocalDate()} (${yearsText(info.friendsSinceMs, nowMs)})."
        else lines += "Roblox does not say since when you are friends (you may not be)."
        if (info.playedTogether) lines += "You have played together."
        if (info.mutual.isNotEmpty()) {
            lines += ""
            lines += "${info.mutual.size} mutual friend${if (info.mutual.size != 1) "s" else ""}:"
            info.mutual.sortedBy { it.title.lowercase() }.forEach { m -> lines += "  ${m.title}" + (if (m.name.isNotEmpty() && m.displayName != m.name && m.displayName.isNotEmpty()) "  (@${m.name})" else "") }
        } else lines += "No mutual friends."
        return lines.joinToString("\n")
    }

    fun voiceText(v: VoiceState): String = when {
        v.banned -> "suspended" + (v.bannedUntil?.take(10)?.let { " until $it" } ?: "")
        !v.eligible -> "not available for this account"
        !v.enabled -> "off"
        else -> (if (v.optedIn) "on" else "available, not switched on") + (if (v.verified) ", verified" else "")
    }

    fun verifiedText(a: AgeState): String = if (!a.verified) "not verified" else "verified" + (a.age?.let { " (age $it)" } ?: "")

    /** The Developer Exchange line. No money value is guessed (the rate is Roblox's to set). */
    fun devexText(d: DevExState): String {
        if (d.eligibleRobux == null && d.minCashOut == null) return "DevEx: not available for this account."
        val fmt = java.text.NumberFormat.getInstance(java.util.Locale.US)
        val parts = ArrayList<String>()
        d.eligibleRobux?.let { parts += "${fmt.format(it)} Robux can be cashed out" + (d.updated?.take(10)?.let { u -> " (as of $u)" } ?: "") }
        d.minCashOut?.takeIf { it > 0 }?.let { parts += "minimum ${fmt.format(it)}" }
        if (d.suspended == true) parts += "DevEx is SUSPENDED" else if (d.atRisk == true) parts += "at risk of suspension"
        if (d.canCashOut == true) parts += "you can cash out now" else if (d.canCashOut == false && d.suspended != true) parts += "cashing out is not open to you right now"
        return "DevEx: " + parts.joinToString("; ") + "."
    }

    private val ORIGINS = mapOf("InGame" to "A game", "UserProfile" to "Your profile", "PhoneContactImport" to "Contacts", "FriendRecommendation" to "Recommendations", "QrCode" to "QR code",
        "ProfileShare" to "A shared profile", "UserSearch" to "Search", "PlayerSearch" to "Search", "Chat" to "Chat")

    /** Where a friend request came from, as Roblox says it; anything unknown is shown as plain letters, cut short. */
    fun originText(kind: String?): String = if (kind.isNullOrEmpty()) "" else ORIGINS[kind] ?: kind.filter { it.isLetterOrDigit() || it in " _-" }.take(30)

    /** The line under a friend request: when it was sent, where it came from, how many friends you share. */
    fun requestExtra(o: JsonObject): String {
        val fr = o.obj("friendRequest")
        val sent = fr?.str("sentAt")?.take(10)?.takeIf { Regex("\\d{4}-\\d{2}-\\d{2}").matches(it) }
        val mutual = o.arr("mutualFriendsList")?.size ?: 0
        return listOfNotNull(sent?.let { "sent $it" }, originText(fr?.str("originSourceType")).takeIf { it.isNotEmpty() }?.let { "from $it" }, if (mutual > 0) "$mutual mutual" else null).joinToString("  ·  ")
    }

    /** "v1805", with "(older)" when other servers run a newer version (the newest one that was looked up). */
    fun versionText(version: Long?, newest: Long): String = if (version == null || version <= 0) "" else "v$version" + if (newest > 0 && version < newest) " (older)" else ""
}

suspend fun RobloxApi.profileInsights(ids: List<Long>): Map<Long, Insight> {
    val list = ids.distinct().take(50)
    if (list.isEmpty()) return emptyMap()
    return Features.parseInsights(client.post("https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights", obj("userIds" to list.map { it.toString() })).json)
}

suspend fun RobloxApi.voiceState(): VoiceState {
    val d = client.get("https://voice.roblox.com/v1/settings").json.obj
    val until = when (val u = d?.get("bannedUntil")) { is JsonObject -> u.long("Seconds")?.toString(); is JsonNull, null -> null; is JsonPrimitive -> u.content; else -> null }
    return VoiceState(d?.bool("isVoiceEnabled") == true, d?.bool("isUserEligible") == true, d?.bool("isUserOptIn") == true, d?.bool("isBanned") == true, until?.take(40), d?.bool("isVerifiedForVoice") == true)
}

suspend fun RobloxApi.verifiedAge(): AgeState {
    val d = client.get("https://apis.roblox.com/age-verification-service/v1/age-verification/verified-age").json.obj
    val numeric = (d?.get("verifiedAge") as? JsonPrimitive)?.isString == false
    return AgeState(d?.bool("isVerified") == true, d?.int("verifiedAge")?.takeIf { numeric && it in 1..119 })
}

/** Both Developer Exchange calls are read-only; one that Roblox refuses (an account that never earned) leaves its values empty. */
suspend fun RobloxApi.devexState(): DevExState {
    var eligible: Long? = null; var updated: String? = null
    try { client.get("https://apis.roblox.com/creator-devex-data-service/v1/devexEligibleRobux").json.obj?.let { o -> eligible = o.long("eligibleRobux"); updated = o.str("updatedUtc")?.take(25) } }
    catch (e: RobloxException) { if (e.status == 401) throw e }
    var min: Long? = null; var can: Boolean? = null; var susp: Boolean? = null; var risk: Boolean? = null
    try { client.get("https://economy.roblox.com/v1/developer-exchange/info").json.obj?.let { o -> min = o.long("minRobuxToCashOut"); can = o.bool("canProceedToCashout"); susp = o.bool("isDevExSuspended"); risk = o.bool("isAtRiskOfSuspension") } }
    catch (e: RobloxException) { if (e.status == 401) throw e }
    return DevExState(eligible, updated, min, can, susp, risk)
}

// ======================================================================== RoSeal's links to game wikis (asked first; see the Settings switch)

object RoSealLinks {
    const val URL = "https://data.roseal.live/v2/experience-links.json"
    const val TTL_MS = 24L * 3600 * 1000
    const val MAX_BYTES = 400_000L
    private val HOST = Regex("^(?:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\\.)+[a-z]{2,24}$")
    private val PATH = Regex("^(?:/[A-Za-z0-9._~%+\\-]{0,100}){0,8}/?$")
    private const val BAD = " \t\r\n\\@:?#&=\"'<>"

    /** 'adoptme.fandom.com' or 'wiki.example.org/Game' -> 'https://...', or null if it is anything else than a plain host (and a path). */
    fun safeUrl(text: String?): String? {
        if (text == null || text.length > 200 || text.any { it in BAD }) return null
        val t = text.trim()
        val host = t.substringBefore("/").lowercase()
        val path = t.substring(t.indexOf("/").let { if (it < 0) t.length else it })
        if (!HOST.matches(host)) return null
        return if (PATH.matches(path)) "https://$host$path" else null
    }

    /** RoSeal's file -> {universe id: links}, keeping only wiki links with a safe address, once each. */
    fun parse(d: JsonElement?): Map<Long, List<WikiLink>> {
        val out = LinkedHashMap<Long, MutableList<WikiLink>>()
        (d as? JsonArray)?.take(5000)?.forEach { e ->
            val o = e.obj ?: return@forEach
            val links = ArrayList<WikiLink>()
            o.arr("links")?.take(20)?.forEach { l ->
                val lo = l.obj ?: return@forEach
                if (lo.str("type") != "communityWiki") return@forEach
                safeUrl(lo.str("url"))?.let { u -> if (links.none { it.url == u }) links += WikiLink("Community wiki", u) }
            }
            if (links.isNotEmpty()) o.arr("universeIds")?.take(50)?.forEach { u -> ((u as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toLongOrNull())?.let { out.getOrPut(it) { ArrayList() }.addAll(links) } }
        }
        return out
    }
}

/** RoSeal's links to game wikis, kept 24 hours in a file. [fetch] downloads the list; it is only called when the person allowed RoSeal's data service. */
class RoSealLinkList(private val file: File, private val fetch: suspend (String) -> JsonElement?, private val now: () -> Long = { System.currentTimeMillis() }) {
    suspend fun linksFor(universeId: Long): List<WikiLink> {
        val kept = try { AppJson.parseToJsonElement(file.readText()).obj } catch (_: Exception) { null }
        if (kept != null && now() - (kept.long("t") ?: 0) < RoSealLinks.TTL_MS) return RoSealLinks.parse(kept["links"])[universeId].orEmpty()
        val data = try { fetch(RoSealLinks.URL) } catch (e: GeoException) {
            val old = RoSealLinks.parse(kept?.get("links"))
            if (old.isNotEmpty()) return old[universeId].orEmpty()
            throw GeoException("RoSeal's list of game links could not be downloaded")
        }
        if (data !is JsonArray) throw GeoException("RoSeal's list of game links did not look right")
        try { file.parentFile?.mkdirs(); file.writeText(AppJson.encodeToString(JsonElement.serializer(), obj("t" to now(), "links" to data))) } catch (_: Exception) { }
        return RoSealLinks.parse(data)[universeId].orEmpty()
    }
}
