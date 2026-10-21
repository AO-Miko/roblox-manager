package app.robloxmanager.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Bulk
import app.robloxmanager.Services
import app.robloxmanager.core.RobloxException
import app.robloxmanager.core.Vip
import app.robloxmanager.core.arr
import app.robloxmanager.core.bool
import app.robloxmanager.core.obj
import app.robloxmanager.core.str
import app.robloxmanager.core.long
import app.robloxmanager.core.int
import app.robloxmanager.core.toJson
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

private const val FREE_LIMIT = "more active free private servers"
private const val CHECK_TTL_MS = 7L * 24 * 3600 * 1000

/** A server's answer to "is it still offered, and what is its link": kept a week per account so the next start does not repeat it. */
private class Checks(val sv: Services, val uid: Long) {
    private val key = "vipChecks.$uid"
    val unavailable = HashMap<Long, Boolean>()
    val reasons = HashMap<Long, String>()
    val links = HashMap<Long, String>()
    private val at = HashMap<Long, Long>()

    init {
        sv.prefs.raw(key).obj?.forEach { (k, v) ->
            val a = v as? kotlinx.serialization.json.JsonArray ?: return@forEach
            val t = (a.getOrNull(1) as? kotlinx.serialization.json.JsonPrimitive)?.content?.toLongOrNull() ?: return@forEach
            if (System.currentTimeMillis() - t < CHECK_TTL_MS) {
                val id = k.toLongOrNull() ?: return@forEach
                unavailable[id] = (a[0] as? kotlinx.serialization.json.JsonPrimitive)?.content == "true"
                at[id] = t
                (a.getOrNull(2) as? kotlinx.serialization.json.JsonPrimitive)?.content?.takeIf { it.isNotEmpty() }?.let { reasons[id] = it }
            }
        }
    }

    fun record(id: Long, gone: Boolean, link: String, why: String) {
        unavailable[id] = gone; at[id] = System.currentTimeMillis()
        if (gone && why.isNotEmpty()) reasons[id] = why
        if (!gone) links[id] = link
    }

    fun save() {
        val o = JsonObject(unavailable.entries.associate { (id, gone) -> id.toString() to listOf(gone, at[id] ?: 0L, reasons[id] ?: "").toJson() })
        sv.prefs.put(key, o)
    }
}

@Composable
fun VipScreen(sv: Services, bulk: Bulk, counts: MutableMap<String, Int>) {
    val me = sv.current.collectAsState().value ?: return
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val checks = remember(me.id) { Checks(sv, me.id) }
    var tick by remember { mutableIntStateOf(0) }
    val places = remember(me.id) { HashMap<Long, String>() }
    val servers = remember(me.id) { mutableStateListOf<Vip>() }
    val loader = rememberLoader(me.id) {
        val items = sv.api.myPrivateServers()
        places.putAll(sv.api.placeNames(items.mapNotNull { it.long("placeId") }))
        items.map { Vip(it) }
    }
    var hideExpired by remember { mutableStateOf(true) }
    var hideGone by remember { mutableStateOf(true) }
    var cost by remember { mutableStateOf("all") }
    var filter by remember { mutableStateOf("") }
    val selected = remember(me.id) { mutableStateListOf<Long>() }
    var dialog by remember { mutableStateOf<(@Composable () -> Unit)?>(null) }
    var message by remember { mutableStateOf("") }
    var checkedCount by remember { mutableIntStateOf(0) }
    val bs by bulk.state.collectAsState()

    LaunchedEffect(loader.value) {
        val v = loader.value ?: return@LaunchedEffect
        servers.clear(); servers.addAll(v)
        v.forEach { s -> s.id?.let { id -> if (checks.unavailable[id] == true) s.unavailable = true; checks.links[id]?.let { s.link = it } } }
        selected.clear()
        counts["VIP"] = v.size
        tick++
        // check every server not checked this week, one request each, out of the way of what the user is doing; paused by a rate limit
        val todo = v.filter { it.id != null && it.id !in checks.unavailable }.sortedBy { it.state(places).isEmpty() }
        var n = 0
        for (s in todo) {
            val id = s.id ?: continue
            while (bulk.state.value.running) delay(500)
            while (true) {
                try {
                    val d = sv.api.vipServer(id, retries = 0)
                    val link = d?.str("link") ?: d?.str("joinCode")?.let { c -> s.placeId?.let { p -> "https://www.roblox.com/games/$p?privateServerLinkCode=$c" } } ?: ""
                    checks.record(id, false, link.ifEmpty { "-" }, ""); if (link.isNotEmpty()) s.link = link
                    break
                } catch (e: RobloxException) {
                    if (e.status == 429 || e.local) { delay(30_000); continue }
                    val gone = Vip.unavailableReason(e.message ?: "")
                    checks.record(id, gone, "-", e.message ?: "")
                    if (gone) { s.unavailable = true; tick++ }
                    break
                }
            }
            n++; checkedCount = n
            if (n % 10 == 0) { checks.save(); tick++ }
        }
        checks.save(); tick++
    }

    val shown = run {
        tick
        servers.filter { s ->
            val st = s.state(places)
            !(st == "Expired" && hideExpired) && !(st == "Unavailable" && hideGone) &&
                (when (cost) { "free" -> s.cost().free; "paid" -> s.cost().paid; "unknown" -> s.cost() is Vip.Cost.Unknown; else -> true }) &&
                (filter.isBlank() || listOf(places[s.placeId] ?: s.gameName, s.name, s.id.toString()).any { it.contains(filter, true) })
        }
    }
    val dups = remember(tick, servers.size) { Vip.duplicates(servers, places) }

    fun status(s: Vip) = s.state(places).ifEmpty { if (s.active == true) "ON" else if (s.active == false) "OFF" else "?" }
    fun chosen() = servers.filter { it.id in selected }.filter { it.state(places).isEmpty() }

    fun switchBulk(want: Boolean) {
        val todo = chosen().filter { (it.active == true) != want }
        if (todo.isEmpty()) { message = "Nothing to change."; return }
        bulk.run(if (want) "Switching on" else "Switching off", todo, { it.name }, { s -> sv.api.setVipActive(s.id!!, want); s.active = want }, each = { tick++ })
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            FilterChip(hideExpired, { hideExpired = !hideExpired }, label = { Text("Hide expired") })
            FilterChip(hideGone, { hideGone = !hideGone }, label = { Text("Hide unavailable") })
            listOf("all" to "All", "free" to "Free", "paid" to "Paid", "unknown" to "Unknown").forEach { (k, l) -> FilterChip(cost == k, { cost = k }, label = { Text(l) }) }
            QuietButton("↻") { loader.load() }
        }
        OutlinedTextField(filter, { filter = it }, placeholder = { Text("Search game, name or id") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuietButton(if (selected.isNotEmpty() && selected.size == shown.size) "Select none" else "Select all (${shown.size})") {
                if (selected.size == shown.size) selected.clear() else { selected.clear(); selected.addAll(shown.mapNotNull { it.id }) }
            }
            PrimaryButton("Switch on (${selected.size})", enabled = selected.isNotEmpty() && !bs.running) { switchBulk(true) }
            QuietButton("Switch off (${selected.size})", enabled = selected.isNotEmpty() && !bs.running) {
                dialog = { Confirm("Switch off", "Switch off ${chosen().size} server(s)? Nobody can join them until they are switched on again.", "Switch off", true, { dialog = null; switchBulk(false) }, { dialog = null }) }
            }
            QuietButton("Only free on", enabled = servers.isNotEmpty() && !bs.running) {
                val (on, off) = Vip.freeOnlyPlan(servers.toList(), places)
                if (on.isEmpty() && off.isEmpty()) message = "Already only free servers are on (servers of unknown cost are left alone)."
                else dialog = {
                    Confirm("Only free servers on", "Switch ${on.size} free server(s) on and ${off.size} paid server(s) off? Servers of unknown cost, expired and unavailable ones are not touched.", "Do it", false, {
                        dialog = null
                        val steps = off.map { it to false } + on.map { it to true }
                        bulk.run("Only free on", steps, { it.first.name }, { (s, want) -> sv.api.setVipActive(s.id!!, want); s.active = want }, each = { tick++ })
                    }, { dialog = null })
                }
            }
            QuietButton("Stop renewing (${selected.size})", enabled = selected.isNotEmpty() && !bs.running) {
                dialog = { Confirm("Stop renewing", "Stop the subscription of ${chosen().size} server(s) from renewing? They keep working until they expire.", "Stop renewing", true, {
                    dialog = null
                    bulk.run("Cancelling renewal", chosen(), { it.name }, { s -> sv.api.cancelVipRenewal(s.id!!) })
                }, { dialog = null }) }
            }
        }
        val on = shown.count { it.active == true && it.state(places).isEmpty() }
        val bits = ArrayList<String>()
        bits += "${shown.size} server(s), $on on"
        if (checkedCount > 0 && checkedCount < servers.size) bits += "checking in the background: $checkedCount"
        if (dups.isNotEmpty()) bits += "${dups.size} game(s) have more than one"
        Text(bits.joinToString(" · ") + if (message.isNotEmpty()) "\n$message" else "", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp))
        LoadView(loader) {
            if (shown.isEmpty()) Box(Modifier.fillMaxSize().padding(24.dp)) { Text("No VIP servers match.", color = C.muted) }
            else LazyColumn(Modifier.fillMaxSize()) {
                items(shown, key = { it.id ?: it.hashCode().toLong() }) { s ->
                    tick
                    val id = s.id
                    Row(Modifier.fillMaxWidth().clickable { dialog = { VipDetails(sv, s, places, checks, ctx, tick, { tick++ }, { dialog = null }) } }.padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(id != null && id in selected, { if (id != null) { if (id in selected) selected.remove(id) else selected.add(id) } })
                        Column(Modifier.weight(1f)) {
                            Text(places[s.placeId] ?: s.gameName.ifEmpty { "Game ${s.placeId ?: "?"}" }, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                            Text(s.name + (dups[Vip.gameKey(s)]?.let { "   ×${it.size}" } ?: ""), color = C.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(s.cost().label, color = C.muted, fontSize = 12.sp)
                        }
                        val st = status(s)
                        Text(st, color = if (st == "ON") C.success else if (st == "OFF" || st == "?") C.muted else C.danger, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
    dialog?.invoke()
}

@Composable
private fun VipDetails(sv: Services, s: Vip, places: Map<Long, String>, checks: Checks, ctx: Context, tick: Int, changed: () -> Unit, close: () -> Unit) {
    val scope = rememberCoroutineScope()
    var link by remember { mutableStateOf(s.link ?: "") }
    var msg by remember { mutableStateOf("") }
    var rename by remember { mutableStateOf<String?>(null) }
    val id = s.id
    val state = s.state(places)
    AlertDialog(
        onDismissRequest = close,
        title = { Text(s.name.ifEmpty { "VIP server" }) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(places[s.placeId] ?: s.gameName, fontWeight = FontWeight.Medium)
                Text("Status: ${state.ifEmpty { if (s.active == true) "ON" else "OFF" }}", color = C.muted)
                Text("Cost: ${s.cost().label}", color = C.muted)
                if (s.expiry.isNotEmpty()) Text("Expires: ${s.expiry.take(10)}", color = C.muted)
                if (id != null) Text("Id: $id", color = C.muted)
                if (state == "Unavailable") Text(checks.reasons[id] ?: "The game is gone or no longer offers VIP servers.", color = C.danger, fontSize = 12.sp)
                if (state == "Expired") Text("The subscription ended; Roblox only allows changes after it is renewed.", color = C.warn, fontSize = 12.sp)
                if (link.isNotEmpty() && link != "-") Text(link, fontSize = 11.sp, color = C.muted)
                if (msg.isNotEmpty()) Text(msg, color = C.warn, fontSize = 12.sp)
                if (state.isEmpty() && id != null) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = {
                            scope.launch {
                                try {
                                    if (link.isEmpty() || link == "-") {
                                        val d = sv.api.vipServer(id)
                                        link = d?.str("link") ?: d?.str("joinCode")?.let { c -> s.placeId?.let { p -> "https://www.roblox.com/games/$p?privateServerLinkCode=$c" } } ?: ""
                                        s.link = link.ifEmpty { null }
                                    }
                                    if (link.isNotEmpty()) {
                                        (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("VIP link", link))
                                        msg = "Link copied."
                                    } else msg = "Roblox did not give a join link."
                                } catch (e: Exception) { msg = errorText(e) }
                            }
                        }) { Text("Copy link") }
                        TextButton(onClick = { rename = s.name }) { Text("Rename") }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = close) { Text("Close") } },
    )
    rename?.let { cur ->
        var t by remember { mutableStateOf(cur) }
        AlertDialog(onDismissRequest = { rename = null }, title = { Text("Rename") }, text = { OutlinedTextField(t, { t = it }, singleLine = true) },
            confirmButton = {
                TextButton(onClick = {
                    rename = null
                    scope.launch { try { sv.api.updateVip(id!!, obj("name" to t.trim())); msg = "Renamed. Refresh to see it."; changed() } catch (e: Exception) { msg = errorText(e) } }
                }) { Text("Save") }
            }, dismissButton = { TextButton(onClick = { rename = null }) { Text("Cancel") } })
    }
}
