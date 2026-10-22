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
        assertEquals("128.116.44.33", api().serverAddress(11, job))
        val body = AppJson.parseToJsonElement(bodies[0]).obj!!
        assertEquals(11L, body.long("placeId")); assertEquals(job, body.str("gameId")); assertEquals(false, body.bool("isTeleport")); assertEquals(36, body.str("gameJoinAttemptId")!!.length)
    }

    @Test fun notReadyAnswersAreAskedAgainButNotForEver() = runBlocking {
        answers = arrayListOf(notReady, notReady, script("128.116.97.20"))
        assertEquals("128.116.97.20", api().serverAddress(11, job, waitMs = 1)); assertEquals(3, bodies.size)
        bodies.clear(); answers = arrayListOf(notReady)
        try { api().serverAddress(11, job, waitMs = 1); org.junit.Assert.fail("no address") } catch (e: RobloxException) { assertTrue(e.message!!.contains("did not give this server's address")) }
        assertEquals(4, bodies.size)
    }

    @Test fun aJoinScriptThatComesAsTextIsReadToo() = runBlocking {
        answers = arrayListOf("""{"status":2,"joinScript":"{\"UdmuxEndpoints\":[{\"Address\":\"128.116.88.5\"}]}"}""")
        assertEquals("128.116.88.5", api().serverAddress(11, job))
    }

    @Test fun aPrivateOrOddAddressIsNeverUsed() = runBlocking {
        for (bad in listOf(arrayOf("10.0.0.5"), arrayOf("192.168.1.1"), arrayOf("127.0.0.1"), arrayOf("169.254.1.1"), arrayOf("::1"), arrayOf("nonsense"), arrayOf<String>())) {
            answers = arrayListOf(script(*bad))
            try { api().serverAddress(11, job); org.junit.Assert.fail("used ${bad.toList()}") } catch (e: RobloxException) { assertTrue(e.message!!.contains("public address")) }
        }
        answers = arrayListOf(script("10.0.0.5", "128.116.5.3"))
        assertEquals("128.116.5.3", api().serverAddress(11, job))                          // the first PUBLIC address
    }

    @Test fun anOddServerIdIsRefusedBeforeAnythingIsSent() = runBlocking {
        for (odd in listOf("x&y=1", "a b", "../x", "")) { try { api().serverAddress(11, odd); org.junit.Assert.fail("accepted $odd") } catch (_: IllegalArgumentException) { } }
        assertTrue(bodies.isEmpty())
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
