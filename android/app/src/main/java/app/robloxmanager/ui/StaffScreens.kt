package app.robloxmanager.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.clickable
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Services
import app.robloxmanager.core.Roles
import app.robloxmanager.core.str
import java.text.NumberFormat
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.JsonObject

/** The colour of a role's heading; it follows the theme. */
private fun roleColour(key: String): Color = when (key) {
    "owner" -> C.warn; "co-owner" -> C.orange; "senior-admin" -> C.violet; "admin" -> C.accent; "trusted-friend" -> C.success; else -> C.muted
}

// ======================================================================== Staff List (everybody)
@Composable
fun StaffScreen(sv: Services) {
    val ver by sv.rolesVersion.collectAsState()
    val staff = remember(ver) { sv.roles.staff() }
    var selected by remember { mutableStateOf<Long?>(null) }
    val profiles = remember { mutableStateMapOf<Long, JsonObject>() }
    val avatars = remember { mutableStateMapOf<Long, String>() }
    val counts = remember { mutableStateMapOf<Long, Map<String, Int?>>() }
    val ctx = LocalContext.current
    val fmt = remember { NumberFormat.getInstance() }

    LaunchedEffect(staff) {                              // public profiles and pictures, one after the other (the client paces the requests)
        for ((id, _) in staff) if (id !in profiles) {
            try { sv.api.profile(id)?.let { profiles[id] = it } } catch (e: CancellationException) { throw e } catch (_: Throwable) { }
        }
        try { avatars.putAll(sv.api.headshots(staff.map { it.first })) } catch (e: CancellationException) { throw e } catch (_: Throwable) { }
    }
    LaunchedEffect(selected) {
        val id = selected ?: return@LaunchedEffect
        if (id !in counts) try { counts[id] = sv.api.counts(id) } catch (e: CancellationException) { throw e } catch (_: Throwable) { }
    }

    if (staff.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
            Text("The staff list is empty or not downloaded yet.", color = C.muted)
            Text("It is fetched when the app starts and every ten minutes.", color = C.muted, fontSize = 12.sp)
        }
        return
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 8.dp)) {
        var last = -1
        val rows = staff.flatMap { (id, role) -> if (role.rank != last) { last = role.rank; listOf<Any>(role, id to role) } else listOf<Any>(id to role) }
        items(rows) { row ->
            if (row is Roles.Role) {
                Text(row.label.uppercase(), Modifier.padding(start = 16.dp, top = 14.dp, bottom = 4.dp), color = roleColour(row.key), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            } else {
                @Suppress("UNCHECKED_CAST") val pair = row as Pair<Long, Roles.Role>
                val (id, role) = pair
                val p = profiles[id]
                val shownName = p?.str("displayName")?.ifEmpty { null } ?: p?.str("name") ?: "User $id"
                Column(Modifier.fillMaxWidth().clickable { selected = if (selected == id) null else id }.padding(horizontal = 16.dp, vertical = 6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Avatar(avatars[id], 44)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(shownName, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(p?.str("name")?.let { "@$it" } ?: "id $id", color = C.muted, fontSize = 12.sp)
                        }
                        Text(role.label, color = roleColour(role.key), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                    if (selected == id) {
                        Spacer(Modifier.height(8.dp))
                        Card {
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Fact("User id", id.toString())
                                Fact("Joined", p?.str("created")?.take(10) ?: "-")
                                val c = counts[id]
                                Fact("Followers", c?.get("followers")?.let { fmt.format(it) } ?: "…")
                                Fact("Following", c?.get("following")?.let { fmt.format(it) } ?: "…")
                                Fact("Friends", c?.get("friends")?.let { fmt.format(it) } ?: "…")
                                val about = p?.str("description").orEmpty()
                                Spacer(Modifier.height(4.dp))
                                Text("Description", color = C.muted, fontSize = 12.sp)
                                Text(about.ifBlank { "No description." }, color = if (about.isBlank()) C.muted else C.text, fontSize = 13.sp)
                                Spacer(Modifier.height(6.dp))
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    PrimaryButton("Go to profile") { openProfile(ctx, id) }
                                    QuietButton("Copy user id") { copyText(ctx, id.toString()) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Fact(k: String, v: String) {
    Row { Text(k, Modifier.width(96.dp), color = C.muted, fontSize = 13.sp); Text(v, fontSize = 13.sp) }
}

private fun openProfile(ctx: Context, id: Long) {
    try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.roblox.com/users/$id/profile")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) { }
}

private fun copyText(ctx: Context, text: String) {
    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText("user id", text))
}

// ======================================================================== Admin (admin and up)
@Composable
fun AdminScreen(sv: Services) {
    val ver by sv.rolesVersion.collectAsState()
    val me by sv.current.collectAsState()
    val rank = remember(ver, me) { me?.let { sv.roles.rankOf(it.id) } ?: 0 }
    val bans = remember(ver) { sv.bans.entries().sortedByDescending { it.since } }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Card {
                Column {
                    Text("${Roles.label(rank)}: ${me?.displayName?.ifEmpty { null } ?: me?.name ?: ""}", fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text("A higher role acts on lower roles and on people without a role. Nobody acts on themselves or on the same or a higher role. An unban needs at least the role of whoever placed the ban.", color = C.muted, fontSize = 12.sp)
                    Spacer(Modifier.height(6.dp))
                    Text("Bans and unbans are signed with the release key, so they are published from a PC that has it (Admin page of the PC app, or tools/ban.sh). This page shows what is in force.", color = C.muted, fontSize = 12.sp)
                }
            }
        }
        item { Text("BANNED (${bans.size})", color = C.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold) }
        if (bans.isEmpty()) item { Text("Nobody is banned.", color = C.muted) }
        items(bans, key = { it.id }) { b ->
            Card {
                Column {
                    Text(b.id.toString(), fontWeight = FontWeight.Medium)
                    if (b.reason.isNotEmpty()) Text(b.reason, fontSize = 13.sp)
                    Text(listOf(b.since, "by " + (b.by?.toString() ?: "owner"), Roles.label(b.rank)).filter { it.isNotEmpty() }.joinToString("  ·  "), color = C.muted, fontSize = 12.sp)
                }
            }
        }
        item { Text("STAFF (${sv.roles.staff().size})", color = C.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold) }
        items(sv.roles.staff(), key = { it.first }) { (id, role) ->
            Row(Modifier.fillMaxWidth()) { Text(id.toString(), Modifier.weight(1f)); Text(role.label, color = roleColour(role.key), fontSize = 13.sp) }
        }
    }
}
