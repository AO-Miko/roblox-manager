package app.robloxmanager.core

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonElement
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.time.ZoneOffset
import java.time.ZonedDateTime

class FeaturesTest {
    private lateinit var server: MockWebServer
    private val seen = ArrayList<String>()
    private var voice = """{"isVoiceEnabled":true,"isUserOptIn":true,"isUserEligible":true,"isBanned":false,"bannedUntil":null,"isVerifiedForVoice":true}"""
    private var age = """{"isVerified":true,"verifiedAge":22,"isSeventeenPlus":false}"""
    private var eligible: String? = """{"eligibleRobux":4214,"updatedUtc":"2026-10-20T00:00:00Z"}"""
    private var info: String? = """{"minRobuxToCashOut":30000,"canProceedToCashout":false,"isDevExSuspended":false,"isAtRiskOfSuspension":false}"""

    private val since = ZonedDateTime.of(2021, 3, 12, 8, 0, 0, 0, ZoneOffset.UTC).toInstant().toEpochMilli()
    private val now = ZonedDateTime.of(2026, 10, 22, 12, 0, 0, 0, ZoneOffset.UTC).toInstant().toEpochMilli()
    private val insights = """{"userInsights":[
        {"targetUser":201,"profileInsights":[{"mutualFriendInsight":{"mutualFriends":{"301":{"username":"zed","displayName":"Zed"},"302":{"username":"amy","displayName":"amy"},"x":{"username":"bad"},"303":"junk"},"insightCase":1},"insightCase":1},
            {"friendshipAgeInsight":{"friendsSinceDateTime":{"seconds":"${since / 1000}"}}},{"offlineFrequentsInsight":{"havePlayedTogether":true},"insightCase":3},"junk",{"friendshipAgeInsight":{"friendsSinceDateTime":{"seconds":"soon"}}}]},
        {"targetUser":202,"profileInsights":[]},{"targetUser":"bad"},{"targetUser":203,"profileInsights":null},"junk"]}"""

    private fun api(): RobloxApi {
        val http = okhttp3.OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request()
            c.proceed(r.newBuilder().url(r.url.newBuilder().scheme("http").host(server.hostName).port(server.port).build()).build())
        }.build()
        val client = RobloxClient(http = http, isRobloxHost = { true }, allowHttp = true)
        client.minGapMs = 0
        return RobloxApi(client)
    }

    @Before fun up() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val p = request.path ?: ""
                seen += "${request.method} $p ${request.body.readUtf8()}"
                val body: String? = when {
                    "multiProfileInsights" in p -> insights
                    p.startsWith("/v1/settings") -> voice
                    "verified-age" in p -> age
                    "devexEligibleRobux" in p -> eligible
                    "developer-exchange/info" in p -> info
                    else -> null
                }
                return if (body == null) MockResponse().setResponseCode(403).setBody("""{"errors":[{"code":0,"message":"refused"}]}""") else MockResponse().setBody(body)
            }
        }
        server.start()
    }

    @After fun down() { server.shutdown() }

    private fun json(s: String): JsonElement = AppJson.parseToJsonElement(s)

    // ---------------------------------------------------------------- what you share with a person
    @Test fun insightsGiveMutualFriendsSinceWhenAndPlayedTogether() {
        val m = Features.parseInsights(json(insights))
        assertEquals(setOf(201L, 202L, 203L), m.keys)
        assertEquals(setOf(301L, 302L), m[201L]!!.mutual.map { it.id }.toSet()); assertEquals(since, m[201L]!!.friendsSinceMs); assertTrue(m[201L]!!.playedTogether)
        assertEquals(Insight(emptyList(), null, false), m[202L]); assertTrue(Features.parseInsights(null).isEmpty())
    }

    @Test fun oneRequestAsksForUpToFiftyPeopleWithTheIdsAsText() = runBlocking {
        val r = api().profileInsights(listOf(201, 202, 203, 204, 201))
        assertEquals(setOf(201L, 202L, 203L), r.keys)
        val body = AppJson.parseToJsonElement(seen.first { "multiProfileInsights" in it }.substringAfter("multiProfileInsights ")).obj!!
        assertEquals(listOf("201", "202", "203", "204"), body.arr("userIds")!!.map { (it as kotlinx.serialization.json.JsonPrimitive).content })
        seen.clear()
        api().profileInsights((1L..80L).toList()); assertEquals(50, AppJson.parseToJsonElement(seen[0].substringAfter("multiProfileInsights ")).obj!!.arr("userIds")!!.size)
        seen.clear(); assertTrue(api().profileInsights(emptyList()).isEmpty()); assertTrue(seen.isEmpty())
    }

    @Test fun whatYouShareIsWrittenPlainly() {
        assertEquals("5 years, 7 months", Features.yearsText(since, now)); assertEquals("under a month", Features.yearsText(now - 5 * 86_400_000L, now))
        assertEquals("1 year", Features.yearsText(ZonedDateTime.of(2025, 10, 22, 0, 0, 0, 0, ZoneOffset.UTC).toInstant().toEpochMilli(), now))
        val t = Features.describe(Features.parseInsights(json(insights))[201L], "Ann", now)
        assertTrue(t, "Friends since 2021-03-12 (5 years, 7 months)." in t && "You have played together." in t && "2 mutual friends:" in t && "  amy" in t && "  Zed  (@zed)" in t && t.indexOf("amy") < t.indexOf("Zed"))
        val s = Features.describe(Insight(emptyList(), null, false), "Bob", now)
        assertTrue("does not say since when" in s && "No mutual friends." in s)
        assertTrue("gave nothing" in Features.describe(null, "Cy", now))
        assertTrue("<b>x</b>" in Features.describe(Insight(listOf(Person(1, "u", "<b>x</b>")), null, false), "n", now))                            // stays text
    }

    // ---------------------------------------------------------------- voice chat, age verification, Developer Exchange
    @Test fun voiceAgeAndDevExAreReadAndTold() = runBlocking {
        val v = api().voiceState()
        assertEquals(VoiceState(true, true, true, false, null, true), v); assertEquals("on, verified", Features.voiceText(v))
        voice = """{"isVoiceEnabled":true,"isUserEligible":true,"isUserOptIn":false,"isBanned":true,"bannedUntil":{"Seconds":1800000000}}"""
        val b = api().voiceState(); assertTrue(b.banned); assertEquals("1800000000", b.bannedUntil)
        assertEquals("suspended until 2027-01-02", Features.voiceText(VoiceState(true, true, true, true, "2027-01-02T03:00", false)))
        assertEquals(listOf("suspended", "not available for this account", "off", "available, not switched on", "on, verified"), listOf(
            Features.voiceText(VoiceState(true, true, true, true, null, false)), Features.voiceText(VoiceState(true, false, true, false, null, false)), Features.voiceText(VoiceState(false, true, true, false, null, false)),
            Features.voiceText(VoiceState(true, true, false, false, null, false)), Features.voiceText(VoiceState(true, true, true, false, null, true))))
        assertEquals(AgeState(true, 22), api().verifiedAge()); assertEquals("verified (age 22)", Features.verifiedText(AgeState(true, 22)))
        age = """{"isVerified":false,"verifiedAge":"x"}"""
        assertEquals(AgeState(false, null), api().verifiedAge()); assertEquals("not verified", Features.verifiedText(AgeState(false, null))); assertEquals("verified", Features.verifiedText(AgeState(true, null)))
        val d = api().devexState()
        assertEquals(DevExState(4214, "2026-10-20T00:00:00Z", 30000, false, false, false), d)
        assertEquals("DevEx: 4,214 Robux can be cashed out (as of 2026-10-20); minimum 30,000; cashing out is not open to you right now.", Features.devexText(d))
        eligible = null                                                                                              // Roblox refuses this one: the other still shows
        val half = api().devexState(); assertNull(half.eligibleRobux); assertEquals(30000L, half.minCashOut)
        info = null
        val none = api().devexState(); assertEquals(DevExState(null, null, null, null, null, null), none); assertEquals("DevEx: not available for this account.", Features.devexText(none))
        assertEquals("DevEx: 5 Robux can be cashed out; DevEx is SUSPENDED.", Features.devexText(DevExState(5, null, null, false, true, null)))
        assertTrue("you can cash out now" in Features.devexText(DevExState(100000, null, 30000, true, false, false)))
    }

    // ---------------------------------------------------------------- friend requests and servers
    @Test fun friendRequestsTellWhenFromWhereAndMutual() {
        fun line(s: String) = Features.requestExtra(json(s).obj!!)
        assertEquals("sent 2026-09-07  ·  from A game  ·  2 mutual", line("""{"friendRequest":{"sentAt":"2026-09-07T07:15:15.592Z","originSourceType":"InGame"},"mutualFriendsList":["Zed","amy"]}"""))
        assertEquals("sent 2026-10-07  ·  from WeirdNewKindb", line("""{"friendRequest":{"sentAt":"2026-10-07T04:21:54Z","originSourceType":"WeirdNewKind<b>"},"mutualFriendsList":[]}"""))
        assertEquals("", line("""{"friendRequest":{"sentAt":"soon","originSourceType":null}}""")); assertEquals("", line("{}"))
        assertEquals(listOf("A game", "Your profile", "WeirdNewKindb", "", ""), listOf("InGame", "UserProfile", "WeirdNewKind<b>", null, "").map { Features.originText(it) })
    }

    @Test fun serverVersionsAndJoinLinks() {
        assertEquals("", Features.versionText(0, 5)); assertEquals("v7", Features.versionText(7, 0)); assertEquals("v7", Features.versionText(7, 7)); assertEquals("v6 (older)", Features.versionText(6, 7))
        assertEquals("https://www.roblox.com/games/start?placeId=11&gameInstanceId=aaaaaaaa-0000-0000-0000-000000000001", Games.serverLink(11, "aaaaaaaa-0000-0000-0000-000000000001"))
        for (bad in listOf("x&y=1", "a b", "../x", "")) assertNull("linked $bad", Games.serverLink(11, bad))
    }

    // ---------------------------------------------------------------- RoSeal's links to game wikis
    @Test fun onlyPlainWikiAddressesBecomeLinks() {
        assertEquals(listOf("https://adoptme.fandom.com", "https://wiki.example.org/Game_Name", "https://a-b.example.co.uk/x/y/"), listOf("adoptme.fandom.com", "Wiki.Example.org/Game_Name", "a-b.example.co.uk/x/y/").map { RoSealLinks.safeUrl(it) })
        val bad = listOf("javascript:alert(1)", "http://evil.example", "https://evil.example", "evil.example:8080", "user@evil.example", "evil.example/a b", "evil.example/../x?y=1", "1.2.3.4", "localhost", "evil", "-a.example.com",
            "a".repeat(300) + ".com", "", "evil.example#frag", "evil.example\\x", "evil.example/a/b/c/d/e/f/g/h/i/j", "exa mple.com", "evil.com/<b>")
        assertEquals(emptyList<String>(), bad.filter { RoSealLinks.safeUrl(it) != null }); assertNull(RoSealLinks.safeUrl(null))
    }

    private val data = """[{"universeIds":[11,12],"links":[{"type":"communityWiki","url":"game.fandom.com","locale":"en"},{"type":"communityWiki","url":"game.fandom.com"},{"type":"discord","url":"discord.gg/x"},{"type":"communityWiki","url":"javascript:alert(1)"}]},
        {"universeIds":["x",true,13],"links":[{"type":"communityWiki","url":"other.wiki.org/Page"}]},{"universeIds":[14],"links":"junk"},"junk",{"links":[]}]"""

    @Test fun roSealsLinksAreReadKeptAndAskedForOnlyWhenNeeded() = runBlocking {
        val p = RoSealLinks.parse(json(data))
        assertEquals(setOf(11L, 12L, 13L), p.keys); assertEquals(listOf(WikiLink("Community wiki", "https://game.fandom.com")), p[11L]); assertEquals("https://other.wiki.org/Page", p[13L]!![0].url)
        val f = File.createTempFile("links", ".json").also { it.delete() }
        var t = 10L
        val urls = ArrayList<String>()
        val list = RoSealLinkList(f, { u -> urls += u; json(data) }, { t })
        assertEquals("https://game.fandom.com", list.linksFor(11)[0].url); assertEquals(listOf("https://data.roseal.live/v2/experience-links.json"), urls)
        assertTrue(list.linksFor(999).isEmpty()); assertEquals(1, urls.size)                                         // kept 24 hours
        t += RoSealLinks.TTL_MS + 1; list.linksFor(11); assertEquals(2, urls.size)
        t += 5 * RoSealLinks.TTL_MS
        assertEquals("https://other.wiki.org/Page", RoSealLinkList(f, { throw GeoException("down") }, { t }).linksFor(13)[0].url)       // down: the old list
        f.delete()
        try { RoSealLinkList(f, { throw GeoException("down") }, { t }).linksFor(11); org.junit.Assert.fail("no list") } catch (e: GeoException) { assertTrue(e.message!!.contains("could not be downloaded")) }
        try { RoSealLinkList(f, { json("""{"x":1}""") }, { t }).linksFor(11); org.junit.Assert.fail("odd list") } catch (e: GeoException) { assertTrue(e.message!!.contains("did not look right")) }
        assertFalse(f.exists())
    }
}
