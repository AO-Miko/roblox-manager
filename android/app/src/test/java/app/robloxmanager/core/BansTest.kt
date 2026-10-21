package app.robloxmanager.core

import java.io.File
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BansTest {
    private fun res(name: String) = File("src/test/resources/bans/$name")
    private val data get() = res("bans.json").readBytes()
    private val sig get() = res("bans.json.sig").readText()
    private val key get() = SshSig.keyOf(res("pub.txt").readText())

    private fun hex(s: String) = s.chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    @Test fun rfc8032Vectors() {
        val pub2 = hex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
        val sig2 = hex("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
        assertTrue(Ed25519.verify(hex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"), ByteArray(0),
            hex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")))
        assertTrue(Ed25519.verify(pub2, hex("72"), sig2))
        assertFalse(Ed25519.verify(pub2, hex("73"), sig2))
        assertFalse(Ed25519.verify(ByteArray(3), ByteArray(1), ByteArray(5)))
    }

    @Test fun readsASignedList() {
        val l = BanStore.parse(data, sig, key)
        assertNotNull(l)
        assertEquals(5L, l!!.serial)
        assertEquals("spamming", l.bans[111])
        assertEquals("", l.bans[222])
    }

    @Test fun refusesWrongKeyChangesAndOtherNamespaces() {
        assertNull(BanStore.parse(data, sig, ByteArray(32)))
        assertNull(BanStore.parse(String(data).replace("111", "999").toByteArray(), sig, key))
        assertFalse(SshSig.verify(data, sig, key, "roblox-manager-release"))
        assertNull(BanStore.parse(data, "nonsense", key))
    }

    @Test fun downloadsCachesAndNeverGoesBack() {
        val server = MockWebServer()
        val cache = File.createTempFile("bans", ".json").also { it.delete() }
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        val store = BanStore(cache, key, http, "https://x.test/")
        assertNull(store.banned(111))
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(store.refresh())                                  // not reachable: nothing changes, nobody is locked out
        server.enqueue(MockResponse().setBody(String(data)))
        server.enqueue(MockResponse().setBody(sig))
        assertEquals(true, store.refresh())
        assertEquals("spamming", store.banned(111))
        assertEquals("", store.banned(222))
        assertNull(store.banned(333))
        assertEquals("spamming", BanStore(cache, key, http, "https://x.test/").banned(111))     // kept on the phone
        server.enqueue(MockResponse().setBody(String(data)))
        server.enqueue(MockResponse().setBody(sig))
        assertEquals(false, store.refresh())                         // the same list: no change
        cache.writeText(cache.readText().replace("\"data\":\"", "\"data\":\"AAAA"))               // a file edited on the phone is not believed
        assertEquals(0L, BanStore(cache, key, http, "https://x.test/").load().serial)
        server.shutdown()
        cache.delete()
    }
}
