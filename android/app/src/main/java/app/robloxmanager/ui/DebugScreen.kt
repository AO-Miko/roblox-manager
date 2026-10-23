package app.robloxmanager.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.BuildConfig
import app.robloxmanager.Services
import app.robloxmanager.core.DebugEvent
import app.robloxmanager.core.DebugLog

/** The levels the person can pick: (label, lowest level shown). */
val DEBUG_LEVELS = listOf("Everything" to "debug", "Info+" to "info", "Warnings+" to "warning", "Errors" to "error")

/**
 * App debug: everything that happens in the app, with the output (a view inside the Request log). Requests with what was sent and what came back, taps on buttons,
 * pages and questions that were opened, settings changed, sign-ins, alerts, downloads, errors with their trace, and what the app prints. Everything private is
 * hidden before an event is kept, so the list can be copied or shared.
 */
@Composable
fun DebugScreen(sv: Services) {
    val ctx = LocalContext.current
    val events by sv.debug.events.collectAsState()
    var level by rememberSaveable { mutableStateOf("debug") }
    var area by rememberSaveable { mutableStateOf("") }
    var text by rememberSaveable { mutableStateOf("") }
    var open by remember { mutableStateOf<Long?>(null) }
    val areas = remember(events.size) { events.map { it.area }.distinct().sorted() }
    val shown = remember(events, level, area, text) { sv.debug.snapshot(level, area, text).asReversed().take(500) }
    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(text, { text = it }, singleLine = true, label = { Text("Filter events") }, modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DEBUG_LEVELS.forEach { (label, key) -> FilterChip(level == key, { level = key }, label = { Text(label) }) }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(area.isEmpty(), { area = "" }, label = { Text("All areas") })
            areas.forEach { a -> FilterChip(area == a, { area = if (area == a) "" else a }, label = { Text(a) }) }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuietButton("Copy") {
                (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText("debug log", DebugLog.export(shown.asReversed(), BuildConfig.VERSION_NAME)))
            }
            QuietButton("Share") {
                val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, DebugLog.export(shown.asReversed(), BuildConfig.VERSION_NAME)).putExtra(Intent.EXTRA_SUBJECT, "Roblox Manager debug log")
                ctx.startActivity(Intent.createChooser(send, "Share the debug log"))
            }
            QuietButton("Clear") { sv.debug.clear(); open = null }
        }
        Text("${shown.size} shown, ${sv.debug.total} events since the app started. Tap an event to see its output.", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp))
        Text("Cookies, tokens, passwords, codes, e-mails, phone numbers, IP addresses and names of accounts and people are hidden before anything is kept.", color = C.muted, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp))
        LazyColumn(Modifier.fillMaxSize()) {
            items(shown, key = { "${it.time}-${it.area}-${it.message.hashCode()}-${it.detail.length}" }) { e -> DebugRow(e, open == e.time) { open = if (open == e.time) null else e.time } }
        }
    }
}

@Composable
private fun DebugRow(e: DebugEvent, expanded: Boolean, toggle: () -> Unit) {
    val colour = when (e.level) { "error" -> C.danger; "warning" -> C.warn; "debug" -> C.muted; else -> C.text }
    Column(Modifier.fillMaxWidth().clickable(onClick = toggle).padding(horizontal = 16.dp, vertical = 4.dp)) {
        Row {
            Text("${DebugLog.clockText(e.time)}  ${e.area}", fontSize = 11.sp, color = C.muted)
            Spacer(Modifier.weight(1f))
            Text(e.level, color = colour, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
        Text(e.message + if (e.detail.isNotEmpty() && !expanded) "   [+ output]" else "", fontSize = 12.sp, color = colour, maxLines = if (expanded) 20 else 2, overflow = TextOverflow.Ellipsis)
        if (expanded && e.detail.isNotEmpty()) {
            Text(e.detail, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = C.muted, modifier = Modifier.fillMaxWidth().background(C.surface2).padding(8.dp))
        }
    }
}
