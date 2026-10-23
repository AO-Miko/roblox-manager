package app.robloxmanager.core

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** Encrypts and decrypts small secrets (the sign-in cookies). The real one keeps its key inside the Android Keystore. */
interface Vault {
    fun seal(plain: String): String
    fun open(sealed: String): String?
}

class KeystoreVault(private val alias: String = "roblox_manager_cookie_key") : Vault {
    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build(),
        )
        return g.generateKey()
    }

    override fun seal(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        val out = c.doFinal(plain.toByteArray())
        return Base64.encodeToString(c.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(out, Base64.NO_WRAP)
    }

    override fun open(sealed: String): String? = try {
        val (iv, data) = sealed.split(":")
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        String(c.doFinal(Base64.decode(data, Base64.NO_WRAP)))
    } catch (_: Exception) {
        null
    }
}

data class Account(val id: Long, val name: String, val displayName: String)

/**
 * The saved accounts. The list (ids and names, no secrets) is a plain json file; every cookie is stored sealed by the [Vault], so the
 * file alone is useless. Switching account only changes which cookie the client uses.
 */
class Accounts(private val file: File, private val vault: Vault) {
    private var accounts = ArrayList<Account>()
    private val sealed = HashMap<Long, String>()
    var activeId: Long? = null
        private set

    init {
        try {
            if (file.exists()) {
                val o = AppJson.parseToJsonElement(file.readText()).obj
                o?.arr("accounts")?.forEach { e ->
                    val a = e.obj ?: return@forEach
                    val id = a.long("id") ?: return@forEach
                    accounts += Account(id, a.str("name") ?: "", a.str("displayName") ?: "")
                    a.str("c")?.let { sealed[id] = it }
                }
                activeId = o?.long("active")
            }
        } catch (_: Exception) {
        }
    }

    fun all(): List<Account> = accounts.toList()
    fun active(): Account? = accounts.firstOrNull { it.id == activeId }
    fun cookie(id: Long): String? = sealed[id]?.let { vault.open(it) }

    fun save(account: Account, cookie: String, makeActive: Boolean = true) {
        accounts.removeAll { it.id == account.id }
        accounts += account
        sealed[account.id] = vault.seal(cookie)
        if (makeActive) activeId = account.id
        persist()
    }

    fun switchTo(id: Long): Boolean {
        if (accounts.none { it.id == id }) return false
        activeId = id
        persist()
        return true
    }

    fun remove(id: Long) {
        accounts.removeAll { it.id == id }
        sealed.remove(id)
        if (activeId == id) activeId = accounts.firstOrNull()?.id
        persist()
    }

    private fun persist() {
        val arr = accounts.map { a -> obj("id" to a.id, "name" to a.name, "displayName" to a.displayName, "c" to sealed[a.id]) }
        val o = obj("accounts" to arr, "active" to activeId)
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        tmp.writeText(AppJson.encodeToString(JsonElement.serializer(), o))
        tmp.renameTo(file)
    }
}

/** Cleans a pasted cookie: removes quotes, spaces and the ".ROBLOSECURITY=" prefix. */
fun cleanCookie(text: String): String {
    var t = text.trim().trim('"', '\'')
    if (t.startsWith(".ROBLOSECURITY=")) t = t.substringAfter("=")
    return t.substringBefore(";").trim()
}

/** Small user settings. */
class Prefs(private val file: File) {
    private var data: JsonObject = try { if (file.exists()) AppJson.parseToJsonElement(file.readText()).obj ?: JsonObject(emptyMap()) else JsonObject(emptyMap()) } catch (_: Exception) { JsonObject(emptyMap()) }

    fun double(key: String, def: Double) = (data[key] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull() ?: def
    fun bool(key: String, def: Boolean) = data.bool(key) ?: def
    fun str(key: String, def: String) = data.str(key) ?: def
    fun raw(key: String): JsonElement? = data[key]

    fun put(key: String, value: Any) {
        Debug.event("settings", "$key = ${value.toString().take(120)}", "debug")
        data = JsonObject(data + (key to value.toJson()))
        file.parentFile?.mkdirs()
        file.writeText(AppJson.encodeToString(JsonElement.serializer(), data))
    }
}
