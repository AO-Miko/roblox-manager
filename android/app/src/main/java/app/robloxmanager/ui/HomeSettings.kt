package app.robloxmanager.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.BuildConfig
import app.robloxmanager.Services
import app.robloxmanager.Updates
import app.robloxmanager.core.Account
import app.robloxmanager.core.Features
import app.robloxmanager.core.devexState
import app.robloxmanager.core.verifiedAge
import app.robloxmanager.core.voiceState
import java.io.File
import java.text.NumberFormat
import kotlinx.coroutines.launch

@Composable
fun AccountScreen(sv: Services, onAddAccount: () -> Unit) {
    val me = sv.current.collectAsState().value ?: return
    val accounts by sv.accountList.collectAsState()
    val scope = rememberCoroutineScope()
    val fmt = NumberFormat.getInstance()
    val avatar = rememberLoader(me.id) { sv.api.headshots(listOf(me.id), "150x150")[me.id] }
    val robux = rememberLoader(me.id) { sv.api.robux() }
    val pending = rememberLoader(me.id) { sv.api.pendingTotal() }
    val counts = rememberLoader(me.id) { sv.api.counts(me.id) }
    val premium = rememberLoader(me.id) { sv.api.hasPremium() }
    val voice = rememberLoader(me.id) { sv.api.voiceState() }
    val age = rememberLoader(me.id) { sv.api.verifiedAge() }
    var msg by remember { mutableStateOf("") }
    var confirmRemove by remember { mutableStateOf<Account?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(avatar.value, 72)
                Spacer(Modifier.width(14.dp))
                Column {
                    Text(me.displayName.ifEmpty { me.name }, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text("@${me.name}  ·  id ${me.id}", color = C.muted, fontSize = 12.sp)
                    premium.value?.let { Text(if (it) "Roblox Plus: active" else "Roblox Plus: not active", color = if (it) C.success else C.muted, fontSize = 12.sp) }
                    Text("Voice chat: " + (voice.value?.let { Features.voiceText(it) } ?: if (voice.state is Load.Failed) "(not available)" else "…"), color = C.muted, fontSize = 12.sp)
                    Text("Age verification: " + (age.value?.let { Features.verifiedText(it) } ?: if (age.state is Load.Failed) "(not available)" else "…"), color = C.muted, fontSize = 12.sp)
                }
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box2("Robux", robux.value?.let { "R$ ${fmt.format(it)}" } ?: "…", Modifier.weight(1f), accent = true)
            Box2("Pending", pending.value?.let { fmt.format(it) } ?: "…", Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val c = counts.value
            Box2("Friends", c?.get("friends")?.toString() ?: "…", Modifier.weight(1f))
            Box2("Followers", c?.get("followers")?.toString() ?: "…", Modifier.weight(1f))
            Box2("Following", c?.get("following")?.toString() ?: "…", Modifier.weight(1f))
        }
        QuietButton("↻ Refresh") { avatar.load(); robux.load(); pending.load(); counts.load(); premium.load(); voice.load(); age.load() }

        Section("ACCOUNTS", collapsible = true) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                accounts.forEach { a ->
                    Card {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(a.displayName.ifEmpty { a.name } + if (a.id == me.id) "  (active)" else "", fontWeight = FontWeight.Medium)
                                Text("@${a.name}", color = C.muted, fontSize = 12.sp)
                            }
                            if (a.id != me.id) QuietButton("Switch", enabled = !busy) {
                                busy = true; msg = ""
                                scope.launch { try { sv.switchTo(a.id) } catch (e: Exception) { msg = errorText(e) }; busy = false }
                            }
                            Spacer(Modifier.width(6.dp))
                            DangerButton("Remove") { confirmRemove = a }
                        }
                    }
                }
                QuietButton("＋ Add another account", onClick = onAddAccount)
            }
        }
        if (msg.isNotEmpty()) Text(msg, color = C.danger)
    }
    confirmRemove?.let { a ->
        Confirm("Remove account", "Remove @${a.name} from this phone? Its saved sign-in is deleted (you are not signed out on roblox.com elsewhere).", "Remove", true, {
            confirmRemove = null
            if (a.id == me.id) sv.signOut(true) else { sv.accounts.remove(a.id); sv.accountList.value = sv.accounts.all() }
        }, { confirmRemove = null })
    }
}

@Composable
private fun Box2(title: String, value: String, modifier: Modifier, accent: Boolean = false) = Card(modifier) {
    Column { Text(title, color = C.muted, fontSize = 12.sp); Text(value, fontSize = 19.sp, fontWeight = FontWeight.Bold, color = if (accent) C.accent else C.text) }
}

@Composable
fun SettingsScreen(sv: Services, part: String = "settings") {
    val ctx = LocalContext.current
    val upd by Updates.state.collectAsState()
    var burst by remember { mutableStateOf(sv.client.readBurst.toFloat()) }
    var logFile by remember { mutableStateOf(sv.log.writeFile) }
    var debugFile by remember { mutableStateOf(sv.debug.writeFile) }
    var url by remember { mutableStateOf(Updates.savedUrl(sv)) }
    var beta by remember { mutableStateOf(Updates.isBeta(sv)) }
    var askBeta by remember { mutableStateOf(false) }
    var auto by remember { mutableStateOf(sv.prefs.bool("autoUpdate", true)) }
    var msg by remember { mutableStateOf("") }
    var confirmSignOut by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (part == "updates") Section("UPDATES", collapsible = true) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Version ${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})", fontWeight = FontWeight.Medium)
                Text("Free software under the GNU GPL v3. Copyright (C) 2026 Miko. No warranty.", color = C.muted, fontSize = 12.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(beta, { on -> if (on) askBeta = true else { beta = false; sv.prefs.put("channel", "stable"); msg = "Back on Stable. You keep this version until Stable catches up."; Updates.check(sv, ctx) } })
                    Spacer(Modifier.width(8.dp))
                    Column { Text("Beta channel"); Text(if (beta) "You get every new version first. Less tested." else "Get new versions before everybody else (less tested).", color = C.muted, fontSize = 12.sp) }
                }
                OutlinedTextField(url, { url = it }, label = { Text("Update server address") }, supportingText = { Text("The raw address of the repository's dist/ folder, ending in /dist/. The beta channel uses the beta branch of the same repository.") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                Row(verticalAlignment = Alignment.CenterVertically) { Switch(auto, { auto = it; sv.prefs.put("autoUpdate", it) }); Spacer(Modifier.width(8.dp)); Text("Check at every start") }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    QuietButton("Save and check", enabled = !upd.busy) { sv.prefs.put("updateUrl", url.trim()); Updates.check(sv, ctx) }
                    if (upd.ready != null) PrimaryButton("Install ${upd.available?.versionName ?: ""}") { msg = Updates.install(ctx, upd.ready!!) }
                }
                if (upd.busy && upd.progress > 0f) LinearProgressIndicator(progress = { upd.progress }, modifier = Modifier.fillMaxWidth())
                if (upd.message.isNotEmpty()) Text(upd.message, color = C.muted, fontSize = 12.sp)
                upd.available?.notes?.takeIf { it.isNotEmpty() }?.let { Text(it, color = C.muted, fontSize = 12.sp) }
                Text("Android always asks you to confirm an install; it only accepts an update signed with the same key as this app.", color = C.muted, fontSize = 11.sp)
            }
        }
        if (part == "updates") UpdateLog()
        if (part == "settings") LooksSection(sv)
        if (part == "settings") Section("RATE LIMITS", collapsible = true) {
            Column {
                Text("How much of a route's limit a read may use at once: ${(burst * 100).toInt()}%", fontSize = 13.sp)
                Slider(burst, { burst = it }, valueRange = 0.1f..1f, onValueChangeFinished = { sv.client.readBurst = burst.toDouble(); sv.prefs.put("readBurst", burst.toDouble()) })
                Text("Changes (unfriend, leave, switch on …) are always spread out evenly. Lower = gentler on Roblox, slower lists.", color = C.muted, fontSize = 12.sp)
            }
        }
        if (part == "settings") Section("LOGS AND CACHE", collapsible = true) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(logFile, { logFile = it; sv.log.writeFile = it; sv.prefs.put("logToFile", it) }); Spacer(Modifier.width(8.dp)); Text("Keep the request log in a file")
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(debugFile, { debugFile = it; sv.debug.writeFile = it; sv.prefs.put("debugToFile", it) }); Spacer(Modifier.width(8.dp)); Text("Keep the app debug log (Request log > App debug) in a file")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    QuietButton("Clear debug log") { sv.debug.clear(); File(sv.filesDir, "debug.log").delete(); File(sv.filesDir, "debug.log.1").delete(); msg = "Debug log cleared." }
                    QuietButton("Clear request log") { sv.log.clear(); File(sv.filesDir, "requests.log").delete(); File(sv.filesDir, "requests.log.1").delete(); msg = "Request log cleared." }
                    QuietButton("Forget saved names") { File(sv.filesDir, "names.json").delete(); msg = "Saved names are forgotten the next time the app starts." }
                }
                Text("The request log never contains your cookie, passwords, codes or request bodies; the debug log hides everything private too.", color = C.muted, fontSize = 12.sp)
            }
        }
        if (part == "settings") Section("FRIEND ALERTS", collapsible = true) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                AlertsSwitch(sv) { msg = it }
                Text("A notification when the friends you picked (People > Alerts) come online or join a game.", color = C.muted, fontSize = 12.sp)
            }
        }
        if (part == "settings") Section("SERVER LOCATIONS", collapsible = true) {
            var roseal by remember { mutableStateOf(sv.prefs.bool("geo.roseal", false)) }
            var ipwho by remember { mutableStateOf(sv.prefs.bool("geo.allowed", false)) }
            var auto by remember { mutableStateOf(sv.prefs.bool("geo.auto", false)) }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) { Switch(roseal, { roseal = it; sv.prefs.put("geo.roseal", it) }); Spacer(Modifier.width(8.dp)); Text("Download RoSeal's public data files (data.roseal.live): its list of Roblox data centres, to show where servers are, and its links to game wikis. Nothing about you is sent.", fontSize = 13.sp) }
                Row(verticalAlignment = Alignment.CenterVertically) { Switch(ipwho, { ipwho = it; sv.prefs.put("geo.allowed", it) }); Spacer(Modifier.width(8.dp)); Text("Ask ipwho.is which city a server's public address is in. The address of the server is sent there, nothing else.", fontSize = 13.sp) }
                Row(verticalAlignment = Alignment.CenterVertically) { Switch(auto, { auto = it; sv.prefs.put("geo.auto", it) }); Spacer(Modifier.width(8.dp)); Text("Look up where servers are and how long they run by themselves when they are listed (needs one of the two above). One request to Roblox per server, up to 25 at a time.", fontSize = 13.sp) }
                Text("Used by Location and uptime on a game's page. Nothing is contacted unless one of the first two is on.", color = C.muted, fontSize = 12.sp)
            }
        }
        if (part == "settings") BackupSection(sv) { msg = it }
        if (part == "settings") Section("ACCOUNT", collapsible = true) { DangerButton("Sign out") { confirmSignOut = true } }
        if (msg.isNotEmpty()) Text(msg, color = C.muted, fontSize = 12.sp)
    }
    if (askBeta) Confirm("Beta versions", "Beta versions get every update before it goes to everybody else. They are less tested and may have bugs.\n\nYou can go back to Stable at any time: you then keep the version you have until Stable catches up.", "Join the beta", false,
        { askBeta = false; beta = true; sv.prefs.put("channel", "beta"); Updates.check(sv, ctx) }, { askBeta = false })
    if (confirmSignOut) Confirm("Sign out", "Sign out and remove this account from the phone?", "Sign out", true, { confirmSignOut = false; sv.signOut(true) }, { confirmSignOut = false })
}

/** What changed in each version (the log ships inside the app). The installed version is marked. */
@Composable
fun UpdateLog() {
    val ctx = LocalContext.current
    val entries = remember {
        try { app.robloxmanager.core.Changelog.parse(ctx.assets.open("changelog.json").bufferedReader().use { it.readText() }) } catch (_: Exception) { emptyList() }
    }
    Section("UPDATE LOG", collapsible = true) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (entries.isEmpty()) Text("No update log is available.", color = C.muted)
            entries.forEach { e ->
                Card {
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Version ${e.version}", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                            if (e.version == BuildConfig.VERSION_NAME) Text("● installed", color = C.success, fontSize = 12.sp)
                            Spacer(Modifier.width(8.dp))
                            Text(e.date, color = C.muted, fontSize = 12.sp)
                        }
                        e.changes.forEach { Text("•  $it", fontSize = 13.sp) }
                    }
                }
            }
        }
    }
}

/** The Settings page: Preferences, and Updates (controls and the update log). */
@Composable
fun InfoScreen(sv: Services, jump: Jump? = null) {
    var sub by remember { mutableStateOf(0) }
    LaunchedEffect(jump) { if (jump != null && jump.dest == "info") sub = jump.sub.coerceIn(0, 1) }
    Column(Modifier.fillMaxSize()) {
        androidx.compose.material3.TabRow(selectedTabIndex = sub, containerColor = C.bg) {
            listOf("Preferences", "Updates").forEachIndexed { i, t -> androidx.compose.material3.Tab(selected = sub == i, onClick = { sub = i }, text = { Text(t) }) }
        }
        SettingsScreen(sv, if (sub == 0) "settings" else "updates")
    }
}
