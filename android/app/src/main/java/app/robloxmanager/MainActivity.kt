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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.ui.AppTheme
import app.robloxmanager.ui.BulkBar
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
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sv = services
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
    Box(Modifier.fillMaxSize().background(C.bg).statusBarsPadding().navigationBarsPadding().imePadding()) {
        when {
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
    val titles = listOf("Home", "People", "Groups", "VIP servers", "Money", "Request log", "Info")
    var tab by remember { mutableStateOf(0) }
    val counts = remember { mutableStateMapOf<String, Int>() }
    val bulk = remember { Bulk(sv.scope) }
    val upd by Updates.state.collectAsState()
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val me by sv.current.collectAsState()
    key(me?.id) {
        Column(Modifier.fillMaxSize()) {
            if (upd.ready != null) Row(Modifier.fillMaxWidth().background(C.accentDim).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Update ${upd.available?.versionName ?: ""} is ready", Modifier.weight(1f), fontSize = 13.sp)
                TextButton(onClick = { Updates.install(ctx, upd.ready!!) }) { Text("Install") }
            }
            ScrollableTabRow(selectedTabIndex = tab, containerColor = C.bg, edgePadding = 8.dp) {
                titles.forEachIndexed { i, t ->
                    val n = when (t) { "VIP servers" -> counts["VIP"]; "Groups" -> counts["Groups"]; "People" -> counts["Friends"]; else -> null }
                    Tab(selected = tab == i, onClick = { tab = i }, text = { Text(if (n != null) "$t ($n)" else t) })
                }
            }
            Box(Modifier.weight(1f)) {
                when (tab) {
                    0 -> HomeScreen(sv, addAccount)
                    1 -> PeopleScreen(sv, bulk, counts)
                    2 -> GroupsScreen(sv, bulk, counts)
                    3 -> VipScreen(sv, bulk, counts)
                    4 -> MoneyScreen(sv)
                    5 -> LogScreen(sv)
                    else -> InfoScreen(sv)
                }
            }
            BulkBar(bulk)
        }
    }
}
