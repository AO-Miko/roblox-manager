package app.robloxmanager.core

import android.util.Base64
import java.io.IOException
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Roblox refused the sign-in (wrong password, locked account, too many tries ...). The message is safe to show. */
class LoginError(message: String, val code: Int? = null, val status: Int? = null) : Exception(message)

/** Roblox asked for a check that cannot be done here (CAPTCHA, passkey ...): the browser sign-in handles every kind of check. */
class NeedBrowser(message: String) : Exception(message)

sealed class LoginStep
class Done(val cookie: String, val user: JsonObject?) : LoginStep()
class TwoStep(val userId: Long, val challengeId: String, val action: String, val methods: List<String>, val unsupported: List<String>, val primary: String) : LoginStep()

/**
 * Signing in with a username and password, including 2-step verification (authenticator app, email, text message, recovery code).
 * The password and codes go only to auth.roblox.com, twostepverification.roblox.com and apis.roblox.com over https. Nothing is logged
 * with a body, and the password is dropped from memory as soon as the attempt ends ([forget]).
 */
class PasswordLogin(
    private val http: OkHttpClient = RobloxClient.defaultHttp(),
    private val allowedHosts: Set<String> = setOf("auth.roblox.com", "twostepverification.roblox.com", "apis.roblox.com"),
    private val base64: (String) -> String? = { t -> try { String(Base64.decode(t, Base64.DEFAULT)) } catch (_: Exception) { null } },
    private val base64Encode: (ByteArray) -> String = { Base64.encodeToString(it, Base64.NO_WRAP) },
    private val log: RequestLog? = null,
    private val allowHttp: Boolean = false,
) {
    companion object {
        val METHODS = mapOf("Authenticator" to "authenticator", "Email" to "email", "SMS" to "sms", "RecoveryCode" to "recoverycode")
        val SENDS_A_CODE = setOf("Email", "SMS")
        val METHOD_TEXT = mapOf("Authenticator" to "Authenticator app", "Email" to "Email", "SMS" to "Text message", "RecoveryCode" to "Recovery code")
    }

    private class Reply(val status: Int, val json: JsonElement?, val headers: Map<String, String>, val cookie: String)

    private var csrf = ""
    private var loginBody: JsonObject? = null
    private var loginChallenge: Triple<String, String, JsonObject>? = null     // id, type, outer metadata
    var step: TwoStep? = null
        private set

    fun forget() { loginBody = null; loginChallenge = null; step = null }

    private suspend fun call(method: String, url: String, body: JsonObject? = null, headers: Map<String, String> = emptyMap()): Reply {
        val u = url.toHttpUrl()
        if ((u.scheme != "https" && !allowHttp) || (u.host !in allowedHosts && !allowHttp)) throw IllegalArgumentException("Refusing to send sign-in details to ${u.host}")
        for (attempt in 0..1) {
            val rb = Request.Builder().url(u).header("User-Agent", RobloxClient.USER_AGENT).header("Accept", "application/json")
            headers.forEach { (k, v) -> rb.header(k, v) }
            if (csrf.isNotEmpty()) rb.header("x-csrf-token", csrf)
            val payload = (body?.let { AppJson.encodeToString(JsonElement.serializer(), it) } ?: "").toRequestBody("application/json".toMediaType())
            rb.method(method, if (method == "GET") null else payload)
            val t0 = System.currentTimeMillis()
            val r = try {
                http.newCall(rb.build()).await()
            } catch (e: IOException) {
                throw LoginError("Could not reach Roblox (${e.javaClass.simpleName}). Check your connection.")
            }
            r.use {
                val text = it.body?.string() ?: ""
                val hs = it.headers.toMultimap().mapValues { e -> e.value.firstOrNull() ?: "" }
                val cookie = it.headers("Set-Cookie").firstOrNull { c -> c.startsWith(".ROBLOSECURITY=") }
                    ?.substringAfter("=")?.substringBefore(";").orEmpty().takeIf { c -> c.isNotEmpty() && c != "deleted" } ?: ""
                log?.record("signing in", method, url.substringBefore("?"), null, it.code, System.currentTimeMillis() - t0, attempt, false,
                    if (hs["rblx-challenge-id"] != null) "challenge" else "")
                val tok = hs["x-csrf-token"]
                if (tok != null) csrf = tok
                // the first write is always answered with a fresh token and a refusal: send it again with the token
                if (it.code == 403 && tok != null && attempt == 0 && hs["rblx-challenge-id"] == null) return@use null
                return Reply(it.code, if (text.isBlank()) null else try { AppJson.parseToJsonElement(text) } catch (_: Exception) { null }, hs, cookie)
            }
        }
        throw LoginError("Roblox did not accept the request.")
    }

    private fun errors(r: Reply): Pair<String, Int?> {
        val e0 = r.json.obj?.arr("errors")?.firstOrNull().obj
        return (e0?.str("userFacingMessage") ?: e0?.str("message") ?: "Roblox refused the request") to e0?.int("code")
    }

    suspend fun start(username: String, password: String): LoginStep {
        val name = username.trim()
        if (name.isEmpty() || password.isEmpty()) throw LoginError("Enter your username and password.")
        loginBody = obj("ctype" to if ("@" in name) "Email" else "Username", "cvalue" to name, "password" to password)
        try {
            return afterLogin(call("POST", "https://auth.roblox.com/v2/login", loginBody))
        } catch (e: Exception) {
            if (e is LoginError || e is NeedBrowser || e is CancellationException) forget()
            throw e
        }
    }

    private suspend fun afterLogin(r: Reply): LoginStep {
        if (r.status == 200) {
            if (r.cookie.isNotEmpty()) {
                val user = r.json.obj?.obj("user")
                forget()
                return Done(r.cookie, user)
            }
            throw NeedBrowser("Roblox asked for an extra check that this app does not handle (older two-step flow).")
        }
        val ctype = r.headers["rblx-challenge-type"]
        val cid = r.headers["rblx-challenge-id"]
        if (ctype != null && cid != null) {
            val meta = decodeMeta(r.headers["rblx-challenge-metadata"].orEmpty())
            if (ctype.equals("twostepverification", true) && meta.long("userId") != null && meta.str("challengeId") != null) {
                loginChallenge = Triple(cid, ctype, meta)
                return twoStep(meta).also { step = it }
            }
            throw NeedBrowser("Roblox asked for a '$ctype' check (for example a CAPTCHA), which has to be done in a browser.")
        }
        var (msg, code) = errors(r)
        if (r.status == 429) msg = "Roblox says too many sign-in attempts. Wait a few minutes before trying again."
        throw LoginError(msg, code, r.status)
    }

    private fun decodeMeta(t: String): JsonObject = try {
        AppJson.parseToJsonElement(base64(t) ?: "").obj ?: JsonObject(emptyMap())
    } catch (_: Exception) {
        JsonObject(emptyMap())
    }

    private suspend fun twoStep(meta: JsonObject): TwoStep {
        val uid = meta.long("userId")!!
        val chid = meta.str("challengeId")!!
        val action = meta.str("actionType") ?: "Login"
        val r = call("GET", "https://twostepverification.roblox.com/v1/users/$uid/configuration?challengeId=$chid&actionType=$action")
        if (r.status != 200) throw NeedBrowser("Roblox wants a 2-step check but would not say which methods you have.")
        val methods = r.json.obj?.arr("methods").orEmpty().mapNotNull { it.obj }.filter { it.bool("enabled") ?: true }.mapNotNull { it.str("mediaType") }
        val ok = methods.filter { it in METHODS }
        val bad = methods.filter { it !in METHODS }
        if (ok.isEmpty()) throw NeedBrowser("Your account uses " + (bad.joinToString(", ").ifEmpty { "a verification method" }) + ", which has to be done in a browser.")
        val primary = r.json.obj?.str("primaryMediaType")
        return TwoStep(uid, chid, action, ok, bad, if (primary in ok) primary!! else ok[0])
    }

    /** Ask Roblox to send the code by email or text message (authenticator and recovery codes need no sending). */
    suspend fun sendCode(method: String) {
        val t = step ?: return
        if (method !in SENDS_A_CODE) return
        val r = call("POST", "https://twostepverification.roblox.com/v1/users/${t.userId}/challenges/${METHODS[method]}/send-code",
            obj("challengeId" to t.challengeId, "actionType" to t.action))
        if (r.status != 200) { val (m, c) = errors(r); throw LoginError(m, c, r.status) }
    }

    /** Check the code and finish signing in. A wrong code throws [LoginError] and the same step can be tried again. */
    suspend fun verify(method: String, code: String, remember: Boolean = false): Done {
        val t = step
        val lc = loginChallenge
        if (t == null || lc == null || method !in METHODS) throw LoginError("Start the sign-in first.")
        val c = code.trim().replace(" ", "")
        if (c.isEmpty()) throw LoginError("Enter the code.")
        val r = call("POST", "https://twostepverification.roblox.com/v1/users/${t.userId}/challenges/${METHODS[method]}/verify",
            obj("challengeId" to t.challengeId, "actionType" to t.action, "code" to c))
        if (r.status != 200) {
            var (m, ec) = errors(r)
            if (r.status == 429) m = "Too many wrong codes. Wait a few minutes before trying again."
            throw LoginError(m, ec, r.status)
        }
        val token = (r.json.obj?.get("verificationToken") as? JsonPrimitive)?.content ?: throw NeedBrowser("Roblox accepted the code but did not finish the check here.")
        val meta = obj("rememberDevice" to remember, "actionType" to t.action, "verificationToken" to token, "challengeId" to t.challengeId)
        val metaText = AppJson.encodeToString(JsonElement.serializer(), meta)
        val cont = call("POST", "https://apis.roblox.com/challenge/v1/continue",
            obj("challengeId" to lc.first, "challengeType" to lc.second, "challengeMetadata" to metaText))
        if (cont.status != 200) { val (m, ec) = errors(cont); throw LoginError(m, ec, cont.status) }
        val headers = mapOf("rblx-challenge-id" to lc.first, "rblx-challenge-type" to lc.second,
            "rblx-challenge-metadata" to base64Encode(metaText.toByteArray()))
        val res = afterLogin(call("POST", "https://auth.roblox.com/v2/login", loginBody, headers))
        return res as? Done ?: throw NeedBrowser("Roblox asked for a second check after the code.")
    }
}
