package app.robloxmanager.core

import java.io.File
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class AppUpdateTest {
    private val sha = "a".repeat(64)

    @Test fun parsesAManifest() {
        val i = AppUpdate.parse("""{"versionCode":3,"versionName":"1.2.0","apk":"roblox-manager.apk","sha256":"$sha","notes":"fixes"}""")
        assertEquals(3, i.versionCode); assertEquals("1.2.0", i.versionName); assertEquals("fixes", i.notes)
    }

    @Test fun refusesBadManifests() {
        for (bad in listOf("nonsense", """{"apk":"a.apk","sha256":"$sha"}""", """{"versionCode":1,"apk":"../x.apk","sha256":"$sha"}""",
            """{"versionCode":1,"apk":"a/b.apk","sha256":"$sha"}""", """{"versionCode":1,"apk":"a.exe","sha256":"$sha"}""", """{"versionCode":1,"apk":"a.apk","sha256":"short"}""")) {
            try { AppUpdate.parse(bad); fail(bad) } catch (_: UpdateError) { }
        }
    }

    @Test fun httpIsRefused() {
        try { AppUpdate("http://example.com/dist/").check(1); fail() } catch (e: UpdateError) { assertTrue(e.message!!.contains("https")) }
        try { AppUpdate("").check(1); fail() } catch (e: UpdateError) { }
    }

    private fun viaServer(server: MockWebServer) = AppUpdate("https://example.invalid/dist/", OkHttpClient.Builder().addInterceptor { c ->
        val r = c.request()
        c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
    }.build())

    @Test fun newerIsOfferedOlderIsNot() {
        val s = MockWebServer()
        s.enqueue(MockResponse().setBody("""{"versionCode":5,"versionName":"2.0","apk":"a.apk","sha256":"$sha"}"""))
        s.enqueue(MockResponse().setBody("""{"versionCode":5,"versionName":"2.0","apk":"a.apk","sha256":"$sha"}"""))
        val u = viaServer(s)
        assertNotNull(u.check(4))
        assertNull(u.check(5))
        s.shutdown()
    }

    @Test fun downloadIsVerified() {
        val s = MockWebServer()
        val body = "pretend apk bytes"
        val dir = File.createTempFile("upd", "").also { it.delete() }
        val tmp = File.createTempFile("pretend", ".apk").also { it.writeText(body) }
        val good = AppUpdate.sha256(tmp)
        s.enqueue(MockResponse().setBody(body))
        val ok = viaServer(s).download(UpdateInfo(7, "7", "a.apk", good, ""), dir)
        assertTrue(ok.exists())
        s.enqueue(MockResponse().setBody(body))
        try { viaServer(s).download(UpdateInfo(8, "8", "a.apk", sha, ""), dir); fail() } catch (e: UpdateError) { assertTrue(e.message!!.contains("checksum")) }
        assertFalse(File(dir, "update-8.apk").exists())
        s.shutdown(); tmp.delete()
    }

    @Test fun betaChannelFollowsTheBetaBranch() {
        assertEquals("https://raw.githubusercontent.com/AO-Miko/roblox-manager/beta/dist/", AppUpdate.betaUrl("https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/"))
        assertEquals("https://example.test/updates/", AppUpdate.betaUrl("https://example.test/updates/"))          // an address that is not the release branch is left alone
    }
}
