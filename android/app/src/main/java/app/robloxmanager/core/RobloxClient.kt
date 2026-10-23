package app.robloxmanager.core

import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.coroutines.cancellation.CancellationException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.json.JsonElement
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

data class RobloxResponse(val status: Int, val json: JsonElement?, val headers: Map<String, String>)

/** Told to the screens: the app waits (proactive) or Roblox refused (not proactive). */
data class RateNotice(val path: String, val waitSeconds: Double, val gaveUp: Boolean, val proactive: Boolean)

/**
 * Sends requests to Roblox. It carries the sign-in cookie only to roblox.com, handles the csrf token, and follows the rate limits
 * Roblox reports (see [RateTable]): changes are spread evenly, reads may use part of a route's limit at once, a route with a hidden limit
 * gets a gap, and a change that is still refused cools down and tries again. Every request is written to the [RequestLog].
 */
class RobloxClient(
    private val http: OkHttpClient = defaultHttp(),
    private val now: () -> Long = { System.currentTimeMillis() },
    val rates: RateTable = RateTable(now),
    val log: RequestLog = RequestLog(),
    private val sleep: suspend (Long) -> Unit = { delay(it) },
    private val isRobloxHost: (String) -> Boolean = ::isRoblox,
    private val allowHttp: Boolean = false,            // tests only: the fake server speaks plain http
) {
    companion object {
        const val USER_AGENT = "Mozilla/5.0 (Linux; Android 14) RobloxManager/1.0"
        fun isRoblox(host: String) = host == "roblox.com" || host.endsWith(".roblox.com")
        fun defaultHttp(): OkHttpClient = OkHttpClient.Builder()
            .followRedirects(false).followSslRedirects(false)
            .connectTimeout(15, TimeUnit.SECONDS).readTimeout(25, TimeUnit.SECONDS).callTimeout(40, TimeUnit.SECONDS).build()

        /** POST requests that only read: not "changes", so not held to the slow pace. */
        val READ_POSTS = setOf(
            "users.roblox.com/v1/users", "users.roblox.com/v1/usernames/users", "presence.roblox.com/v1/presence/users",
            "presence.roblox.com/v1/presence/last-online", "friends.roblox.com/v1/user/following-exists",
            "apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles",
        )
        private val VIP_DETAIL = Regex("/v1/vip-servers/\\d+$")
    }

    // ---- tunables (the Settings screen changes readBurst)
    @Volatile var readBurst = 0.5
    var slowGapBaseMs = 2875L
    var slowGapMaxMs = 10_000L
    var cooldownMs = 45_000L
    var patience = 2
    var maxWaitReadMs = 20_000L
    var maxWaitChangeMs = 150_000L
    var minWaitMs = 10_000L
    var minGapMs = 120L

    @Volatile var cookie: String = ""
    @Volatile var user: JsonElement? = null
    @Volatile private var csrf = ""
    private val epoch = AtomicInteger(0)
    private val paceLock = Any()
    private var slowNext = 0L
    private var slowGap = slowGapBaseMs
    private var lastSent = 0L

    private val _notices = MutableSharedFlow<RateNotice>(extraBufferCapacity = 32)
    val notices: SharedFlow<RateNotice> = _notices

    val userId: Long? get() = user.obj?.long("id")
    private fun who() = user.obj?.str("name") ?: if (cookie.isNotEmpty()) "signing in" else "anonymous"

    /** The account is about to change: everything waiting or in flight for the old one is dropped, and pacing starts over. */
    fun invalidate() {
        epoch.incrementAndGet()
        rates.clear()
        synchronized(paceLock) { slowNext = 0; slowGap = slowGapBaseMs }
        csrf = ""
    }

    fun signOut() {
        invalidate()
        cookie = ""
        user = null
    }

    // ---- what kind of request is it
    private fun isRead(method: String, url: String): Boolean {
        if (method == "GET") return true
        val u = java.net.URI(url)
        return "${u.host}${u.path}" in READ_POSTS
    }

    private fun isSlow(method: String, url: String): Boolean =
        !isRead(method, url) || VIP_DETAIL.containsMatchIn(java.net.URI(url).path)

    // ---- pacing
    private suspend fun slowPace(ep: Int) {
        val wait: Long
        synchronized(paceLock) {
            val t = now()
            val slot = maxOf(t, slowNext)
            slowNext = slot + slowGap
            wait = slot - t
        }
        if (wait > 0) nap(wait, ep)
    }

    private fun slowBackoff(waitMs: Long) {
        synchronized(paceLock) {
            slowGap = minOf(slowGapMaxMs, (slowGap * 1.5).toLong())
            slowNext = maxOf(slowNext, now() + minOf(waitMs, 30_000) + slowGap)
        }
    }

    private suspend fun minGapPace(ep: Int) {
        val wait: Long
        synchronized(paceLock) {
            val t = now()
            wait = maxOf(0, lastSent + minGapMs - t)
            lastSent = t + wait
        }
        if (wait > 0) nap(wait, ep)
    }

    private fun check(ep: Int) {
        if (epoch.get() != ep) throw StaleAccount()
    }

    /** A sleep that notices when the account changes. */
    private suspend fun nap(ms: Long, ep: Int) {
        var left = ms
        while (left > 0) {
            check(ep)
            val slice = minOf(left, 500)
            sleep(slice)
            left -= slice
        }
        check(ep)
    }

    private fun notice(url: String, waitMs: Long, gaveUp: Boolean, proactive: Boolean = false) {
        _notices.tryEmit(RateNotice(java.net.URI(url).path, waitMs / 1000.0, gaveUp, proactive))
    }

    // ---- the request
    suspend fun request(
        method: String, url: String, params: Map<String, String>? = null, body: JsonElement? = null, auth: Boolean = true, retries: Int = 3,
    ): RobloxResponse {
        val m = method.uppercase()
        val patience = if (isRead(m, url)) 0 else this.patience
        var round = 0
        while (true) {
            try {
                return requestOnce(m, url, params, body, auth, retries)
            } catch (e: CancellationException) {
                log.record(who(), m, url, params, null, null, 0, false, "cancelled (stopped, closed or account changed)")
                throw e
            } catch (e: RobloxException) {
                if (e.status != 429 || round >= patience || e.local) throw e
                // A change that is still refused after its quick retries waits out a cool-down and tries again, so a long batch
                // survives a rate limit instead of stopping at the first refusal.
                val wait = cooldownMs * (round + 1)
                notice(url, wait, false)
                slowBackoff(wait)
                log.record(who(), m, url, params, null, null, 0, false, "cool-down: waiting ${wait / 1000} s after repeated 429")
                nap(wait, epoch.get())
                round++
            }
        }
    }

    suspend fun get(url: String, params: Map<String, String>? = null, auth: Boolean = true, retries: Int = 3) = request("GET", url, params, null, auth, retries)
    suspend fun post(url: String, body: JsonElement? = null, retries: Int = 3) = request("POST", url, null, body, true, retries)
    suspend fun patch(url: String, body: JsonElement? = null) = request("PATCH", url, null, body, true, 3)
    suspend fun delete(url: String, body: JsonElement? = null) = request("DELETE", url, null, body, true, 3)

    private suspend fun requestOnce(
        m: String, url: String, params: Map<String, String>?, body: JsonElement?, auth: Boolean, retries: Int,
    ): RobloxResponse {
        require(url.startsWith("https://") || (allowHttp && url.startsWith("http://"))) { "Only https:// addresses are allowed" }
        val ep = epoch.get()
        val read = isRead(m, url)
        val slow = isSlow(m, url)
        val key = RateTable.key(m, url)
        var refreshedCsrf = false
        var attempt = 0
        while (true) {
            check(ep)
            if (rates.known(key)) {
                rates.gate(key, { nap(it, ep) }, if (read) maxWaitReadMs else maxWaitChangeMs, { notice(url, it, false, true) }, if (read) readBurst else 0.0)
            } else if (slow) {
                slowPace(ep)
            }
            check(ep)
            minGapPace(ep)
            val t0 = now()
            val call = http.newCall(build(m, url, params, body, auth))
            val status: Int
            val headers: Map<String, String>
            val text: String
            try {
                call.await().use { r ->
                    status = r.code
                    headers = r.headers.toMultimap().mapValues { it.value.firstOrNull() ?: "" }
                    text = r.body?.string() ?: ""
                }
            } catch (e: IOException) {
                log.record(who(), m, url, params, null, now() - t0, attempt, slow, "network error: ${e.javaClass.simpleName}")
                if (attempt < retries) {
                    nap(1500L * (attempt + 1), ep)
                    attempt++
                    continue
                }
                throw RobloxException(0, "Network error: ${e.javaClass.simpleName}")
            }
            var note = ""
            if (status == 429) note = "retry-after ${headers["retry-after"] ?: "?"}"
            else if (status == 403 && headers["x-csrf-token"] != null && m != "GET") note = "csrf token refresh"
            val rate = rates.learn(key, headers, status, attempt, minWaitMs)
            log.record(who(), m, url, params, status, now() - t0, attempt, slow, note, rate, sent = body, answer = text, contentType = headers["content-type"])
            check(ep)                                        // the account changed while this was in flight: its answer is not used
            val tok = headers["x-csrf-token"]
            if (tok != null && m != "GET") csrf = tok
            if (status == 403 && tok != null && !refreshedCsrf && m != "GET") {
                refreshedCsrf = true                         // Roblox hands out the token on the first rejected write: just retry
                continue
            }
            if (slow && status == 429) slowBackoff(((headers["retry-after"]?.toDoubleOrNull() ?: 5.0) * 1000).toLong())
            else if (slow && status < 400) synchronized(paceLock) { slowGap = maxOf(slowGapBaseMs, (slowGap * 0.95).toLong()) }
            if (status == 429 && attempt < retries) {
                val known = rates.known(key)
                val wait = if (known) maxOf(1000, rates.waitLeftMs(key)) else ((headers["retry-after"]?.toDoubleOrNull() ?: Math.pow(2.0, attempt + 1.0)) * 1000).toLong()
                notice(url, minOf(wait, 60_000), false)
                if (!known) nap(minOf(wait, 30_000), ep)   // (with route data, the gate at the top of the loop waits it out)
                attempt++
                continue
            }
            if (status == 429) notice(url, 0, true)
            if (status >= 500 && attempt < retries) {
                nap(1500L * (attempt + 1), ep)
                attempt++
                continue
            }
            val json: JsonElement? = if (text.isBlank()) null else try { AppJson.parseToJsonElement(text) } catch (_: Exception) { null }
            if (status >= 400) {
                var msg = ""
                var code: Int? = null
                val e0 = json.obj?.arr("errors")?.firstOrNull().obj
                if (e0 != null) {
                    msg = e0.str("userFacingMessage") ?: e0.str("message") ?: ""
                    code = e0.int("code")
                }
                throw RobloxException(status, Redact.text(msg.ifEmpty { "request failed" }), code)
            }
            return RobloxResponse(status, json, headers)
        }
    }

    private fun build(m: String, url: String, params: Map<String, String>?, body: JsonElement?, auth: Boolean): Request {
        val b = url.toHttpUrl().newBuilder()
        params?.forEach { (k, v) -> b.addQueryParameter(k, v) }
        val httpUrl = b.build()
        val rb = Request.Builder().url(httpUrl).header("User-Agent", USER_AGENT).header("Accept", "application/json")
        if (auth && cookie.isNotEmpty() && isRobloxHost(httpUrl.host)) {
            rb.header("Cookie", ".ROBLOSECURITY=$cookie")
            if (m != "GET" && csrf.isNotEmpty()) rb.header("X-CSRF-TOKEN", csrf)
        }
        val payload = if (body != null) AppJson.encodeToString(JsonElement.serializer(), body).toRequestBody("application/json".toMediaType())
        else ByteArray(0).toRequestBody("application/json".toMediaType())
        when (m) {
            "GET" -> rb.get()
            "DELETE" -> if (body != null) rb.delete(payload) else rb.delete()
            else -> rb.method(m, payload)
        }
        return rb.build()
    }
}

/** Suspends until the call is answered; cancelling the coroutine cancels the call. */
suspend fun Call.await(): okhttp3.Response = suspendCancellableCoroutine { cont: CancellableContinuation<okhttp3.Response> ->
    cont.invokeOnCancellation { try { cancel() } catch (_: Throwable) { } }
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: okhttp3.Response) = cont.resume(response)
        override fun onFailure(call: Call, e: IOException) { if (!cont.isCancelled) cont.resumeWithException(e) }
    })
}
