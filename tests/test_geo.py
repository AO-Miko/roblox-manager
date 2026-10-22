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


rbx.Client.JOIN_WAIT = 0.01
c = FakeRoblox()

# ================================================================ the address from Roblox's join answer
FakeRoblox.answers = [script("128.116.44.33")]
check("a join answer gives the server's public address", c.server_address(11, JOB) == "128.116.44.33")
url, body = FakeRoblox.calls[-1]
check("...asked like the website asks, for that place and that server, and nothing is joined by it", url == "https://gamejoin.roblox.com/v1/join-game-instance" and body["placeId"] == 11
      and body["gameId"] == JOB and body["isTeleport"] is False and len(body["gameJoinAttemptId"]) == 36, body)
FakeRoblox.answers, FakeRoblox.calls = [NOT_READY, NOT_READY, script("128.116.97.20")], []
check("'not ready' answers are asked again", c.server_address(11, JOB) == "128.116.97.20" and len(FakeRoblox.calls) == 3, len(FakeRoblox.calls))
FakeRoblox.answers, FakeRoblox.calls = [NOT_READY], []
try:
    c.server_address(11, JOB)
    msg = "no error"
except rbx.RobloxError as e:
    msg = str(e)
check("...but not for ever (4 times), and then it says so", "did not give this server's address" in msg and len(FakeRoblox.calls) == 4, (msg, len(FakeRoblox.calls)))
FakeRoblox.answers = [{"status": 2, "joinScript": json.dumps({"UdmuxEndpoints": [{"Address": "128.116.88.5"}]})}]
check("a join script that comes as text is read too", c.server_address(11, JOB) == "128.116.88.5")
for bad in (["10.0.0.5"], ["192.168.1.1"], ["127.0.0.1"], ["169.254.1.1"], ["::1"], ["not an address"], [], [None]):
    FakeRoblox.answers = [script(*bad)]
    try:
        r = c.server_address(11, JOB)
    except rbx.RobloxError:
        r = None
    check(f"a private or odd address is never used: {bad}", r is None, r)
FakeRoblox.answers = [script("10.0.0.5", "128.116.5.3")]
check("the first PUBLIC address is taken", c.server_address(11, JOB) == "128.116.5.3")
for odd in ("x&y=1", "a b", "../x", ""):
    try:
        c.server_address(11, odd)
        r = "accepted"
    except ValueError:
        r = "refused"
    check(f"an odd server id is refused before anything is sent: {odd!r}", r == "refused")
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
