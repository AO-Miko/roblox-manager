package app.robloxmanager.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.Badge
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Services
import app.robloxmanager.core.Debug
import app.robloxmanager.core.Notice

/** The small red circle with a number that says how many notifications are unread ("99+" at most). Nothing is drawn for 0. */
@Composable
fun UnreadBadge(n: Int) {
    if (n > 0) Badge(containerColor = androidx.compose.ui.graphics.Color(0xFFCF2A37), contentColor = androidx.compose.ui.graphics.Color.White) { Text(if (n > 99) "99+" else n.toString(), fontSize = 10.sp) }
}

private fun levelColour(level: String) = when (level) { "warning" -> C.warn; "important" -> C.accent; else -> C.muted }

/** News from the developer: newest first; tapping one opens it and marks it read. Text is shown as plain text. */
@Composable
fun NoticesScreen(sv: Services) {
    val unread by sv.unreadNotices.collectAsState()
    var version by remember { mutableStateOf(0) }            // counts up when something was marked read, so the list is drawn again
    LaunchedEffect(Unit) { sv.refreshNotices(); version++ }
    val list = remember(unread, version) { sv.visibleNotices() }
    val ctx = LocalContext.current
    var open by remember { mutableStateOf<String?>(null) }
    var showRead by remember { mutableStateOf(false) }               // the check icon: also show the messages that were read
    var justRead by remember { mutableStateOf(setOf<String>()) }     // read a moment ago: stays in the list until the page is left, so the card you opened does not vanish
    val readCount = list.count { sv.isNoticeRead(it.id) }
    val shown = if (showRead) list else list.filter { !sv.isNoticeRead(it.id) || it.id in justRead }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (unread > 0) "$unread unread" else "All read", Modifier.weight(1f), color = C.muted, fontSize = 13.sp)
            IconButton(onClick = { showRead = !showRead; Debug.event("notices", if (showRead) "showing read notifications" else "hiding read notifications") }, enabled = readCount > 0 || showRead,
                modifier = Modifier.background(if (showRead) C.accentDim else androidx.compose.ui.graphics.Color.Transparent, CircleShape)) {
                Icon(Icons.Outlined.Check, if (showRead) "Hide the messages I have read ($readCount)" else "Show the messages I have read ($readCount)", tint = if (showRead) C.onDim else C.muted)
            }
            QuietButton("Mark all as read", enabled = unread > 0) { sv.markAllNoticesRead(); version++ }
        }
        if (list.isEmpty()) Box(Modifier.fillMaxSize(), Alignment.Center) { Text("No notifications.", color = C.muted) }
        else if (shown.isEmpty()) Box(Modifier.fillMaxSize().padding(24.dp), Alignment.Center) { Text("You are all caught up. Tap the check mark above to see the messages you have read.", color = C.muted) }
        else LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(shown, key = { it.id }) { n ->
                val read = remember(n.id, unread, version) { sv.isNoticeRead(n.id) }
                NoticeCard(n, read, open == n.id) {
                    Debug.event("notices", "opened notification '${n.id}'")
                    open = if (open == n.id) null else n.id
                    if (!read) { sv.markNoticeRead(n.id); justRead = justRead + n.id; version++ }
                }
            }
        }
    }
}

@Composable
private fun NoticeCard(n: Notice, read: Boolean, expanded: Boolean, onClick: () -> Unit) {
    val ctx = LocalContext.current
    Card(onClick = onClick) {
        Row {
            if (read) Icon(Icons.Outlined.Check, "read", Modifier.padding(top = 3.dp).size(14.dp), tint = C.success)
            else Box(Modifier.padding(top = 6.dp).size(10.dp).clip(CircleShape).background(C.danger))
            Spacer(Modifier.width(if (read) 8.dp else 10.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(n.title.ifEmpty { "(no title)" }, Modifier.weight(1f), fontWeight = if (read) FontWeight.Medium else FontWeight.Bold, maxLines = if (expanded) Int.MAX_VALUE else 2)
                    Text(n.date, color = C.muted, fontSize = 12.sp)
                }
                if (n.level != "info") Text(if (n.level == "warning") "WARNING" else "IMPORTANT", color = levelColour(n.level), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Text(n.body, color = if (expanded) C.text else C.muted, fontSize = 13.sp, maxLines = if (expanded) Int.MAX_VALUE else 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                if (expanded && n.link != null) QuietButton("Open the link") {
                    Debug.event("notices", "opened a link of notification '${n.id}'")
                    if (n.link.startsWith("https://")) try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(n.link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) { }
                }
            }
        }
    }
}
