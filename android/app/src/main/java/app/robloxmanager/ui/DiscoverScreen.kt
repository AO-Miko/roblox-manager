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
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.collectAsState
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
import app.robloxmanager.core.Features
import app.robloxmanager.core.FriendGame
import app.robloxmanager.core.Geo
import app.robloxmanager.core.GeoException
import app.robloxmanager.core.Place
import app.robloxmanager.core.WorldMap
import app.robloxmanager.core.serverInfo
import app.robloxmanager.core.GameSort
import app.robloxmanager.core.RecentGames
import app.robloxmanager.core.ServerInfo
import app.robloxmanager.core.favoriteGames
import app.robloxmanager.core.favoriteState
import app.robloxmanager.core.friendsInGames
import app.robloxmanager.core.gameServers
import app.robloxmanager.core.setFavorite
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
fun launchRoblox(ctx: Context, placeId: Long, linkCode: String? = null, web: String = Games.pageUrl(placeId), jobId: String? = null, onMissing: () -> Unit = {}): Boolean {
    if (!robloxInstalled(ctx)) { onMissing(); return false }
    fun view(url: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    val link = try { Games.launcherUrl(placeId, linkCode, jobId) } catch (_: IllegalArgumentException) { return false }          // (a join code that does not look like one opens nothing)
    return try {
        view(link); true
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
private fun FriendCardView(f: FriendGame, icons: IconBook, head: String?, onJoin: () -> Unit) {
    Column(Modifier.width(140.dp).clip(RoundedCornerShape(12.dp)).background(C.surface).padding(8.dp)) {
        Box(Modifier.size(124.dp).clip(RoundedCornerShape(10.dp)).background(C.surface3)) {
            f.universe?.let { u -> icons.urls[u]?.let { AsyncImage(model = it, contentDescription = f.game, modifier = Modifier.size(124.dp), contentScale = ContentScale.Crop) } }
        }
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(22.dp).clip(CircleShape).background(C.surface3)) {                                  // (the friend's picture, before the name)
                head?.let { AsyncImage(model = it, contentDescription = f.name, modifier = Modifier.size(22.dp), contentScale = ContentScale.Crop) }
            }
            Spacer(Modifier.width(6.dp))
            Text(f.displayName.ifEmpty { f.name }, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Text(f.game.ifEmpty { "In a game" }, color = C.muted, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.height(30.dp))
        Spacer(Modifier.height(4.dp))
        PrimaryButton("Join", onClick = onJoin)
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
    val me by sv.current.collectAsState()
    var friends by remember { mutableStateOf<List<FriendGame>>(emptyList()) }
    val friendHeads = remember { mutableStateMapOf<Long, String>() }
    var favorites by remember { mutableStateOf<List<GameCard>>(emptyList()) }
    var recents by remember { mutableStateOf(RecentGames.load(sv.prefs)) }
    var askInstall by remember { mutableStateOf(false) }

    LaunchedEffect(me?.id) {                                                       // your own rows: friends in games and favorites (signed in)
        val m = me
        if (m == null) { friends = emptyList(); favorites = emptyList(); return@LaunchedEffect }
        try { friends = sv.api.friendsInGames(); icons.ensure(friends.mapNotNull { it.universe }) } catch (e: CancellationException) { throw e } catch (_: Exception) { }
        try { friendHeads.putAll(sv.api.headshots(friends.take(Games.ROW_LIMIT).map { it.id }, "48x48")) } catch (e: CancellationException) { throw e } catch (_: Exception) { }
        try { favorites = sv.api.favoriteGames(m.id); icons.ensure(favorites.map { it.universeId }) } catch (e: CancellationException) { throw e } catch (_: Exception) { }
    }
    LaunchedEffect(recents) { icons.ensure(recents.map { it.universeId }) }
    if (askInstall) InstallRobloxDialog { askInstall = false }
    fun backFromGame() { selected = null; recents = RecentGames.load(sv.prefs) }

    BackHandler(enabled = selected != null) { backFromGame() }

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

    selected?.let { GameScreen(sv, it, icons) { backFromGame() }; return }

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
                if (friends.isNotEmpty()) item(key = "friends") {
                    Text("Friends in games", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 6.dp))
                    LazyRow(contentPadding = PaddingValues(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(friends.take(Games.ROW_LIMIT), key = { it.id }) { f -> FriendCardView(f, icons, friendHeads[f.id]) { launchRoblox(ctx, f.place, jobId = f.job) { askInstall = true } } }
                    }
                }
                if (favorites.isNotEmpty()) item(key = "favorites") {
                    Text("Your favorites", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 6.dp))
                    LazyRow(contentPadding = PaddingValues(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(favorites.take(Games.ROW_LIMIT), key = { it.universeId }) { g -> GameCardView(g, icons) { selected = g } }
                    }
                }
                if (recents.isNotEmpty()) item(key = "recents") {
                    Text("Recently viewed", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 6.dp))
                    LazyRow(contentPadding = PaddingValues(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(recents.take(Games.ROW_LIMIT), key = { it.universeId }) { g -> GameCardView(g, icons) { selected = g } }
                    }
                }
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
    var fav by remember(card.universeId) { mutableStateOf<Boolean?>(null) }
    var favBusy by remember { mutableStateOf(false) }
    var sort by remember { mutableStateOf("Asc") }
    var order by remember { mutableStateOf("roblox") }
    val places = remember(card.universeId) { mutableStateMapOf<String, Place>() }
    val started = remember(card.universeId) { mutableStateMapOf<String, Long>() }
    val versions = remember(card.universeId) { mutableStateMapOf<String, Long>() }
    var wikiUrl by remember(card.universeId) { mutableStateOf<String?>(null) }
    var wikiTick by remember { mutableStateOf(0) }                              // (raised when RoSeal's data service gets allowed: the game is checked again)
    var locating by remember { mutableStateOf(false) }
    val stopLocate = remember { booleanArrayOf(false) }
    val autoAgain = remember { booleanArrayOf(false) }
    var askGeo by remember { mutableStateOf(false) }
    var showMap by remember { mutableStateOf(false) }
    var mapFilter by remember(card.universeId) { mutableStateOf<List<String>?>(null) }
    var servers by remember(card.universeId) { mutableStateOf<List<ServerInfo>>(emptyList()) }
    var cursor by remember(card.universeId) { mutableStateOf("") }
    var srvBusy by remember(card.universeId) { mutableStateOf(false) }
    var srvNote by remember(card.universeId) { mutableStateOf("") }
    val signedIn by sv.current.collectAsState()
    val place = details?.placeId ?: card.placeId
    BackHandler { onBack() }

    /** The loaded servers that are not looked up yet (25 at a time): Roblox's join answer gives each one's data centre, address and start time; the place comes from RoSeal's list
     *  or ipwho.is, whichever the person allowed. */
    fun locate(auto: Boolean = false, all: Boolean = false) {
        val p = place ?: return
        if (locating) { if (auto) autoAgain[0] = true; return }                      // (the look-up of the old list is ending: this one follows)
        if (signedIn == null) { if (!auto) srvNote = "Sign in first: this needs your account."; return }
        val todo = servers.filter { it.id !in started }.let { if (all) it else it.take(25) }          // (the map wants every loaded server)
        if (todo.isEmpty()) { if (!auto) srvNote = if (servers.isEmpty()) "Press Find servers first." else "Every loaded server is looked up already."; return }
        val useRoseal = sv.prefs.bool("geo.roseal", false)
        val useIpwho = sv.prefs.bool("geo.allowed", false)
        locating = true; stopLocate[0] = false
        scope.launch {
            var located = 0
            val problems = ArrayList<String>()
            var looked = 0
            try {
                for ((k, s) in todo.withIndex()) {
                    if (stopLocate[0]) break
                    srvNote = "Looking up servers: $k/${todo.size}…"
                    try {
                        val info = sv.api.serverInfo(p, s.id)
                        started[s.id] = info.startedMs ?: 0; versions[s.id] = info.placeVersion ?: 0; looked++
                        places[s.id] = sv.geo.resolve(info, useRoseal, useIpwho, sv.rosealList); located++
                    }
                    catch (e: CancellationException) { throw e }
                    catch (e: RobloxException) { problems += errorText(e); if (e.status == 401) break }
                    catch (e: GeoException) { problems += e.message ?: "unknown" }
                    catch (e: IllegalArgumentException) { problems += "odd server id" }
                }
            } finally { locating = false }
            srvNote = "Looked up $looked of ${todo.size} server(s), $located located." + (problems.firstOrNull()?.let { " ${problems.size} could not be looked up: $it" } ?: "")
            if (autoAgain[0]) {
                autoAgain[0] = false
                if (Geo.autoWanted(sv.prefs.bool("geo.auto", false), sv.prefs.bool("geo.roseal", false), sv.prefs.bool("geo.allowed", false), signedIn != null)) locate(true)
            }
        }
    }

    fun findServers(reset: Boolean) {
        val p = place ?: return
        if (srvBusy || (!reset && cursor.isEmpty())) return                         // one page at a time: pressing again meanwhile does nothing
        srvBusy = true; srvNote = "Looking for servers…"
        if (reset) { places.clear(); started.clear(); versions.clear(); mapFilter = null; stopLocate[0] = true }          // (a look-up of the old list ends)
        val s0 = sort
        scope.launch {
            try {
                val (s, n) = sv.api.gameServers(p, s0, if (reset) "" else cursor)
                servers = if (reset) s else servers + s.filter { x -> servers.none { it.id == x.id } }
                cursor = n
                srvNote = if (servers.isEmpty()) "No public servers are open right now." else "${servers.size} servers" + if (n.isNotEmpty()) "  (more available)" else ""
                if (Geo.autoWanted(sv.prefs.bool("geo.auto", false), sv.prefs.bool("geo.roseal", false), sv.prefs.bool("geo.allowed", false), signedIn != null)) locate(true)
            } catch (e: CancellationException) { throw e } catch (e: Exception) { srvNote = "The servers could not be loaded: ${errorText(e)}" } finally { srvBusy = false }
        }
    }

    /** With RoSeal's data service allowed, the game's wiki is looked for as the game opens; the button appears only for a game that has one. Without the permission nothing is contacted. */
    LaunchedEffect(card.universeId, wikiTick) {
        if (!sv.prefs.bool("geo.roseal", false)) return@LaunchedEffect
        try { wikiUrl = sv.rosealLinks.linksFor(card.universeId).firstOrNull()?.url } catch (e: CancellationException) { throw e } catch (_: Exception) { }
    }

    LaunchedEffect(card.universeId) {
        RecentGames.add(sv.prefs, card)                                           // (the 'Recently viewed' row)
        suspend fun <T> quiet(b: suspend () -> T): T? = try { b() } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
        if (signedIn != null) fav = quiet { sv.api.favoriteState(card.universeId) }
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

    if (askGeo) androidx.compose.material3.AlertDialog(
        onDismissRequest = { askGeo = false }, title = { Text("Where should server locations come from?") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Roblox's answer says which data centre a server runs in and its public address. To turn that into a city, one of these services can be used:", fontSize = 13.sp)
                Text("• RoSeal's list (data.roseal.live): the app downloads the public list of Roblox data centres kept by the RoSeal extension. Nothing about you, your account or the server is sent: " +
                    "it is one plain download. This service is run by RoSeal, not by Roblox or by this app.", fontSize = 13.sp)
                Text("• ipwho.is: the server's public address is sent there, and it says which city the address is in. Nothing else is sent.", fontSize = 13.sp)
                Text("Nothing is contacted until you choose. You can change this later in Settings.", color = C.muted, fontSize = 12.sp)
                TextButton(onClick = { askGeo = false }) { Text("Cancel") }
            }
        },
        confirmButton = { TextButton(onClick = { askGeo = false; sv.prefs.put("geo.roseal", true); wikiTick++; locate() }) { Text("Use RoSeal's list") } },
        dismissButton = { TextButton(onClick = { askGeo = false; sv.prefs.put("geo.allowed", true); locate() }) { Text("Use ipwho.is") } },
    )
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
            if (fav != null) QuietButton(if (fav == true) "★ Favorited" else "☆ Favorite", enabled = !favBusy) {
                val want = fav != true
                favBusy = true
                scope.launch {
                    try { sv.api.setFavorite(card.universeId, want); fav = want; note = if (want) "Added to your favorites." else "Removed from your favorites." }
                    catch (e: CancellationException) { throw e } catch (e: Exception) { note = errorText(e) } finally { favBusy = false }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QuietButton("Open on roblox.com") { openUrl(ctx, Games.pageUrl(place)) }
                wikiUrl?.let { u -> QuietButton("Game wiki") { openUrl(ctx, u) } }
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
            Text("Servers", fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.FilterChip(selected = sort == "Asc", onClick = { sort = "Asc" }, label = { Text("Fewest first") })
                androidx.compose.material3.FilterChip(selected = sort == "Desc", onClick = { sort = "Desc" }, label = { Text("Most first") })
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Sort:", color = C.muted, fontSize = 12.sp)
                Games.SERVER_ORDERS.forEach { (key, label) -> androidx.compose.material3.FilterChip(selected = order == key, onClick = { order = key }, label = { Text(label) }) }
            }
            Text("Sorts the servers loaded so far. The running time needs Location and uptime first.", color = C.muted, fontSize = 11.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QuietButton(if (locating) "Looking up…" else "Location and uptime", enabled = !locating && servers.isNotEmpty()) {
                    if (sv.prefs.bool("geo.roseal", false) || sv.prefs.bool("geo.allowed", false)) locate() else askGeo = true
                }
                if (locating) QuietButton("Stop") { stopLocate[0] = true }
                QuietButton(if (showMap) "Hide map" else "Show map") {
                    showMap = !showMap
                    // the map looks the servers up by itself when it opens (asking first which service to use, if none is allowed yet)
                    if (showMap && !locating && signedIn != null && servers.any { it.id !in started }) {
                        if (sv.prefs.bool("geo.roseal", false) || sv.prefs.bool("geo.allowed", false)) locate(all = true) else askGeo = true
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QuietButton(if (srvBusy) "Looking…" else "Find servers", enabled = !srvBusy && place != null) { findServers(true) }
                QuietButton("Join the emptiest", enabled = place != null) {
                    val p = place ?: return@QuietButton
                    scope.launch {
                        try {
                            val best = sv.api.gameServers(p, "Asc", "", 25).first.filter { it.playing < it.max }.minByOrNull { it.playing }
                            if (best == null) srvNote = "No server with room was found right now." else { srvNote = "Joining a server with ${best.playing} of ${best.max} players."; launchRoblox(ctx, p, jobId = best.id) { askInstall = true } }
                        } catch (e: CancellationException) { throw e } catch (e: Exception) { srvNote = "The servers could not be loaded: ${errorText(e)}" }
                    }
                }
            }
            if (srvNote.isNotEmpty()) Text(srvNote, color = C.muted, fontSize = 12.sp)
            if (showMap) {
                val groups = WorldMap.groupPlaces(servers, places)
                ServerMap(groups, mapFilter) { ids -> mapFilter = if (mapFilter == ids) null else ids }
                Text(if (groups.isEmpty()) "No server is located yet. Press Location and uptime." else "${places.size} of ${servers.size} loaded servers are located, in ${groups.size} place(s). Press a dot to list its servers.",
                    color = C.muted, fontSize = 12.sp)
            }
            mapFilter?.let { f -> Row(verticalAlignment = Alignment.CenterVertically) { Text("Showing ${f.size} server(s) at one place", color = C.muted, fontSize = 12.sp, modifier = Modifier.weight(1f)); QuietButton("Show all") { mapFilter = null } } }
            if (servers.isNotEmpty() && (!showMap || mapFilter != null)) Card {          // (with the map open, only the servers of the pressed place are listed)
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Games.sortServers(servers, order, started).filter { s -> mapFilter?.let { s.id in it } ?: true }.forEach { s ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("${s.playing}/${s.max}", Modifier.width(64.dp), fontWeight = FontWeight.Medium)
                            Text(listOfNotNull(s.ping?.let { "$it ms" } ?: "-", s.fps?.let { "$it fps" }, places[s.id]?.label, started[s.id]?.takeIf { it > 0 }?.let { "running ${Games.ageText(it)}" },
                                versions[s.id]?.takeIf { it > 0 }?.let { Features.versionText(it, versions.values.maxOrNull() ?: 0) }).joinToString("  ·  "),
                                Modifier.weight(1f), color = C.muted, fontSize = 12.sp)
                            TextButton(onClick = {
                                place?.let { p -> Games.serverLink(p, s.id)?.let { link ->
                                    (ctx.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager)?.setPrimaryClip(android.content.ClipData.newPlainText("Join link", link))
                                    srvNote = "Join link copied."
                                } }
                            }) { Text("Link") }
                            TextButton(onClick = { place?.let { launchRoblox(ctx, it, jobId = s.id) { askInstall = true } } }) { Text("Join") }
                        }
                    }
                    if (cursor.isNotEmpty()) QuietButton(if (srvBusy) "Loading…" else "Load more", enabled = !srvBusy) { findServers(false) }
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
