package app.robloxmanager.core

import java.io.File
import java.time.LocalDate
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NoticesTest {
    private fun res(name: String) = File("src/test/resources/notices/$name")
    private val data get() = res("notifications.json").readBytes()
    private val sig get() = res("notifications.json.sig").readText()
    private val key get() = SshSig.keyOf(res("pub.txt").readText())
    private fun tmp(prefix: String) = File.createTempFile("tmp_$prefix", ".json").also { it.delete(); it.deleteOnExit() }
    private val day = { LocalDate.of(2026, 10, 28) }

    private fun http(server: MockWebServer) = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
        val r = c.request()
        c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
    }.build()

    private fun serve(server: MockWebServer, d: ByteArray = data, s: String = sig) {
        server.enqueue(MockResponse().setBody(String(d))); server.enqueue(MockResponse().setBody(s))
    }

    @Test fun readsASignedListAndCleansIt() {
        val l = NoticeStore.parse(data, sig, key)!!
        assertEquals(7L, l.serial)
        assertEquals(listOf("n1", "n2", "n3", "n4", "n5", "n6", "n7"), l.items.map { it.id })          // the duplicate id and the id with a space are dropped
        assertEquals("Hello <b>there</b>", l.items[0].body)                                          // kept as text: the screen never reads it as HTML
        assertEquals("important", l.items[1].level); assertEquals("https://example.com/news", l.items[1].link)
        assertEquals("beta", l.items[2].channel); assertEquals("all", l.items[0].channel)
        assertNull(l.items[5].link); assertEquals("info", l.items[5].level)                          // an http link is dropped, an unknown level is info
        assertEquals(80, l.items[6].title.length); assertEquals(1000, l.items[6].body.length)
        assertEquals("2026-01-02", l.items[3].expires)
    }

    @Test fun refusesWrongKeyChangesAndOtherNamespaces() {
        assertNull(NoticeStore.parse(data, sig, ByteArray(32)))
        assertNull(NoticeStore.parse(String(data).replace("Welcome", "Hacked").toByteArray(), sig, key))
        assertFalse(SshSig.verify(data, sig, key, "roblox-manager-bans"))
        assertNull(NoticeStore.parse(data, "nonsense", key))
    }

    @Test fun onlyThisChannelAndNotExpired() {
        val server = MockWebServer(); serve(server)
        val store = NoticeStore(tmp("n"), Prefs(tmp("p")), key, http(server), "https://x.test/", day)
        assertEquals(true, store.refresh())
        assertEquals(listOf("n1", "n2", "n5", "n6", "n7"), store.visible("stable").map { it.id })      // n3 is for beta, n4 expired on 2026-01-02
        assertEquals(listOf("n1", "n2", "n3", "n6", "n7"), store.visible("beta").map { it.id })
        server.shutdown()
    }

    @Test fun downloadsCachesAndNeverGoesBack() {
        val server = MockWebServer()
        val cache = tmp("n")
        val store = NoticeStore(cache, Prefs(tmp("p")), key, http(server), "https://x.test/", day)
        assertEquals(0, store.visible("stable").size)
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(store.refresh())                                                                   // not reachable: nothing changes
        serve(server)
        assertEquals(true, store.refresh())
        serve(server)
        assertEquals(false, store.refresh())                                                          // the same list: no change
        serve(server, data, "nonsense")
        assertNull(store.refresh())                                                                   // not signed: refused
        serve(server, String(data).replace("\"serial\": 7", "\"serial\": 3").toByteArray(), sig)
        assertNull(store.refresh())                                                                   // changed after signing: refused
        assertEquals(5, NoticeStore(cache, Prefs(tmp("p")), key, http(server), "https://x.test/", day).visible("stable").size)      // kept on the phone
        cache.writeText(cache.readText().replace("\"data\":\"", "\"data\":\"AAAA"))                   // a file edited on the phone is not believed
        assertEquals(0L, NoticeStore(cache, Prefs(tmp("p")), key, http(server), "https://x.test/", day).load().serial)
        server.shutdown()
    }

    @Test fun readAndUnreadAreKeptInTheSettings() {
        val server = MockWebServer(); serve(server)
        val pf = tmp("p"); val nf = tmp("n")
        val store = NoticeStore(nf, Prefs(pf), key, http(server), "https://x.test/", day)
        store.refresh()
        assertEquals(5, store.unreadCount("stable")); assertEquals(5, store.unreadCount("beta"))
        store.markRead("n2")
        assertEquals(4, store.unreadCount("stable")); assertTrue(store.isRead("n2")); assertFalse(store.isRead("n1"))
        store.markRead("nothing-like-this")                                                           // an id that does not exist is not remembered
        assertFalse(store.isRead("nothing-like-this"))
        assertTrue(NoticeStore(nf, Prefs(pf), key, http(server), "https://x.test/", day).isRead("n2"))      // (a new store reads the same settings file)
        store.markAllRead("stable")
        assertEquals(0, store.unreadCount("stable"))
        assertEquals(1, store.unreadCount("beta"))                                                    // n3 is for beta and was not read
        server.shutdown()
    }

    @Test fun nothingIsAnnouncedOnTheFirstFetch() {
        val server = MockWebServer(); serve(server)
        val store = NoticeStore(tmp("n"), Prefs(tmp("p")), key, http(server), "https://x.test/", day)
        store.refresh()
        assertTrue(store.takeNew("stable").isEmpty())                                                 // first ever fetch: everything is only remembered
        assertTrue(store.takeNew("stable").isEmpty())
        server.shutdown()
    }

    @Test fun anAnnouncedListWithANewIdIsReturnedOnce() {
        // the store is told the list through a prefs file that already knows n1..n7, then a notice with another id shows up
        val p = Prefs(tmp("p"))
        p.put("notices.seen", listOf("n1", "n2", "n5", "n6"))
        val server = MockWebServer(); serve(server)
        val store = NoticeStore(tmp("n"), p, key, http(server), "https://x.test/", day)
        store.refresh()
        assertEquals(listOf("n7"), store.takeNew("stable").map { it.id })                            // n7 was never announced
        assertTrue(store.takeNew("stable").isEmpty())                                                 // and now it was
        server.shutdown()
    }
}
