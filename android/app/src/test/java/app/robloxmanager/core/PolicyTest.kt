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

class PolicyTest {
    private fun res(name: String) = File("src/test/resources/policy/$name")
    private val data get() = res("policy.json").readBytes()
    private val sig get() = res("policy.json.sig").readText()
    private val key get() = SshSig.keyOf(res("pub.txt").readText())

    private fun store(): Pair<PolicyStore, MockWebServer> {
        val server = MockWebServer()
        val cache = File.createTempFile("policy", ".json").also { it.delete() }
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        return PolicyStore(cache, key, http, "https://x.test/") to server
    }

    private fun serve(server: MockWebServer, body: String = String(data), s: String = sig) {
        server.enqueue(MockResponse().setBody(body))
        server.enqueue(MockResponse().setBody(s))
    }

    @Test fun versionsCompareNumberByNumber() {
        assertEquals(listOf(1, 7, 0, 0, 0), Versions.key("1.7.0"))
        assertEquals(0, Versions.compare("1.9.0.0", "1.9.0.0.0"))
        assertTrue(Versions.compare("1.10.0.0.0", "1.9.0.0.0") > 0)
        assertTrue(Versions.compare("1.9.0.1.0", "1.9.0.0.9") > 0)
        assertTrue(Versions.compare("2.0.0.0.0", "1.99.99.99.99") > 0)
        assertTrue(Versions.valid("1.9.0.0.0") && Versions.valid("1.7.0") && !Versions.valid("1") && !Versions.valid("a.b.c") && !Versions.valid("1.2.3.4.5.6"))
    }

    @Test fun readsASignedPolicyAndRefusesTheRest() {
        val p = PolicyStore.parse(data, sig, key)
        assertNotNull(p)
        assertEquals(3L, p!!.serial)
        assertEquals(2, p.limit)
        assertEquals(listOf("1.8.0.0.0", "1.9.0.0.0", "1.9.0.0"), p.stable)
        assertNull(PolicyStore.parse(data, sig, ByteArray(32)))
        assertNull(PolicyStore.parse(String(data).replace("1.8.0.0.0", "1.0.0.0.0").toByteArray(), sig, key))
        assertNull(PolicyStore.parse(data, "nonsense", key))
        assertFalse(SshSig.verify(data, sig, key, BanStore.NAMESPACE))            // signed for the policy, not for bans
    }

    @Test fun twoUpdatesBehindIsBlockedOneIsNot() {
        val (s, server) = store()
        serve(server)
        assertEquals(true, s.refresh())
        val old = s.status("1.7.0")
        assertTrue(old.blocked); assertEquals(2, old.behind); assertEquals("1.9.0.0.0".let { Versions.key(it) }, Versions.key(old.latest))
        val one = s.status("1.8.0.0.0")
        assertFalse(one.blocked); assertEquals(1, one.behind)
        assertEquals(0, s.status("1.9.0.0.0").behind)                  // on the newest (1.9.0.0 and 1.9.0.0.0 count once)
        assertEquals(0, s.status("1.9.0.0").behind)
        assertFalse(s.status("1.9.1.1.1").blocked)                      // a beta newer than every stable version is never behind
        assertTrue(s.status("1.0.0").blocked)
        server.shutdown()
    }

    @Test fun theBetaChannelCountsEveryReleaseAndTheStableChannelItsOwn() {
        val dir = File("src/test/resources/policy-beta")
        val bdata = File(dir, "policy.json").readBytes(); val bsig = File(dir, "policy.json.sig").readText(); val bkey = SshSig.keyOf(File(dir, "pub.txt").readText())
        val p = PolicyStore.parse(bdata, bsig, bkey)!!
        assertEquals(listOf("1.8.0.0.0", "1.9.0.0.0"), p.stable); assertEquals(5, p.beta!!.size)
        assertNull(PolicyStore.parse(String(bdata).replace("1.9.3.0.0", "x").toByteArray(), bsig, bkey))                    // a tampered list is refused
        assertNull(PolicyStore.parse(res("policy.json").readBytes(), sig, key)!!.beta)                                          // an old policy has no beta list
        assertTrue(PolicyStore.BETA_BASE_URL.endsWith("/beta/dist/") && PolicyStore.BETA_BASE_URL.replace("/beta/", "/release/") == BanStore.BASE_URL)
        for ((beta, want) in listOf(true to listOf(3, true), false to listOf(0, false))) {
            val server = MockWebServer()
            val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
                val r = c.request()
                c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
            }.build()
            val s = PolicyStore(File.createTempFile("policy", ".json").also { it.delete() }, bkey, http, "https://x.test/", useBeta = beta)
            serve(server, String(bdata), bsig)
            assertEquals(true, s.refresh())
            val st = s.status("1.9.0.0.0")
            assertEquals("beta=$beta", want[0], st.behind); assertEquals(want[1], st.blocked)
            if (beta) {
                assertEquals("1.9.3.0.0", st.latest); assertFalse(s.status("1.9.2.0.0").blocked); assertEquals(1, s.status("1.9.2.0.0").behind)
                assertTrue(s.status("1.9.1.0.0").blocked); assertEquals(0, s.status("1.9.3.0.0").behind); assertEquals(0, s.status("1.9.9.0.0").behind)
            }
            server.shutdown()
        }
        val (old, server) = store()                                   // a beta store that gets a policy without a beta list counts the stable one
        val s = PolicyStore(File.createTempFile("policy", ".json").also { it.delete() }, key, okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request(); c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build(), "https://x.test/", useBeta = true)
        serve(server); assertEquals(true, s.refresh())
        assertTrue(s.status("1.7.0").blocked); assertFalse(s.status("1.9.0.0.0").blocked)
        server.shutdown()
    }

    @Test fun nothingDownloadedMeansNobodyIsLockedOut() {
        val (s, server) = store()
        assertFalse(s.status("1.0.0").blocked)
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(s.refresh())
        assertFalse(s.status("1.0.0").blocked)
        server.shutdown()
    }

    @Test fun cachesAndNeverGoesBackOrAcceptsATamperedFile() {
        val (s, server) = store()
        serve(server)
        assertEquals(true, s.refresh())
        serve(server)
        assertEquals(false, s.refresh())                                 // the same policy again
        serve(server, String(data).replace("1.8.0.0.0", "1.0.0.0.0"))
        assertNull(s.refresh())                                          // changed: refused, the old one stays
        assertTrue(s.status("1.7.0").blocked)
        server.enqueue(MockResponse().setResponseCode(500))
        assertNull(s.refresh())                                          // offline: the last good policy still applies
        assertTrue(s.status("1.7.0").blocked)
        server.shutdown()
    }
}
