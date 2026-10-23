package app.robloxmanager

import android.app.Application
import android.content.Context
import java.io.File
import kotlin.coroutines.cancellation.CancellationException
import app.robloxmanager.core.Account
import app.robloxmanager.core.Debug
import app.robloxmanager.core.DebugLog
import app.robloxmanager.core.Scrub
import app.robloxmanager.core.AlertRules
import app.robloxmanager.core.AlertSettings
import app.robloxmanager.core.Seen
import app.robloxmanager.core.presence
import app.robloxmanager.core.Accounts
import app.robloxmanager.core.BanStore
import app.robloxmanager.core.KeystoreVault
import app.robloxmanager.core.NameCache
import app.robloxmanager.core.Geo
import app.robloxmanager.core.GeoBook
import app.robloxmanager.core.RoSealLinkList
import app.robloxmanager.core.RoSealLinks
import app.robloxmanager.core.RoSealList
import app.robloxmanager.core.Prefs
import app.robloxmanager.core.PolicyStatus
import app.robloxmanager.core.PolicyStore
import app.robloxmanager.core.RequestLog
import app.robloxmanager.core.RoleStore
import app.robloxmanager.core.RobloxApi
import app.robloxmanager.core.RobloxClient
import app.robloxmanager.core.RobloxException
import app.robloxmanager.core.cleanCookie
import app.robloxmanager.core.long
import app.robloxmanager.core.str
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class RobloxManagerApp : Application() {
    lateinit var services: Services
    override fun onCreate() {
        super.onCreate()
        services = Services(this)
    }
}

val Context.services: Services get() = (applicationContext as RobloxManagerApp).services

/** Everything the screens share: one client, the saved accounts, settings, and who is signed in. */
class Services(app: Application) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val dir: File = app.filesDir
    val log = RequestLog(File(dir, "requests.log"))
    /** What happens in the app, with the output (the App debug view of the Request log; everything private is hidden). */
    val debug = DebugLog(File(dir, "debug.log"))
    val client = RobloxClient(log = log)
    val names = NameCache(File(dir, "names.json"))
    val api = RobloxApi(client, names)
    val accounts = Accounts(File(dir, "accounts.json"), KeystoreVault())
    val prefs = Prefs(File(dir, "prefs.json"))
    init {
        debug.writeFile = prefs.bool("debugToFile", true)
        Debug.install(debug)                                   // uncaught errors and printed lines too
        debug.event("app", "started version ${BuildConfig.VERSION_NAME}")
    }
    val alerts = AlertSettings(prefs)
    /** Where servers are (answers kept 30 days); only used when the person presses Location and uptime and allowed a service. */
    val geo = GeoBook(File(dir, "server_places.json"), Geo.httpFetch())
    /** RoSeal's public list of Roblox data centres (data.roseal.live), only downloaded when the person allowed it. */
    val rosealList = RoSealList(File(dir, "roseal_datacenters.json"), Geo.rosealFetch())
    /** RoSeal's links to game wikis, only downloaded when the person allowed it and pressed Game wiki. */
    val rosealLinks = RoSealLinkList(File(dir, "roseal_links.json"), Geo.rosealFetch(max = RoSealLinks.MAX_BYTES))
    /** Shows one piece of friend news (set by the activity, which has the Android context). */
    var notifier: (String) -> Unit = {}
    /** Whether friend alerts are on (shown by the switch in People > Alerts and in Settings). */
    val alertsOn = MutableStateFlow(prefs.bool("alerts.enabled", false))
    private var seen: Map<Long, Seen> = emptyMap()
    private var seenFor: Long? = null
    val bans = BanStore(File(dir, "bans.cache.json"))
    val roles = RoleStore(File(dir, "roles.cache.json"))
    val policy = PolicyStore(File(dir, "policy.cache.json"))
    /** The Beta channel counts its own updates (every release, betas included), from the beta branch; its serial is independent of the stable one. */
    val policyBeta = PolicyStore(File(dir, "policy.cache.beta.json"), baseUrl = PolicyStore.BETA_BASE_URL, useBeta = true)
    /** The policy of the channel this phone follows (Settings > Updates). */
    fun activePolicy(): PolicyStore = if (prefs.str("channel", "stable") == "beta") policyBeta else policy
    /** Not null while this version is too far behind (see PolicyStore): the whole app is covered by the update page. */
    val updateRequired = MutableStateFlow<PolicyStatus?>(null)
    /** Counts up when the role list changed, so the screens look at it again. */
    val rolesVersion = MutableStateFlow(0)
    /** Set when an account was signed out because it is banned; the screen shows it once. */
    val banNotice = MutableStateFlow<String?>(null)
    val cacheDir: File = app.cacheDir
    val filesDir: File = dir

    /** The signed-in account, or null (the sign-in screen is shown). */
    val current = MutableStateFlow<Account?>(null)
    val ready = MutableStateFlow(false)
    val accountList = MutableStateFlow<List<Account>>(emptyList())

    init {
        client.readBurst = prefs.double("readBurst", 0.5)
        scope.launch {                         // the accounts in use are hidden in the debug log; signing in and out are events
            current.collect { a -> Scrub.setIdentity(a); Debug.event("account", if (a != null) "signed in" else "signed out") }
        }
        scope.launch { accountList.collect { l -> Scrub.setIdentity(*l.toTypedArray()) } }
        log.writeFile = prefs.bool("logToFile", true)
        enforcePolicy()                       // from the last policy kept on the phone: a version that is too far behind is covered before anything is sent
        scope.launch { restore() }
        scope.launch {                         // friend alerts: a look every 90 seconds while the app is running (a problem here must never stop the app)
            while (true) {
                delay(AlertRules.INTERVAL_MS)
                try { pollAlerts() } catch (e: CancellationException) { throw e } catch (_: Throwable) { }
            }
        }
        scope.launch {                         // the ban list: at the start and every ten minutes while the app is open
            while (true) {
                try {                              // (a problem with the ban list must never stop or crash the app)
                    enforce()
                    withContext(Dispatchers.IO) { bans.refresh() }
                    enforce()
                    if (withContext(Dispatchers.IO) { roles.refresh() } == true) rolesVersion.value++
                    withContext(Dispatchers.IO) { activePolicy().refresh() }
                    enforcePolicy()
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (_: Throwable) {
                }
                delay(BanStore.REFRESH_MS)
            }
        }
    }

    /** One look at the watched friends: news goes to [notifier]. The first look of an account only learns who is where. */
    suspend fun pollAlerts() {
        val me = current.value
        if (me == null || !alerts.enabled || updateRequired.value != null) { seen = emptyMap(); seenFor = null; return }
        val watched = alerts.watched(me.id)
        if (watched.isEmpty()) { seen = emptyMap(); return }
        if (seenFor != me.id) { seen = emptyMap(); seenFor = me.id }
        val now = AlertRules.snapshot(api.presence(watched.keys.toList()))
        val found = AlertRules.news(seen, now, watched, alerts.online, alerts.ingame)
        Debug.event("alerts", "looked at ${watched.size} watched friend(s): ${found.size} piece(s) of news", "debug")
        seen = now
        found.take(5).forEach { Debug.event("alerts", "notification: ${it.second}"); notifier(it.second) }
        if (found.size > 5) notifier("...and ${found.size - 5} more friends")
    }

    /** Switches friend alerts on or off everywhere; switching on takes the first look at once. */
    fun setAlerts(on: Boolean) {
        alerts.enabled = on
        alertsOn.value = on
        resetAlerts()
        if (on) scope.launch { try { pollAlerts() } catch (e: CancellationException) { throw e } catch (_: Throwable) { } }
    }

    /** Forget where everybody was (alerts were switched on, or the watch list changed), so the next look starts fresh. */
    fun resetAlerts() { seen = emptyMap() }

    private fun refreshList() { accountList.value = accounts.all() }

    /** Covers the app with the update page when this version has missed too many updates, and uncovers it when it has not (an update, a new policy). */
    fun enforcePolicy() {
        val st = try { activePolicy().status(BuildConfig.VERSION_NAME) } catch (_: Throwable) { null }
        updateRequired.value = if (st != null && st.blocked) st else null
    }

    private suspend fun restore() {
        refreshList()
        val id = accounts.activeId
        val cookie = id?.let { accounts.cookie(it) }
        if (cookie != null && updateRequired.value == null) try { signIn(cookie, save = false) } catch (_: Throwable) { }
        ready.value = true
    }

    /** Checks the cookie with Roblox, remembers who it belongs to, and makes it the active account. */
    suspend fun signIn(rawCookie: String, save: Boolean = true): Account {
        val cookie = cleanCookie(rawCookie)
        if (cookie.length < 40) throw RobloxException(401, "That does not look like a .ROBLOSECURITY cookie", local = true)
        client.invalidate()
        client.cookie = cookie
        val u = try { api.login() } catch (e: Exception) { client.signOut(); throw e }
        val acc = Account(u.long("id") ?: 0, u.str("name") ?: "", u.str("displayName") ?: u.str("name") ?: "")
        if (bans.banned(acc.id) != null) {                  // banned: not even shown as signed in
            current.value = acc
            enforce()
            throw RobloxException(403, "This account may not use Roblox Manager", local = true)
        }
        if (save) accounts.save(acc, cookie)
        current.value = acc
        refreshList()
        scope.launch { try { if (withContext(Dispatchers.IO) { bans.refresh() } == true) enforce() } catch (_: Throwable) { } }      // a fresh list at every sign-in
        return acc
    }

    /** Signs out and forgets every banned account, the one in use too (also in the middle of a session). */
    fun enforce() {
        val hit = accounts.all().filter { bans.banned(it.id) != null }.toMutableList()
        current.value?.let { c -> if (bans.banned(c.id) != null && hit.none { it.id == c.id }) hit += c }
        if (hit.isEmpty()) return
        val wasCurrent = current.value?.let { c -> hit.any { it.id == c.id } } == true
        hit.forEach { accounts.remove(it.id) }
        refreshList()
        banNotice.value = hit.joinToString("\n") { a -> "@${a.name}" + (bans.banned(a.id)?.takeIf { it.isNotEmpty() }?.let { ": $it" } ?: "") }
        if (wasCurrent) {
            client.signOut()                                // everything waiting or running for that account is dropped
            current.value = null
            accounts.activeId?.let { next -> scope.launch { try { switchTo(next) } catch (_: Exception) { } } }
        }
    }

    suspend fun switchTo(id: Long) {
        val cookie = accounts.cookie(id) ?: throw RobloxException(401, "This account's saved cookie cannot be read; sign in again", local = true)
        signIn(cookie, save = false)
        accounts.switchTo(id)
    }

    fun signOut(forget: Boolean) {
        val id = current.value?.id
        client.signOut()
        current.value = null
        if (forget && id != null) accounts.remove(id)
        val next = accounts.activeId
        refreshList()
        if (next != null) scope.launch { try { switchTo(next) } catch (_: Exception) { } }
    }
}

/** State of a batch of changes: what is happening, how far it is, and what failed. */
data class BulkState(val label: String = "", val done: Int = 0, val total: Int = 0, val running: Boolean = false, val failed: List<String> = emptyList(), val stopped: Boolean = false, val note: String = "") {
    val active get() = running || total > 0
}

/** Runs a change on many items one after another (the client spreads them to the rate limit); Stop ends it between two items. */
class Bulk(private val scope: CoroutineScope) {
    val state = MutableStateFlow(BulkState())
    private var job: Job? = null

    fun <T> run(label: String, items: List<T>, name: (T) -> String, action: suspend (T) -> Unit, each: (T) -> Unit = {}, finished: () -> Unit = {}) {
        if (state.value.running) return
        state.value = BulkState(label, 0, items.size, true)
        job = scope.launch {
            val failed = ArrayList<String>()
            var stopped = false
            try {
                for ((i, it) in items.withIndex()) {
                    state.value = state.value.copy(done = i, failed = failed.toList())
                    try {
                        action(it)
                        each(it)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: RobloxException) {
                        failed += "${name(it)}: ${e.message}"
                        if (e.status == 401) { failed += "Signed out: stopping."; break }
                    }
                }
            } catch (e: CancellationException) {
                stopped = true
            } finally {
                state.value = state.value.copy(done = if (stopped) state.value.done else items.size, running = false, stopped = stopped, failed = failed.toList())
                finished()
            }
        }
    }

    fun stop() { job?.cancel() }
    fun dismiss() { if (!state.value.running) state.value = BulkState() }
}
