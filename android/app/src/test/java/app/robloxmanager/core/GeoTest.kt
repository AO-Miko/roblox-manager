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

class GeoTest {
    private lateinit var server: MockWebServer
    private val bodies = ArrayList<String>()
    private var answers = ArrayList<String>()
    private val job = "aaaaaaaa-0000-0000-0000-000000000001"

    private fun script(vararg addresses: String) =
        """{"jobId":"$job","status":2,"joinScript":{"MachineAddress":"10.9.2.145","UdmuxEndpoints":[${addresses.joinToString(",") { """{"Address":"$it","Port":1}""" }}],"ClientTicket":"SECRET"},"joinTicket":"SECRET"}"""

    private val notReady = """{"jobId":"$job","status":22,"joinScript":null,"joinTicket":"SECRET"}"""

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
                bodies += request.body.readUtf8()
                return MockResponse().setBody(if (answers.size > 1) answers.removeAt(0) else answers[0])
            }
        }
        server.start()
    }

    @After fun down() { server.shutdown() }

    // ---------------------------------------------------------------- the address from Roblox's join answer
    @Test fun aJoinAnswerGivesThePublicAddress() = runBlocking {
        answers = arrayListOf(script("128.116.44.33"))
        assertEquals("128.116.44.33", api().serverInfo(11, job).address)
        val body = AppJson.parseToJsonElement(bodies[0]).obj!!
        assertEquals(11L, body.long("placeId")); assertEquals(job, body.str("gameId")); assertEquals(false, body.bool("isTeleport")); assertEquals(36, body.str("gameJoinAttemptId")!!.length)
    }

    @Test fun notReadyAnswersAreAskedAgainButNotForEver() = runBlocking {
        answers = arrayListOf(notReady, notReady, script("128.116.97.20"))
        assertEquals("128.116.97.20", api().serverInfo(11, job, waitMs = 1).address); assertEquals(3, bodies.size)
        bodies.clear(); answers = arrayListOf(notReady)
        try { api().serverInfo(11, job, waitMs = 1).address; org.junit.Assert.fail("no address") } catch (e: RobloxException) { assertTrue(e.message!!.contains("still getting this server ready")) }
        assertEquals(8, bodies.size)
    }

    @Test fun aJoinScriptThatComesAsTextIsReadToo() = runBlocking {
        answers = arrayListOf("""{"status":2,"joinScript":"{\"UdmuxEndpoints\":[{\"Address\":\"128.116.88.5\"}]}"}""")
        assertEquals("128.116.88.5", api().serverInfo(11, job).address)
    }

    @Test fun aPrivateOrOddAddressIsNeverUsed() = runBlocking {
        for (bad in listOf(arrayOf("10.0.0.5"), arrayOf("192.168.1.1"), arrayOf("127.0.0.1"), arrayOf("169.254.1.1"), arrayOf("::1"), arrayOf("nonsense"), arrayOf<String>())) {
            answers = arrayListOf(script(*bad))
            try { api().serverInfo(11, job).address; org.junit.Assert.fail("used ${bad.toList()}") } catch (e: RobloxException) { assertTrue(e.message!!.contains("public address")) }
        }
        answers = arrayListOf(script("10.0.0.5", "128.116.5.3"))
        assertEquals("128.116.5.3", api().serverInfo(11, job).address)                          // the first PUBLIC address
    }

    @Test fun anOddServerIdIsRefusedBeforeAnythingIsSent() = runBlocking {
        for (odd in listOf("x&y=1", "a b", "../x", "")) { try { api().serverInfo(11, odd); org.junit.Assert.fail("accepted $odd") } catch (_: IllegalArgumentException) { } }
        assertTrue(bodies.isEmpty())
    }

    @Test fun theJoinAnswerAlsoGivesTheStartTimeTheDataCentreAndThePlaceVersion() = runBlocking {
        val now = System.currentTimeMillis()
        answers = arrayListOf(script("128.116.44.33").replace("\"ClientTicket\"", "\"ServerClaimedTime\":${now - 6 * 3600 * 1000},\"DataCenterId\":25960,\"PlaceVersion\":1805,\"ClientTicket\""))
        assertEquals(ServerFacts("128.116.44.33", now - 6 * 3600 * 1000, 25960, 1805), api().serverInfo(11, job))
        for (bad in listOf("null", "\"yesterday\"", "true", "0", "-5", "${now + 10L * 86400 * 1000}", "1792672523")) {          // missing, text, a boolean, zero, negative, in the future, seconds instead of milliseconds
            answers = arrayListOf(script("128.116.44.33").replace("\"ClientTicket\"", "\"ServerClaimedTime\":$bad,\"ClientTicket\""))
            assertNull("accepted $bad", api().serverInfo(11, job).startedMs)
        }
        answers = arrayListOf("""{"status":2,"joinScript":{"udmuxEndpoints":[{"address":"128.116.5.9"}],"serverClaimedTime":${now - 1000},"dataCenterId":7,"placeVersion":3}}""")
        assertEquals(ServerFacts("128.116.5.9", now - 1000, 7, 3), api().serverInfo(11, job))                                  // camelCase names are read too
        answers = arrayListOf("""{"status":2,"joinScript":{"ServerConnections":[{"Address":"128.116.31.33"}],"MachineAddress":"10.0.0.1"}}""")
        assertEquals("128.116.31.33", api().serverInfo(11, job).address)
    }

    @Test fun statusesZeroTwoAndTwentyTwoAreAskedAgainAndOthersAreNot() = runBlocking {
        for (status in listOf(0, 2)) { bodies.clear(); answers = arrayListOf("""{"status":$status,"joinScript":null}""", script("128.116.44.1")); assertEquals("128.116.44.1", api().serverInfo(11, job, waitMs = 1).address); assertEquals(2, bodies.size) }
        bodies.clear(); answers = arrayListOf("""{"status":12,"joinScript":null}""")
        try { api().serverInfo(11, job, waitMs = 1); org.junit.Assert.fail("answered") } catch (e: RobloxException) { assertTrue(e.message!!.contains("status 12")) }
        assertEquals(1, bodies.size)
    }

    // ---------------------------------------------------------------- RoSeal's list and the choice of service
    private val groups = """[{"id":1,"dataCenterIds":[295,25960],"robloxIps":["1.2.3.4"],"location":{"city":"Frankfurt","region":"Hesse","country":"DE","latLong":["50.1155","8.6842"]}},
        {"id":2,"dataCenterIds":[25853],"location":{"city":"Singapore","region":"Singapore","country":"SG","latLong":["1.2897","103.8501"]}}]"""

    @Test fun roSealsListIsReadAndWrongEntriesAreDropped() {
        val g = RoSeal.parseGroups(json(groups))
        assertEquals(2, g.size); assertEquals(setOf(295L, 25960L), g[0].ids); assertEquals(Place("Frankfurt", "Hesse", "", "DE", 50.116, 8.684), g[0].place)
        val bad = """[{"dataCenterIds":[1],"location":{"city":"x","latLong":["95","0"]}},{"dataCenterIds":[1],"location":{"city":"x","latLong":["a","b"]}},{"dataCenterIds":["x",true],"location":{"city":"x","latLong":["1","2"]}},
            {"dataCenterIds":[1]},"junk",null,{"dataCenterIds":[5],"location":{"city":"${"y".repeat(500)}","latLong":[1,2]}}]"""
        val r = RoSeal.parseGroups(json(bad))
        assertEquals(1, r.size); assertEquals(setOf(5L), r[0].ids); assertEquals(60, r[0].place.city.length)
        assertTrue(RoSeal.parseGroups(json("""{"a":1}""")).isEmpty()); assertTrue(RoSeal.parseGroups(null).isEmpty())
    }

    @Test fun roSealsListIsKeptSixHoursAndAnOldOneIsBetterThanNone() = runBlocking {
        val f = File.createTempFile("dcs", ".json").also { it.delete() }
        var t = 10L
        val urls = ArrayList<String>()
        val list = RoSealList(f, { u -> urls += u; json(groups) }, { t })
        assertEquals("Frankfurt", list.placeFor(25960)!!.city); assertEquals(listOf("https://data.roseal.live/v2/grouped-datacenters.json"), urls)
        assertNull(list.placeFor(999)); assertEquals(1, urls.size)                                                           // kept: not downloaded again
        t += RoSeal.TTL_MS + 1
        assertEquals("Singapore", list.placeFor(25853)!!.city); assertEquals(2, urls.size)                                   // after 6 hours: again
        t += 3 * RoSeal.TTL_MS
        assertEquals("Singapore", RoSealList(f, { throw GeoException("down") }, { t }).placeFor(25853)!!.city)               // down: the old list
        f.delete()
        try { RoSealList(f, { throw GeoException("down") }, { t }).placeFor(25853); org.junit.Assert.fail("no list") } catch (e: GeoException) { assertTrue(e.message!!.contains("could not be downloaded")) }
        try { RoSealList(f, { json("""{"x":1}""") }, { t }).placeFor(25853); org.junit.Assert.fail("odd list") } catch (e: GeoException) { assertTrue(e.message!!.contains("did not look right")) }
    }

    @Test fun theChoiceOfServiceFollowsWhatThePersonAllowed() = runBlocking {
        val f = File.createTempFile("places", ".json").also { it.delete() }
        val ipAsked = ArrayList<String>(); val listAsked = ArrayList<String>()
        val roseal = RoSealList(File.createTempFile("dcs", ".json").also { it.delete() }, { u -> listAsked += u; json(groups) })
        val book = GeoBook(f, { ip -> ipAsked += ip; json(good) })
        val info = ServerFacts("128.116.44.33", 1, 25960, 1)
        assertEquals("Frankfurt", book.resolve(info, true, false, roseal).city); assertTrue(ipAsked.isEmpty()); assertEquals(1, listAsked.size)          // RoSeal's list: nothing is sent to ipwho.is
        assertEquals("Frankfurt", book.resolve(info.copy(address = "128.116.99.1"), true, true, roseal).city); assertEquals(1, listAsked.size); assertTrue(ipAsked.isEmpty())   // kept by data centre
        assertEquals("Frankfurt", book.resolve(info, false, false, roseal).city)                                                                         // kept answers need no permission
        val other = ServerFacts("128.116.31.33", null, 77, null)
        try { book.resolve(other, false, false, roseal); org.junit.Assert.fail("off") } catch (e: GeoException) { assertEquals("Server locations are switched off in Settings", e.message) }
        try { book.resolve(other, true, false, roseal); org.junit.Assert.fail("unknown") } catch (e: GeoException) { assertTrue(e.message!!.contains("does not know this data centre") && e.message!!.contains("ipwho.is is switched off")) }
        assertTrue(ipAsked.isEmpty())                                                                                                                   // ipwho.is is not used without permission
        assertEquals("Frankfurt am Main", book.resolve(other, true, true, roseal).city); assertEquals(1, ipAsked.size)                                    // the fallback, once allowed
        assertEquals("Frankfurt am Main", book.resolve(ServerFacts("128.116.55.9", null, null, null), false, true, roseal).city)                          // no data centre id: ipwho.is
        try { book.resolve(ServerFacts("128.116.97.50", null, null, null), true, false, roseal); org.junit.Assert.fail("no dc") } catch (e: GeoException) { assertTrue(e.message!!.contains("without its data centre id")) }
    }

    // ---------------------------------------------------------------- the lookup of an address
    @Test fun onlyPublicIpv4AddressesAreLookedUp() {
        assertEquals("128.116.44.33", Geo.publicIpv4("128.116.44.33")); assertEquals("8.8.8.8", Geo.publicIpv4(" 8.8.8.8 "))
        for (bad in listOf("10.1.2.3", "192.168.0.1", "127.0.0.1", "169.254.2.2", "172.16.0.1", "172.31.255.255", "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "256.1.1.1", "1.2.3", "1.2.3.4.5", "::1", "2606:4700::1111", "x", "", "1.2.3.-4"))
            assertNull("accepted $bad", Geo.publicIpv4(bad))
        assertNull(Geo.publicIpv4(null)); assertEquals("172.32.0.1", Geo.publicIpv4("172.32.0.1"))
        assertEquals("128.116.44", Geo.blockOf("128.116.44.33"))
    }

    private val good = """{"success":true,"country":"Germany","country_code":"DE","region":"Hessen","city":"Frankfurt am Main","latitude":50.1155207,"longitude":8.6841662}"""
    private fun json(s: String): JsonElement = AppJson.parseToJsonElement(s)

    @Test fun anAnswerBecomesAPlaceAndWrongAnswersAreRefused() {
        val p = Geo.clean(json(good))!!
        assertEquals(Place("Frankfurt am Main", "Hessen", "Germany", "DE", 50.116, 8.684), p); assertEquals("Frankfurt am Main, Germany", p.label)
        assertEquals("Unknown", Place("", "", "", "", 0.0, 0.0).label)
        for (bad in listOf("""{"success":false}""", """{"success":true}""", good.replace("50.1155207", "91"), good.replace("8.6841662", "\"8\""), "[1]", "7")) assertNull(bad, Geo.clean(json(bad)))
        assertEquals(60, Geo.clean(json(good.replace("Frankfurt am Main", "x".repeat(500))))!!.city.length)
    }

    private fun book(file: File, now: () -> Long, asked: MutableList<String>, answer: (String) -> JsonElement? = { json(good) }) =
        GeoBook(file, { ip -> asked += ip; answer(ip) }, now)

    @Test fun answersAreKeptByBlockForThirtyDays() = runBlocking {
        val f = File.createTempFile("places", ".json").also { it.delete() }
        var t = 1000L
        val asked = ArrayList<String>()
        val b = book(f, { t }, asked)
        val p = b.lookup("128.116.44.33")
        assertEquals("Frankfurt am Main", p.city); assertEquals(listOf("128.116.44.33"), asked)
        assertEquals(p, b.lookup("128.116.44.77")); assertEquals(1, asked.size)                                       // the same block: not asked again
        assertEquals(p, book(f, { t }, asked).lookup("128.116.44.2")); assertEquals(1, asked.size)                    // ...also after a restart (it is in the file)
        b.lookup("128.116.97.20"); assertEquals(2, asked.size)                                                        // another block
        t += Geo.TTL_MS + 1
        b.lookup("128.116.44.33"); assertEquals(3, asked.size)                                                        // an old answer is asked again
    }

    @Test fun badAnswersAndBadKeptEntriesAreNotUsed() = runBlocking {
        val f = File.createTempFile("places", ".json").also { it.delete() }
        val asked = ArrayList<String>()
        for (bad in listOf("""{"success":false}""", good.replace("50.1155207", "95"))) {
            try { book(f, { 5 }, asked) { json(bad) }.lookup("128.116.55.9"); org.junit.Assert.fail("accepted") } catch (e: GeoException) { assertTrue(e.message!!.length > 10) }
        }
        try { book(f, { 5 }, asked) { null }.lookup("128.116.55.9"); org.junit.Assert.fail("accepted") } catch (_: GeoException) { }
        asked.clear()
        try { book(f, { 5 }, asked).lookup("10.0.0.1"); org.junit.Assert.fail("private") } catch (e: GeoException) { assertTrue(e.message!!.contains("public")) }
        assertTrue(asked.isEmpty())                                                                                   // a private address is never sent
        f.writeText("""{"128.116.44":{"city":"X","lat":"far","lon":5,"cc":"DE","t":${System.currentTimeMillis()}}}""")      // a kept entry that is wrong: asked again
        assertEquals("Frankfurt am Main", book(f, { System.currentTimeMillis() }, asked).lookup("128.116.44.1").city); assertEquals(1, asked.size)
        f.writeText("{not json")
        assertEquals("Frankfurt am Main", book(f, { 9 }, asked).lookup("128.116.44.1").city)                          // a damaged file is ignored
    }

    @Test fun atMostFiveHundredAnswersAreKept() = runBlocking {
        val f = File.createTempFile("places", ".json").also { it.delete() }
        var t = 100L
        val b = book(f, { t++ }, ArrayList())
        for (i in 0 until 600) b.lookup("20.${i % 250}.${i / 250}.1")
        assertTrue((AppJson.parseToJsonElement(f.readText()).obj!!).size <= Geo.MAX_CACHED)
    }

    // ---------------------------------------------------------------- the map's data
    @Test fun theMapKnowsWhereEverythingIs() {
        assertEquals(360f to 180f, WorldMap.project(0.0, 0.0, 720f, 360f)); assertEquals(0f to 0f, WorldMap.project(90.0, -180.0, 720f, 360f)); assertEquals(720f to 360f, WorldMap.project(-90.0, 180.0, 720f, 360f))
        val (x, y) = WorldMap.project(50.1, 8.7, 720f, 360f)
        assertTrue(x in 360f..400f && y < 120f)
        val land = WorldMap.parseLand(File("src/main/assets/world_land.json").readText())
        assertTrue("only ${land.size} rings", land.size > 100)
        assertTrue(land.all { ring -> ring.size >= 4 && ring.all { (lon, lat) -> lon in -180.0..180.0 && lat in -90.0..90.0 } })
        assertTrue(WorldMap.parseLand("not json").isEmpty())
    }

    @Test fun serversInOnePlaceShareADot() {
        val servers = listOf("a", "b", "c", "d").map { ServerInfo(it, 1, 12, 40, 60) }
        val places = mapOf("a" to Place("F", "", "", "DE", 50.1, 8.7), "b" to Place("S", "", "", "SG", 1.3, 103.8), "c" to Place("F", "", "", "DE", 50.1, 8.7))
        val g = WorldMap.groupPlaces(servers, places)
        assertEquals(listOf(2, 1), g.map { it.second.size }.sortedDescending()); assertTrue(g.any { it.second == listOf("a", "c") })
        assertFalse(g.any { "d" in it.second })                                                                         // not located: no dot
    }
}
