package app.robloxmanager.ui

import android.content.Intent
import java.io.File
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.SystemUpdate
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.robloxmanager.Services
import app.robloxmanager.Updates
import app.robloxmanager.core.Debug
import app.robloxmanager.core.PolicyStatus
import app.robloxmanager.core.PolicyStore

/**
 * Covers the whole app when this version is too far behind (see PolicyStore): nothing else can be used until it is updated. One button, Update now: the newest version is
 * downloaded and checked, and Android's installer opens by itself (after the person allowed installs from this app, once, it carries on by itself). The download page
 * (GitHub) is only offered when the automatic update did not work.
 */
@Composable
fun UpdateRequiredScreen(sv: Services, st: PolicyStatus) {
    val ctx = LocalContext.current
    val upd by Updates.state.collectAsState()
    var note by remember { mutableStateOf("") }
    var wanted by remember { mutableStateOf(false) }                  // Update now was pressed: install as soon as the file is ready
    var needPermission by remember { mutableStateOf(false) }          // the phone has to allow installs from this app first (then it carries on by itself)
    fun install(f: File) {
        needPermission = !ctx.packageManager.canRequestPackageInstalls()
        Debug.event("update", "opening the installer for the update", "info")
        note = Updates.install(ctx, f).let { if (needPermission) "Allow installs from this app, then come back: the update installs by itself." else it }
    }
    LaunchedEffect(Unit) { if (upd.ready == null && !upd.busy) Updates.check(sv, ctx) }                  // start fetching it at once: the button then installs it straight away
    LaunchedEffect(wanted, upd.ready) { val f = upd.ready; if (wanted && f != null && !needPermission) install(f) }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner, upd.ready, needPermission) {
        val observer = LifecycleEventObserver { _, e ->
            val f = upd.ready
            if (e == Lifecycle.Event.ON_RESUME && wanted && needPermission && f != null && ctx.packageManager.canRequestPackageInstalls()) { needPermission = false; install(f) }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    val failed = wanted && !upd.busy && upd.ready == null
    Column(
        Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(28.dp),
        verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Outlined.SystemUpdate, null, Modifier.size(56.dp), tint = C.accent)
        Spacer(Modifier.height(16.dp))
        Text("Please update Roblox Manager", fontSize = 22.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        Spacer(Modifier.height(10.dp))
        Text(
            "This is version ${st.installed} and it is ${st.behind} update${if (st.behind == 1) "" else "s"} behind (the newest is ${st.latest}). Roblox Manager cannot be used until it is updated.",
            color = C.muted, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(6.dp))
        Text("Nothing is lost: your saved accounts and settings stay on this phone.", color = C.muted, fontSize = 13.sp, textAlign = TextAlign.Center)
        Spacer(Modifier.height(22.dp))
        val ready = upd.ready
        PrimaryButton(if (upd.busy) "Downloading…" else if (ready != null) "Update now (${upd.available?.versionName ?: ""})" else "Update now", enabled = !upd.busy) {
            if (ready == null) Updates.check(sv, ctx)
            if (!wanted) wanted = true                                      // (the effect above installs a file that is ready)
            else if (ready != null) install(ready)                          // (pressed again after the installer was cancelled)
        }
        if (upd.busy && upd.progress > 0f) { Spacer(Modifier.height(10.dp)); LinearProgressIndicator(progress = { upd.progress }, modifier = Modifier.fillMaxWidth()) }
        if (failed) {
        Spacer(Modifier.height(10.dp))
        QuietButton("Open the download page") {
            try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(if (sv.prefs.str("channel", "stable") == "beta") PolicyStore.RELEASES_ALL_URL else PolicyStore.RELEASES_URL)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) { }
        }
        }
        val msg = note.ifEmpty { upd.message }
        if (msg.isNotEmpty()) { Spacer(Modifier.height(12.dp)); Text(msg, color = C.muted, fontSize = 12.sp, textAlign = TextAlign.Center) }
    }
}
