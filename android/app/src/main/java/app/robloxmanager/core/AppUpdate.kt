package app.robloxmanager.core

import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request

/** What the update server (the git repository's dist/ folder) says is the newest build. */
data class UpdateInfo(val versionCode: Int, val versionName: String, val apk: String, val sha256: String, val notes: String)

class UpdateError(message: String) : Exception(message)

/**
 * The phone's side of the update server. The server is the git repository: its `dist/` folder holds `update.json` and the signed
 * release APK, and [baseUrl] is the raw address of that folder (for example https://raw.githubusercontent.com/USER/REPO/release/dist/).
 * An update is used only if its SHA-256 matches the manifest, and Android itself refuses to install it unless it is signed with the
 * same key as the installed app.
 */
class AppUpdate(private val baseUrl: String, private val http: OkHttpClient = RobloxClient.defaultHttp().newBuilder().followRedirects(true).followSslRedirects(true).build()) {
    companion object {
        const val MAX_APK = 80L * 1024 * 1024

        /** The beta channel is the `beta` branch of the same repository: .../release/dist/ becomes .../beta/dist/. Other addresses are left as they are. */
        fun betaUrl(stableUrl: String): String = stableUrl.replace("/release/dist", "/beta/dist")

        fun parse(text: String): UpdateInfo {
            val o = try { AppJson.parseToJsonElement(text).obj } catch (_: Exception) { null } ?: throw UpdateError("The update information is not valid")
            return fromJson(o)
        }

        fun fromJson(o: JsonObject): UpdateInfo {
            val code = o.int("versionCode") ?: throw UpdateError("The update information has no version")
            val apk = o.str("apk") ?: throw UpdateError("The update information has no file name")
            if ('/' in apk || '\\' in apk || ".." in apk || !apk.endsWith(".apk")) throw UpdateError("The update file name is not allowed")
            val sha = (o.str("sha256") ?: "").lowercase()
            if (!Regex("[0-9a-f]{64}").matches(sha)) throw UpdateError("The update information has no valid checksum")
            return UpdateInfo(code, o.str("versionName") ?: code.toString(), apk, sha, o.str("notes") ?: "")
        }

        fun sha256(f: File): String {
            val md = MessageDigest.getInstance("SHA-256")
            f.inputStream().use { s -> val buf = ByteArray(65536); while (true) { val n = s.read(buf); if (n < 0) break; md.update(buf, 0, n) } }
            return md.digest().joinToString("") { "%02x".format(it) }
        }
    }

    private fun base() = baseUrl.trim().let { if (it.endsWith("/")) it else "$it/" }

    private fun get(url: String): okhttp3.Response {
        if (!url.startsWith("https://")) throw UpdateError("The update address must start with https://")
        val r = try { Debug.execute(http, Request.Builder().url(url).header("User-Agent", RobloxClient.USER_AGENT).header("Cache-Control", "no-cache").build()) } catch (e: IOException) { throw UpdateError("Could not reach the update server (${e.javaClass.simpleName})") }
        if (!r.isSuccessful) { val c = r.code; r.close(); throw UpdateError(if (c == 404) "The update server has no update.json yet" else "The update server answered $c") }
        return r
    }

    /** The newest published build, or null when the installed one ([currentCode]) is already it. */
    fun check(currentCode: Int): UpdateInfo? {
        if (baseUrl.isBlank()) throw UpdateError("No update address is set")
        val info = get(base() + "update.json").use { parse(it.body?.string() ?: "") }
        return if (info.versionCode > currentCode) info else null
    }

    /** Downloads the APK into [dir] and verifies it. Returns the file; a file that fails the check is deleted. */
    fun download(info: UpdateInfo, dir: File, progress: (Long, Long) -> Unit = { _, _ -> }): File {
        dir.mkdirs()
        dir.listFiles()?.forEach { it.delete() }
        val out = File(dir, "update-${info.versionCode}.apk")
        get(base() + info.apk).use { r ->
            val body = r.body ?: throw UpdateError("Empty download")
            val total = body.contentLength()
            if (total > MAX_APK) throw UpdateError("The update file is too large")
            var done = 0L
            out.outputStream().use { o ->
                body.byteStream().use { s ->
                    val buf = ByteArray(65536)
                    while (true) {
                        val n = s.read(buf)
                        if (n < 0) break
                        done += n
                        if (done > MAX_APK) { out.delete(); throw UpdateError("The update file is too large") }
                        o.write(buf, 0, n)
                        progress(done, total)
                    }
                }
            }
        }
        if (sha256(out) != info.sha256) { out.delete(); throw UpdateError("The downloaded update does not match its checksum, so it was discarded") }
        return out
    }
}
