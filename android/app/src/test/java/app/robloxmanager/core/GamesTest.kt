package app.robloxmanager.core

import kotlinx.coroutines.runBlocking
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

class GamesTest {
    private lateinit var server: MockWebServer
    private val paths = ArrayList<String>()
    private val favoritePosts = ArrayList<String>()

    private fun game(uid: Long, place: Long, name: String, playing: Int = 100, up: Int = 90, down: Int = 10, sponsored: Boolean = false) =
        """{"universeId":$uid,"rootPlaceId":$place,"name":"$name","playerCount":$playing,"totalUpVotes":$up,"totalDownVotes":$down,"isSponsored":$sponsored,"creatorName":"Maker","creatorHasVerifiedBadge":true,"ageRecommendationDisplayName":"Maturity: Mild","genreL1":"Adventure"}"""

    private val sorts = """{"sorts":[{"contentType":"Filters","sortId":"filters_v5","sortDisplayName":""},
        {"contentType":"Games","sortId":"top-trending","sortDisplayName":"Top Trending","games":[${game(1, 11, "Alpha", 18769, 407265, 264201)},${game(2, 22, "Beta", 5, 0, 0)},${game(3, 33, "An Ad", sponsored = true)}]},
        {"contentType":"Games","sortId":"empty","sortDisplayName":"Empty","games":[]}]}"""

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
                paths += p
                val body = when {
                    "get-sorts" in p -> sorts
                    "omni-search" in p && "pageToken=page2" in p -> """{"searchResults":[{"contentGroupType":"Game","contents":[${game(5, 55, "Obby Five")},${game(7, 77, "Obby Seven")}]}],"nextPageToken":""}"""
                    "omni-search" in p -> """{"searchResults":[{"contentGroupType":"Game","contents":[${game(1, 11, "Alpha")}]},{"contentGroupType":"Game","contents":[${game(5, 55, "Obby Five")}]},{"contentGroupType":"Player","contents":[{"id":1}]}],"nextPageToken":"page2"}"""
                    "/votes" in p -> """{"data":[{"id":1,"upVotes":407269,"downVotes":264202}]}"""
                    "favorites/count" in p -> """{"favoritesCount":105252027}"""
                    "thumbnails/icons" in p || "games/icons" in p -> """{"data":[{"targetId":1,"imageUrl":"https://tr.rbxcdn.com/i1.png"},{"targetId":2,"imageUrl":""}]}"""
                    "multiget/thumbnails" in p -> """{"data":[{"universeId":1,"thumbnails":[{"imageUrl":"https://tr.rbxcdn.com/cover.png"}]}]}"""
                    "/servers/Public" in p && "cursor=s2" in p -> """{"data":[{"id":"aaaaaaaa-0000-0000-0000-000000000003","playing":3,"maxPlayers":12,"ping":53,"fps":59.5}],"nextPageCursor":null}"""
                    "/servers/Public" in p -> """{"data":[{"id":"aaaaaaaa-0000-0000-0000-000000000001","playing":1,"maxPlayers":12,"ping":51,"fps":59.5},{"id":"x&y=1","playing":0,"maxPlayers":12,"ping":1,"fps":60},{"id":"aaaaaaaa-0000-0000-0000-000000000003","playing":3,"maxPlayers":12}],"nextPageCursor":"s2"}"""
                    "/favorites" in p && request.method == "POST" -> { favoritePosts += request.body.readUtf8(); "{}" }
                    "/favorites" in p -> """{"isFavorited":true}"""
                    "favorite/games" in p -> """{"data":[{"id":1,"name":"Alpha","rootPlace":{"id":11},"creator":{"name":"Maker"}},{"name":"no id"}]}"""
                    "groups/search" in p -> """{"data":[{"id":7,"name":"Roblox","memberCount":13508413,"description":"The official group"}]}"""
                    "/v1/games?" in p -> """{"data":[{"id":1,"rootPlaceId":11,"name":"Alpha","description":"The best game.","creator":{"id":9,"name":"PlatinumFalls","hasVerifiedBadge":true},
                        "playing":18793,"visits":4753432465,"maxPlayers":12,"created":"2022-02-02T19:57:39.97Z","updated":"2026-10-14T09:24:58.905Z","genre":"Adventure","genre_l1":"Obby & Platformer","favoritedCount":105252027}]}"""
                    else -> return MockResponse().setResponseCode(404).setBody("{}")
                }
                return MockResponse().setBody(body)
            }
        }
    }

    @After fun down() { server.shutdown() }

    @Test fun homePageRowsAreGamesWithoutAdsOrFilters() = runBlocking {
        val rows = api().discoverSorts("sid")
        assertEquals(listOf("Top Trending"), rows.map { it.name })                              // the filter row and the empty row are not shown
        assertEquals(listOf("Alpha", "Beta"), rows[0].games.map { it.name })                    // the ad is not a game
        val a = rows[0].games[0]
        assertEquals(1L, a.universeId); assertEquals(11L, a.placeId); assertEquals(18769L, a.playing); assertEquals(407265L, a.up)
        assertTrue(a.verified)
        assertTrue(paths.any { "sessionId=sid" in it && "device=phone" in it })
    }

    @Test fun searchGivesGamesAndTheNextPageToken() = runBlocking {
        val (cards, token) = api().searchGames("obby", "sid")
        assertEquals(listOf("Alpha", "Obby Five"), cards.map { it.name })                       // only the Game groups
        assertEquals("page2", token)
        assertTrue(paths.last().contains("searchQuery=obby"))
        val (more, next) = api().searchGames("obby", "sid", token)
        assertEquals(listOf("Obby Five", "Obby Seven"), more.map { it.name })
        assertEquals("", next)
    }

    @Test fun gameDetailsVotesFavoritesPicturesAndGroups() = runBlocking {
        val a = api()
        val d = a.gameDetails(1)!!
        assertEquals("Alpha", d.name); assertEquals("PlatinumFalls", d.creator); assertTrue(d.creatorVerified)
        assertEquals(4753432465L, d.visits); assertEquals(18793L, d.playing); assertEquals(12, d.maxPlayers); assertEquals(105252027L, d.favorites)
        assertEquals("Obby & Platformer", d.genre); assertEquals(11L, d.placeId)
        assertEquals(407269L to 264202L, a.gameVotes(1))
        assertEquals(105252027L, a.gameFavorites(1))
        assertEquals(mapOf(1L to "https://tr.rbxcdn.com/i1.png"), a.gameIcons(listOf(1, 2)))     // an entry without a picture is left out
        assertEquals("https://tr.rbxcdn.com/cover.png", a.gameCover(1))
        val g = a.searchGroups("roblox").single()
        assertEquals(7L, g.id); assertEquals(13508413L, g.members)
    }

    @Test fun publicServersParsePageAndRefuseOddIds() = runBlocking {
        val a = api()
        val (s, next) = a.gameServers(11, "Asc")
        assertEquals(listOf("aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000003"), s.map { it.id })          // the server with an odd id is left out
        assertEquals(1, s[0].playing); assertEquals(12, s[0].max); assertEquals(51, s[0].ping); assertEquals(59, s[0].fps)
        assertNull(s[1].ping)
        assertEquals("s2", next)
        assertTrue(paths.any { "sortOrder=Asc" in it && "excludeFullGames=true" in it && "/games/11/servers/Public" in it })
        val (more, end) = a.gameServers(11, "Asc", "s2")
        assertEquals(1, more.size); assertEquals("", end)
    }

    @Test fun favorites() = runBlocking {
        val a = api()
        assertTrue(a.favoriteState(1))
        a.setFavorite(1, true)
        assertEquals(1, favoritePosts.size)
        assertTrue("\"isFavorited\":true" in favoritePosts[0])
        assertEquals(listOf("Alpha"), a.favoriteGames(156).map { it.name })                    // an entry without an id is left out
        assertEquals(11L, a.favoriteGames(156)[0].placeId)
    }

    @Test fun friendsInGamesAreThoseInAGameWithAServer() {
        val friends = mapOf(201L to Person(201, "ann", "Ann"), 202L to Person(202, "bob", "Bob"))
        val presence = AppJson.parseToJsonElement("""{"userPresences":[{"userId":201,"userPresenceType":2,"lastLocation":"Alpha","rootPlaceId":11,"gameId":"job-1","universeId":1},
            {"userId":202,"userPresenceType":1,"lastLocation":"Website"},{"userId":203,"userPresenceType":2,"rootPlaceId":12,"gameId":"x&y"},{"userPresenceType":2,"rootPlaceId":13}]}""")
        val out = Games.friendGames(presence, friends)
        assertEquals(listOf(201L, 203L), out.map { it.id })
        assertEquals("Ann", out[0].displayName); assertEquals("job-1", out[0].job); assertEquals("Alpha", out[0].game)
        assertNull(out[1].job)                                                                  // a server id that could add something to the link is dropped
        assertTrue(Games.friendGames(null, friends).isEmpty())
    }

    @Test fun recentGamesAreKeptNewestFirstOncePerGameAtMostTwenty() {
        val f = java.io.File.createTempFile("prefs", ".json").also { it.delete() }
        val prefs = Prefs(f)
        assertTrue(RecentGames.load(prefs).isEmpty())
        fun g(i: Long) = GameCard(i, 1, "G$i", 1, 2, 3, "by", true, "age", "genre")
        RecentGames.add(prefs, g(1)); RecentGames.add(prefs, g(2)); RecentGames.add(prefs, g(1))
        assertEquals(listOf(1L, 2L), RecentGames.load(Prefs(f)).map { it.universeId })          // read again from the file: it was saved
        for (i in 10L..40L) RecentGames.add(prefs, g(i))
        assertEquals(20, RecentGames.load(prefs).size); assertEquals(40L, RecentGames.load(prefs)[0].universeId)
        f.writeText("{not json")
        assertTrue(RecentGames.load(Prefs(f)).isEmpty())
    }

    @Test fun serversCanBeSortedByPingFpsAndPlayers() {
        val a = ServerInfo("a", 5, 12, 90, 30); val b = ServerInfo("b", 2, 12, 40, 59); val c = ServerInfo("c", 9, 12, null, null); val d = ServerInfo("d", 1, 12, 40, 60)
        val all = listOf(a, b, c, d)
        assertEquals(listOf("a", "b", "c", "d"), Games.sortServers(all, "roblox").map { it.id })
        assertEquals(listOf("b", "d", "a", "c"), Games.sortServers(all, "ping").map { it.id })          // a server without a ping is last, ties keep Roblox's order
        assertEquals(listOf("d", "b", "a", "c"), Games.sortServers(all, "fps").map { it.id })
        assertEquals(listOf("c", "a", "b", "d"), Games.sortServers(all, "most").map { it.id })
        assertEquals(listOf("d", "b", "a", "c"), Games.sortServers(all, "fewest").map { it.id })
        assertEquals(listOf("a", "b", "c", "d"), Games.sortServers(all, "nonsense").map { it.id })
        assertEquals(listOf("roblox", "ping", "fps", "most", "fewest", "oldest", "newest"), Games.SERVER_ORDERS.map { it.first })
        val started = mapOf("a" to 3000L, "b" to 1000L, "d" to 2000L)                                       // c: not looked up
        assertEquals(listOf("b", "d", "a", "c"), Games.sortServers(all, "oldest", started).map { it.id })          // running longest = started first; unknown last
        assertEquals(listOf("a", "d", "b", "c"), Games.sortServers(all, "newest", started).map { it.id })
        assertEquals(listOf("a", "b", "c", "d"), Games.sortServers(all, "oldest", mapOf("a" to 0L)).map { it.id })       // 0 means not known: nothing to sort by, Roblox's order stays
    }

    @Test fun howLongAServerHasBeenRunning() {
        val now = 10_000_000_000L
        assertEquals("", Games.ageText(null, now)); assertEquals("", Games.ageText(0, now))
        assertEquals("under a minute", Games.ageText(now - 30_000, now)); assertEquals("under a minute", Games.ageText(now + 5000, now))
        assertEquals("12 min", Games.ageText(now - 12 * 60_000, now)); assertEquals("6 h 12 min", Games.ageText(now - (6 * 60 + 12) * 60_000, now))
        assertEquals("1 h 00 min", Games.ageText(now - 60 * 60_000, now)); assertEquals("2 d 3 h", Games.ageText(now - (2 * 24 + 3) * 3600_000, now))
    }

    @Test fun launcherLinkWithAServerId() {
        assertEquals("roblox://experiences/start?placeId=5&gameInstanceId=aaaaaaaa-0000-0000-0000-000000000001", Games.launcherUrl(5, null, "aaaaaaaa-0000-0000-0000-000000000001"))
        for (bad in listOf("x&y=1", "a b", "A/B", "é")) try { Games.launcherUrl(5, null, bad); org.junit.Assert.fail("accepted: $bad") } catch (_: IllegalArgumentException) { }
        assertEquals("roblox://experiences/start?placeId=5&linkCode=AB", Games.launcherUrl(5, "AB", "ignored-when-a-code-is-given"))
    }

    @Test fun launcherLinksAndJoinLinks() {
        assertEquals("roblox://experiences/start?placeId=5", Games.launcherUrl(5))
        assertEquals("roblox://experiences/start?placeId=5&linkCode=ABC", Games.launcherUrl(5, "ABC"))
        assertEquals("roblox://experiences/start?placeId=5", Games.launcherUrl(5, ""))
        assertEquals(123L to "AB", Games.linkParts("https://www.roblox.com/games/123/x?privateServerLinkCode=AB"))
        assertEquals(123L to null, Games.linkParts("https://www.roblox.com/games/123"))
        assertEquals(null to null, Games.linkParts("nonsense ::"))
        assertEquals(null to null, Games.linkParts(null))
        assertEquals("https://www.roblox.com/games/11", Games.pageUrl(11))
        assertEquals("https://www.roblox.com/discover", Games.pageUrl(null))
    }

    @Test fun aJoinCodeCannotAddAnythingToTheLauncherLink() {
        assertEquals("roblox://experiences/start?placeId=5&linkCode=AbC-123_x", Games.launcherUrl(5, "AbC-123_x"))
        for (bad in listOf("AB&x=1", "AB CD", "AB;rm", "a".repeat(65), "é", "A/B", "A?B", "A%26B", "../x", "A\nB", "<x>")) {
            try { Games.launcherUrl(5, bad); org.junit.Assert.fail("accepted: $bad") } catch (_: IllegalArgumentException) { }
            assertFalse(Games.validCode(bad))
        }
        assertEquals(5L to null, Games.linkParts("https://www.roblox.com/games/5?privateServerLinkCode=A%26B"))       // an odd code gives no code
        assertEquals(5L to "AB", Games.linkParts("https://www.roblox.com/games/5?privateServerLinkCode=AB&x=1"))
        assertTrue(Games.validCode("AbC-123_x"))
        assertFalse(Games.validCode(null)); assertFalse(Games.validCode(""))
    }

    @Test fun numbersAndPercentages() {
        assertEquals(listOf("5", "999", "1K", "18.8K", "1.5M", "4.8B", "657K"), listOf(5L, 999, 1000, 18769, 1_500_000, 4_753_429_786, 657_353).map { Games.short(it) })
        assertEquals(90, Games.likePercent(90, 10)); assertNull(Games.likePercent(0, 0)); assertEquals(33, Games.likePercent(1, 2)); assertEquals(61, Games.likePercent(407269, 264202))
    }

    @Test fun oddAnswersNeverCrash() {
        assertTrue(Games.parseSorts(null).isEmpty())
        assertTrue(Games.parseSorts(AppJson.parseToJsonElement("""{"sorts":"x"}""")).isEmpty())
        assertEquals(emptyList<GameCard>() to "", Games.parseSearch(AppJson.parseToJsonElement("[]")))
        assertNull(Games.card(null)); assertNull(Games.card(AppJson.parseToJsonElement("""{"name":"no id"}""").obj))
        assertNull(Games.parseDetails(null))
        assertFalse(Games.card(AppJson.parseToJsonElement("""{"universeId":1,"name":"x"}""").obj) == null)
    }
}
