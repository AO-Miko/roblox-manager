package app.robloxmanager.ui

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Bulk
import app.robloxmanager.Services
import app.robloxmanager.core.Money
import app.robloxmanager.core.RobloxApi
import app.robloxmanager.core.bool
import app.robloxmanager.core.str
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ======================================================================== Groups
@Composable
fun GroupsScreen(sv: Services, bulk: Bulk, counts: MutableMap<String, Int>) {
    val me = sv.current.collectAsState().value ?: return
    val groups = remember(me.id) { mutableStateListOf<RobloxApi.Group>() }
    val created = remember(me.id) { mutableStateMapOf<Long, String>() }
    val selected = remember(me.id) { mutableStateListOf<Long>() }
    var filter by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf(false) }
    val bs by bulk.state.collectAsState()
    val loader = rememberLoader(me.id) { sv.api.myGroups() }

    LaunchedEffect(loader.value) {
        val v = loader.value ?: return@LaunchedEffect
        groups.clear(); groups.addAll(v.sortedBy { it.name.lowercase() }); selected.clear()
        counts["Groups"] = v.size
        try { sv.api.groupsCreated(v.map { it.id }).forEach { (id, c) -> if (c != null) created[id] = c.take(10) } } catch (_: Exception) { }
    }
    val shown = groups.filter { filter.isBlank() || it.name.contains(filter, true) }
    val leavable = shown.filter { !it.owned }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(filter, { filter = it }, placeholder = { Text("Search groups") }, singleLine = true, modifier = Modifier.weight(1f))
            QuietButton("↻") { loader.load() }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuietButton(if (selected.size == leavable.size && leavable.isNotEmpty()) "Select none" else "Select all (${leavable.size})") {
                if (selected.size == leavable.size) selected.clear() else { selected.clear(); selected.addAll(leavable.map { it.id }) }
            }
            DangerButton("Leave (${selected.size})", enabled = selected.isNotEmpty() && !bs.running) { confirm = true }
            QuietButton("Oldest first") { groups.sortBy { created[it.id] ?: "9999" } }
            QuietButton("Newest first") { groups.sortByDescending { created[it.id] ?: "" } }
        }
        Text("You cannot leave a group you own; those have no checkbox.", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(16.dp, 4.dp))
        LoadView(loader) {
            LazyColumn(Modifier.fillMaxSize()) {
                items(shown, key = { it.id }) { g ->
                    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (g.owned) Box(Modifier.padding(horizontal = 12.dp)) { Text("★", color = C.warn) }
                        else Checkbox(g.id in selected, { if (g.id in selected) selected.remove(g.id) else selected.add(g.id) })
                        Column(Modifier.weight(1f)) {
                            Text(g.name, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                            Text(listOfNotNull(g.role, g.members?.let { "${NumberFormat.getInstance().format(it)} members" }, created[g.id]?.let { "created $it" }).joinToString("  ·  "), color = C.muted, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
    if (confirm) Confirm("Leave groups", "Leave ${selected.size} group(s)? You would have to be accepted again to rejoin.", "Leave", true, { confirm = false
        val todo = groups.filter { it.id in selected }
        bulk.run("Leaving groups", todo, { it.name }, { sv.api.leaveGroup(it.id) }, each = { g -> groups.remove(g); selected.remove(g.id); counts["Groups"] = groups.size })
    }, { confirm = false })
}

// ======================================================================== Money
@Composable
fun MoneyScreen(sv: Services) {
    val me = sv.current.collectAsState().value ?: return
    var period by remember { mutableStateOf("Month") }
    var kind by remember { mutableStateOf("Sale") }
    var onlyPending by remember { mutableStateOf(false) }
    val fmt = NumberFormat.getInstance()
    val balance = rememberLoader(me.id) { sv.api.robux() }
    val pending = rememberLoader(me.id) { sv.api.pendingTotal() }
    val totals = rememberLoader(listOf(me.id, period)) { Money.totalRows(sv.api.transactionTotals(period)) }
    val tx = rememberLoader(listOf(me.id, kind, onlyPending)) {
        val items = sv.api.transactions(kind)
        Money.rows(if (onlyPending) items.filter { it.bool("isPending") == true } else items)
    }
    Column(Modifier.fillMaxSize().padding(bottom = 8.dp)) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
            Column { Text("Robux", color = C.muted, fontSize = 12.sp); Text(balance.value?.let { "R$ ${fmt.format(it)}" } ?: "-", fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
            Column { Text("Pending", color = C.muted, fontSize = 12.sp); Text(pending.value?.let { fmt.format(it) } ?: "-", fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
            QuietButton("↻") { balance.load(); pending.load(); totals.load(); tx.load() }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Money.PERIODS.forEach { (k, l) -> FilterChip(period == k, { period = k }, label = { Text(l) }) }
        }
        val rows = totals.value
        if (rows != null) Column(Modifier.padding(16.dp, 8.dp)) {
            if (rows.isEmpty()) Text("No money moved in this period.", color = C.muted)
            rows.forEach { (l, v) -> Row { Text(l, Modifier.weight(1f)); Text(fmt.format(v), color = if (v > 0) C.success else C.danger) } }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Money.KINDS.forEach { (k, l) -> FilterChip(kind == k, { kind = k }, label = { Text(l) }) }
        }
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 4.dp)) {
            Checkbox(onlyPending, { onlyPending = it }); Text("Only pending")
        }
        LoadView(tx) { rows2 ->
            if (rows2.isEmpty()) Text("No transactions of this kind.", color = C.muted, modifier = Modifier.padding(16.dp))
            else LazyColumn(Modifier.fillMaxSize()) {
                items(rows2) { r ->
                    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
                        Row { Text(r.item.ifEmpty { r.source }, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis); Text(fmt.format(r.robux), color = if (r.robux >= 0) C.success else C.danger, fontWeight = FontWeight.SemiBold) }
                        Text(listOf(r.date, r.source, r.game, r.from).filter { it.isNotEmpty() }.joinToString("  ·  "), color = C.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

// ======================================================================== Request log
@Composable
fun LogScreen(sv: Services) {
    val entries by sv.log.entries.collectAsState()
    var onlyProblems by remember { mutableStateOf(false) }
    var showLimits by remember { mutableStateOf(false) }
    val tf = remember { SimpleDateFormat("HH:mm:ss", Locale.US) }
    val shown = remember(entries, onlyProblems) { entries.asReversed().filter { !onlyProblems || it.isProblem }.take(400) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            FilterChip(onlyProblems, { onlyProblems = !onlyProblems }, label = { Text("Only problems") })
            FilterChip(showLimits, { showLimits = !showLimits }, label = { Text("Limits Roblox reported") })
            QuietButton("Clear") { sv.log.clear() }
        }
        val s = sv.log.summary()
        Text("Last 30 s: ${s[0]} requests, ${s[1]} changes, ${s[2]} rate-limited, ${s[3]} failed", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp))
        if (showLimits) Column(Modifier.padding(16.dp, 8.dp)) {
            val snap = sv.client.rates.snapshot()
            if (snap.isEmpty()) Text("No limits learned yet.", color = C.muted)
            snap.forEach { r -> Text("${r.route}  ${r.left ?: "?"}/${r.limit ?: "?"}${r.window?.let { " per $it s" } ?: ""}", fontSize = 11.sp, color = C.muted) }
        }
        LazyColumn(Modifier.fillMaxSize()) {
            items(shown) { e ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
                    Row {
                        Text("${tf.format(Date(e.time))}  ${e.method}", fontSize = 12.sp, color = C.muted)
                        Spacer(Modifier.weight(1f))
                        Text(e.status?.toString() ?: "—", color = if (e.isProblem) C.danger else C.success, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                    Text(e.host + e.path + if (e.query.isNotEmpty()) "?${e.query}" else "", fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    val extra = listOf(e.note, e.rate, e.ms?.let { "$it ms" } ?: "", if (e.paced) "paced" else "").filter { it.isNotEmpty() }.joinToString(" · ")
                    if (extra.isNotEmpty()) Text(extra, color = C.muted, fontSize = 11.sp)
                }
            }
        }
    }
}
