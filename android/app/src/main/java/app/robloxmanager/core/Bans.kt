package app.robloxmanager.core

import java.io.File
import java.math.BigInteger
import java.security.MessageDigest
import java.util.Base64
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

/** Ed25519 signature checking (RFC 8032), verification only: enough to check the signed ban list without an extra library. */
object Ed25519 {
    private val TWO = BigInteger.valueOf(2)          // (BigInteger.TWO needs Android 13)
    private val P = TWO.pow(255) - BigInteger.valueOf(19)
    private val Q = TWO.pow(252) + BigInteger("27742317777372353535851937790883648493")
    private fun inv(x: BigInteger) = x.modPow(P - TWO, P)
    private val D = (BigInteger.valueOf(-121665) * inv(BigInteger.valueOf(121666))).mod(P)
    private val I = TWO.modPow((P - BigInteger.ONE) / BigInteger.valueOf(4), P)

    private fun recoverX(y: BigInteger, sign: Int): BigInteger? {
        if (y >= P) return null
        val x2 = ((y * y - BigInteger.ONE) * inv(D * y * y + BigInteger.ONE)).mod(P)
        if (x2.signum() == 0) return if (sign == 1) null else BigInteger.ZERO
        var x = x2.modPow((P + BigInteger.valueOf(3)) / BigInteger.valueOf(8), P)
        if ((x * x - x2).mod(P).signum() != 0) x = (x * I).mod(P)
        if ((x * x - x2).mod(P).signum() != 0) return null
        if ((if (x.testBit(0)) 1 else 0) != sign) x = P - x
        return x
    }

    private fun add(a: Array<BigInteger>, b: Array<BigInteger>): Array<BigInteger> {
        val aa = ((a[1] - a[0]) * (b[1] - b[0])).mod(P)
        val bb = ((a[1] + a[0]) * (b[1] + b[0])).mod(P)
        val c = (TWO * a[3] * b[3] * D).mod(P)
        val d = (TWO * a[2] * b[2]).mod(P)
        val e = bb - aa; val f = d - c; val g = d + c; val h = bb + aa
        return arrayOf((e * f).mod(P), (g * h).mod(P), (f * g).mod(P), (e * h).mod(P))
    }

    private fun mul(s0: BigInteger, p0: Array<BigInteger>): Array<BigInteger> {
        var s = s0
        var pt = p0
        var q = arrayOf(BigInteger.ZERO, BigInteger.ONE, BigInteger.ONE, BigInteger.ZERO)
        while (s.signum() > 0) {
            if (s.testBit(0)) q = add(q, pt)
            pt = add(pt, pt)
            s = s.shiftRight(1)
        }
        return q
    }

    private fun same(a: Array<BigInteger>, b: Array<BigInteger>) =
        (a[0] * b[2] - b[0] * a[2]).mod(P).signum() == 0 && (a[1] * b[2] - b[1] * a[2]).mod(P).signum() == 0

    private fun le(b: ByteArray) = BigInteger(1, b.reversedArray())

    private fun decompress(s: ByteArray): Array<BigInteger>? {
        if (s.size != 32) return null
        var y = le(s)
        val sign = if (y.testBit(255)) 1 else 0
        y = y.clearBit(255)
        val x = recoverX(y, sign) ?: return null
        return arrayOf(x, y, BigInteger.ONE, (x * y).mod(P))
    }

    private val G: Array<BigInteger> by lazy {
        val gy = (BigInteger.valueOf(4) * inv(BigInteger.valueOf(5))).mod(P)
        val gx = recoverX(gy, 0)!!
        arrayOf(gx, gy, BigInteger.ONE, (gx * gy).mod(P))
    }

    fun verify(publicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean {
        if (publicKey.size != 32 || signature.size != 64) return false
        val a = decompress(publicKey) ?: return false
        val r = decompress(signature.copyOfRange(0, 32)) ?: return false
        val s = le(signature.copyOfRange(32, 64))
        if (s >= Q) return false
        val h = le(MessageDigest.getInstance("SHA-512").digest(signature.copyOfRange(0, 32) + publicKey + message)).mod(Q)
        return same(mul(s, G), add(r, mul(h, a)))
    }
}

/** What an OpenSSH file signature (`ssh-keygen -Y sign`) says, checked for Ed25519 keys. */
object SshSig {
    private class Reader(val d: ByteArray) {
        var i = 0
        fun take(n: Int): ByteArray { require(n >= 0 && i + n <= d.size); return d.copyOfRange(i, i + n).also { i += n } }
        fun u32(): Int { val b = take(4); return ((b[0].toInt() and 255) shl 24) or ((b[1].toInt() and 255) shl 16) or ((b[2].toInt() and 255) shl 8) or (b[3].toInt() and 255) }
        fun string(): ByteArray = take(u32())
    }

    private fun str(b: ByteArray) = byteArrayOf((b.size ushr 24).toByte(), (b.size ushr 16).toByte(), (b.size ushr 8).toByte(), b.size.toByte()) + b

    /** The raw 32 byte key of an "ssh-ed25519 AAAA..." line (or just its base64 part). */
    fun keyOf(authorizedKey: String): ByteArray {
        val b64 = authorizedKey.trim().split(Regex("\\s+")).let { if (it.size >= 2 && it[0] == "ssh-ed25519") it[1] else it[0] }
        val r = Reader(Base64.getDecoder().decode(b64))
        require(String(r.string()) == "ssh-ed25519")
        return r.string()
    }

    /** True if `armored` is a valid signature of `message` for `namespace` made by `trusted` (a raw 32 byte key). */
    fun verify(message: ByteArray, armored: String, trusted: ByteArray, namespace: String): Boolean = try {
        val lines = armored.trim().lines().map { it.trim() }
        if (lines.first() != "-----BEGIN SSH SIGNATURE-----" || lines.last() != "-----END SSH SIGNATURE-----") false
        else {
            val r = Reader(Base64.getDecoder().decode(lines.drop(1).dropLast(1).joinToString("")))
            if (!r.take(6).contentEquals("SSHSIG".toByteArray()) || r.u32() != 1) false
            else {
                val pub = r.string(); val ns = String(r.string()); r.string(); val hashAlg = String(r.string()); val sig = r.string()
                val digest = when (hashAlg) { "sha512" -> "SHA-512"; "sha256" -> "SHA-256"; else -> null }
                val pr = Reader(pub)
                val sr = Reader(sig)
                if (ns != namespace || digest == null || String(pr.string()) != "ssh-ed25519" || String(sr.string()) != "ssh-ed25519") false
                else {
                    val key = pr.string()
                    val raw = sr.string()
                    val signed = "SSHSIG".toByteArray() + str(namespace.toByteArray()) + str(ByteArray(0)) + str(hashAlg.toByteArray()) +
                        str(MessageDigest.getInstance(digest).digest(message))
                    key.contentEquals(trusted) && Ed25519.verify(key, signed, raw)
                }
            }
        }
    } catch (_: Throwable) {
        false
    }
}

/** Roblox user ids that may not use the app, as published (signed) by the maintainer. */
class BanList(val serial: Long, val bans: Map<Long, String>)

/**
 * The ban list: dist/bans.json + dist/bans.json.sig of the update repository, signed with the release key (built in below).
 * It is only believed if the signature is valid; a newer list (higher serial) replaces an older one and an older one is never taken again; the last good
 * list is kept on the phone and applies offline; if the list cannot be fetched, nobody is locked out. Nothing about the user is sent.
 */
class BanStore(
    private val file: File,
    private val trusted: ByteArray = RELEASE_KEY,
    private val http: OkHttpClient = RobloxClient.defaultHttp().newBuilder().followRedirects(true).followSslRedirects(true).build(),
    private val baseUrl: String = BASE_URL,
) {
    companion object {
        const val BASE_URL = "https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/"
        const val NAMESPACE = "roblox-manager-bans"
        const val REFRESH_MS = 600_000L
        const val MAX_BYTES = 300_000L
        val RELEASE_KEY: ByteArray = SshSig.keyOf("AAAAC3NzaC1lZDI1NTE5AAAAIOIrL6gArNibpgZ32RNQts1DOPQlWn6y0pvEDlGPzQmG")

        fun parse(data: ByteArray, sig: String, trusted: ByteArray = RELEASE_KEY): BanList? {
            if (!SshSig.verify(data, sig, trusted, NAMESPACE)) return null
            val d = try { AppJson.parseToJsonElement(String(data, Charsets.UTF_8)).obj } catch (_: Exception) { null } ?: return null
            val serial = d.long("serial") ?: return null
            val map = HashMap<Long, String>()
            (d["bans"] as? JsonArray)?.forEach { e -> val o = e.obj ?: return@forEach; val id = o.long("id") ?: return@forEach; map[id] = (o.str("reason") ?: "").take(200) }
            return BanList(serial, map)
        }
    }

    @Volatile private var cached: BanList? = null

    /** The last good list from disk, checked again (so a file edited on the phone is not believed). */
    fun load(): BanList {
        cached?.let { return it }
        val list = try {
            val o = AppJson.parseToJsonElement(file.readText()).obj
            parse(Base64.getDecoder().decode(o?.str("data") ?: ""), o?.str("sig") ?: "", trusted)
        } catch (_: Throwable) { null }
        return (list ?: BanList(0, emptyMap())).also { cached = it }
    }

    /** The reason (possibly empty) if this user id is banned, otherwise null. */
    fun banned(userId: Long): String? = try { load().bans[userId] } catch (_: Throwable) { null }

    private fun get(url: String, limit: Long): ByteArray {
        require(url.startsWith("https://"))
        http.newCall(Request.Builder().url(url).header("User-Agent", RobloxClient.USER_AGENT).header("Cache-Control", "no-cache").build()).execute().use { r ->
            if (!r.isSuccessful) error("HTTP ${r.code}")
            val b = r.body?.bytes() ?: error("empty")
            if (b.size > limit) error("too large")
            return b
        }
    }

    /** Downloads the list and keeps it if it is signed and not older. true = changed, false = no change, null = could not fetch or refused. Blocking. */
    fun refresh(): Boolean? {
        val data: ByteArray
        val sig: String
        try {
            data = get(baseUrl + "bans.json", MAX_BYTES)
            sig = String(get(baseUrl + "bans.json.sig", 20_000), Charsets.UTF_8)
        } catch (_: Exception) {
            return null
        }
        val got = try { parse(data, sig, trusted) } catch (_: Throwable) { null } ?: return null
        val have = load()
        if (got.serial < have.serial || (got.serial == have.serial && got.bans == have.bans)) return false
        try {
            file.parentFile?.mkdirs()
            val tmp = File(file.path + ".tmp")
            tmp.writeText(AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), obj("data" to Base64.getEncoder().encodeToString(data), "sig" to sig)))
            tmp.renameTo(file)
        } catch (_: Exception) {
            return null
        }
        cached = got
        return true
    }
}
