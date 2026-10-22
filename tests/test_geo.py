"""Test of where servers are: the address from Roblox's join answer, the lookup of the address (with its cache), and the world map's data and drawing.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_geo.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="geo-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off"})
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import geo
import rbx
import worldmap
from theme import T

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:240]) if e else ""))


JOB = "aaaaaaaa-0000-0000-0000-000000000001"


def script(*addresses, extra=None):
    d = {"jobId": JOB, "status": 2, "joinScript": {"MachineAddress": "10.9.2.145", "ServerPort": 50705, "UdmuxEndpoints": [{"Address": a, "Port": 50705} for a in addresses],
                                                  "ClientTicket": "SECRET-TICKET", "UserId": 5}, "joinTicket": "SECRET-JOIN"}
    d.update(extra or {})
    return d


NOT_READY = {"jobId": JOB, "status": 22, "joinScript": None, "joinTicket": "SECRET-JOIN", "message": None}


class FakeRoblox(rbx.Client):
    answers = []
    calls = []

    def post(self, url, body=None, **kw):
        FakeRoblox.calls.append((url, body))
        if "join-game-instance" in url:
            return FakeRoblox.answers.pop(0) if len(FakeRoblox.answers) > 1 else FakeRoblox.answers[0]
        raise rbx.RobloxError(404, "not faked: " + url)


rbx.Client.JOIN_WAIT = 0.001
c = FakeRoblox()

# ================================================================ the address from Roblox's join answer
FakeRoblox.answers = [script("128.116.44.33")]
check("a join answer gives the server's public address", c.server_info(11, JOB)["address"] == "128.116.44.33")
url, body = FakeRoblox.calls[-1]
check("...asked like the website asks, for that place and that server, and nothing is joined by it", url == "https://gamejoin.roblox.com/v1/join-game-instance" and body["placeId"] == 11
      and body["gameId"] == JOB and body["isTeleport"] is False and len(body["gameJoinAttemptId"]) == 36, body)
FakeRoblox.answers, FakeRoblox.calls = [NOT_READY, NOT_READY, script("128.116.97.20")], []
check("'not ready' answers (status 22) are asked again", c.server_info(11, JOB)["address"] == "128.116.97.20" and len(FakeRoblox.calls) == 3, len(FakeRoblox.calls))
FakeRoblox.answers, FakeRoblox.calls = [NOT_READY], []
try:
    c.server_info(11, JOB)
    msg = "no error"
except rbx.RobloxError as e:
    msg = str(e)
check("...but not for ever (8 times), and then it says so", "still getting this server ready" in msg and len(FakeRoblox.calls) == 8, (msg, len(FakeRoblox.calls)))
for status in (0, 2):
    FakeRoblox.answers, FakeRoblox.calls = [{"status": status, "joinScript": None}, script("128.116.44.1")], []
    check(f"status {status} is 'ask again' too", c.server_info(11, JOB)["address"] == "128.116.44.1" and len(FakeRoblox.calls) == 2)
FakeRoblox.answers, FakeRoblox.calls = [{"status": 12, "joinScript": None, "message": "x"}], []
try:
    c.server_info(11, JOB)
    msg = "no error"
except rbx.RobloxError as e:
    msg = str(e)
check("any other status is answered at once, without asking again", "would not let this server be looked at (status 12)" in msg and len(FakeRoblox.calls) == 1, (msg, len(FakeRoblox.calls)))
FakeRoblox.answers = [{"status": 2, "joinScript": json.dumps({"UdmuxEndpoints": [{"Address": "128.116.88.5"}]})}]
check("a join script that comes as text is read too", c.server_info(11, JOB)["address"] == "128.116.88.5")
for bad in (["10.0.0.5"], ["192.168.1.1"], ["127.0.0.1"], ["169.254.1.1"], ["::1"], ["not an address"], [], [None]):
    FakeRoblox.answers = [script(*bad)]
    try:
        r = c.server_info(11, JOB)
    except rbx.RobloxError:
        r = None
    check(f"a private or odd address is never used: {bad}", r is None, r)
FakeRoblox.answers = [script("10.0.0.5", "128.116.5.3")]
check("the first PUBLIC address is taken", c.server_info(11, JOB)["address"] == "128.116.5.3")
for odd in ("x&y=1", "a b", "../x", ""):
    try:
        c.server_info(11, odd)
        r = "accepted"
    except ValueError:
        r = "refused"
    check(f"an odd server id is refused before anything is sent: {odd!r}", r == "refused")
NOW_MS = int(__import__("time").time() * 1000)
FakeRoblox.answers = [script("128.116.44.33", extra=None)]
FakeRoblox.answers[0]["joinScript"].update({"ServerClaimedTime": NOW_MS - 6 * 3600 * 1000, "DataCenterId": 25960, "PlaceVersion": 1805})
i = c.server_info(11, JOB)
check("the join answer also gives when the server started, its data centre and its place version", i == {"address": "128.116.44.33", "started_ms": NOW_MS - 6 * 3600 * 1000, "dc": 25960, "place_version": 1805}, i)
for name, value in (("missing", None), ("text", "yesterday"), ("a boolean", True), ("zero", 0), ("negative", -5), ("in the future", NOW_MS + 10 * 86400 * 1000), ("long ago (seconds, not milliseconds)", 1792672523)):
    FakeRoblox.answers = [script("128.116.44.33")]
    FakeRoblox.answers[0]["joinScript"]["ServerClaimedTime"] = value
    check(f"a start time that is {name} is left out", c.server_info(11, JOB)["started_ms"] is None, name)
FakeRoblox.answers = [{"status": 2, "joinScript": {"udmuxEndpoints": [{"address": "128.116.5.9"}], "serverClaimedTime": NOW_MS - 1000, "dataCenterId": 7, "placeVersion": 3}}]
check("camelCase names are read too", c.server_info(11, JOB) == {"address": "128.116.5.9", "started_ms": NOW_MS - 1000, "dc": 7, "place_version": 3})
FakeRoblox.answers = [{"status": 2, "joinScript": {"ServerConnections": [{"Address": "128.116.31.33", "Port": 1}], "MachineAddress": "10.0.0.1"}}]
check("the server connections are used when there are no udmux endpoints", c.server_info(11, JOB)["address"] == "128.116.31.33")
FakeRoblox.answers = [script("128.116.44.33")]
log_text = (rbx.STATE_DIR / "requests.log").read_text(encoding="utf-8", errors="replace") if (rbx.STATE_DIR / "requests.log").exists() else ""
check("the tickets of the join answer are not in the request log", "SECRET" not in log_text)

# ================================================================ the lookup of an address
check("only public IPv4 addresses are looked up", [geo.public_ipv4(x) for x in ("128.116.44.33", " 8.8.8.8 ", "10.1.2.3", "192.168.0.1", "127.0.0.1", "169.254.2.2", "::1", "2606:4700::1111", "x", "", None)]
      == ["128.116.44.33", "8.8.8.8", None, None, None, None, None, None, None, None, None])
check("an address is kept by its first three numbers", geo.block_of("128.116.44.33") == "128.116.44")
GOOD = {"success": True, "country": "Germany", "country_code": "DE", "region": "Hessen", "city": "Frankfurt am Main", "latitude": 50.1155207, "longitude": 8.6841662}
asked = []


def fake(url):
    asked.append(url)
    return GOOD


p = geo.lookup("128.116.44.33", fake, now=1000)
check("an address gives its place", p == {"city": "Frankfurt am Main", "region": "Hessen", "country": "Germany", "cc": "DE", "lat": 50.116, "lon": 8.684}, p)
check("...asked of ipwho.is, with only the address in the address", asked == ["https://ipwho.is/128.116.44.33"], asked)
check("the place is written as a label", geo.label(p) == "Frankfurt am Main, Germany" and geo.label({}) == "Unknown")
p2 = geo.lookup("128.116.44.77", fake, now=2000)
check("another address of the same block is not asked again (the answer is kept)", p2 == p and len(asked) == 1, asked)
check("the kept answers are private to this user", (geo.CACHE_FILE.stat().st_mode & 0o777) == 0o600 if os.name == "posix" else True)
geo.lookup("128.116.97.20", lambda u: dict(GOOD, city="Singapore", country="Singapore", country_code="SG", latitude=1.3, longitude=103.8), now=2000)
check("another block is asked", len(json.loads(geo.CACHE_FILE.read_text())) == 2)
geo.lookup("128.116.44.33", fake, now=1000 + geo.TTL + 1)
check("an old answer is asked again (after 30 days)", len(asked) == 2, asked)


def boom(url):
    raise geo.requests.ConnectionError("down")


for name, bad in (("success false", {"success": False}), ("no position", {"success": True}), ("a position out of range", dict(GOOD, latitude=91)), ("text for a position", dict(GOOD, longitude="8")),
                  ("a boolean for a position", dict(GOOD, latitude=True)), ("not an object", ["x"])):
    try:
        geo.lookup("128.116.55.9", lambda u, b=bad: b, now=5)
        r = "accepted"
    except geo.GeoError as e:
        r = str(e)
    check(f"a wrong answer is refused: {name}", r != "accepted" and len(r) > 10, r)
try:
    geo.lookup("128.116.55.9", boom, now=5)
    r = "accepted"
except geo.GeoError as e:
    r = str(e)
check("a service that cannot be reached says so in plain words", "could not be reached" in r, r)
n = len(asked)
try:
    geo.lookup("10.0.0.1", fake, now=5)
except geo.GeoError:
    pass
check("a private address is never sent to the service", len(asked) == n)
long = geo.clean(dict(GOOD, city="x" * 500))
check("text of the answer is limited in length", len(long["city"]) == 60)
geo.CACHE_FILE.write_text("{not json")
check("a damaged answer file is ignored", geo.lookup("128.116.44.33", fake, now=9) == p)
for i in range(600):
    geo.lookup(f"20.{i % 250}.{i // 250}.1", fake, now=100 + i)
check("at most 500 answers are kept", len(json.loads(geo.CACHE_FILE.read_text())) <= geo.MAX_CACHED)

# ================================================================ RoSeal's list of data centres, and the choice of service
GROUPS = [{"id": 1, "dataCenterIds": [295, 25960], "robloxIps": ["1.2.3.4"], "location": {"city": "Frankfurt", "region": "Hesse", "country": "DE", "latLong": ["50.1155", "8.6842"]}},
          {"id": 2, "dataCenterIds": [25853], "location": {"city": "Singapore", "region": "Singapore", "country": "SG", "latLong": ["1.2897", "103.8501"]}}]
check("RoSeal's list is read (text positions become numbers)", geo.clean_groups(GROUPS)[0] == {"ids": {295, 25960}, "city": "Frankfurt", "region": "Hesse", "cc": "DE", "lat": 50.115, "lon": 8.684}, geo.clean_groups(GROUPS)[0])
bad_groups = [{"dataCenterIds": [1], "location": {"city": "x", "latLong": ["95", "0"]}}, {"dataCenterIds": [1], "location": {"city": "x", "latLong": ["a", "b"]}},
              {"dataCenterIds": ["x", True], "location": {"city": "x", "latLong": ["1", "2"]}}, {"dataCenterIds": [1]}, "junk", None, {"dataCenterIds": [5], "location": {"city": "y" * 500, "latLong": [1, 2]}}]
check("wrong entries of the list are dropped, long text is cut", [g["ids"] for g in geo.clean_groups(bad_groups)] == [{5}] and len(geo.clean_groups(bad_groups)[0]["city"]) == 60)
check("anything that is not a list gives nothing", geo.clean_groups({"a": 1}) == [] and geo.clean_groups(None) == [])
fetched = []


def roseal(url):
    fetched.append(url)
    return GROUPS


check("a data centre id gives its place from RoSeal's list", geo.place_for_dc(25960, roseal, now=10) == {"city": "Frankfurt", "region": "Hesse", "country": "", "cc": "DE", "lat": 50.115, "lon": 8.684})
check("...asked of data.roseal.live, a plain download", fetched == ["https://data.roseal.live/v2/grouped-datacenters.json"], fetched)
check("a data centre that is not in the list gives None", geo.place_for_dc(999, roseal, now=11) is None)
check("the list is kept for 6 hours (not downloaded again)", len(fetched) == 1, fetched)
geo.place_for_dc(25853, roseal, now=10 + geo.ROSEAL_TTL + 1)
check("...and downloaded again after that", len(fetched) == 2)


def down(url):
    raise geo.requests.ConnectionError("down")


check("when it cannot be downloaded, the old list is used", geo.place_for_dc(25853, down, now=10 + 3 * geo.ROSEAL_TTL)["city"] == "Singapore")
geo.ROSEAL_FILE.unlink()
try:
    geo.place_for_dc(25853, down, now=5)
    r = "found"
except geo.GeoError as e:
    r = str(e)
check("...and with no old list, it says so in plain words", "could not be downloaded" in r, r)
try:
    geo.place_for_dc(25853, lambda u: {"x": 1}, now=5)
    r = "found"
except geo.GeoError as e:
    r = str(e)
check("a list that does not look right is refused", "did not look right" in r, r)
geo.CACHE_FILE.unlink(missing_ok=True)
geo.ROSEAL_FILE.unlink(missing_ok=True)
fetched.clear()
asked_ip = []
info = {"address": "128.116.44.33", "dc": 25960, "started_ms": 1, "place_version": 1}
check("RoSeal's list says where a server is when the person allowed it (and nothing is sent to ipwho.is)",
      geo.resolve(info, True, False, roseal, lambda u: asked_ip.append(u), now=100)["city"] == "Frankfurt" and not asked_ip and len(fetched) == 1)
check("the answer is kept by data centre: the next server there needs no download and no lookup", geo.resolve(dict(info, address="128.116.99.1"), True, True, roseal, lambda u: asked_ip.append(u), now=200)["city"] == "Frankfurt"
      and len(fetched) == 1 and not asked_ip)
check("...also when both services are switched off afterwards (nothing is contacted)", geo.resolve(info, False, False, roseal, lambda u: asked_ip.append(u), now=300)["city"] == "Frankfurt" and len(fetched) == 1)
try:
    geo.resolve({"address": "128.116.31.33", "dc": 77, "started_ms": None, "place_version": None}, False, False, roseal, fake, now=100)
    r = "found"
except geo.GeoError as e:
    r = str(e)
check("with both services off, a new data centre is not looked up at all and the reason is clear", r == "Server locations are switched off in Settings" and len(fetched) == 1, r)
try:
    geo.resolve({"address": "128.116.31.33", "dc": 77, "started_ms": None, "place_version": None}, True, False, roseal, fake, now=100)
    r = "found"
except geo.GeoError as e:
    r = str(e)
check("a data centre RoSeal does not know is reported (and ipwho.is is not used without permission)", "does not know this data centre" in r and "ipwho.is is switched off" in r, r)
n = len(asked)
p3 = geo.resolve({"address": "128.116.31.33", "dc": 77, "started_ms": None, "place_version": None}, True, True, roseal, fake, now=100)
check("with ipwho.is allowed too, it is the fallback for a data centre RoSeal does not know", p3["city"] == "Frankfurt am Main" and len(asked) == n + 1, p3)
p4 = geo.resolve({"address": "128.116.97.50", "dc": None, "started_ms": None, "place_version": None}, True, True, roseal, lambda u: dict(GOOD, city="Singapore", country="Singapore", country_code="SG", latitude=1.3, longitude=103.8), now=100)
check("a join answer without a data centre id uses ipwho.is when allowed", p4["city"] == "Singapore")
try:
    geo.resolve({"address": "128.116.97.51", "dc": None, "started_ms": None, "place_version": None}, True, False, down, fake, now=100)
    r = "found"
except geo.GeoError as e:
    r = str(e)
check("RoSeal's list alone cannot place a server without a data centre id, and says so", r != "found" and len(r) > 10, r)
geo.CACHE_FILE.unlink(missing_ok=True)
geo.ROSEAL_FILE.unlink(missing_ok=True)

# ================================================================ the map
check("the land of the world is there (128 rings of Natural Earth)", len(worldmap.land()) > 100, len(worldmap.land()))
check("...every point is a real longitude and latitude", all(-180 <= lon <= 180 and -90 <= lat <= 90 for ring in worldmap.land() for lon, lat in ring))
check("the map is twice as wide as high: the middle of the world is the middle of the picture", worldmap.project(0, 0, 720, 360) == (360, 180))
check("...the corners are the corners", worldmap.project(90, -180, 720, 360) == (0, 0) and worldmap.project(-90, 180, 720, 360) == (720, 360))
check("...Frankfurt is in the upper middle", 360 < worldmap.project(50.1, 8.7, 720, 360)[0] < 400 and worldmap.project(50.1, 8.7, 720, 360)[1] < 120)
servers = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
places = {"a": {"lat": 50.1, "lon": 8.7}, "b": {"lat": 1.3, "lon": 103.8}, "c": {"lat": 50.1, "lon": 8.7}}
g = worldmap.group_places(servers, places)
check("servers in the same place share a dot; a server that is not located has none", sorted(len(ids) for _, ids in g) == [1, 2] and ["a", "c"] in [ids for _, ids in g], g)
m = worldmap.WorldMap()
m.resize(720, 360)
m.set_dots([{"lat": 50.1, "lon": 8.7, "label": "Frankfurt", "ids": ["a", "c"]}])
img = m.grab().toImage()
x, y = (int(v) for v in worldmap.project(50.1, 8.7, 720, 360))
check("the map draws a dot (the accent colour) where the server is", QColor(img.pixel(x, y)).name() == T["accent"], QColor(img.pixel(x, y)).name())
x, y = (int(v) for v in worldmap.project(48, 10, 720, 360))
land_px = QColor(img.pixel(x + 40, y)).name()
x2, y2 = (int(v) for v in worldmap.project(10, -35, 720, 360))
check("...land and sea have their own colours", land_px != QColor(img.pixel(x2, y2)).name() and QColor(img.pixel(x2, y2)).name() == T["surface"], (land_px, QColor(img.pixel(x2, y2)).name()))
got = []
m.picked.connect(lambda ids: got.append(ids))
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
QTest.mouseClick(m, Qt.MouseButton.LeftButton, pos=QPoint(*(int(v) for v in worldmap.project(50.1, 8.7, 720, 360))))
check("pressing a dot gives the servers there", got == [["a", "c"]], got)
QTest.mouseClick(m, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
check("pressing the sea gives nothing", got == [["a", "c"]])
check("the map keeps two to one when the window is resized", m.heightForWidth(800) == 400)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
