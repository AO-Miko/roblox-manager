package app.robloxmanager.core

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.File

class ExtrasTest {
    private lateinit var server: MockWebServer
    private val seen = ArrayList<String>()           // "METHOD path body"

    private fun api(): RobloxApi {
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        val client = RobloxClient(http = http, isRobloxHost = { true }, allowHttp = true)
        client.minGapMs = 0
        return RobloxApi(client)
    }

    private fun req(gid: Int, uid: Int) = """{"requester":{"userId":$uid,"username":"u$uid","displayName":"User $uid"},"created":"2026-10-01T10:00:00Z"}"""

    @Before fun up() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val p = request.path ?: ""
                val body = request.body.readUtf8()
                seen += "${request.method} $p $body"
                val out = when {
                    "presence/users" in p -> """{"userPresences":[{"userId":201,"userPresenceType":2,"lastLocation":"Alpha","rootPlaceId":11}]}"""
                    "/groups/1/membership" in p -> """{"permissions":{"groupMembershipPermissions":{"inviteMembers":true}}}"""
                    "/groups/2/membership" in p -> """{"permissions":{"groupMembershipPermissions":{"inviteMembers":false}}}"""
                    "/groups/3/membership" in p -> return MockResponse().setResponseCode(403).setBody("""{"errors":[{"code":0,"message":"nope"}]}""")
                    "/groups/4/membership" in p -> """{"permissions":{"groupMembershipPermissions":{"inviteMembers":true}}}"""
                    "/groups/1/join-requests" in p && request.method == "GET" -> """{"data":[${req(1, 301)},${req(1, 302)}],"nextPageCursor":null}"""
                    "/groups/4/join-requests" in p && request.method == "GET" && "cursor=p2" in p -> """{"data":[${req(4, 403)}],"nextPageCursor":"p3"}"""
                    "/groups/4/join-requests" in p && request.method == "GET" -> """{"data":[${req(4, 401)},{"requester":{}}],"nextPageCursor":"p2"}"""
                    "/join-requests" in p -> "{}"
                    else -> return MockResponse().setResponseCode(404).setBody("{}")
                }
                return MockResponse().setBody(out)
            }
        }
        server.start()
    }

    @After fun down() { server.shutdown() }

    private fun prefs(): Prefs = Prefs(File.createTempFile("prefs", ".json").also { it.delete() })

    // ---------------------------------------------------------------- alert rules
    private val O = Seen(0, null, ""); private val ON = Seen(1, null, ""); private fun inGame(place: Long, name: String) = Seen(2, place, name)
    private val names = mapOf(1L to "Ann", 2L to "Bob")

    @Test fun alertNews() {
        assertTrue(AlertRules.news(emptyMap(), mapOf(1L to ON), names).isEmpty())                                              // the first look only learns
        assertEquals(listOf(1L to "Ann is online"), AlertRules.news(mapOf(1L to O), mapOf(1L to ON), names))
        assertEquals(listOf(1L to "Ann joined Alpha"), AlertRules.news(mapOf(1L to ON), mapOf(1L to inGame(11, "Alpha")), names))
        assertEquals(listOf(1L to "Ann joined Alpha"), AlertRules.news(mapOf(1L to O), mapOf(1L to inGame(11, "Alpha")), names))   // one piece of news, not two
        assertTrue(AlertRules.news(mapOf(1L to inGame(11, "Alpha")), mapOf(1L to inGame(11, "Alpha")), names).isEmpty())
        assertEquals(listOf(1L to "Ann joined Beta"), AlertRules.news(mapOf(1L to inGame(11, "Alpha")), mapOf(1L to inGame(22, "Beta")), names))
        assertTrue(AlertRules.news(mapOf(1L to inGame(11, "A")), mapOf(1L to O), names).isEmpty())
        assertTrue(AlertRules.news(mapOf(1L to inGame(11, "A")), mapOf(1L to ON), names).isEmpty())
        assertTrue(AlertRules.news(mapOf(1L to O), mapOf(1L to ON), names, online = false).isEmpty())
        assertTrue(AlertRules.news(mapOf(1L to ON), mapOf(1L to inGame(11, "A")), names, ingame = false).isEmpty())
        assertEquals(listOf(1L to "Ann is online"), AlertRules.news(mapOf(1L to O), mapOf(1L to inGame(11, "A")), names, ingame = false))
        assertEquals(listOf(7L to "User 7 is online"), AlertRules.news(mapOf(7L to O), mapOf(7L to ON), emptyMap()))
    }

    @Test fun snapshotsReadRobloxsAnswerAndIgnoreBrokenEntries() {
        val s = AlertRules.snapshot(AppJson.parseToJsonElement("""{"userPresences":[{"userId":1,"userPresenceType":2,"rootPlaceId":11,"placeId":12,"lastLocation":"Alpha"},
            {"userId":2,"userPresenceType":9},{"userPresenceType":1},"junk"]}"""))
        assertEquals(mapOf(1L to Seen(2, 11, "Alpha"), 2L to Seen(0, null, "")), s)
        assertTrue(AlertRules.snapshot(null).isEmpty())
    }

    @Test fun alertSettingsAreKeptPerAccountAndCleaned() {
        val f = File.createTempFile("prefs", ".json").also { it.delete() }
        val a = AlertSettings(Prefs(f))
        assertFalse(a.enabled); assertTrue(a.online); assertTrue(a.ingame)
        a.enabled = true; a.online = false
        a.setWatched(156, mapOf(201L to "Ann", 202L to "x".repeat(99)))
        a.setWatched(157, mapOf(300L to "Zed"))
        val again = AlertSettings(Prefs(f))                                       // read back from the file
        assertTrue(again.enabled); assertFalse(again.online)
        assertEquals(setOf(201L, 202L), again.watched(156).keys); assertEquals(60, again.watched(156)[202L]!!.length)
        assertEquals(mapOf(300L to "Zed"), again.watched(157)); assertTrue(again.watched(1).isEmpty())
        val c = AlertSettings.clean(AppJson.parseToJsonElement("""{"5":{"7":"ok","bad":"x"},"bad":{"1":"z"},"6":"not an object"}"""))
        assertEquals(mapOf(5L to mapOf(7L to "ok")), c)
        a.setWatched(156, (1L..500L).associateWith { "n" })
        assertEquals(AlertRules.MAX_WATCHED, AlertSettings(Prefs(f)).watched(156).size)
    }

    @Test fun presenceIsAskedForOneHundredAtATime() = runBlocking {
        val r = api().presence((1L..150L).toList())
        assertEquals(2, seen.count { "presence/users" in it })
        val sizes = seen.filter { "presence/users" in it }.map { AppJson.parseToJsonElement(it.substringAfter("users ")).obj!!.arr("userIds")!!.size }
        assertEquals(listOf(100, 50), sizes)
        assertEquals(setOf(201L), AlertRules.snapshot(r).keys)
    }

    // ---------------------------------------------------------------- join requests of all groups
    private fun groups() = listOf(
        RobloxApi.Group(1, "Alpha", "Admin", 200, 10, false), RobloxApi.Group(2, "Plain", "Member", 1, 99, false),
        RobloxApi.Group(3, "Locked", "Admin", 100, 5, false), RobloxApi.Group(4, "Busy", "Admin", 100, 5, false))

    @Test fun joinRequestsOfAllGroupsAskOnlyWhereYouMayAnswer() = runBlocking {
        val scan = api().joinRequestsOfAll(groups())
        assertEquals(listOf("1:301", "1:302", "4:401", "4:403"), scan.requests.map { it.key })          // a request without a person is dropped; page 2 of group 4 is read
        assertEquals(2, scan.checked)
        assertEquals(1, scan.failed.size); assertTrue(scan.failed[0].startsWith("Locked"))
        assertTrue(seen.none { "/groups/2/join-requests" in it })
        assertEquals(2, seen.count { "/groups/4/join-requests" in it })                                  // two pages at most, even though Roblox offers a third
        assertEquals("Alpha", scan.requests[0].group); assertEquals("User 301", scan.requests[0].title)
        assertTrue(JoinRequests.mayAnswer(AppJson.parseToJsonElement("""{"permissions":{"groupMembershipPermissions":{"inviteMembers":true}}}""")))
        assertFalse(JoinRequests.mayAnswer(AppJson.parseToJsonElement("""{"permissions":{}}""")))
        assertFalse(JoinRequests.mayAnswer(null))
    }

    @Test fun acceptingPostsAndDecliningDeletesWithTheUserIds() = runBlocking {
        val a = api()
        a.answerJoinRequests(1, listOf(301, 302), true)
        a.answerJoinRequests(4, listOf(401), false)
        assertTrue(seen.any { it.startsWith("POST /v1/groups/1/join-requests") && it.contains("\"UserIds\":[301,302]") })
        assertTrue(seen.any { it.startsWith("DELETE /v1/groups/4/join-requests") && it.contains("\"UserIds\":[401]") })
    }

    // ---------------------------------------------------------------- backup
    @Test fun aBackupHoldsSettingsAlertsAndGamesButNothingElse() {
        val p = prefs()
        p.put("readBurst", 0.3); p.put("logToFile", false); p.put("alerts.enabled", true); p.put("alerts.online", false)
        p.put("updateUrl", "https://secret.example/update"); p.put("channel", "beta"); p.put("cookie", "_|WARNING:-DO-NOT-SHARE")
        AlertSettings(p).setWatched(156, mapOf(201L to "Ann"))
        RecentGames.add(p, GameCard(1, 11, "Alpha", 1, 2, 3, "Maker", true, "age", "genre"))
        val d = Backup.build(p, "1.2.3.4.5", "2026-10-22T10:00:00Z", Person(156, "me", "Me"), listOf(Person(201, "ann", "Ann")), listOf(Person(601, "fan", "Fan")), emptyList(),
            listOf(RobloxApi.Group(1, "Alpha", "Admin", 200, 10, false)))
        val text = AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), d)
        assertEquals("roblox-manager", d.str("app")); assertEquals(1, d.int("format"))
        assertEquals(0.3, d.obj("settings")!!.str("readBurst")!!.toDouble(), 0.0)
        assertEquals(setOf("readBurst", "logToFile", "alerts.enabled", "alerts.online"), d.obj("settings")!!.keys)
        assertEquals("Ann", d.obj("alerts")!!.obj("156")!!.str("201"))
        assertEquals(1, d.arr("recent_games")!!.size); assertEquals(201L, d.arr("friends")!![0].obj!!.long("id")); assertEquals(1, d.arr("groups")!!.size)
        assertTrue(d.arr("following")!!.isEmpty())
        assertFalse("secret.example" in text); assertFalse("WARNING" in text); assertFalse("\"channel\"" in text); assertFalse("updateUrl" in text)       // nothing outside the list of known settings
        val lean = Backup.build(p, "v", "t")
        assertNull(lean["friends"]); assertNull(lean["account"])
    }

    @Test fun restoringBringsBackWhatWasSaved() {
        val p = prefs()
        p.put("readBurst", 0.3); p.put("alerts.enabled", true)
        AlertSettings(p).setWatched(156, mapOf(201L to "Ann"))
        RecentGames.add(p, GameCard(1, 11, "Alpha", 1, 2, 3, "Maker", true, "age", "genre"))
        val text = AppJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), Backup.build(p, "v", "t"))
        val q = prefs()
        val (s, w, g) = Backup.restore(q, Backup.read(text))
        assertEquals(2, s); assertEquals(1, w); assertEquals(1, g)
        assertEquals(0.3, q.double("readBurst", 0.5), 0.0); assertTrue(AlertSettings(q).enabled)
        assertEquals(mapOf(201L to "Ann"), AlertSettings(q).watched(156)); assertEquals("Alpha", RecentGames.load(q)[0].name)
    }

    @Test fun badBackupsAreRefusedInPlainWords() {
        fun refused(text: String) = try { Backup.read(text); null } catch (e: BackupException) { e.message }
        assertTrue(refused("not json")!!.contains("not valid JSON"))
        assertTrue(refused("""{"app":"other","format":1}""")!!.contains("not a backup"))
        assertTrue(refused("[1,2]")!!.contains("not a backup"))
        assertTrue(refused("""{"app":"roblox-manager"}""")!!.contains("version number"))
        assertTrue(refused("""{"app":"roblox-manager","format":99}""")!!.contains("newer version"))
        assertTrue(refused(" ".repeat(Backup.MAX_BYTES + 1))!!.contains("too big"))
        try { Backup.read("""{"app":"roblox-manager","format":1}"""); } catch (_: BackupException) { fail("a minimal backup is fine") }
    }

    @Test fun aHostileBackupIsCleanedOnRestore() {
        val q = prefs()
        val d = Backup.read("""{"app":"roblox-manager","format":1,"settings":{"readBurst":"5","logToFile":"maybe","alerts.online":false,"updateUrl":"https://evil.example","channel":"beta","cookie":"x"},
            "alerts":{"../etc":{"1":"x"},"156":{"../../x":"y","5":"ok"}},"recent_games":[{"u":7},{"u":8,"n":"Good"},"junk",{"n":"no id"}]}""")
        val (s, w, g) = Backup.restore(q, d)
        assertEquals(1, s)                                                       // only alerts.online: readBurst is out of range and logToFile is not a boolean
        assertNull(q.raw("updateUrl")); assertNull(q.raw("channel")); assertNull(q.raw("cookie"))        // nothing but the known settings is ever written
        assertEquals(1, w); assertEquals(mapOf(5L to "ok"), AlertSettings(q).watched(156))
        assertEquals(1, g); assertEquals("Good", RecentGames.load(q)[0].name)
        assertFalse(AlertSettings(q).online)
    }
}
