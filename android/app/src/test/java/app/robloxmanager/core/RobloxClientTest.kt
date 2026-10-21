package app.robloxmanager.core

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class RobloxClientTest {
    private lateinit var server: MockWebServer
    private var clock = 1_000_000L
    private val slept = ArrayList<Long>()

    private fun client(): RobloxClient {
        val c = RobloxClient(
            now = { clock },
            sleep = { clock += it; slept += it },
            isRobloxHost = { true },
            allowHttp = true,
        )
        c.minGapMs = 0
        return c
    }

    private fun url(path: String) = server.url(path).toString()

    @Before fun up() { server = MockWebServer() }
    @After fun down() { server.shutdown() }

    @Test fun plainHttpIsRefused() = runBlocking {
        try {
            RobloxClient().get("http://example.com/x")
            fail()
        } catch (e: IllegalArgumentException) {
        }
    }

    @Test fun rateTableLearnsAndGates() = runBlocking {
        val t = RateTable { clock }
        val k = RateTable.key("GET", "https://friends.roblox.com/v1/users/123/friends")
        assertEquals("friends.roblox.com/v1/users/{n}/friends", k.substringAfter(' '))
        assertFalse(t.known(k))
        t.learn(k, mapOf("x-ratelimit-limit" to "10, 10;w=60", "x-ratelimit-remaining" to "0", "x-ratelimit-reset" to "30"), 200, 0, 10_000)
        assertTrue(t.known(k))
        assertEquals(30_000L, t.waitLeftMs(k))
        t.gate(k, { clock += it; slept += it })
        assertTrue(slept.sum() >= 30_000)
    }

    @Test fun hiddenLimitKeepsGap() {
        val t = RateTable { clock }
        val k = "POST x/y"
        val text = t.learn(k, mapOf("x-ratelimit-remaining" to "9", "x-ratelimit-reset" to "5", "x-ratelimit-limit" to "10"), 429, 0, 10_000)
        assertTrue(text.contains("hidden limit"))
        assertTrue(t.waitLeftMs(k) >= 10_000)
    }

    @Test fun localLimitWhenTooLong() = runBlocking {
        val t = RateTable { clock }
        val k = "GET a/b"
        t.learn(k, mapOf("x-ratelimit-limit" to "1;w=600", "x-ratelimit-remaining" to "0", "x-ratelimit-reset" to "600"), 200, 0, 10_000)
        try {
            t.gate(k, { }, maxWaitMs = 5_000)
            fail()
        } catch (e: LocalLimit) {
            assertEquals(429, e.status)
            assertTrue(e.local)
        }
    }

    @Test fun csrfIsRefreshedAndRetried() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setHeader("x-csrf-token", "tok1"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"ok\":true}"))
        val c = client()
        c.cookie = "secret-cookie"
        val r = c.post(url("/v1/thing"), obj("a" to 1))
        assertEquals(200, r.status)
        val first = server.takeRequest()
        val second = server.takeRequest()
        assertNull(first.getHeader("X-CSRF-TOKEN"))
        assertEquals("tok1", second.getHeader("X-CSRF-TOKEN"))
        assertEquals(".ROBLOSECURITY=secret-cookie", second.getHeader("Cookie"))
    }

    @Test fun cookieOnlyGoesToRoblox() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        val c = RobloxClient(now = { clock }, sleep = { clock += it }, isRobloxHost = { false }, allowHttp = true)
        c.cookie = "secret-cookie"
        c.get(url("/x"))
        assertNull(server.takeRequest().getHeader("Cookie"))
    }

    @Test fun errorsCarryMessageAndNeverTheCookie() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(400).setBody("{\"errors\":[{\"code\":7,\"message\":\"bad _|WARNING:abc123 thing\"}]}"))
        val c = client()
        try {
            c.get(url("/x"))
            fail()
        } catch (e: RobloxException) {
            assertEquals(400, e.status)
            assertEquals(7, e.code)
            assertFalse(e.message!!.contains("abc123"))
        }
    }

    @Test fun readRetries429ThenSucceeds() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(429).setHeader("retry-after", "2"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"data\":[]}"))
        val r = client().get(url("/v1/list"))
        assertEquals(200, r.status)
        assertTrue(slept.sum() >= 2_000)
    }

    @Test fun staleAccountIsDropped() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        val c = client()
        c.cookie = "x"
        c.signOut()
        assertEquals("", c.cookie)
        assertEquals(200, c.get(url("/x")).status)
    }

    @Test fun requestsAreLoggedWithoutSecrets() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        val c = client()
        c.get(url("/v1/x"), mapOf("token" to "abc", "limit" to "10"))
        val e = c.log.entries.value.last()
        assertEquals(200, e.status)
        assertTrue(e.query.contains("token=***"))
        assertTrue(e.query.contains("limit=10"))
    }

    @Test fun jsonHelpers() {
        val o = obj("a" to 1, "b" to "x", "c" to listOf(1, 2), "d" to null)
        assertEquals(1, o.int("a"))
        assertEquals("x", o.str("b"))
        assertEquals(2, o.arr("c")!!.size)
        assertFalse(o.containsKey("d"))
        assertEquals("x", (JsonPrimitive("x") as kotlinx.serialization.json.JsonElement).text)
    }
}
