package app.robloxmanager.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

object Money {
    val PERIODS = listOf("Day" to "Today", "Week" to "This week", "Month" to "This month", "Year" to "This year")
    val KINDS = listOf(
        "Sale" to "Sales", "Purchase" to "Purchases", "GroupPayout" to "Group payouts", "EngagementPayout" to "Premium payouts",
        "GroupEngagementPayout" to "Group premium payouts", "AffiliateSale" to "Affiliate sales", "AdImpressionPayout" to "Ad payouts",
        "PremiumStipend" to "Premium stipends", "CurrencyPurchase" to "Robux bought", "TradeSystem" to "Trades",
    )
    private val TOTAL_NAMES = mapOf(
        "salesTotal" to "Sales", "purchasesTotal" to "Purchases", "affiliateSalesTotal" to "Affiliate sales", "groupPayoutsTotal" to "Group payouts",
        "currencyPurchasesTotal" to "Robux bought", "premiumStipendsTotal" to "Premium stipends", "tradeSystemEarningsTotal" to "Trade earnings",
        "tradeSystemCostsTotal" to "Trade costs", "pendingRobuxTotal" to "Pending Robux", "incomingRobuxTotal" to "Incoming",
        "outgoingRobuxTotal" to "Outgoing", "engagementPayoutTotal" to "Premium payouts", "adImpressionPayoutsTotal" to "Ad payouts",
        "groupPremiumPayoutsTotal" to "Group premium payouts",
    )
    private val SOURCES = mapOf(
        "gamepass" to "Game pass", "asset" to "Item sale", "developerproduct" to "Developer product", "subscription" to "Subscription",
        "privateserver" to "VIP server", "badge" to "Badge", "bundle" to "Bundle", "assetownership" to "Item sale", "plugin" to "Plugin sale",
        "pass" to "Game pass", "product" to "Developer product", "game" to "Game sale",
    )

    fun totalLabel(key: String): String = TOTAL_NAMES[key]
        ?: key.removeSuffix("Total").replace(Regex("(?<!^)(?=[A-Z])"), " ").lowercase().replaceFirstChar { it.uppercase() }

    /** (label, amount) for every non-zero "...Total" field Roblox returns. */
    fun totalRows(totals: JsonObject?): List<Pair<String, Long>> = totals?.entries.orEmpty().sortedBy { it.key }.mapNotNull { (k, v) ->
        val n = (v as? JsonPrimitive)?.content?.toDoubleOrNull()?.toLong()
        if (k.endsWith("Total") && n != null && n != 0L) totalLabel(k) to n else null
    }

    /** What a transaction came from: a group, a game pass, an item, a developer product ... */
    fun sourceLabel(item: JsonObject): String {
        val agent = item.obj("agent")
        val d = item.obj("details")
        if (agent?.str("type").equals("group", true)) return "Group: ${agent?.str("name") ?: agent?.str("id")}"
        val kind = (d?.str("type") ?: d?.str("itemType") ?: "").trim()
        if (kind.isNotEmpty()) return SOURCES[kind.replace(" ", "").lowercase()] ?: kind
        return when (val t = item.str("transactionType") ?: "") {
            "Sale" -> "Sale"; "GroupPayout" -> "Group payout"; "EngagementPayout" -> "Premium payout"
            "GroupEngagementPayout" -> "Group premium payout"; "AdImpressionPayout" -> "Ad payout"; "AffiliateSale" -> "Affiliate sale"
            "PremiumStipend" -> "Premium stipend"; "" -> "Other"; else -> t
        }
    }

    class Row(val date: String, val robux: Long, val source: String, val item: String, val game: String, val from: String)

    fun rows(items: List<JsonObject>): List<Row> = items.map { it0 ->
        val d = it0.obj("details")
        val agent = it0.obj("agent")
        Row(
            (it0.str("created") ?: "").take(10), it0.obj("currency")?.long("amount") ?: 0, sourceLabel(it0), d?.str("name") ?: "",
            d?.obj("place")?.str("name") ?: "", (agent?.str("name") ?: "") + if (agent?.str("type").equals("group", true)) " (group)" else "",
        )
    }
}
