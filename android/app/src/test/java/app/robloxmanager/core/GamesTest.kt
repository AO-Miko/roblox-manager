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
