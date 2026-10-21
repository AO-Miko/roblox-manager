package app.robloxmanager.ui

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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ListAlt
import androidx.compose.material.icons.outlined.AdminPanelSettings
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Dns
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Paid
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import app.robloxmanager.core.Account

/** One place in the app. [words] are extra search words ("robux" finds Money). */
class Dest(val id: String, val title: String, val icon: ImageVector, val hint: String, val words: String)

val HOME = Dest("home", "Home", Icons.Outlined.Home, "Your account at a glance: Robux, pending, friends, and your accounts.", "account login sign in profile switch avatar")
val PEOPLE = Dest("people", "People", Icons.Outlined.People, "Friends, requests, followers, following, blocked users, find a user.", "friends requests followers following blocked unfriend find")
val GROUPS = Dest("groups", "Groups", Icons.Outlined.Groups, "Your groups: members, ranks, requests, roles and bans.", "group members ranks roles audit join requests shout leave")
val VIP = Dest("vip", "VIP servers", Icons.Outlined.Dns, "Every private server you have: switch on or off, renew, bulk actions.", "vip private servers renew expire duplicates link")
val MONEY = Dest("money", "Money", Icons.Outlined.Paid, "Robux balance, pending, totals and the transaction history.", "robux balance pending transactions history revenue")
val LOG = Dest("log", "Request log", Icons.AutoMirrored.Outlined.ListAlt, "Every request the app sends to Roblox and the answer.", "log requests http rate limit errors")
val STAFF = Dest("staff", "Staff List", Icons.Outlined.Badge, "Who is on the staff, from the owner down, with their Roblox profiles.", "staff team owner co-owner senior admin trusted friends roles hierarchy members profile")
val ADMIN = Dest("admin", "Admin", Icons.Outlined.AdminPanelSettings, "Who is banned and by whom (admin role or higher).", "ban unban banned reason roles moderator")
val INFO = Dest("info", "Info", Icons.Outlined.Info, "Settings, updates and what changed in each version.", "settings updates update log version changes about preferences")
val MORE = Dest("more", "More", Icons.Outlined.MoreHoriz, "Money, request log, settings and updates.", "")

val BOTTOM = listOf(HOME, PEOPLE, GROUPS, VIP, MORE)
val IN_MORE = listOf(MONEY, LOG, STAFF, ADMIN, INFO)           // (the Admin page is only offered to the admin role and higher)
val ALL = listOf(HOME, PEOPLE, GROUPS, VIP, MONEY, LOG, STAFF, ADMIN, INFO)

/** A request to open a page, and optionally one of its sub pages (People: 0..5, Info: 0 settings / 1 updates). [nonce] makes the same request work twice. */
class Jump(val dest: String, val sub: Int = 0, val nonce: Int = 0)

/** What the search can open: pages, and the sub pages of People and Info. */
class Hit(val title: String, val where: String, val words: String, val icon: ImageVector, val jump: Jump)

private val PEOPLE_SUBS = listOf("Friends", "Requests", "Followers", "Following", "Blocked", "Find a user")

fun searchHits(admin: Boolean = false): List<Hit> = buildList {
    ALL.filter { admin || it != ADMIN }.forEach { add(Hit(it.title, "page", it.words, it.icon, Jump(it.id))) }
    PEOPLE_SUBS.forEachIndexed { i, s -> add(Hit(s, "People", "", PEOPLE.icon, Jump("people", i))) }
    add(Hit("Settings", "Info", "preferences options rate limit log cache confirm", INFO.icon, Jump("info", 0)))
    add(Hit("Updates", "Info", "update version changes log install", INFO.icon, Jump("info", 1)))
}

/** Pages whose words contain every word the person typed, best (title starts with it) first. */
fun matchHits(hits: List<Hit>, query: String): List<Hit> {
    val words = query.lowercase().trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
    if (words.isEmpty()) return hits
    return hits.filter { h -> val hay = (h.title + " " + h.where + " " + h.words).lowercase(); words.all { it in hay } }
        .sortedBy { h -> val t = h.title.lowercase(); if (t == words.joinToString(" ")) 0 else if (t.startsWith(words[0])) 1 else 2 }
}

@Composable
fun TopBar(title: String, onBack: (() -> Unit)?, accounts: List<Account>, me: Account?, onSwitch: (Account) -> Unit, onAdd: () -> Unit, onSearch: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(C.bg).statusBarsPadding().padding(start = if (onBack != null) 4.dp else 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        if (onBack != null) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") }
        Text(title, Modifier.weight(1f), fontSize = 20.sp, fontWeight = FontWeight.Bold, maxLines = 1)
        IconButton(onClick = onSearch) { Icon(Icons.Outlined.Search, "Search") }
        var open by remember { mutableStateOf(false) }
        Box {
            IconButton(onClick = { open = true }) {
                Box(Modifier.size(32.dp).clip(CircleShape).background(C.accentDim), Alignment.Center) {
                    Text((me?.name ?: "?").take(1).uppercase(), fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                accounts.forEach { a ->
                    DropdownMenuItem(
                        text = { Column { Text(a.displayName.ifEmpty { a.name } + if (a.id == me?.id) "  (in use)" else "", fontWeight = FontWeight.Medium); Text("@${a.name}", color = C.muted, fontSize = 12.sp) } },
                        onClick = { open = false; if (a.id != me?.id) onSwitch(a) },
                    )
                }
                DropdownMenuItem(text = { Text("Add another account") }, onClick = { open = false; onAdd() })
            }
        }
    }
}

@Composable
fun BottomBar(current: String, counts: Map<String, Int>, onPick: (Dest) -> Unit) {
    NavigationBar(containerColor = C.surface, tonalElevation = 0.dp) {
        BOTTOM.forEach { d ->
            val selected = current == d.id || (d == MORE && IN_MORE.any { it.id == current })
            val n = when (d) { PEOPLE -> counts["Friends"]; GROUPS -> counts["Groups"]; VIP -> counts["VIP"]; else -> null }
            NavigationBarItem(
                selected = selected, onClick = { onPick(d) }, alwaysShowLabel = true,
                icon = {
                    BadgedBox(badge = { if (n != null && n > 0) Badge(containerColor = C.accent) { Text(if (n > 999) "999+" else n.toString(), fontSize = 10.sp) } }) { Icon(d.icon, d.title) }
                },
                label = { Text(d.title, fontSize = 11.sp, maxLines = 1) },
                colors = NavigationBarItemDefaults.colors(indicatorColor = C.accentDim, selectedIconColor = C.text, selectedTextColor = C.text, unselectedIconColor = C.muted, unselectedTextColor = C.muted),
            )
        }
    }
}

@Composable
fun MoreScreen(admin: Boolean, onOpen: (Dest) -> Unit) {
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        IN_MORE.filter { admin || it != ADMIN }.forEach { d ->
            Card(onClick = { onOpen(d) }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(C.surface3), Alignment.Center) { Icon(d.icon, null, tint = C.accent) }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(d.title, fontWeight = FontWeight.SemiBold)
                        Text(d.hint, color = C.muted, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun SearchDialog(admin: Boolean, onClose: () -> Unit, onPick: (Jump) -> Unit) {
    var q by remember { mutableStateOf("") }
    val hits = remember(q, admin) { matchHits(searchHits(admin), q) }
    val focus = remember { FocusRequester() }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(C.bg).statusBarsPadding().padding(12.dp)) {
            OutlinedTextField(
                value = q, onValueChange = { q = it }, singleLine = true, modifier = Modifier.fillMaxWidth().focusRequester(focus),
                placeholder = { Text("Search pages and settings...") }, leadingIcon = { Icon(Icons.Outlined.Search, null) },
                trailingIcon = { IconButton(onClick = onClose) { Icon(Icons.Outlined.Close, "Close") } },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go), keyboardActions = KeyboardActions(onGo = { hits.firstOrNull()?.let { onPick(it.jump) } }),
            )
            LaunchedEffect(Unit) { focus.requestFocus() }
            Spacer(Modifier.size(8.dp))
            LazyColumn(Modifier.fillMaxSize()) {
                if (hits.isEmpty()) item { Text("Nothing found.", color = C.muted, modifier = Modifier.padding(16.dp)) }
                items(hits, key = { it.title + it.where }) { h ->
                    Row(Modifier.fillMaxWidth().clickable { onPick(h.jump) }.padding(horizontal = 8.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(h.icon, null, tint = C.accent)
                        Spacer(Modifier.width(14.dp))
                        Text(h.title, Modifier.weight(1f), fontWeight = FontWeight.Medium)
                        Text(h.where, color = C.muted, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}
