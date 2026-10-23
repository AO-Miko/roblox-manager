package app.robloxmanager.core

import java.io.File
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** The app debug log: everything is recorded with its output, and nothing private survives. */
class DebugLogTest {
    private val cookie = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_ABCDEF0123456789"
    private val email = "secret.person@example.org"
    private val ip4 = "203.0.113.77"
    private val ip6 = "2001:db8:85a3::8a2e:370:7334"
    private val token = "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLL"
    private val secrets = listOf("ABCDEF0123456789", email, ip4, "8a2e:370:7334", "612 345 678", token, "hunter2", "JohnnyPrivate", "Johnny Display", "424242", "AliceFriendName", "Alice Friend Display", "Bobby Secret Description")
    private lateinit var tmp: File
    private lateinit var server: MockWebServer

    @Before fun up() {
        tmp = createTempDir("debuglog")
        server = MockWebServer()
        Scrub.forgetIdentity()
        Scrub.setIdentity(Account(424242, "JohnnyPrivate", "Johnny Display"))
        Scrub.home = "/home/someone"
        Debug.log = null
    }

    @After fun down() {
        server.shutdown()
        Debug.log = null
        Scrub.forgetIdentity()
        tmp.deleteRecursively()
    }

    @Test fun cookiesMailsAddressesAndSecretsAreHidden() {
        assertFalse("ABCDEF0123456789" in Scrub.text("cookie sent: .ROBLOSECURITY=$cookie end"))
        assertTrue("[cookie]" in Scrub.text(".ROBLOSECURITY=$cookie"))
        val t = Scrub.text("mail $email phone +34 612 345 678 v4 $ip4 v6 $ip6")
        listOf(email, "612 345 678", ip4, "370:7334").forEach { assertFalse(it, it in t) }
        assertFalse("hunter2" in Scrub.text("""{"password": "hunter2"}"""))
        assertFalse("abcd" in Scrub.text("?token=abcd&limit=3"))
        assertTrue("limit=3" in Scrub.text("?token=abcd&limit=3"))
        assertFalse("secretvalue123" in Scrub.text("Authorization: Bearer secretvalue123"))
        assertFalse("shortcsrf" in Scrub.text("x-csrf-token: shortcsrf"))
        assertFalse(token in Scrub.text("value $token"))
        assertFalse("123456" in Scrub.text("""{"code": "123456"}"""))
        assertFalse("123456" in Scrub.text("code=123456"))
    }

    @Test fun theAccountAndTheHomeFolderAreHidden() {
        val t = Scrub.text("acct=johnnyprivate /v1/users/424242/friends hello Johnny Display file /home/someone/x/y.json")
        assertFalse("johnnyprivate" in t.lowercase())
        assertFalse("424242" in t)
        assertFalse("Johnny Display" in t)
        assertTrue("<my id>" in t && "~/x/y.json" in t)
    }

    @Test fun usefulThingsStay() {
        val s = "server 3f2a9c1e-1111-2222-3333-444455556666 ping 45 fps 60 code=5 limit=10 12:30:45"
        assertEquals(s, Scrub.text(s))
        assertTrue(Scrub.text("word ".repeat(1000), 100).endsWith("more characters]"))
    }

    @Test fun answersShowNamesAsStarsAndKeepNumbers() {
        val item = """{"id":5,"name":"AliceFriendName","displayName":"Alice Friend Display","isOnline":true,"description":"Bobby Secret Description","ping":33}"""
        val pv = Scrub.preview("""{"data":[${List(9) { item }.joinToString(",")}],"email":"$email","nextPageCursor":null}""")
        listOf("AliceFriendName", "Alice Friend Display", "Bobby Secret Description", email).forEach { assertFalse(it, it in pv) }
        assertTrue(""""isOnline":true""" in pv && """"ping":33""" in pv && "more" in pv && """"nextPageCursor":null""" in pv)
        assertFalse("AliceFriendName" in Scrub.preview("""{"name": "AliceFriendName", "x": [1,"""))
        assertTrue("not json" in Scrub.preview("not json at all"))
    }

    @Test fun eventsKeepAreaLevelAndOutputAndFilter() {
        val log = DebugLog(File(tmp, "debug.log"))
        log.event("test", "hello $email", "warning", "output with $ip4\nsecond line")
        log.event("test", "plain info")
        log.event("other", "an error", "error", "trace")
        val first = log.events.value[0]
        assertTrue(first.area == "test" && first.level == "warning" && email !in first.message && ip4 !in first.detail && "second line" in first.detail)
        assertEquals(listOf("hello [email]", "an error"), log.snapshot("warning").map { it.message })
        assertEquals(1, log.snapshot(area = "other").size)
        assertEquals(1, log.snapshot(text = "second line").size)
        assertEquals(0, log.snapshot(text = "plain nothing").size)
        val txt = DebugLog.export(log.events.value, "9.9.9")
        assertTrue(txt.startsWith("Roblox Manager debug log") && "app 9.9.9" in txt && "hidden" in txt && "    second line" in txt && email !in txt)
        val f = File(tmp, "debug.log")
        assertTrue(f.exists() && "plain info" in f.readText() && email !in f.readText())
        log.writeFile = false
        log.event("test", "not written to the file")
        assertFalse("not written to the file" in f.readText())
        assertTrue(log.events.value.any { it.message == "not written to the file" })
        log.clear()
        assertTrue(log.events.value.isEmpty())
    }

    @Test fun theFileRotates() {
        val f = File(tmp, "debug.log")
        f.writeText("x".repeat(1_600_000))
        DebugLog(f).event("test", "after the limit")
        assertTrue(File(tmp, "debug.log.1").exists() && f.length() < 1000)
    }

    @Test fun ringKeepsTheNewest() {
        val log = DebugLog(null, keep = 50)
        repeat(80) { log.event("t", "e$it") }
        assertEquals(50, log.events.value.size)
        assertEquals("e79", log.events.value.last().message)
        assertEquals(80L, log.total)
    }

    @Test fun requestsBecomeHttpEventsWithOutputHidden() = runBlocking {
        val debug = DebugLog(File(tmp, "debug.log"))
        Debug.log = debug
        server.enqueue(MockResponse().setHeader("content-type", "application/json").setBody("""{"data":[{"id":7,"name":"AliceFriendName","displayName":"Alice Friend Display"}],"email":"$email","ip":"$ip4"}"""))
        server.enqueue(MockResponse().setResponseCode(404).setHeader("content-type", "application/json").setBody("""{"errors":[{"code":2,"message":"User not found"}]}"""))
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        val c = RobloxClient(http = http, isRobloxHost = { true }, allowHttp = true, log = RequestLog(File(tmp, "requests.log")))
        c.minGapMs = 0
        val r = c.get("https://friends.roblox.com/v1/users/424242/friends", mapOf("limit" to "10", "cursor" to token), auth = false)
        assertTrue(r.json.toString().contains("AliceFriendName"))                                            // (the real data is untouched)
        val e = debug.events.value.single { it.area == "http" }
        assertTrue("GET friends.roblox.com/v1/users/<my id>/friends" in e.message && "-> 200" in e.message && token !in e.message)
        assertTrue("answer: HTTP 200" in e.detail)
        listOf("AliceFriendName", email, ip4).forEach { assertFalse(it, it in e.detail) }
        try { c.get("https://users.roblox.com/v1/users/1", auth = false) } catch (_: RobloxException) { }
        val bad = debug.events.value.last { it.area == "http" }
        assertTrue(bad.level == "warning" && "User not found" in bad.detail)
        val all = debug.events.value.joinToString("\n") { DebugLog.line(it) } + File(tmp, "debug.log").readText()
        assertTrue(secrets.filter { it in all }.toString(), secrets.none { it in all })
    }

    @Test fun downloadsAreEventsWithHostAndPathOnly() {
        val debug = DebugLog(null)
        debug.net("GET", "https://ipwho.is/$ip4?fields=city", 200, 120)
        debug.net("GET", "https://data.roseal.live/v2/grouped-datacenters.json", null, 0, "SocketTimeoutException")
        val a = debug.events.value[0]
        val b = debug.events.value[1]
        assertTrue(a.area == "net" && ip4 !in a.message && "fields" !in a.message && "-> 200" in a.message)
        assertTrue(b.level == "warning" && "no answer" in b.message && "SocketTimeoutException" in b.message)
    }

    @Test fun anEventNeverThrowsAndNothingHappensWithoutALog() {
        Debug.event("x", "nothing is set")                                                   // (no log: nothing happens)
        val log = DebugLog(File("/proc/definitely/not/writable/debug.log"))
        assertNotNull(log.event("t", "file cannot be written"))                              // (a file problem never breaks the app)
    }
}
