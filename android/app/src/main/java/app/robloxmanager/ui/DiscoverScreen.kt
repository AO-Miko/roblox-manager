package app.robloxmanager.ui

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Services
import app.robloxmanager.core.GameCard
import app.robloxmanager.core.GameDetails
import app.robloxmanager.core.GameSort
import app.robloxmanager.core.Games
import app.robloxmanager.core.GroupHit
import app.robloxmanager.core.Person
import app.robloxmanager.core.RobloxException
import app.robloxmanager.core.Vip
import app.robloxmanager.core.discoverSorts
import app.robloxmanager.core.gameCover
import app.robloxmanager.core.gameDetails
import app.robloxmanager.core.gameFavorites
import app.robloxmanager.core.gameIcons
import app.robloxmanager.core.gameVotes
import app.robloxmanager.core.searchGames
import app.robloxmanager.core.searchGroups
import app.robloxmanager.core.str
import coil.compose.AsyncImage
import java.text.NumberFormat
import java.util.UUID
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

const val ROBLOX_PACKAGE = "com.roblox.client"

/** Is the Roblox app on this phone? (Play needs it.) */
fun robloxInstalled(ctx: Context): Boolean = try {
    ctx.packageManager.getPackageInfo(ROBLOX_PACKAGE, 0); true
} catch (_: Exception) {
    false
}

/** Open the Google Play page of Roblox (the Play Store app if there is one, else the web page). */
fun openRobloxInStore(ctx: Context) {
    for (url in listOf("market://details?id=$ROBLOX_PACKAGE", "https://play.google.com/store/apps/details?id=$ROBLOX_PACKAGE")) {
        try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return } catch (_: Exception) { }
    }
}

/** Open the Roblox app and join a game, or a private/VIP server (place id + link code). If the Roblox app is not installed nothing is opened and [onMissing] is called
 *  (the screen then offers to install it). Without a handler for the link the game's page opens instead. */
fun launchRoblox(ctx: Context, placeId: Long, linkCode: String? = null, web: String = Games.pageUrl(placeId), onMissing: () -> Unit = {}): Boolean {
    if (!robloxInstalled(ctx)) { onMissing(); return false }
    fun view(url: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    return try {
        view(Games.launcherUrl(placeId, linkCode)); true
    } catch (_: ActivityNotFoundException) {
        try { view(web) } catch (_: Exception) { }
        false
    }
}

/** "Roblox is not installed. Install it?": Yes opens Roblox in Google Play. */
@Composable
fun InstallRobloxDialog(onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss, title = { Text("Roblox is not installed") },
        text = { Text("Play needs the Roblox app on this phone. Do you want to install it? Google Play opens on the Roblox page; install it there, then press Play again.", color = C.muted) },
        confirmButton = { TextButton(onClick = { onDismiss(); openRobloxInStore(ctx) }) { Text("Open Google Play") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

fun openUrl(ctx: Context, url: String) {
    try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) { }
}

// ======================================================================== Home: Account and Discover
@Composable
fun HomeScreen(sv: Services, onAddAccount: () -> Unit, jump: Jump? = null) {
    var sub by rememberSaveable { mutableStateOf(0) }
    var discoverSeen by rememberSaveable { mutableStateOf(false) }          // (Discover is only built once it is opened, then it stays as it is)
    LaunchedEffect(jump) { if (jump != null && jump.dest == "home") sub = jump.sub.coerceIn(0, 1) }
    if (sub == 1) discoverSeen = true
    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = sub, containerColor = C.bg) {
            listOf("Account", "Discover").forEachIndexed { i, t -> Tab(selected = sub == i, onClick = { sub = i }, text = { Text(t) }) }
        }
        Box(Modifier.weight(1f)) {
            Box(if (sub == 0) Modifier.fillMaxSize() else Modifier.size(0.dp).clipToBounds()) { AccountScreen(sv, onAddAccount) }
            if (discoverSeen) Box(if (sub == 1) Modifier.fillMaxSize() else Modifier.size(0.dp).clipToBounds()) { DiscoverScreen(sv) }
        }
    }
}

// ======================================================================== small pieces
/** Pictures of the games on screen, fetched in batches of 100 and kept while the page is open. */
class IconBook(private val sv: Services) {
    val urls = mutableStateMapOf<Long, String>()
    suspend fun ensure(ids: List<Long>) {
        val todo = ids.filter { it !in urls }.distinct().take(300)
        if (todo.isNotEmpty()) try { urls.putAll(sv.api.gameIcons(todo)) } catch (e: CancellationException) { throw e } catch (_: Exception) { }
    }
}

/** The likes/dislikes bar of a game: the green part is the likes. */
@Composable
fun RatioBar(up: Long, down: Long, height: Int = 4) {
    val pct = Games.likePercent(up, down)
    Box(Modifier.fillMaxWidth().height(height.dp).clip(RoundedCornerShape((height / 2).dp)).background(C.surface3)) {
        if (pct != null && pct > 0) Box(Modifier.fillMaxWidth(pct / 100f).fillMaxHeight().background(C.success))
    }
}

@Composable
private fun GameCardView(g: GameCard, icons: IconBook, onClick: () -> Unit) {
    val pct = Games.likePercent(g.up, g.down)
    Column(Modifier.width(140.dp).clip(RoundedCornerShape(12.dp)).background(C.surface).clickable(onClick = onClick).padding(8.dp)) {
        Box(Modifier.size(124.dp).clip(RoundedCornerShape(10.dp)).background(C.surface3)) {
            icons.urls[g.universeId]?.let { AsyncImage(model = it, contentDescription = g.name, modifier = Modifier.size(124.dp), contentScale = ContentScale.Crop) }
        }
        Spacer(Modifier.height(6.dp))
        Text(g.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.height(36.dp))
        Text("${Games.short(g.playing)} playing" + (pct?.let { "   $it%" } ?: ""), color = C.muted, fontSize = 11.sp, maxLines = 1)
        Spacer(Modifier.height(4.dp))
        RatioBar(g.up, g.down)
    }
}

@Composable
private fun GameRow(g: GameCard, icons: IconBook, onClick: () -> Unit) {
    val pct = Games.likePercent(g.up, g.down)
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(64.dp).clip(RoundedCornerShape(10.dp)).background(C.surface3)) {
            icons.urls[g.universeId]?.let { AsyncImage(model = it, contentDescription = g.name, modifier = Modifier.size(64.dp), contentScale = ContentScale.Crop) }
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(g.name, fontWeight = FontWeight.Medium, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text("${Games.short(g.playing)} playing" + (pct?.let { "   $it% liked" } ?: ""), color = C.muted, fontSize = 12.sp)
            Spacer(Modifier.height(4.dp))
            RatioBar(g.up, g.down)
        }
    }
}

// ======================================================================== Discover
@Composable
fun DiscoverScreen(sv: Services) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val session = rememberSaveable { UUID.randomUUID().toString() }
    var query by rememberSaveable { mutableStateOf("") }
    var kind by rememberSaveable { mutableStateOf(0) }                         // 0 games, 1 people, 2 groups
    var submitted by rememberSaveable { mutableStateOf("") }                    // what is searched; "" shows the home page rows
    var selected by remember { mutableStateOf<GameCard?>(null) }
    val icons = remember { IconBook(sv) }
    var sorts by remember { mutableStateOf<List<GameSort>?>(null) }
    var games by remember { mutableStateOf<List<GameCard>>(emptyList()) }
    var token by remember { mutableStateOf("") }
    var people by remember { mutableStateOf<List<Person>>(emptyList()) }
    val heads = remember { mutableStateMapOf<Long, String>() }
    var groups by remember { mutableStateOf<List<GroupHit>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    val fmt = remember { NumberFormat.getInstance() }

    BackHandler(enabled = selected != null) { selected = null }

    suspend fun <T> guarded(what: String, block: suspend () -> T): T? = try {
        busy = true; message = ""; block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        message = "$what could not be loaded: ${errorText(e)}"; null
    } finally {
        busy = false
    }

    fun loadFeed() { scope.launch { guarded("The home page") { sv.api.discoverSorts(session) }?.let { sorts = it; icons.ensure(it.take(Games.ROWS_LIMIT).flatMap { s -> s.games.take(Games.ROW_LIMIT) }.map { c -> c.universeId }) } } }

    LaunchedEffect(submitted, kind) {
        if (submitted.isEmpty()) {
            if (sorts == null) loadFeed()
            return@LaunchedEffect
        }
        when (kind) {
            0 -> guarded("The search") { sv.api.searchGames(submitted, session) }?.let { (c, t) -> games = c; token = t; icons.ensure(c.map { g -> g.universeId }); if (c.isEmpty()) message = "No games found for '$submitted'." }
            1 -> guarded("The search") { sv.api.search(submitted) }?.let { p ->
                people = p.take(25); if (p.isEmpty()) message = "No people found for '$submitted'."
                try { heads.putAll(sv.api.headshots(people.map { it.id }, "48x48")) } catch (e: CancellationException) { throw e } catch (_: Exception) { }
            }
            else -> guarded("The search") { sv.api.searchGroups(submitted) }?.let { groups = it; if (it.isEmpty()) message = "No groups found for '$submitted'." }
        }
    }

    selected?.let { GameScreen(sv, it, icons) { selected = null }; return }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            query, { query = it }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            placeholder = { Text("Search games, people and groups") },
            trailingIcon = { if (query.isNotEmpty()) IconButton(onClick = { query = ""; submitted = "" }) { Icon(Icons.Outlined.Close, "Clear") } },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search), keyboardActions = KeyboardActions(onSearch = { submitted = query.trim() }),
        )
        Row(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Games", "People", "Groups").forEachIndexed { i, t ->
                FilterChip(selected = kind == i, onClick = { kind = i }, label = { Text(t) }, colors = FilterChipDefaults.filterChipColors(selectedContainerColor = C.accentDim))
            }
        }
        if (busy) Box(Modifier.fillMaxWidth().padding(16.dp), Alignment.Center) { CircularProgressIndicator() }
        if (message.isNotEmpty()) {
            Text(message, color = if (message.contains("could not")) C.danger else C.muted, modifier = Modifier.padding(16.dp))
            if (message.contains("could not")) TextButton(onClick = { if (submitted.isEmpty()) loadFeed() else { val s = submitted; submitted = ""; submitted = s } }, modifier = Modifier.padding(horizontal = 8.dp)) { Text("Try again") }
        }
        if (submitted.isEmpty()) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(vertical = 8.dp)) {
                items(sorts?.take(Games.ROWS_LIMIT) ?: emptyList(), key = { it.id }) { s ->
                    Text(s.name, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 6.dp))
                    LazyRow(contentPadding = PaddingValues(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(s.games.take(Games.ROW_LIMIT), key = { it.universeId }) { g -> GameCardView(g, icons) { selected = g } }
                    }
                }
            }
        } else when (kind) {
            0 -> LazyColumn(Modifier.fillMaxSize()) {
                items(games, key = { it.universeId }) { g -> GameRow(g, icons) { selected = g } }
                if (token.isNotEmpty()) item {
                    QuietButton(if (busy) "Loading…" else "Load more", enabled = !busy) {
                        val t = token
                        scope.launch { guarded("More games") { sv.api.searchGames(submitted, session, t) }?.let { (c, n) -> val have = games.map { it.universeId }.toSet(); games = games + c.filter { it.universeId !in have }; token = n; icons.ensure(c.map { g -> g.universeId }) } }
                    }
                }
            }
            1 -> LazyColumn(Modifier.fillMaxSize()) {
                items(people, key = { it.id }) { p ->
                    PersonRow(p, heads[p.id]) { TextButton(onClick = { openUrl(ctx, "https://www.roblox.com/users/${p.id}/profile") }) { Text("Profile") } }
                }
            }
            else -> LazyColumn(Modifier.fillMaxSize()) {
                items(groups, key = { it.id }) { g ->
                    Row(Modifier.fillMaxWidth().clickable { openUrl(ctx, "https://www.roblox.com/communities/${g.id}") }.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(g.name, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${fmt.format(g.members)} members" + g.description.trim().replace("\n", " ").take(80).let { if (it.isEmpty()) "" else "  ·  $it" }, color = C.muted, fontSize = 12.sp, maxLines = 2)
                        }
                        TextButton(onClick = { openUrl(ctx, "https://www.roblox.com/communities/${g.id}") }) { Text("Open") }
                    }
                }
            }
        }
    }
}

// ======================================================================== a game's page
@Composable
fun GameScreen(sv: Services, card: GameCard, icons: IconBook, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val fmt = remember { NumberFormat.getInstance() }
    var details by remember(card.universeId) { mutableStateOf<GameDetails?>(null) }
    var votes by remember(card.universeId) { mutableStateOf(card.up to card.down) }
    var favorites by remember(card.universeId) { mutableStateOf<Long?>(null) }
    var cover by remember(card.universeId) { mutableStateOf("") }
    var vip by remember(card.universeId) { mutableStateOf<List<Vip>>(emptyList()) }
    var menu by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var askInstall by remember { mutableStateOf(false) }
    val place = details?.placeId ?: card.placeId
    BackHandler { onBack() }

    LaunchedEffect(card.universeId) {
        suspend fun <T> quiet(b: suspend () -> T): T? = try { b() } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
        quiet { sv.api.gameDetails(card.universeId) }?.let { details = it }
        quiet { sv.api.gameVotes(card.universeId) }?.let { votes = it }
        favorites = details?.favorites ?: quiet { sv.api.gameFavorites(card.universeId) }
        cover = quiet { sv.api.gameCover(card.universeId) } ?: ""
        val p = details?.placeId ?: card.placeId
        vip = quiet { sv.api.myPrivateServers() }?.map { Vip(it) }?.filter { v -> (p != null && v.placeId == p) && v.active != false && v.state(null).isEmpty() && v.id != null } ?: emptyList()
    }

    suspend fun joinVip(v: Vip) {
        try {
            val d = sv.api.vipServer(v.id!!)
            val link = d?.str("link") ?: d?.str("joinCode")?.let { c -> v.placeId?.let { "https://www.roblox.com/games/$it?privateServerLinkCode=$c" } } ?: ""
            val (pl, code) = Games.linkParts(link)
            if (code == null) note = "Roblox did not give a join link for this server." else launchRoblox(ctx, pl ?: v.placeId ?: place ?: 0, code, link) { askInstall = true }
        } catch (e: RobloxException) { note = errorText(e) }
    }

    if (askInstall) InstallRobloxDialog { askInstall = false }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 16.dp)) {
        TextButton(onClick = onBack, modifier = Modifier.padding(start = 4.dp)) { Text("‹ Back") }
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(C.surface3)) {
            val img = cover.ifEmpty { icons.urls[card.universeId] ?: "" }
            if (img.isNotEmpty()) AsyncImage(model = img, contentDescription = card.name, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        }
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(details?.name?.ifEmpty { null } ?: card.name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            val by = details?.creator?.ifEmpty { null } ?: card.creator
            if (by.isNotEmpty()) Text("by $by" + if (details?.creatorVerified ?: card.verified) "  ✔" else "", color = C.muted)

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                PrimaryButton("Play", enabled = place != null) { place?.let { launchRoblox(ctx, it) { askInstall = true } } }
                if (vip.isNotEmpty()) Box {
                    QuietButton("Join my VIP server") { if (vip.size == 1) scope.launch { joinVip(vip[0]) } else menu = true }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        vip.forEach { v -> DropdownMenuItem(text = { Text(v.name.ifEmpty { "Server ${v.id}" }) }, onClick = { menu = false; scope.launch { joinVip(v) } }) }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QuietButton("Open on roblox.com") { openUrl(ctx, Games.pageUrl(place)) }
                QuietButton("Copy link") {
                    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText("game", Games.pageUrl(place)))
                    note = "Game link copied."
                }
            }
            if (note.isNotEmpty()) Text(note, color = C.muted, fontSize = 12.sp)

            Text("Rating", fontWeight = FontWeight.Bold)
            val pct = Games.likePercent(votes.first, votes.second)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Likes  ${fmt.format(votes.first)}")
                    Text("Dislikes  ${fmt.format(votes.second)}")
                }
                Text(pct?.let { "$it%" } ?: "No votes yet", fontSize = 22.sp, fontWeight = FontWeight.Bold)
            }
            RatioBar(votes.first, votes.second, 10)

            Text("Stats", fontWeight = FontWeight.Bold)
            Card {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    fun row(k: String, v: String) = @Composable { Row { Text(k, Modifier.width(120.dp), color = C.muted, fontSize = 13.sp); Text(v, fontSize = 13.sp) } }
                    row("Playing now", fmt.format(details?.playing ?: card.playing))()
                    row("Visits", details?.visits?.let { fmt.format(it) } ?: "…")()
                    row("Favorites", favorites?.let { fmt.format(it) } ?: "…")()
                    row("Max players", details?.maxPlayers?.toString() ?: "-")()
                    row("Created", details?.created?.take(10)?.ifEmpty { null } ?: "-")()
                    row("Updated", details?.updated?.take(10)?.ifEmpty { null } ?: "-")()
                    row("Genre", details?.genre?.ifEmpty { null } ?: card.genre.ifEmpty { "-" })()
                    row("Age rating", card.age.ifEmpty { "-" })()
                }
            }
            val about = details?.description.orEmpty()
            if (about.isNotBlank()) {
                Text("Description", fontWeight = FontWeight.Bold)
                Text(about, color = C.muted, fontSize = 13.sp)
            }
        }
    }
}
