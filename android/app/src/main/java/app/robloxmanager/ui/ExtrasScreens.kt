package app.robloxmanager.ui

import android.Manifest
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Bulk
import app.robloxmanager.Notifier
import app.robloxmanager.Services
import app.robloxmanager.core.AlertRules
import app.robloxmanager.core.Backup
import app.robloxmanager.core.BackupException
import app.robloxmanager.core.JoinRequest
import app.robloxmanager.core.Person
import app.robloxmanager.core.RobloxApi
import app.robloxmanager.core.answerJoinRequests
import app.robloxmanager.core.joinRequestsOfAll
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

// ======================================================================== People > Alerts
@Composable
fun AlertsScreen(sv: Services) {
    val me = sv.current.collectAsState().value ?: return
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader(me.id) { sv.api.friends() }
    val avatars = remember { AvatarBook(sv) }
    val watched = remember(me.id) { mutableStateMapOf<Long, String>().also { it.putAll(sv.alerts.watched(me.id)) } }
    var enabled by remember { mutableStateOf(sv.alerts.enabled) }
    var online by remember { mutableStateOf(sv.alerts.online) }
    var ingame by remember { mutableStateOf(sv.alerts.ingame) }
    var filter by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }

    fun save() { sv.alerts.setWatched(me.id, watched.toMap()); sv.resetAlerts() }
    fun turnOn() {
        enabled = true; sv.alerts.enabled = true; sv.resetAlerts()
        scope.launch { try { sv.pollAlerts() } catch (e: CancellationException) { throw e } catch (_: Exception) { } }          // (the first look: who is where)
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) note = "Notifications are blocked for this app, so alerts cannot be shown. Allow them in the phone's settings."
        turnOn()
    }
    LaunchedEffect(loader.value) { loader.value?.let { avatars.ensure(it.map { p -> p.id }) } }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(enabled, { on ->
                    if (!on) { enabled = false; sv.alerts.enabled = false; sv.resetAlerts() }
                    else if (Build.VERSION.SDK_INT >= 33 && !Notifier.allowed(ctx)) permission.launch(Manifest.permission.POST_NOTIFICATIONS) else turnOn()
                })
                Spacer(Modifier.width(8.dp)); Text("Alerts on", fontWeight = FontWeight.Medium)
            }
            Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(online, { online = it; sv.alerts.online = it }); Text("when a friend comes online") }
            Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(ingame, { ingame = it; sv.alerts.ingame = it }); Text("when a friend joins a game") }
            Text("Tick the friends you want news about. The app looks at them every ${AlertRules.INTERVAL_MS / 1000} seconds while it is running (Android may pause it " +
                "when it is long in the background). Nothing is sent to anyone but Roblox.", color = C.muted, fontSize = 12.sp)
            if (note.isNotEmpty()) Text(note, color = C.warn, fontSize = 12.sp)
        }
        Row(Modifier.padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(filter, { filter = it }, placeholder = { Text("Filter friends") }, singleLine = true, modifier = Modifier.weight(1f))
            QuietButton("↻") { loader.load() }
        }
        val all = loader.value.orEmpty()
        val shown = all.filter { filter.isBlank() || it.title.contains(filter, true) || it.name.contains(filter, true) }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuietButton("Watch all shown (${shown.size})") { shown.forEach { if (watched.size < AlertRules.MAX_WATCHED) watched[it.id] = it.title }; save() }
            QuietButton("Watch none") { shown.forEach { watched.remove(it.id) }; save() }
            QuietButton("Test") { sv.notifier("This is how a friend alert looks.") }
            Text("${watched.size} watched", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(start = 4.dp))
        }
        LoadView(loader) {
            LazyColumn(Modifier.fillMaxSize()) {
                items(shown, key = { it.id }) { p ->
                    PersonRow(p, avatars.urls[p.id], selected = p.id in watched, onToggle = {
                        if (p.id in watched) watched.remove(p.id)
                        else if (watched.size < AlertRules.MAX_WATCHED) watched[p.id] = p.title
                        else note = "At most ${AlertRules.MAX_WATCHED} friends can be watched."
                        save()
                    })
                }
            }
        }
    }
}

// ======================================================================== Groups > Join requests of all groups
@Composable
fun JoinRequestsScreen(sv: Services, bulk: Bulk) {
    val me = sv.current.collectAsState().value ?: return
    val scope = rememberCoroutineScope()
    val rows = remember(me.id) { mutableStateListOf<JoinRequest>() }
    val selected = remember(me.id) { mutableStateListOf<String>() }
    var busy by remember(me.id) { mutableStateOf(false) }
    var note by remember(me.id) { mutableStateOf("") }
    var scanned by remember(me.id) { mutableStateOf(false) }
    var ask by remember { mutableStateOf<Boolean?>(null) }
    val bs by bulk.state.collectAsState()

    fun scan() {
        if (busy) return
        busy = true; note = "Checking your groups…"
        scope.launch {
            try {
                val groups = sv.api.myGroups()
                val r = sv.api.joinRequestsOfAll(groups) { k -> note = "Checking group ${k + 1} of ${groups.size}…" }
                rows.clear(); rows.addAll(r.requests); selected.clear()
                note = "${r.requests.size} request(s) in ${r.requests.map { it.gid }.toSet().size} group(s); you may answer requests in ${r.checked} of your ${groups.size} groups." +
                    if (r.failed.isNotEmpty()) "\n${r.failed.size} group(s) could not be checked: " + r.failed.take(3).joinToString("; ") else ""
                scanned = true
            } catch (e: CancellationException) { throw e } catch (e: Exception) { note = "Could not check: ${errorText(e)}" }
            busy = false
        }
    }
    LaunchedEffect(me.id) { if (!scanned) scan() }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuietButton(if (busy) "Checking…" else "Check my groups", enabled = !busy) { scan() }
            QuietButton(if (selected.size == rows.size && rows.isNotEmpty()) "Select none" else "Select all (${rows.size})") {
                if (selected.size == rows.size) selected.clear() else { selected.clear(); selected.addAll(rows.map { it.key }) }
            }
            PrimaryButton("Accept (${selected.size})", enabled = selected.isNotEmpty() && !bs.running && !busy) { ask = true }
            DangerButton("Decline (${selected.size})", enabled = selected.isNotEmpty() && !bs.running && !busy) { ask = false }
        }
        if (note.isNotEmpty()) Text(note, color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
        LazyColumn(Modifier.fillMaxSize()) {
            items(rows, key = { it.key }) { r ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(r.key in selected, { if (r.key in selected) selected.remove(r.key) else selected.add(r.key) })
                    Column(Modifier.weight(1f)) {
                        Text(r.title, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                        Text(listOf("@" + r.username, r.group, r.created?.take(10)).filterNotNull().filter { it != "@" }.joinToString("  ·  "), color = C.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
    ask?.let { accept ->
        val verb = if (accept) "Accept" else "Decline"
        val picked = rows.filter { it.key in selected }
        Confirm("$verb requests", "$verb ${picked.size} join request(s) in ${picked.map { it.gid }.toSet().size} group(s)?", verb, !accept, {
            ask = null
            val batches = picked.groupBy { it.gid }.map { (gid, l) -> gid to l }
            bulk.run(if (accept) "Accepting requests" else "Declining requests", batches, { b -> picked.first { it.gid == b.first }.group }, { b -> sv.api.answerJoinRequests(b.first, b.second.map { it.id }, accept) },
                each = { b -> rows.removeAll { r -> r.gid == b.first && b.second.any { it.id == r.id } }; selected.removeAll(b.second.map { it.key }.toSet()) })
        }, { ask = null })
    }
}

/** At most [limit] bytes of a stream (a backup is small; a huge file is refused rather than read whole). */
private fun readLimited(input: java.io.InputStream, limit: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buf = ByteArray(8192)
    while (out.size() < limit) {
        val n = input.read(buf, 0, minOf(buf.size, limit - out.size()))
        if (n < 0) break
        out.write(buf, 0, n)
    }
    return out.toByteArray()
}

// ======================================================================== Settings > Backup
@Composable
fun BackupSection(sv: Services, onMessage: (String) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var lists by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var pending by remember { mutableStateOf<kotlinx.serialization.json.JsonObject?>(null) }

    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        busy = true; onMessage("Collecting…")
        scope.launch {
            try {
                val me = sv.current.value
                val want = lists && me != null
                val data = Backup.build(sv.prefs, app.robloxmanager.BuildConfig.VERSION_NAME, java.time.Instant.now().toString(),
                    account = if (want) Person(me!!.id, me.name, me.displayName) else null,
                    friends = if (want) sv.api.friends() else null, followers = if (want) sv.api.followers() else null,
                    following = if (want) sv.api.followings() else null, groups = if (want) sv.api.myGroups() else null)
                val text = app.robloxmanager.core.AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), data)
                ctx.contentResolver.openOutputStream(uri, "wt")?.use { it.write(text.toByteArray()) } ?: throw java.io.IOException("the file could not be opened")
                onMessage("Backup saved (${text.length / 1024 + 1} KB).")
            } catch (e: CancellationException) { throw e } catch (e: Exception) { onMessage("The backup was not saved: ${errorText(e)}") }
            busy = false
        }
    }
    val open = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        try {
            val bytes = ctx.contentResolver.openInputStream(uri)?.use { readLimited(it, Backup.MAX_BYTES + 1) } ?: throw java.io.IOException("the file could not be opened")
            pending = Backup.read(String(bytes))
        } catch (e: BackupException) { onMessage(e.message ?: "That is not a backup.") } catch (e: Exception) { onMessage("The file could not be read: ${errorText(e)}") }
    }

    Section("BACKUP", collapsible = true) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Save your settings, friend alerts and recently viewed games to a file, and bring them back later or on another phone. Your sign-ins are never in the file.", color = C.muted, fontSize = 12.sp)
            Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(lists, { lists = it }); Text("Also keep a copy of my friends, followers, following and groups", fontSize = 13.sp) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PrimaryButton(if (busy) "Saving…" else "Save a backup", enabled = !busy) { save.launch("roblox-manager-backup-${java.time.LocalDate.now()}.json") }
                QuietButton("Restore") { open.launch(arrayOf("application/json", "text/plain", "*/*")) }
            }
        }
    }
    pending?.let { d ->
        Confirm("Restore backup", "Replace your settings, friend alerts and recently viewed games with those in this backup? Nothing on Roblox is changed and your sign-ins stay as they are.", "Restore", false, {
            pending = null
            val (s, w, g) = Backup.restore(sv.prefs, d)
            sv.client.readBurst = sv.prefs.double("readBurst", 0.5)
            sv.log.writeFile = sv.prefs.bool("logToFile", true)
            sv.resetAlerts()
            onMessage("Restored $s setting(s), $w watched friend(s) and $g recent game(s). Open the pages again to see them.")
        }, { pending = null })
    }
}
