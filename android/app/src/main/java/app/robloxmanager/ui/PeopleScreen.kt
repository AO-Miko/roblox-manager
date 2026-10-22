package app.robloxmanager.ui

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
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import app.robloxmanager.Bulk
import app.robloxmanager.Services
import app.robloxmanager.core.Person
import kotlinx.coroutines.launch

/** What can be done to the selected people on one list. */
class PeopleAction(val label: String, val verb: String, val danger: Boolean = false, val confirm: Boolean = false, val removes: Boolean = true, val run: suspend (Person) -> Unit)

/** Headshots of whoever is on screen, fetched 100 at a time. */
class AvatarBook(private val sv: Services) {
    val urls = mutableStateMapOf<Long, String>()
    suspend fun ensure(ids: List<Long>) {
        val todo = ids.filter { it !in urls }.take(300)
        for (c in todo.chunked(100)) urls.putAll(sv.api.headshots(c))
    }
}

@Composable
fun PeopleScreen(sv: Services, bulk: Bulk, counts: MutableMap<String, Int>, jump: Jump? = null) {
    val kinds = listOf("Friends", "Requests", "Followers", "Following", "Blocked", "Find", "Alerts")
    var tab by remember { mutableStateOf(0) }
    LaunchedEffect(jump) { if (jump != null && jump.dest == "people") tab = jump.sub.coerceIn(0, kinds.size - 1) }
    val api = sv.api
    Column(Modifier.fillMaxSize()) {
        ScrollableTabRow(selectedTabIndex = tab, containerColor = C.bg, edgePadding = 8.dp) {
            kinds.forEachIndexed { i, k ->
                val n = counts[k]
                Tab(selected = tab == i, onClick = { tab = i }, text = { Text(if (n != null) "$k ($n)" else k) })
            }
        }
        val kind = kinds[tab]
        when (kind) {
            "Friends" -> PeopleList(sv, bulk, kind, counts, { api.friends() }, listOf(
                PeopleAction("Unfriend", "Unfriending", danger = true, confirm = true) { api.unfriend(it.id) },
                PeopleAction("Block", "Blocking", danger = true, confirm = true) { api.block(it.id) },
            ))
            "Requests" -> PeopleList(sv, bulk, kind, counts, { api.friendRequests() }, listOf(
                PeopleAction("Accept", "Accepting") { api.acceptRequest(it.id) },
                PeopleAction("Decline", "Declining", danger = true) { api.declineRequest(it.id) },
            ), resolveNames = true)
            "Followers" -> PeopleList(sv, bulk, kind, counts, { api.followers() }, listOf(
                PeopleAction("Follow back", "Following", removes = false) { api.follow(it.id) },
                PeopleAction("Block", "Blocking", danger = true, confirm = true) { api.block(it.id) },
            ), resolveNames = true)
            "Following" -> PeopleList(sv, bulk, kind, counts, { api.followings() }, listOf(
                PeopleAction("Unfollow", "Unfollowing", danger = true, confirm = true) { api.unfollow(it.id) },
            ), resolveNames = true)
            "Blocked" -> PeopleList(sv, bulk, kind, counts, { api.blocked() }, listOf(
                PeopleAction("Unblock", "Unblocking") { api.unblock(it.id) },
            ))
            "Alerts" -> AlertsScreen(sv)
            else -> FindPeople(sv, bulk)
        }
    }
}

@Composable
private fun PeopleList(
    sv: Services, bulk: Bulk, kind: String, counts: MutableMap<String, Int>, fetch: suspend () -> List<Person>,
    actions: List<PeopleAction>, resolveNames: Boolean = false,
) {
    val loader = rememberLoader(kind) { fetch() }
    val list = remember(kind) { mutableStateListOf<Person>() }
    val selected = remember(kind) { mutableStateListOf<Long>() }
    val avatars = remember { AvatarBook(sv) }
    var filter by remember(kind) { mutableStateOf("") }
    var pending by remember(kind) { mutableStateOf<PeopleAction?>(null) }
    val scope = rememberCoroutineScope()
    val bs by bulk.state.collectAsState()

    LaunchedEffect(loader.value) {
        val v = loader.value ?: return@LaunchedEffect
        list.clear(); list.addAll(v); selected.clear()
        counts[kind] = v.size
        avatars.ensure(v.map { it.id })
        if (resolveNames) {           // the lists leave names blank: fill them in gradually, 200 per request
            val missing = v.filter { it.name.isEmpty() }.map { it.id }
            if (missing.isNotEmpty()) sv.api.lookupNames(missing) { got ->
                got.forEach { g -> val i = list.indexOfFirst { it.id == g.id }; if (i >= 0) list[i] = g.copy(extra = list[i].extra) }
            }
            avatars.ensure(list.map { it.id })
        }
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            OutlinedTextField(filter, { filter = it }, placeholder = { Text("Search this list") }, singleLine = true, modifier = Modifier.weight(1f))
            QuietButton("↻") { loader.load() }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val shown = list.filter { filter.isBlank() || it.title.contains(filter, true) || it.name.contains(filter, true) }
            QuietButton(if (selected.size == shown.size && shown.isNotEmpty()) "Select none" else "Select all (${shown.size})") {
                if (selected.size == shown.size) selected.clear() else { selected.clear(); selected.addAll(shown.map { it.id }) }
            }
            actions.forEach { a ->
                val btn: @Composable () -> Unit = {
                    val label = "${a.label} (${selected.size})"
                    if (a.danger) DangerButton(label, enabled = selected.isNotEmpty() && !bs.running) { run(a, selected, list, bulk, scope) { pending = it } }
                    else PrimaryButton(label, enabled = selected.isNotEmpty() && !bs.running) { run(a, selected, list, bulk, scope) { pending = it } }
                }
                btn()
            }
            if (kind == "Requests") DangerButton("Decline all", enabled = list.isNotEmpty() && !bs.running) {
                pending = PeopleAction("Decline all", "Declining all", danger = true, confirm = true) { sv.api.declineAllRequests() }
            }
        }
        LoadView(loader) {
            val shown = list.filter { filter.isBlank() || it.title.contains(filter, true) || it.name.contains(filter, true) }
            if (shown.isEmpty()) Box(Modifier.fillMaxSize().padding(24.dp)) { Text("Nobody here.", color = C.muted) }
            else LazyColumn(Modifier.fillMaxSize()) {
                items(shown, key = { it.id }) { p ->
                    PersonRow(p, avatars.urls[p.id], selected = p.id in selected, onToggle = { if (p.id in selected) selected.remove(p.id) else selected.add(p.id) })
                }
            }
        }
    }

    pending?.let { a ->
        val ids = if (a.label == "Decline all") emptyList() else selected.toList()
        Confirm(a.label, if (a.label == "Decline all") "Decline every pending friend request?" else "${a.label} ${ids.size} ${if (ids.size == 1) "person" else "people"}?",
            ok = a.label, danger = a.danger, onNo = { pending = null }, onYes = {
                pending = null
                if (a.label == "Decline all") {
                    bulk.run(a.verb, listOf(Person(0)), { "all requests" }, { a.run(it) }, finished = { loader.load() })
                } else execute(a, ids, list, selected, bulk)
            })
    }
}

private fun run(a: PeopleAction, selected: List<Long>, list: List<Person>, bulk: Bulk, scope: kotlinx.coroutines.CoroutineScope, ask: (PeopleAction) -> Unit) {
    if (selected.isEmpty()) return
    if (a.confirm) ask(a) else execute(a, selected.toList(), list, null, bulk)
}

private fun execute(a: PeopleAction, ids: List<Long>, list: List<Person>, selected: MutableList<Long>?, bulk: Bulk) {
    val people = ids.mapNotNull { id -> list.firstOrNull { it.id == id } }
    val mutable = list as? MutableList<Person>
    bulk.run(a.verb, people, { it.title }, { a.run(it) }, each = { p ->
        if (a.removes) { mutable?.removeAll { it.id == p.id }; selected?.remove(p.id) }
    })
}

@Composable
private fun FindPeople(sv: Services, bulk: Bulk) {
    var text by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Person>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val avatars = remember { AvatarBook(sv) }
    val doSearch = {
        if (text.isNotBlank() && !busy) {
            busy = true; msg = ""
            scope.launch {
                try {
                    results = sv.api.search(text)
                    avatars.ensure(results.map { it.id })
                    if (results.isEmpty()) msg = "Nobody found."
                } catch (e: Exception) { msg = errorText(e) }
                busy = false
            }
        }
    }
    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(text, { text = it }, label = { Text("Username or user id") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(12.dp),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search), keyboardActions = KeyboardActions(onSearch = { doSearch() }))
        PrimaryButtonRow(if (busy) "Searching…" else "Search", !busy && text.isNotBlank()) { doSearch() }
        if (msg.isNotEmpty()) Text(msg, color = C.muted, modifier = Modifier.padding(16.dp))
        LazyColumn(Modifier.fillMaxSize()) {
            items(results, key = { it.id }) { p ->
                Column {
                    PersonRow(p, avatars.urls[p.id])
                    Row(Modifier.padding(start = 72.dp, bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        QuietButton("Add friend") { bulk.run("Friend request", listOf(p), { it.title }, { sv.api.sendRequest(it.id) }) }
                        QuietButton("Follow") { bulk.run("Following", listOf(p), { it.title }, { sv.api.follow(it.id) }) }
                    }
                }
            }
        }
    }
}

@Composable
private fun PrimaryButtonRow(text: String, enabled: Boolean, onClick: () -> Unit) =
    Row(Modifier.padding(horizontal = 12.dp)) { PrimaryButton(text, enabled, onClick) }
