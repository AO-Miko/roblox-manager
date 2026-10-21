package app.robloxmanager.core

import java.io.File
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RolesTest {
    private fun res(name: String) = File("src/test/resources/roles/$name")
    private val data get() = res("roles.json").readBytes()
    private val sig get() = res("roles.json.sig").readText()
    private val key get() = SshSig.keyOf(res("pub.txt").readText())

    @Test fun readsASignedListInEverySpelling() {
        val l = RoleStore.parse(data, sig, key)
        assertNotNull(l)
        assertEquals(7L, l!!.serial)
        assertEquals("owner", l.roles[1001])
        assertEquals("co-owner", l.roles[1002])                  // "Co Owner"
        assertEquals("senior-admin", l.roles[1003])              // "senior_admin"
        assertNull(l.roles[9999])                                // an unknown role is dropped
    }

    @Test fun refusesWrongKeyChangesAndOtherNamespaces() {
        assertNull(RoleStore.parse(data, sig, ByteArray(32)))
        assertNull(RoleStore.parse(String(data).replace("admin", "owner").toByteArray(), sig, key))
        assertNull(RoleStore.parse(data, "nonsense", key))
        assertTrue(!SshSig.verify(data, sig, key, BanStore.NAMESPACE))            // signed for roles, not for bans
    }

    @Test fun theRanksFollowTheHierarchy() {
        assertEquals(listOf("owner", "co-owner", "senior-admin", "admin", "trusted-friend"), Roles.ORDER.map { it.key })
        assertEquals(listOf(5, 4, 3, 2, 1), Roles.ORDER.map { it.rank })
        assertEquals("Senior admin", Roles.label(3))
        assertEquals("", Roles.label(0))
        assertEquals("senior-admin", Roles.normalize(" Senior Admin "))
    }

    @Test fun downloadsCachesRanksAndNeverGoesBack() {
        val server = MockWebServer()
        val cache = File.createTempFile("roles", ".json").also { it.delete() }
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        val store = RoleStore(cache, key, http, "https://x.test/")
        assertEquals(0, store.rankOf(1001))
        assertTrue(store.staff().isEmpty())
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(store.refresh())                                  // not reachable: nothing changes
        server.enqueue(MockResponse().setBody(String(data)))
        server.enqueue(MockResponse().setBody(sig))
        assertEquals(true, store.refresh())
        assertEquals(5, store.rankOf(1001))
        assertEquals(2, store.rankOf(2002))
        assertEquals(1, store.rankOf(4004))
        assertEquals(0, store.rankOf(12345))                         // no role
        assertTrue(store.rankOf(2002) >= Roles.MODERATOR && store.rankOf(4004) < Roles.MODERATOR)
        assertEquals(listOf(1001L, 1002L, 1003L, 2002L, 4004L), store.staff().map { it.first })          // highest role first
        server.enqueue(MockResponse().setBody(String(data)))
        server.enqueue(MockResponse().setBody(sig))
        assertEquals(false, store.refresh())                         // the same list again
        server.enqueue(MockResponse().setBody(String(data).replace("admin", "owner")))
        server.enqueue(MockResponse().setBody(sig))
        assertNull(store.refresh())                                  // changed: refused
        assertEquals(2, store.rankOf(2002))
        assertEquals(5, RoleStore(cache, key, http, "https://x.test/").rankOf(1001))      // kept for the next start
        server.shutdown()
    }
}
