package app.robloxmanager.ui

import android.content.Intent
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
import app.robloxmanager.Services
import app.robloxmanager.Updates
import app.robloxmanager.core.PolicyStatus
import app.robloxmanager.core.PolicyStore

/** Covers the whole app when this version is too far behind (see PolicyStore): nothing else can be used until it is updated. */
@Composable
fun UpdateRequiredScreen(sv: Services, st: PolicyStatus) {
    val ctx = LocalContext.current
    val upd by Updates.state.collectAsState()
    var note by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { if (upd.ready == null && !upd.busy) Updates.check(sv, ctx) }                  // start fetching it at once: the button then only installs
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
        if (ready != null) PrimaryButton("Install ${upd.available?.versionName ?: ""}") { note = Updates.install(ctx, ready) }
        else PrimaryButton(if (upd.busy) "Downloading…" else "Update now", enabled = !upd.busy) { Updates.check(sv, ctx) }
        if (upd.busy && upd.progress > 0f) { Spacer(Modifier.height(10.dp)); LinearProgressIndicator(progress = { upd.progress }, modifier = Modifier.fillMaxWidth()) }
        Spacer(Modifier.height(10.dp))
        QuietButton("Open the download page") {
            try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(if (sv.prefs.str("channel", "stable") == "beta") PolicyStore.RELEASES_ALL_URL else PolicyStore.RELEASES_URL)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) { }
        }
        val msg = note.ifEmpty { upd.message }
        if (msg.isNotEmpty()) { Spacer(Modifier.height(12.dp)); Text(msg, color = C.muted, fontSize = 12.sp, textAlign = TextAlign.Center) }
    }
}
