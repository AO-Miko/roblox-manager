package app.robloxmanager

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import app.robloxmanager.ui.AppTheme
import app.robloxmanager.ui.ADMIN
import app.robloxmanager.ui.ALL
import app.robloxmanager.ui.AdminScreen
import app.robloxmanager.ui.STAFF
import app.robloxmanager.ui.StaffScreen
import app.robloxmanager.ui.BottomBar
import app.robloxmanager.ui.BulkBar
import app.robloxmanager.ui.GROUPS
import app.robloxmanager.ui.HOME
import app.robloxmanager.ui.IN_MORE
import app.robloxmanager.ui.INFO
import app.robloxmanager.ui.Jump
import app.robloxmanager.ui.LOG
import app.robloxmanager.ui.MONEY
import app.robloxmanager.ui.MORE
import app.robloxmanager.ui.MoreScreen
import app.robloxmanager.ui.PEOPLE
import app.robloxmanager.ui.SearchDialog
import app.robloxmanager.ui.TopBar
import app.robloxmanager.ui.UpdateRequiredScreen
import app.robloxmanager.ui.VIP
import app.robloxmanager.ui.C
import app.robloxmanager.ui.GroupsScreen
import app.robloxmanager.ui.HomeScreen
import app.robloxmanager.ui.LoginScreen
import app.robloxmanager.ui.LogScreen
import app.robloxmanager.ui.MoneyScreen
import app.robloxmanager.ui.PeopleScreen
import app.robloxmanager.ui.InfoScreen
import app.robloxmanager.ui.VipScreen

class MainActivity : ComponentActivity() {
    /** Android 13 and newer: the phone's own question "Allow Roblox Manager to send you notifications?". */
    private val askNotifications = registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { granted -> if (granted) services.resetAlerts() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sv = services
        if (sv.alerts.enabled && android.os.Build.VERSION.SDK_INT >= 33 && !Notifier.allowed(this)) {          // alerts are on but the phone has not been asked (or said no once): ask, at most twice
            val asked = sv.prefs.str("notifAsks", "0").toIntOrNull() ?: 0
            if (asked < 2) { sv.prefs.put("notifAsks", (asked + 1).toString()); askNotifications.launch(android.Manifest.permission.POST_NOTIFICATIONS) }
        }
        sv.notifier = { text -> Notifier.show(applicationContext, text) }
        // At every start: look for a newer build on the update server and have it ready (never blocks the app).
        if (sv.prefs.bool("autoUpdate", true) && Updates.url(sv).isNotBlank()) Updates.check(sv, applicationContext, quiet = true)
        setContent { AppTheme { Root(sv) } }
    }
}

@Composable
private fun Root(sv: Services) {
    val ready by sv.ready.collectAsState()
    val me by sv.current.collectAsState()
    var adding by remember { mutableStateOf(false) }
    val notice by sv.banNotice.collectAsState()
    val lock by sv.updateRequired.collectAsState()
    notice?.let { n ->
        AlertDialog(
            onDismissRequest = { sv.banNotice.value = null }, title = { Text("Account not allowed") },
            text = { Text("This account may not use Roblox Manager and was signed out and removed from this phone:\n\n$n") },
            confirmButton = { TextButton(onClick = { sv.banNotice.value = null }) { Text("OK") } },
        )
    }
    Box(Modifier.fillMaxSize().background(C.bg).statusBarsPadding().navigationBarsPadding().imePadding()) {
        when {
            lock != null -> UpdateRequiredScreen(sv, lock!!)                    // too far behind: nothing else can be used
            !ready -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            me == null || adding -> {
                LaunchedEffect(me) { if (me != null) adding = false }
                BackHandler(enabled = adding) { adding = false }
                LoginScreen(sv, canCancel = adding && me != null) { adding = false }
            }
            else -> Main(sv) { adding = true }
        }
    }
}

@Composable
private fun Main(sv: Services, addAccount: () -> Unit) {
    var dest by rememberSaveable { mutableStateOf(HOME.id) }
    val visited = remember { mutableStateListOf(dest) }           // pages already opened stay alive, so going back to one does not load it again
    var jump by remember { mutableStateOf<Jump?>(null) }
    var searching by remember { mutableStateOf(false) }
    val counts = remember { mutableStateMapOf<String, Int>() }
    val bulk = remember { Bulk(sv.scope) }
    val upd by Updates.state.collectAsState()
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val me by sv.current.collectAsState()
    val accounts by sv.accountList.collectAsState()
    val rolesVersion by sv.rolesVersion.collectAsState()
    val rank = remember(me, rolesVersion) { me?.let { sv.roles.rankOf(it.id) } ?: 0 }
    val isAdmin = rank >= app.robloxmanager.core.Roles.MODERATOR
    fun open(id: String, sub: Int = 0) {
        app.robloxmanager.core.Debug.event("page", "opened page '${(ALL.firstOrNull { it.id == id } ?: MORE).title}'")
        if (id !in visited) visited.add(id)
        dest = id
        if (id == PEOPLE.id || id == INFO.id || id == HOME.id || id == GROUPS.id) jump = Jump(id, sub, (jump?.nonce ?: 0) + 1)
    }
    if (dest !in visited) visited.add(dest)
    if (dest == ADMIN.id && !isAdmin) dest = MORE.id                  // an account without the role (or one that lost it) cannot be on the Admin page
    val inMore = IN_MORE.any { it.id == dest }
    BackHandler(enabled = inMore) { open(MORE.id) }
    BackHandler(enabled = !inMore && dest != HOME.id) { open(HOME.id) }
    key(me?.id) {
        Column(Modifier.fillMaxSize()) {
            TopBar(
                title = (ALL.firstOrNull { it.id == dest } ?: MORE).title, subtitle = (ALL.firstOrNull { it.id == dest } ?: MORE).hint, onBack = if (inMore) ({ open(MORE.id) }) else null,
                accounts = accounts, me = me, onAdd = addAccount, onSearch = { searching = true },
                onSwitch = { a -> sv.scope.launch { try { sv.switchTo(a.id) } catch (_: Exception) { } } },
            )
            if (upd.ready != null) Row(Modifier.fillMaxWidth().background(C.accentDim).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Update ${upd.available?.versionName ?: ""} is ready", Modifier.weight(1f), fontSize = 13.sp)
                TextButton(onClick = { Updates.install(ctx, upd.ready!!) }) { Text("Install") }
            }
            Box(Modifier.weight(1f)) {
                fun shown(id: String) = if (dest == id) Modifier.fillMaxSize() else Modifier.size(0.dp).clipToBounds()   // (clipped: a checkbox keeps its 48 dp touch size and would draw outside)
                if (HOME.id in visited) Box(shown(HOME.id)) { HomeScreen(sv, addAccount, jump) }
                if (PEOPLE.id in visited) Box(shown(PEOPLE.id)) { PeopleScreen(sv, bulk, counts, jump) }
                if (GROUPS.id in visited) Box(shown(GROUPS.id)) { GroupsScreen(sv, bulk, counts, jump) }
                if (VIP.id in visited) Box(shown(VIP.id)) { VipScreen(sv, bulk, counts) }
                if (MONEY.id in visited) Box(shown(MONEY.id)) { MoneyScreen(sv) }
                if (LOG.id in visited) Box(shown(LOG.id)) { LogScreen(sv) }
                if (STAFF.id in visited) Box(shown(STAFF.id)) { StaffScreen(sv) }
                if (ADMIN.id in visited && isAdmin) Box(shown(ADMIN.id)) { AdminScreen(sv) }
                if (INFO.id in visited) Box(shown(INFO.id)) { InfoScreen(sv, jump) }
                if (dest == MORE.id) MoreScreen(isAdmin) { open(it.id) }
            }
            BulkBar(bulk)
            BottomBar(current = dest, counts = counts) { open(it.id) }
        }
    }
    if (searching) SearchDialog(admin = isAdmin, onClose = { searching = false }) { j -> searching = false; open(j.dest, j.sub) }
}
