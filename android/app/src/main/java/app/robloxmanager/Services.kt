package app.robloxmanager

import android.app.Application
import android.content.Context
import java.io.File
import kotlin.coroutines.cancellation.CancellationException
import app.robloxmanager.core.Account
import app.robloxmanager.core.Accounts
import app.robloxmanager.core.KeystoreVault
import app.robloxmanager.core.NameCache
import app.robloxmanager.core.Prefs
import app.robloxmanager.core.RequestLog
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
import kotlinx.coroutines.launch

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
    val client = RobloxClient(log = log)
    val names = NameCache(File(dir, "names.json"))
    val api = RobloxApi(client, names)
    val accounts = Accounts(File(dir, "accounts.json"), KeystoreVault())
    val prefs = Prefs(File(dir, "prefs.json"))
    val cacheDir: File = app.cacheDir
    val filesDir: File = dir

    /** The signed-in account, or null (the sign-in screen is shown). */
    val current = MutableStateFlow<Account?>(null)
    val ready = MutableStateFlow(false)
    val accountList = MutableStateFlow<List<Account>>(emptyList())

    init {
        client.readBurst = prefs.double("readBurst", 0.5)
        log.writeFile = prefs.bool("logToFile", true)
        scope.launch { restore() }
    }

    private fun refreshList() { accountList.value = accounts.all() }

    private suspend fun restore() {
        refreshList()
        val id = accounts.activeId
        val cookie = id?.let { accounts.cookie(it) }
        if (cookie != null) try { signIn(cookie, save = false) } catch (_: Exception) { }
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
        if (save) accounts.save(acc, cookie)
        current.value = acc
        refreshList()
        return acc
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
