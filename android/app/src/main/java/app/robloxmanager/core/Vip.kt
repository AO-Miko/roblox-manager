package app.robloxmanager.core

import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.ZonedDateTime
import kotlinx.serialization.json.JsonObject

/** One private (VIP) server as Roblox lists it, plus what the app concluded about it. */
class Vip(val raw: JsonObject) {
    var active: Boolean? = raw.bool("active")
    var unavailable = false          // Roblox said its game is gone / has no VIP servers any more
    var renewed = false
    var link: String? = null

    val id: Long? = listOf("vipServerId", "privateServerId", "id", "serverId").firstNotNullOfOrNull { raw.long(it) }
    val name: String get() = raw.str("name") ?: ""
    val placeId: Long? get() = raw.long("placeId")
    val universeId: Long? get() = raw.long("universeId")
    val gameName: String get() = raw.str("universeName") ?: raw.str("gameName") ?: ""
    val sub: JsonObject? get() = raw.obj("subscription")
    val willRenew: Boolean get() = raw.bool("willRenew") ?: false

    val expiry: String get() = raw.str("expirationDate") ?: sub?.str("expirationDate") ?: sub?.str("expiresAt") ?: ""

    fun state(placeNames: Map<Long, String>?, now: Instant = Instant.now()): String {
        if (renewed) return ""
        if ("content deleted" in gameName.lowercase() || unavailable) return "Unavailable"
        val pid = placeId
        if (pid != null && placeNames != null && placeNames.isNotEmpty() && pid !in placeNames) return "Unavailable"
        if (sub?.bool("expired") == true) return "Expired"
        parse(expiry)?.let { if (it.isBefore(now)) return "Expired" }
        return ""
    }

    fun cost(now: Instant = Instant.now()): Cost {
        val price = raw.long("priceInRobux") ?: sub?.long("price") ?: 0
        val discount = raw.long("totalDiscountAmountInRobux") ?: sub?.long("totalDiscountAmountInRobux") ?: 0
        if (price > 0) return Cost.Paid(price.toInt())
        if (discount > 0) return Cost.FreePlus
        parse(expiry)?.let { if (it.atZone(ZoneOffset.UTC).year >= now.atZone(ZoneOffset.UTC).year + 50) return Cost.FreeGame }
        return Cost.Unknown
    }

    sealed class Cost(val label: String) {
        class Paid(val robux: Int) : Cost("Paid $robux R$")
        data object FreePlus : Cost("Free (Roblox Plus)")
        data object FreeGame : Cost("Free (game)")
        data object Unknown : Cost("Unknown")
        val free get() = this is FreePlus || this is FreeGame
        val paid get() = this is Paid
    }

    companion object {
        fun parse(s: String): Instant? = try {
            if (s.isBlank()) null else try { OffsetDateTime.parse(s).toInstant() } catch (_: Exception) { ZonedDateTime.parse(s).toInstant() }
        } catch (_: Exception) {
            try { Instant.parse(s) } catch (_: Exception) { null }
        }

        fun gameKey(v: Vip): Any = v.universeId ?: v.placeId ?: v.gameName

        /** Higher is better to keep when a game has several: working, then on, then renewing, then the later expiry. */
        private fun keeperScore(v: Vip, names: Map<Long, String>?) =
            listOf(if (v.state(names).isEmpty()) 1 else 0, if (v.active == true) 1 else 0, if (v.willRenew) 1 else 0)

        private val keeperOrder = Comparator<Pair<Vip, List<Int>>> { a, b ->
            for (i in a.second.indices) { val c = a.second[i].compareTo(b.second[i]); if (c != 0) return@Comparator c }
            a.first.expiry.compareTo(b.first.expiry)
        }

        /** Servers sorted best-first within each game that has more than one. */
        fun duplicates(servers: List<Vip>, names: Map<Long, String>? = null): Map<Any, List<Vip>> =
            servers.groupBy { gameKey(it) }.filter { it.value.size > 1 }
                .mapValues { (_, v) -> v.map { it to keeperScore(it, names) }.sortedWith(keeperOrder.reversed()).map { it.first } }

        fun keepers(servers: List<Vip>, names: Map<Long, String>? = null): Set<Vip> =
            servers.groupBy { gameKey(it) }.values.map { g -> g.map { it to keeperScore(it, names) }.sortedWith(keeperOrder.reversed()).first().first }.toSet()

        /** What "only free servers on" would do: (switch on, switch off). Unknown-cost, expired and unavailable servers are left alone. */
        fun freeOnlyPlan(servers: List<Vip>, names: Map<Long, String>? = null): Pair<List<Vip>, List<Vip>> {
            val best = keepers(servers, names)
            val working = servers.filter { it.state(names).isEmpty() && it.id != null }
            val on = working.filter { it.cost().free && it.active != true && it in best }
            val off = working.filter { it.cost().paid && it.active == true }
            return on to off
        }

        fun unavailableReason(msg: String): Boolean {
            val m = msg.lowercase()
            return "disabled private servers" in m || "does not exist" in m || "content deleted" in m || "not found" in m
        }
    }
}
