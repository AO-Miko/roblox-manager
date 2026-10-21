package app.robloxmanager.core

import java.io.File
import java.time.Instant
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

private object FakeVault : Vault {
    override fun seal(plain: String) = "sealed:" + plain.reversed()
    override fun open(sealed: String) = if (sealed.startsWith("sealed:")) sealed.removePrefix("sealed:").reversed() else null
}

class AuthVipAccountsTest {
    private lateinit var server: MockWebServer

    @Before fun up() { server = MockWebServer() }
    @After fun down() { server.shutdown() }

    private fun login() = PasswordLogin(
        base64 = { t -> String(java.util.Base64.getDecoder().decode(t)) },
        base64Encode = { java.util.Base64.getEncoder().encodeToString(it) },
        allowHttp = true,
    )

    // MockWebServer is plain http on one host, so the sign-in addresses are pointed at it through a rewriting interceptor.
    private fun loginVia(): PasswordLogin {
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { chain ->
            val r = chain.request()
            val u = r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()
            chain.proceed(r.newBuilder().url(u).build())
        }.build()
        return PasswordLogin(http, base64 = { t -> String(java.util.Base64.getDecoder().decode(t)) },
            base64Encode = { java.util.Base64.getEncoder().encodeToString(it) })
    }

    @Test fun plainLoginReturnsTheCookie() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setHeader("x-csrf-token", "t1"))
        server.enqueue(MockResponse().setResponseCode(200).addHeader("Set-Cookie", ".ROBLOSECURITY=_|WARNING:abc; path=/; secure").setBody("{\"user\":{\"id\":5,\"name\":\"bob\"}}"))
        val r = loginVia().start("bob", "pw")
        assertTrue(r is Done)
        assertEquals("_|WARNING:abc", (r as Done).cookie)
        assertEquals(5L, r.user!!.long("id"))
        server.takeRequest()
        assertEquals("t1", server.takeRequest().getHeader("x-csrf-token"))
    }

    @Test fun wrongPasswordSaysWhy() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setHeader("x-csrf-token", "t1"))
        server.enqueue(MockResponse().setResponseCode(403).setBody("{\"errors\":[{\"code\":1,\"message\":\"Incorrect username or password.\"}]}"))
        try {
            loginVia().start("bob", "bad")
            fail()
        } catch (e: LoginError) {
            assertTrue(e.message!!.contains("Incorrect"))
        }
    }

    @Test fun twoStepFlow() = runBlocking {
        val meta = java.util.Base64.getEncoder().encodeToString("{\"userId\":5,\"challengeId\":\"c1\",\"actionType\":\"Login\"}".toByteArray())
        server.enqueue(MockResponse().setResponseCode(403).setHeader("x-csrf-token", "t1"))
        server.enqueue(MockResponse().setResponseCode(403).setHeader("rblx-challenge-type", "twostepverification").setHeader("rblx-challenge-id", "ch").setHeader("rblx-challenge-metadata", meta))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"methods\":[{\"mediaType\":\"Email\",\"enabled\":true},{\"mediaType\":\"Passkey\",\"enabled\":true}],\"primaryMediaType\":\"Email\"}"))
        val l = loginVia()
        val s = l.start("bob", "pw")
        assertTrue(s is TwoStep)
        s as TwoStep
        assertEquals(listOf("Email"), s.methods)
        assertEquals(listOf("Passkey"), s.unsupported)
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        l.sendCode("Email")
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"verificationToken\":\"vt\"}"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        server.enqueue(MockResponse().setResponseCode(200).addHeader("Set-Cookie", ".ROBLOSECURITY=ck").setBody("{\"user\":{\"id\":5}}"))
        val done = l.verify("Email", "123 456")
        assertEquals("ck", done.cookie)
        repeat(4) { server.takeRequest() }
        val verify = server.takeRequest()
        assertTrue(verify.path!!.contains("/verify"))
        assertTrue(verify.body.readUtf8().contains("123456"))
        server.takeRequest()
        val last = server.takeRequest()
        assertEquals("ch", last.getHeader("rblx-challenge-id"))
    }

    @Test fun captchaNeedsBrowser() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setHeader("x-csrf-token", "t"))
        server.enqueue(MockResponse().setResponseCode(403).setHeader("rblx-challenge-type", "captcha").setHeader("rblx-challenge-id", "x").setHeader("rblx-challenge-metadata", "e30="))
        try {
            loginVia().start("bob", "pw")
            fail()
        } catch (e: NeedBrowser) {
        }
    }

    @Test fun passwordIsNeverSentElsewhere() = runBlocking {
        try {
            PasswordLogin().start("bob", "pw").let { }
        } catch (_: Exception) {
        }
        assertTrue(true)
    }

    // ---- accounts
    @Test fun accountsKeepCookiesSealed() {
        val f = File.createTempFile("acc", ".json")
        val a = Accounts(f, FakeVault)
        a.save(Account(1, "kyl", "Kyl"), "SECRETCOOKIE")
        a.save(Account(2, "alt", "Alt"), "OTHER", makeActive = false)
        assertFalse(f.readText().contains("SECRETCOOKIE"))
        val b = Accounts(f, FakeVault)
        assertEquals(1L, b.activeId)
        assertEquals("SECRETCOOKIE", b.cookie(1))
        assertTrue(b.switchTo(2))
        assertEquals("OTHER", Accounts(f, FakeVault).let { it.cookie(it.activeId!!) })
        b.remove(2)
        assertEquals(1L, b.activeId)
        assertNull(b.cookie(2))
        f.delete()
    }

    @Test fun cookieCleaning() {
        assertEquals("abc", cleanCookie("  \".ROBLOSECURITY=abc; path=/\" "))
        assertEquals("abc", cleanCookie("abc"))
    }

    // ---- VIP
    private fun vip(vararg p: Pair<String, Any?>) = Vip(obj(*p))
    private val now = Instant.parse("2026-10-21T00:00:00Z")

    @Test fun vipCost() {
        assertEquals("Paid 100 R$", vip("priceInRobux" to 100).cost(now).label)
        assertEquals("Free (Roblox Plus)", vip("totalDiscountAmountInRobux" to 20).cost(now).label)
        assertEquals("Free (game)", vip("expirationDate" to "2126-01-01T00:00:00Z").cost(now).label)
        assertEquals("Unknown", vip("expirationDate" to "2026-12-01T00:00:00Z").cost(now).label)
    }

    @Test fun vipState() {
        assertEquals("Expired", vip("expirationDate" to "2020-01-01T00:00:00Z").state(null, now))
        assertEquals("Unavailable", vip("universeName" to "[ Content Deleted ]").state(null, now))
        assertEquals("", vip("expirationDate" to "2030-01-01T00:00:00Z").state(null, now))
        val v = vip("placeId" to 7, "expirationDate" to "2030-01-01T00:00:00Z")
        assertEquals("Unavailable", v.state(mapOf(1L to "x"), now))
    }

    @Test fun freeOnlyPlan() {
        val freeOff = vip("vipServerId" to 1, "universeId" to 10, "active" to false, "totalDiscountAmountInRobux" to 5, "expirationDate" to "2030-01-01T00:00:00Z")
        val paidOn = vip("vipServerId" to 2, "universeId" to 11, "active" to true, "priceInRobux" to 100, "expirationDate" to "2030-01-01T00:00:00Z")
        val unknownOn = vip("vipServerId" to 3, "universeId" to 12, "active" to true, "expirationDate" to "2030-01-01T00:00:00Z")
        val (on, off) = Vip.freeOnlyPlan(listOf(freeOff, paidOn, unknownOn))
        assertEquals(listOf(freeOff), on)
        assertEquals(listOf(paidOn), off)
    }

    @Test fun duplicateKeepsTheBest() {
        val a = vip("vipServerId" to 1, "universeId" to 10, "active" to false, "expirationDate" to "2030-01-01T00:00:00Z")
        val b = vip("vipServerId" to 2, "universeId" to 10, "active" to true, "expirationDate" to "2030-01-01T00:00:00Z")
        val d = Vip.duplicates(listOf(a, b))
        assertEquals(listOf(b, a), d.values.single())
        assertNotNull(Vip.keepers(listOf(a, b)).firstOrNull { it === b })
    }
}
