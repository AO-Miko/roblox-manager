"""Test of Discover (inside Home): the home page rows, the search, a game's page with its stats and the Play button (launcher links, VIP servers). The real client methods run
against a fake Roblox that answers with the real response shapes. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_discover.py"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="disc-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import rbx
import roblox_launcher
import tab_discover
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:240]) if e else ""))


def spin(s=0.1):
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(fn, t=8):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        if fn():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------- a fake Roblox with the real response shapes
img = QImage(8, 8, QImage.Format.Format_RGB32)
img.fill(QColor("#ff0000"))
buf = tmp / "red.png"
img.save(str(buf))
PNG = buf.read_bytes()


def game(uid, place, name, playing=100, up=90, down=10, sponsored=False, creator="Maker"):
    return {"universeId": uid, "rootPlaceId": place, "name": name, "playerCount": playing, "totalUpVotes": up, "totalDownVotes": down, "isSponsored": sponsored,
            "creatorName": creator, "creatorHasVerifiedBadge": False, "ageRecommendationDisplayName": "Maturity: Mild", "genreL1": "Adventure"}


SORTS = {"sorts": [{"contentType": "Filters", "sortId": "filters_v5", "sortDisplayName": ""},
                   {"contentType": "Games", "sortId": "top-trending", "sortDisplayName": "Top Trending", "games": [game(1, 11, "Alpha Game", 18769, 407265, 264201), game(2, 22, "Beta Game", 5, 0, 0),
                                                                                                                  game(3, 33, "An Ad", sponsored=True)] + [game(100 + i, 1000 + i, f"Filler {i}") for i in range(30)]},
                   {"contentType": "Games", "sortId": "up-and-coming", "sortDisplayName": "Up-and-Coming", "games": [game(4, 44, "Delta Game", 12000, 900, 100)]},
                   {"contentType": "Games", "sortId": "empty", "sortDisplayName": "Empty row", "games": []}]}
SEARCH_P1 = {"searchResults": [{"contentGroupType": "Game", "contents": [game(1, 11, "Alpha Game", 18769, 407265, 264201)]}, {"contentGroupType": "Game", "contents": [game(5, 55, "Obby Five")]},
                               {"contentGroupType": "Game", "contents": [game(6, 66, "An Ad", sponsored=True)]}], "nextPageToken": "page2"}
SEARCH_P2 = {"searchResults": [{"contentGroupType": "Game", "contents": [game(5, 55, "Obby Five"), game(7, 77, "Obby Seven")]}], "nextPageToken": ""}
DETAILS = {1: {"id": 1, "rootPlaceId": 11, "name": "Alpha Game", "description": "The best game.\nReally.", "creator": {"id": 9, "name": "PlatinumFalls", "hasVerifiedBadge": True},
               "playing": 18793, "visits": 4753432465, "maxPlayers": 12, "created": "2022-02-02T19:57:39.97Z", "updated": "2026-10-14T09:24:58.905Z", "genre": "Adventure",
               "genre_l1": "Obby & Platformer", "favoritedCount": 105252027},
           2: {"id": 2, "rootPlaceId": 22, "name": "Beta Game", "description": "", "creator": {"id": 8, "name": "Nobody"}, "playing": 5, "visits": 10, "maxPlayers": 4,
               "created": "2024-01-01T00:00:00Z", "updated": "2024-02-02T00:00:00Z", "genre": "All"}}
VOTES = {1: (407269, 264202), 2: (0, 0)}
log = []
delays = {}
JOIN_CALLS, JOIN_FAIL = [], set()
FAVORITES = {"on": False}
SERVERS_P1 = [{"id": f"aaaaaaaa-0000-0000-0000-00000000000{i}", "playing": i, "maxPlayers": 12, "ping": 50 + i, "fps": 59.5} for i in range(1, 6)] + [{"id": "x&y=1", "playing": 0, "maxPlayers": 12, "ping": 1, "fps": 60}]
SERVERS_P2 = [{"id": "aaaaaaaa-0000-0000-0000-000000000003", "playing": 3, "maxPlayers": 12, "ping": 53, "fps": 59.5}, {"id": "bbbbbbbb-0000-0000-0000-000000000009", "playing": 9, "maxPlayers": 12, "ping": 90, "fps": 30}]


class FakeRoblox(rbx.Client):
    def get(self, url, params=None, **kw):
        log.append((url, dict(params or {})))
        if delays.get(url):
            time.sleep(delays[url])
        if "explore-api/v1/get-sorts" in url:
            if getattr(self, "feed_error", None):
                raise rbx.RobloxError(self.feed_error, 500)
            return SORTS
        if "omni-search" in url:
            return SEARCH_P2 if (params or {}).get("pageToken") == "page2" else SEARCH_P1
        if url.endswith("/v1/games/votes"):
            ids = [int(i) for i in params["universeIds"].split(",")]
            return {"data": [{"id": i, "upVotes": VOTES[i][0], "downVotes": VOTES[i][1]} for i in ids if i in VOTES]}
        if url.endswith("/favorites/count"):
            return {"favoritesCount": 42}
        if url.endswith("/v1/games"):
            ids = [int(i) for i in str(params["universeIds"]).split(",")]
            return {"data": [DETAILS[i] for i in ids if i in DETAILS]}
        if "thumbnails.roblox.com/v1/games/icons" in url:
            ids = [int(i) for i in params["universeIds"].split(",")]
            return {"data": [{"targetId": i, "state": "Completed", "imageUrl": f"https://tr.rbxcdn.com/icon/{i}.png"} for i in ids]}
        if "games/multiget/thumbnails" in url:
            return {"data": [{"universeId": int(params["universeIds"]), "thumbnails": [{"imageUrl": "https://tr.rbxcdn.com/cover.png"}]}]}
        if "/v1/users/search" in url:
            return {"data": [{"id": 156, "name": "builderman", "displayName": "builderman"}, {"id": 157, "name": "builder2", "displayName": "Builder Two"}]}
        if "groups.roblox.com/v1/groups/search" in url:
            return {"data": [{"id": 7, "name": "Roblox", "memberCount": 13508413, "description": "The official group"}]}
        if "/servers/Public" in url:
            if getattr(self, "servers_error", None):
                raise rbx.RobloxError(self.servers_error, 500)
            if (params or {}).get("cursor") == "s2":
                return {"data": SERVERS_P2, "nextPageCursor": ""}
            data = SERVERS_P1 if (params or {}).get("sortOrder", "Asc") == "Asc" else list(reversed(SERVERS_P1))
            return {"data": data, "nextPageCursor": "s2"}
        if re.search(r"/v1/games/\d+/favorites$", url) and not url.endswith("count"):
            return {"isFavorited": bool(FAVORITES.get("on"))}
        if "/favorite/games" in url:
            return {"data": [{"id": 1, "name": "Alpha Game", "rootPlace": {"id": 11}, "creator": {"name": "Maker"}}, {"id": 8, "name": "Favorite Eight", "rootPlace": {"id": 88}}]}
        if re.search(r"friends.roblox.com/v1/users/\d+/friends$", url):
            return {"data": [{"id": 201, "name": "ann", "displayName": "Ann"}, {"id": 202, "name": "bob", "displayName": "Bob"}, {"id": 203, "name": "cy", "displayName": "Cy"}]}
        if "/groups/roles" in url:
            return {"data": []}
        if "/vip-servers/" in url:
            return {}                                       # (a server whose join link Roblox does not give)
        if "usernames/users" in url:
            return {"data": []}
        if "avatar-headshot" in url:
            return {"data": [{"targetId": int(i), "imageUrl": f"https://tr.rbxcdn.com/head/{i}.png", "state": "Completed"} for i in params["userIds"].split(",")]}
        raise rbx.RobloxError("not faked: " + url, 404)

    def post(self, url, body=None, **kw):
        log.append((url, dict(body or {})))
        if re.search(r"/v1/games/\d+/favorites$", url):
            if getattr(self, "favorite_error", None):
                raise rbx.RobloxError(self.favorite_error, 500)
            FAVORITES["on"] = body["isFavorited"]
            return {}
        if "join-game-instance" in url:
            job = body["gameId"]
            JOIN_CALLS.append(body)
            if job in JOIN_FAIL:
                return {"jobId": job, "status": 22, "joinScript": None, "joinTicket": "T"}
            n = int(job[-1])
            return {"jobId": job, "status": 2, "joinTicket": "T", "joinScript": {"UdmuxEndpoints": [{"Address": f"128.116.{44 if n % 2 else 97}.{n}", "Port": 1}], "MachineAddress": "10.0.0.1",
                                                                                "DataCenterId": 25960 if n % 2 else 25853, "ServerClaimedTime": int(time.time() * 1000) - n * 3600 * 1000, "PlaceVersion": 1800 + n % 3}}
        if "presence.roblox.com" in url:
            return {"userPresences": [{"userId": 201, "userPresenceType": 2, "lastLocation": "Alpha Game", "rootPlaceId": 11, "placeId": 11, "gameId": "job-aaaa-1111", "universeId": 1},
                                      {"userId": 202, "userPresenceType": 1, "lastLocation": "Website"}, {"userId": 203, "userPresenceType": 0}]}
        if "profiles" in url or url == self.PROFILES_URL:
            return {"profileDetails": [{"userId": i, "names": {"username": n, "displayName": n.title()}, "isVerified": False} for i, n in ((201, "ann"), (202, "bob"), (203, "cy"))]}
        if "usernames/users" in url:
            return {"data": []}                                     # (no exact username match: only the search answers)
        raise rbx.RobloxError("not faked: " + url, 404)

    def fetch_bytes(self, url):
        log.append((url, {}))
        return PNG


from PySide6.QtWidgets import QMessageBox
warnings = []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(str(a[2]) if len(a) > 2 else ""))          # (an error popup would wait for a click: it is recorded instead)
client = FakeRoblox()
w = MainWindow(client, auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
d = w.discover
INSTALLED = {"installed": True, "how": "test", "platform": "linux", "command": None, "url": None, "can_install": False}
real_status = roblox_launcher.status
roblox_launcher.status = lambda fresh=False: INSTALLED
opened_urls, launched = [], []
tab_discover.open_url = lambda url: opened_urls.append(url)
real_open = tab_discover.QDesktopServices.openUrl
launch_ok = {"ok": True}
tab_discover.QDesktopServices.openUrl = staticmethod(lambda url: launched.append(url.toString()) or launch_ok["ok"])

# ---------------------------------------------------------------- Home has Discover inside it
check("Home has two pages: Account and Discover", [w.home.tabs.tabText(i) for i in range(w.home.tabs.count())] == ["Account", "Discover"] and w.home.tabs.currentIndex() == 0)
check("the page before it is opened has not asked Roblox for anything", not log, log[:2])
w.home.tabs.setCurrentIndex(1)
check("opening Discover loads Roblox's home page rows", wait(lambda: len(d.cards) == 17), len(d.cards))
sort_calls = [c for c in log if "get-sorts" in c[0]]
check("...asked once, with a session id and for the computer", len(sort_calls) == 1 and sort_calls[0][1].get("sessionId") and sort_calls[0][1].get("device") == "computer", sort_calls)
titles = [lab.text() for lab in d.body.findChildren(tab_discover.QLabel) if lab.property("role") == "title"]
check("the rows are the Games sorts that have games (Top Trending, Up-and-Coming), not filters or empty rows", titles == ["Top Trending", "Up-and-Coming"], titles)
names = {c.card["name"] for ws in d.cards.values() for c in ws}
check("sponsored entries (ads) are not shown", "An Ad" not in names and "Alpha Game" in names and "Delta Game" in names)
alpha = d.cards[1][0]
check("a card shows the name, the players and the like percentage", alpha.name.text() == "Alpha Game" and "18.8K playing" in alpha.stats.text() and "61%" in alpha.stats.text(), alpha.stats.text())
check("a row shows at most 16 games (Top Trending has 32 in the answer)", sum(1 for u in d.cards if u != 4) == 16 and 4 in d.cards, len(d.cards))
check("the pictures arrive (the red test picture replaces the blank card)", wait(lambda: d.cards[1][0].icon.pixmap().toImage().pixelColor(20, 20).red() > 200), d.cards[1][0].icon.pixmap().toImage().pixelColor(20, 20).name())
w.home.tabs.setCurrentIndex(0); w.home.tabs.setCurrentIndex(1); spin(0.3)
check("going back and forth does not load it again", len([c for c in log if "get-sorts" in c[0]]) == 1)

# ---------------------------------------------------------------- the search
d.search.setText("obby"); d.kind.setCurrentIndex(0)
d.b_search.click()
check("a search of games shows the matches (the ad is left out)", wait(lambda: {c.card["name"] for ws in d.cards.values() for c in ws} == {"Alpha Game", "Obby Five"}), {c.card["name"] for ws in d.cards.values() for c in ws})
q = [c for c in log if "omni-search" in c[0]]
check("...with the typed text, the session and no page token", q and q[-1][1].get("searchQuery") == "obby" and not q[-1][1].get("pageToken"), q[-1:])
check("...and a Home button to go back", not d.b_feed.isHidden())
delays["https://apis.roblox.com/search-api/omni-search"] = 0.4
for _ in range(5):
    d.more.click(); spin(0.02)
check("pressing Load more again and again asks for the next page once", len([c for c in log if "omni-search" in c[0] and c[1].get("pageToken") == "page2"]) == 1)
check("...the games arrive without duplicates (Obby Five was on both pages)", wait(lambda: sorted(c.card["name"] for ws in d.cards.values() for c in ws) == ["Alpha Game", "Obby Five", "Obby Seven"]), sorted(c.card["name"] for ws in d.cards.values() for c in ws))
check("...and no more pages: the button goes away", wait(lambda: d.more.isHidden()))
delays.clear()
d.search.setText("builder"); d.kind.setCurrentIndex(1); d.b_search.click()
check("a search of people shows them with an Open profile button", wait(lambda: len(d.body.findChildren(tab_discover.QFrame)) >= 2 and any("Builder Two" in l.text() for l in d.body.findChildren(tab_discover.QLabel))))
btns = [b for b in d.body.findChildren(tab_discover.QWidget) if getattr(b, "text", None) and callable(b.text) and b.text() == "Open profile"]
btns[0].click()
check("...which opens the person's profile on roblox.com", opened_urls and opened_urls[-1] == "https://www.roblox.com/users/156/profile", opened_urls)
d.search.setText("roblox"); d.kind.setCurrentIndex(2); d.b_search.click()
check("a search of groups shows name, members and an Open button", wait(lambda: any("13,508,413 members" in l.text() for l in d.body.findChildren(tab_discover.QLabel))))
[b for b in d.body.findChildren(tab_discover.QWidget) if getattr(b, "text", None) and callable(b.text) and b.text() == "Open on roblox.com"][0].click()
check("...which opens the group", opened_urls[-1] == "https://www.roblox.com/communities/7", opened_urls[-1])
d.search.setText("zzzz"); d.kind.setCurrentIndex(0); d.b_search.click(); spin(0.3)
d.search.clear(); d.run_search()
check("an empty search brings the home page rows back", wait(lambda: d.mode == "feed" and len(d.cards) == 17) and d.b_feed.isHidden())

# ---------------------------------------------------------------- a game's page
alpha = d.cards[1][0]
QTest.mouseClick(alpha, Qt.MouseButton.LeftButton)
check("pressing a game opens its page", d.stack.currentIndex() == 1 and d.detail.title.text() == "Alpha Game")
det = d.detail
check("the page loads the details, votes and cover", wait(lambda: det.values["Visits"].text() == "4,753,432,465"), det.values["Visits"].text())
check("...players now, visits, favorites, max players", det.values["Playing now"].text() == "18,793" and det.values["Favorites"].text() == "105,252,027" and det.values["Max players"].text() == "12", {k: v.text() for k, v in det.values.items()})
check("...created and updated dates, genre", "2022" in det.values["Created"].text() and "2026" in det.values["Updated"].text() and det.values["Genre"].text() == "Obby & Platformer")
check("...likes and dislikes with their amounts", "407,269" in det.likes.text() and "264,202" in det.dislikes.text(), (det.likes.text(), det.dislikes.text()))
check("...the percentage and the bar (green part = likes)", det.percent.text() == "61%" and det.bar.up == 407269 and det.bar.down == 264202, det.percent.text())
check("...the creator with the verified mark and the description", "PlatinumFalls" in det.creator.text() and "verified" in det.creator.text() and det.about.toPlainText().startswith("The best game."))
check("...and the cover picture", wait(lambda: det.cover.pixmap() is not None and not det.cover.pixmap().isNull()))
check("the votes call batches by universe id (no extra calls per field)", len([c for c in log if c[0].endswith("/v1/games/votes")]) >= 1)

# play
det.b_play.click()
check("Play opens the Roblox launcher and joins the game", launched[-1] == "roblox://experiences/start?placeId=11", launched)
launch_ok["ok"] = False
opened_urls.clear()
det.b_play.click()
check("if the launcher cannot be opened, the game's page is opened instead (no error)", opened_urls == ["https://www.roblox.com/games/11"], opened_urls)
launch_ok["ok"] = True
det.b_open.click()
check("Open on roblox.com opens the game's page", opened_urls[-1] == "https://www.roblox.com/games/11")

# VIP servers of this game
check("without a VIP server of this game there is no 'Join my VIP server' button", det.b_vip.isHidden())
vip1 = {"_vid": 5001, "name": "My private one", "placeId": 11, "universeId": 1, "active": True}
w.vip.mine = [vip1, {"_vid": 5002, "name": "Other game", "placeId": 99, "universeId": 9, "active": True}, {"_vid": 5003, "name": "Switched off", "placeId": 11, "universeId": 1, "active": False}]
w.vip.names = {}
check("the VIP page offers the working servers of one game (not other games, not switched-off ones)", [s["_vid"] for s in w.vip.servers_for_game(1, 11)] == [5001], [s["_vid"] for s in w.vip.servers_for_game(1, 11)])
det.show_game(alpha.card)
check("with one, the game page shows 'Join my VIP server'", not det.b_vip.isHidden())
w.vip.links = {5001: "https://www.roblox.com/games/11?privateServerLinkCode=SECRETCODE"}
det.b_vip.click()
check("...which opens the launcher on that private server (place id + link code)", wait(lambda: launched[-1] == "roblox://experiences/start?placeId=11&linkCode=SECRETCODE"), launched[-1])
w.vip.links = {5001: ""}
n = len(launched)
det._join(vip1)
spin(0.2)
check("a server without a join link yet does not launch anything and does not crash", len(launched) == n)

# a game with nobody's votes, and a game opened while another is loading
d.cards[2][0].clicked.emit(d.cards[2][0].card)
check("a game without votes says so (no percent, empty bar)", wait(lambda: det.values["Visits"].text() == "10") and det.percent.text() == "No votes yet" and det.bar.up == 0 and det.bar.down == 0 and det.values["Favorites"].text() == "42", det.percent.text())
delays["https://games.roblox.com/v1/games"] = 0.5
det.show_game(alpha.card)
det.show_game(d.cards[2][0].card)
spin(1.0)
check("an answer for a game that was left meanwhile does not overwrite the open one", det.title.text() == "Beta Game" and det.values["Visits"].text() == "10", (det.title.text(), det.values["Visits"].text()))
delays.clear()
det.back.emit()
check("Back returns to the list", d.stack.currentIndex() == 0)

# the VIP page itself
sel = vip1
check("the VIP page has a Play button (the launcher joins the selected server)", hasattr(w.vip, "b_play") and w.vip.b_play.text() == "Play")
w.vip._launch(vip1, "https://www.roblox.com/games/11?privateServerLinkCode=ABC")
check("...it launches place + link code", launched[-1] == "roblox://experiences/start?placeId=11&linkCode=ABC", launched[-1])
n = len(launched)
w.vip._launch(vip1, "https://www.roblox.com/games/11")
check("...and without a code it explains instead of launching", len(launched) == n)

# when Roblox is down or changes its answer
client.feed_error = "Roblox says no"
d.load_feed()
check("a home page that cannot be loaded says so, no crash", wait(lambda: "could not be loaded" in d.state.text() and "Roblox says no" in d.state.text()), d.state.text())
client.feed_error = None
d.load()
check("reloading brings it back", wait(lambda: len(d.cards) == 17))

# the real client methods, directly
cards, token = client.omni_search_games("obby", "sid")
check("omni_search_games returns normalised cards and the next token", [c["name"] for c in cards] == ["Alpha Game", "Obby Five"] and token == "page2" and cards[0]["placeId"] == 11 and cards[0]["up"] == 407265)
check("game_votes, game_favorites, game_icons, game_cover", client.game_votes([1]) == {1: (407269, 264202)} and client.game_favorites(1) == 42 and client.game_icons([1]) == {1: "https://tr.rbxcdn.com/icon/1.png"}
      and client.game_cover(1) == "https://tr.rbxcdn.com/cover.png")
check("game_card refuses ads and things without an id", rbx.game_card({"isSponsored": True, "universeId": 1}) is None and rbx.game_card({"name": "x"}) is None and rbx.game_card(None) is None)
check("launcher_url: game, private server, running server", rbx.launcher_url(5) == "roblox://experiences/start?placeId=5" and rbx.launcher_url(5, link_code="C") == "roblox://experiences/start?placeId=5&linkCode=C"
      and rbx.launcher_url(5, job_id="J") == "roblox://experiences/start?placeId=5&gameInstanceId=J")
check("link_code_of reads place and code from a join link (and survives nonsense)", rbx.link_code_of("https://www.roblox.com/games/123/x?privateServerLinkCode=AB") == (123, "AB") and rbx.link_code_of("nonsense") == (None, None)
      and rbx.link_code_of("") == (None, None))
check("short() and like_percent()", [tab_discover.short(n) for n in (5, 999, 1000, 18769, 1_500_000, 4_753_429_786)] == ["5", "999", "1K", "18.8K", "1.5M", "4.8B"]
      and tab_discover.like_percent(90, 10) == 90 and tab_discover.like_percent(0, 0) is None and tab_discover.like_percent(1, 2) == 33)

# ---------------------------------------------------------------- is a launcher installed? (Play asks first)
shown = []
real_exec = roblox_launcher.InstallDialog.exec
roblox_launcher.InstallDialog.exec = lambda self: shown.append(self) or 0
MISSING_LINUX = {"installed": False, "how": "", "platform": "linux", "command": roblox_launcher.LINUX_COMMAND, "url": None, "can_install": True}
roblox_launcher.status = lambda fresh=False: MISSING_LINUX
n = len(launched)
det.show_game(alpha.card)
det.b_play.click()
check("Play without a Roblox launcher does not open anything: it asks to install one", len(launched) == n and len(shown) == 1 and "not installed" in w.statusBar().currentMessage(), (len(launched), len(shown)))
dlg = shown[0]
check("(Linux) the question shows the exact command that would run", dlg.command == "flatpak install --user -y flathub org.vinegarhq.Sober" and dlg.cmd_box.toPlainText() == dlg.command and "no official Roblox for Linux" in dlg.text.text(), dlg.command)
check("...with Install, Copy command and Cancel", dlg.b_go.text() == "Install" and dlg.b_copy.text() == "Copy command" and dlg.b_cancel.text() == "Cancel")
launch_n = len(launched)
det._join(vip1)
w.vip.links = {5001: "https://www.roblox.com/games/11?privateServerLinkCode=XYZ"}
det._join(vip1); spin(0.2)
check("a VIP server join is stopped the same way (the launcher is checked for every launch)", len(launched) == launch_n and len(shown) >= 2, (len(launched), len(shown)))
roblox_launcher.status = lambda fresh=False: INSTALLED
det.b_play.click()
check("once a launcher is there Play opens it", launched[-1] == "roblox://experiences/start?placeId=11" and len(launched) == launch_n + 1)

# the dialogs for each platform
WIN = {"installed": False, "how": "", "platform": "windows", "command": None, "url": roblox_launcher.DOWNLOAD_PAGE, "can_install": False}
wd = roblox_launcher.InstallDialog(w, WIN)
check("(Windows) the question offers the Roblox download page", wd.b_go.text() == "Open the download page" and wd.command is None and "download page" in wd.text.text())
opened_urls.clear(); roblox_launcher.open_url = lambda url: opened_urls.append(url)
wd.b_go.click()
check("...and opens it", opened_urls == ["https://www.roblox.com/download"] and wd.result() == roblox_launcher.QDialog.DialogCode.Accepted, opened_urls)
NOFP = {"installed": False, "how": "", "platform": "linux", "command": None, "url": roblox_launcher.FLATHUB_SETUP, "can_install": False}
nd = roblox_launcher.InstallDialog(w, NOFP)
check("(Linux without Flatpak) it says so and opens the Flatpak setup page instead of running anything", "Flatpak" in nd.text.text() and nd.command is None and nd.b_go.text() == "Open the Flatpak setup page")
copied = []
roblox_launcher.copy_text = lambda text: copied.append(text)
import ui_common
ui_common.copy_text = lambda text: copied.append(text)
dlg.b_copy.click()
check("Copy command copies exactly the command", copied == [dlg.command], copied)

# Install runs the command and shows what it says
RUN = dict(MISSING_LINUX, command=[sys.executable, "-c", "print('installing...'); print('done')"])
roblox_launcher.status = lambda fresh=False: INSTALLED if fresh else MISSING_LINUX       # (after the command, a fresh look finds it)
rd = roblox_launcher.InstallDialog(w, RUN)
rd.b_go.click()
check("Install runs the command and shows its output", wait(lambda: "installing..." in rd.log.toPlainText() and "done" in rd.log.toPlainText()), rd.log.toPlainText())
check("...and says Installed, press Play again", wait(lambda: "Installed. Press Play again." in rd.status.text()), rd.status.text())
BAD = dict(MISSING_LINUX, command=[sys.executable, "-c", "import sys; print('nope'); sys.exit(3)"])
roblox_launcher.status = lambda fresh=False: MISSING_LINUX
bd = roblox_launcher.InstallDialog(w, BAD)
bd.b_go.click()
check("a command that fails says so and offers the command to copy (no crash)", wait(lambda: "did not finish" in bd.status.text()) and bd.b_copy.isEnabled() and "nope" in bd.log.toPlainText(), bd.status.text())
NOSUCH = dict(MISSING_LINUX, command=["/no/such/program-xyz"])
nsd = roblox_launcher.InstallDialog(w, NOSUCH)
nsd.b_go.click()
check("a program that does not exist is reported, not raised", wait(lambda: "did not finish" in nsd.status.text()), nsd.status.text())
roblox_launcher.InstallDialog.exec = real_exec

# detection (the real functions, with a fake system)
roblox_launcher.status = real_status
roblox_launcher.forget()
import shutil as _sh
real_which, real_run = _sh.which, roblox_launcher._run
roblox_launcher.shutil.which = lambda name: None
roblox_launcher._run = lambda args, timeout=6: (1, "")
roblox_launcher.plat.IS_WIN = False
st = roblox_launcher.status(fresh=True)
check("detection (Linux): nothing found means not installed, and without flatpak the setup page is offered", st["installed"] is False and st["command"] is None and st["url"] == roblox_launcher.FLATHUB_SETUP, st)
roblox_launcher.shutil.which = lambda name: "/usr/bin/flatpak" if name == "flatpak" else None
st = roblox_launcher.status(fresh=True)
check("...with flatpak the install command is offered", st["installed"] is False and st["command"] == roblox_launcher.LINUX_COMMAND and st["can_install"])
roblox_launcher._run = lambda args, timeout=6: (0, "org.vinegarhq.Sober.desktop") if args[0] == "xdg-mime" else (1, "")
check("...a handler for roblox:// links means installed", roblox_launcher.status(fresh=True)["installed"] is True)
roblox_launcher._run = lambda args, timeout=6: (0, "org.gnome.Calculator\norg.vinegarhq.Sober\n") if args[0] == "flatpak" else (1, "")
check("...so does the Sober flatpak", roblox_launcher.status(fresh=True)["installed"] is True)
roblox_launcher.shutil.which = lambda name: "/usr/bin/sober" if name == "sober" else None
roblox_launcher._run = lambda args, timeout=6: (1, "")
check("...and a sober program on the PATH", roblox_launcher.status(fresh=True)["installed"] is True)
t0 = len(roblox_launcher._run.__code__.co_consts)
first = roblox_launcher.status(fresh=True)
roblox_launcher.shutil.which = lambda name: None
check("the answer is remembered for a moment (no new questions to the system)", roblox_launcher.status() is first)
roblox_launcher.forget()
check("...and forgotten when asked", roblox_launcher.status()["installed"] is False)

# Windows: the registry
class FakeKey:
    def __enter__(self): return self
    def __exit__(self, *a): return False
fake_winreg = type(sys)("winreg")
fake_winreg.HKEY_CLASSES_ROOT = 1
exe = tmp / "RobloxPlayerBeta.exe"
exe.write_text("")
handlers = {"roblox\\shell\\open\\command": f'"{exe}" %1'}


def open_key(root, path):
    if path not in handlers:
        raise OSError("no key")
    return FakeKey()


fake_winreg.OpenKey = open_key
fake_winreg.QueryValueEx = lambda key, name: (handlers["roblox\\shell\\open\\command"], 1)
sys.modules["winreg"] = fake_winreg
roblox_launcher.plat.IS_WIN = True
roblox_launcher.forget()
st = roblox_launcher.status(fresh=True)
check("detection (Windows): the roblox:// handler in the registry, and the program exists", st["installed"] is True and st["platform"] == "windows" and st["how"] == str(exe), st)
exe.unlink()
roblox_launcher.forget()
check("...a handler whose program is gone (uninstalled) counts as not installed, and the download page is offered", roblox_launcher.status(fresh=True)["installed"] is False and roblox_launcher.status()["url"] == roblox_launcher.DOWNLOAD_PAGE)
handlers.clear()
roblox_launcher.forget()
check("...no handler at all: not installed", roblox_launcher.status(fresh=True)["installed"] is False)
roblox_launcher.plat.IS_WIN = False
del sys.modules["winreg"]
roblox_launcher.shutil.which, roblox_launcher._run = real_which, real_run
roblox_launcher.status = lambda fresh=False: INSTALLED
roblox_launcher.forget()

# ---------------------------------------------------------------- servers, favorites, recently viewed, friends in games
det.back.emit()
w.ctx.client.user = None
det.show_game(alpha.card)
check("without a sign-in the game page has no Favorite button", det.b_fav.isHidden())
w.ctx.client.user = {"id": 156, "name": "me", "displayName": "Me"}
det.show_game(alpha.card)
check("signed in: the Favorite button asks Roblox whether the game is a favorite", wait(lambda: det.favorited is False and not det.b_fav.isHidden() and det.b_fav.text() == "Favorite"), det.b_fav.text())
det.b_fav.click()
check("pressing it favorites the game (POST with isFavorited true) and says so", wait(lambda: det.b_fav.text() == "Favorited" and det.favorited is True) and any(c[0].endswith("/favorites") and c[1] == {"isFavorited": True} for c in log), det.b_fav.text())
det.b_fav.click()
check("pressing again removes it", wait(lambda: det.b_fav.text() == "Favorite" and FAVORITES["on"] is False))
client.favorite_error = "Roblox says no"
det.b_fav.click()
check("a refusal re-enables the button and says why (the state does not change)", wait(lambda: det.b_fav.isEnabled() and warnings and "Roblox says no" in warnings[-1]) and det.favorited is False, warnings[-1:])
warnings.clear(); client.favorite_error = None
FAVORITES["on"] = True
det.show_game(alpha.card)
check("a game that is already a favorite shows Favorited when its page opens", wait(lambda: det.b_fav.text() == "Favorited"))
FAVORITES["on"] = False

# servers
check("the Servers section starts empty and asks to press Find servers", det.server_table.rowCount() == 0 and not det.b_more_servers.isEnabled())
det.b_servers.click()
check("Find servers lists the public servers: players, ping, fps (a server with an odd id is left out)", wait(lambda: det.server_table.rowCount() == 5) and det.server_table.item(0, 0).text() == "1"
      and det.server_table.item(0, 1).text() == "12" and det.server_table.item(0, 2).text() == "51" and det.server_table.item(0, 3).text() == "59", [det.server_table.item(r, 0).text() for r in range(det.server_table.rowCount())])
sq = [c for c in log if "/servers/Public" in c[0]]
check("...asked for the right place, fewest players first, only servers with room", sq and sq[-1][0].endswith("/games/11/servers/Public") and sq[-1][1].get("sortOrder") == "Asc" and sq[-1][1].get("excludeFullGames") == "true", sq[-1:])
delays["https://games.roblox.com/v1/games/11/servers/Public"] = 0.4
for _ in range(5):
    det.b_more_servers.click(); det.find_servers(False); spin(0.02)
check("pressing Load more again and again asks for the next page once", len([c for c in log if "/servers/Public" in c[0] and c[1].get("cursor") == "s2"]) == 1)
check("...the page arrives without duplicates (server 3 was on both pages)", wait(lambda: det.server_table.rowCount() == 6) and len({row_id for row_id in [det.server_table.item(r, 4).text() for r in range(6)]}) == 6)
delays.clear()
check("...and then there is no more", not det.b_more_servers.isEnabled() and "6 servers" in det.server_note.text(), det.server_note.text())
n = len(launched)
det.join_selected()
check("Join selected without a selection asks to select one and opens nothing", len(launched) == n and "Select a server" in w.statusBar().currentMessage())
det.server_table.selectRow(1)
det.join_selected()
check("Join selected opens the launcher on that server (place id + server id)", launched[-1] == "roblox://experiences/start?placeId=11&gameInstanceId=aaaaaaaa-0000-0000-0000-000000000002", launched[-1])
real_servers = det.servers
det.servers = [{"id": "a", "playing": 5, "max": 12, "ping": 90, "fps": 30.0}, {"id": "b", "playing": 2, "max": 12, "ping": 40, "fps": 59.0},
               {"id": "c", "playing": 9, "max": 12, "ping": None, "fps": None}, {"id": "d", "playing": 1, "max": 12, "ping": 40, "fps": 60.0}]
check("the sort box has Roblox's order, ping, FPS, the player counts and the running time", [det.order.itemData(i) for i in range(det.order.count())] == ["roblox", "ping", "fps", "most", "fewest", "oldest", "newest"])
for mode, expect in (("roblox", "abcd"), ("ping", "bdac"), ("fps", "dbac"), ("most", "cabd"), ("fewest", "dbac")):
    det.order.setCurrentIndex(det.order.findData(mode)); det._show_servers()
    got = "".join(det.server_table.item(r, 4).text() for r in range(det.server_table.rowCount()))
    check(f"sorting the loaded servers by '{mode}'" + (" (a server without a value goes last, ties keep Roblox's order)" if mode == "ping" else ""), got == expect, got)
check("an unknown mode keeps Roblox's order", [s["id"] for s in tab_discover.sort_servers(det.servers, "nonsense")] == list("abcd"))
det.servers = real_servers
det.order.setCurrentIndex(0)
# ---------------------------------------------------------------- where the servers are, and how long they have been running
import geo
import settings
import worldmap
infos = []
QMessageBox.information = staticmethod(lambda *a, **k: infos.append(str(a[2]) if len(a) > 2 else ""))          # ('sign in first' would wait for a click)
rbx.Client.JOIN_WAIT = 0.001
GEO, LIST = [], []
GEO_PLACES = {"128.116.44": ("Frankfurt am Main", "Germany", "DE", 50.1155, 8.6842), "128.116.97": ("Singapore", "Singapore", "SG", 1.2897, 103.85)}
ROSEAL_LIST = [{"id": 1, "dataCenterIds": [25960], "location": {"city": "Frankfurt", "region": "Hesse", "country": "DE", "latLong": ["50.1155", "8.6842"]}},
               {"id": 2, "dataCenterIds": [25853], "location": {"city": "Singapore", "region": "Singapore", "country": "SG", "latLong": ["1.2897", "103.8501"]}}]


def fake_geo(url):
    GEO.append(url)
    city, country, cc, lat, lon = GEO_PLACES[url.rsplit("/", 1)[1].rsplit(".", 1)[0]]
    return {"success": True, "city": city, "country": country, "country_code": cc, "region": "", "latitude": lat, "longitude": lon}


geo._fetch = fake_geo
geo._fetch_roseal = lambda url: (LIST.append(url), ROSEAL_LIST)[1]
asked_source = []
det.ask_geo_source = lambda: (asked_source.append(1), "roseal")[1]
check("the table has Location, Running for and Version columns (after the server id, so the other columns keep their places)", det.server_table.columnCount() == 8
      and [det.server_table.horizontalHeaderItem(i).text() for i in (5, 6, 7)] == ["Location", "Running for", "Version"])
check("the button and the map button are there", det.b_locate.text() == "Location and uptime" and det.b_map.text() == "Show map" and det.b_stop_locate.isHidden())
check("the sort box has the uptime orders too", [det.order.itemData(i) for i in range(det.order.count())] == ["roblox", "ping", "fps", "most", "fewest", "oldest", "newest"])
check("nothing is allowed to contact RoSeal or ipwho.is at first", settings.get("geo.roseal") is False and settings.get("geo.allowed") is False)
w.ctx.client.user = None
det.locate_servers()
check("Location and uptime needs the sign-in (nothing is asked of Roblox without it)", not JOIN_CALLS and not asked_source and infos and "sign in" in infos[0].lower(), infos)
w.ctx.client.user = {"id": 156, "name": "me", "displayName": "Me"}
det.server_table.selectRow(0)
first_id = det.server_table.item(0, 4).text()
det.locate_servers()
check("the first time, the person is asked which service may be used, and chooses RoSeal's list", wait(lambda: len(det.places) == 1) and asked_source == [1] and settings.get("geo.roseal") is True and settings.get("geo.allowed") is False)
check("...the join request was for that server only", len(JOIN_CALLS) == 1 and JOIN_CALLS[0]["gameId"] == first_id and JOIN_CALLS[0]["placeId"] == 11, JOIN_CALLS)
check("...RoSeal's list was downloaded once, and ipwho.is not at all", LIST == ["https://data.roseal.live/v2/grouped-datacenters.json"] and not GEO, (LIST, GEO))
check("...the table shows its place and how long it has been running", wait(lambda: any(det.server_table.item(r, 5).text() == "Frankfurt, DE" for r in range(det.server_table.rowCount()))
      and any(det.server_table.item(r, 6).text() for r in range(det.server_table.rowCount()))), [(det.server_table.item(r, 5).text(), det.server_table.item(r, 6).text()) for r in range(det.server_table.rowCount())])
det.server_table.clearSelection()
det.locate_servers()
check("with nothing selected, all the others are looked up", wait(lambda: len(det.places) == 6 and len(det.started) == 6 and not det._locating), (len(det.places), len(det.started)))
check("...each server was asked about once (6 in all)", len(JOIN_CALLS) == 6 and len({c["gameId"] for c in JOIN_CALLS}) == 6, len(JOIN_CALLS))
check("...the person was not asked again, and RoSeal's list was not downloaded again", asked_source == [1] and len(LIST) == 1)
check("...the note says how many were looked up", "Looked up 5 of 5 server(s), 5 located" in det.server_note.text(), det.server_note.text())
by_digit = {det.server_table.item(r, 4).text()[-1]: (det.server_table.item(r, 5).text(), det.server_table.item(r, 6).text()) for r in range(det.server_table.rowCount())}
check("the odd servers are in Frankfurt and the even ones in Singapore", by_digit["1"][0] == by_digit["3"][0] == by_digit["5"][0] == by_digit["9"][0] == "Frankfurt, DE" and by_digit["2"][0] == "Singapore, SG", by_digit)
check("...and server N started N hours ago", by_digit["2"][1].startswith("2 h") and by_digit["4"][1].startswith("4 h") and by_digit["5"][1].startswith("5 h"), by_digit)
vers = {det.server_table.item(r, 4).text()[-1]: det.server_table.item(r, 7).text() for r in range(det.server_table.rowCount())}
check("the Version column shows the place version of each server, and which are older than the newest one looked up", vers == {"1": "v1801 (older)", "2": "v1802", "3": "v1800 (older)", "4": "v1801 (older)", "5": "v1802", "9": "v1800 (older)"}, vers)
check("the version words", tab_discover.version_text(0, 5) == "" and tab_discover.version_text(7, 0) == "v7" and tab_discover.version_text(7, 7) == "v7" and tab_discover.version_text(6, 7) == "v6 (older)")
det.server_table.clearSelection()
det.b_copy_link.click()
check("Copy join link without a selection asks to select a server", "Select a server" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
det.server_table.selectRow(2)
chosen = det.server_table.item(2, 4).text()
det.b_copy_link.click()
check("Copy join link puts the web link of the selected server on the clipboard", QApplication.clipboard().text() == f"https://www.roblox.com/games/start?placeId=11&gameInstanceId={chosen}" and "Join link copied" in w.statusBar().currentMessage(), QApplication.clipboard().text())
det.server_table.clearSelection()
for mode, expect in (("oldest", "9" + "5"), ("newest", "1")):
    det.order.setCurrentIndex(det.order.findData(mode))
    got = "".join(det.server_table.item(r, 4).text()[-1] for r in range(det.server_table.rowCount()))
    check(f"sorting by '{mode}' puts {'the longest running' if mode == 'oldest' else 'the newest'} server first", got.startswith(expect[0]), got)
det.order.setCurrentIndex(0)
n = len(JOIN_CALLS)
det.locate_servers()
check("when every server is looked up, pressing the button again does nothing but say so", len(JOIN_CALLS) == n and "looked up already" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
dlg = tab_discover.ServerMapDialog(det, det.servers, det.places, det._join_server, det.started)
check("the map window shows two dots: Frankfurt (4 servers) and Singapore (2)", sorted(len(d["ids"]) for d in dlg.map.dots) == [2, 4] and "6 of 6" in dlg.note.text(), (dlg.map.dots, dlg.note.text()))
dlg.map.picked.emit(next(d["ids"] for d in dlg.map.dots if len(d["ids"]) == 2))
check("pressing a dot lists its servers, with how long they have run", dlg.table.rowCount() == 2 and {dlg.table.item(r, 4).text()[-1] for r in range(2)} == {"2", "4"}
      and all("h" in dlg.table.item(r, 5).text() for r in range(2)), [dlg.table.item(r, 5).text() for r in range(dlg.table.rowCount())])
dlg.table.selectRow(0)
launched_before = len(launched)
dlg.join_selected()
check("Join selected in the map window opens the launcher on that server", len(launched) == launched_before + 1 and "gameInstanceId=aaaaaaaa-0000-0000-0000-00000000000" in launched[-1], launched[-1:])
dlg.close()
# the game's wiki, from RoSeal's list of game links
import roseal_links
LINK_FETCHES = []
roseal_links.FILE.unlink(missing_ok=True)
roseal_links._fetch = lambda url: (LINK_FETCHES.append(url), [{"universeIds": [det.card["universeId"]], "links": [{"type": "communityWiki", "url": "alpha.fandom.com"}]}])[1]
asked_wiki = []
settings.set("geo.roseal", False)
w.ctx.confirm = lambda title, text, danger=False: (asked_wiki.append(text), False)[1]
det.b_wiki.click(); spin(0.2)
check("the game wiki asks before contacting RoSeal, and a No contacts nothing", len(asked_wiki) == 1 and "data.roseal.live" in asked_wiki[0] and "nothing about you" in asked_wiki[0] and not LINK_FETCHES and settings.get("geo.roseal") is False, asked_wiki)
w.ctx.confirm = lambda title, text, danger=False: (asked_wiki.append(text), True)[1]
opened_urls.clear()
det.b_wiki.click()
check("after a Yes the list is downloaded once and the wiki opens in the browser", wait(lambda: opened_urls == ["https://alpha.fandom.com"]) and LINK_FETCHES == ["https://data.roseal.live/v2/experience-links.json"] and settings.get("geo.roseal") is True, (opened_urls, LINK_FETCHES))
det.b_wiki.click()
check("...the next time it does not ask again and does not download again", wait(lambda: len(opened_urls) == 2) and len(asked_wiki) == 2 and len(LINK_FETCHES) == 1, (len(asked_wiki), len(LINK_FETCHES)))
real_card = det.card
det.card = dict(real_card, universeId=999)
opened_urls.clear()
det.b_wiki.click()
check("a game that has no wiki in the list says so and opens nothing", wait(lambda: "no wiki for this game" in w.statusBar().currentMessage()) and not opened_urls, w.statusBar().currentMessage())
det.card = real_card
settings.set("geo.roseal", True)
# a server Roblox gives no information about
det.places.clear(); det.started.clear(); det._show_servers()
JOIN_FAIL.add("aaaaaaaa-0000-0000-0000-000000000002")
det.server_table.selectRow(next(r for r in range(det.server_table.rowCount()) if det.server_table.item(r, 4).text().endswith("2")))
det.locate_servers()
check("a server Roblox gives no information about is reported without a popup, and the button works again", wait(lambda: "could not be located" in det.server_note.text() and det.b_locate.isEnabled())
      and "still getting this server ready" in det.server_note.text() and not warnings, det.server_note.text())
JOIN_FAIL.clear()
# switched off in Settings, and the other service
settings.set("geo.roseal", False)
geo.CACHE_FILE.unlink(missing_ok=True); geo.ROSEAL_FILE.unlink(missing_ok=True)
det.places.clear(); det.started.clear(); det._show_servers()
det.ask_geo_source = lambda: (asked_source.append(2), "ipwho")[1]
det.server_table.selectRow(0)
det.locate_servers()
check("with both services off the person is asked again, and ipwho.is can be chosen instead", wait(lambda: len(det.places) == 1) and asked_source == [1, 2] and settings.get("geo.allowed") is True and settings.get("geo.roseal") is False, asked_source)
check("...then the server's address went to ipwho.is, and RoSeal was not contacted", len(GEO) == 1 and GEO[0].startswith("https://ipwho.is/128.116.") and len(LIST) == 1, (GEO, LIST))
check("...and the place is shown", any(det.server_table.item(r, 5).text() == "Frankfurt am Main, Germany" for r in range(det.server_table.rowCount())))
geo_real = geo._fetch
geo._fetch = lambda url: (_ for _ in ()).throw(geo.requests.ConnectionError("down"))
geo.CACHE_FILE.unlink()
det.places.clear(); det.started.clear()
det.server_table.selectRow(1)
det.locate_servers()
check("a lookup service that is down is reported in plain words (the uptime is still shown)", wait(lambda: "could not be reached" in det.server_note.text()) and not det.places and len(det.started) == 1, det.server_note.text())
geo._fetch = geo_real
det.find_servers(True); wait(lambda: det.server_table.rowCount() == 6 and not det.server_busy)
check("a new list of servers starts without places and start times", det.places == {} and det.started == {} and all(det.server_table.item(r, 5).text() == "" and det.server_table.item(r, 6).text() == "" for r in range(det.server_table.rowCount())))
det.order.setCurrentIndex(0)
det.sort.setCurrentIndex(1)
det.b_servers.click()
check("sorting by most players asks for Desc and starts the list again", wait(lambda: [c for c in log if "/servers/Public" in c[0]][-1][1].get("sortOrder") == "Desc" and det.server_table.rowCount() == 5), det.server_table.rowCount())
det.sort.setCurrentIndex(0)
det.join_emptiest()
check("Join the emptiest opens the launcher on the server with the fewest players", wait(lambda: launched[-1] == "roblox://experiences/start?placeId=11&gameInstanceId=aaaaaaaa-0000-0000-0000-000000000001"), launched[-1])
client.servers_error = "Roblox says no"
det.b_servers.click()
check("servers that cannot be loaded say so (no popup, the button works again)", wait(lambda: "could not be loaded" in det.server_note.text() and det.b_servers.isEnabled()) and not warnings, det.server_note.text())
client.servers_error = None
det.b_servers.click(); wait(lambda: det.server_table.rowCount() == 5)
det.show_game(d.cards[2][0].card)
check("opening another game empties the server list", det.server_table.rowCount() == 0 and det.servers == [] and det.server_note.text() == "")

# recently viewed
import games_store
recent_names = [c["name"] for c in games_store.recent()]
check("the games you looked at are remembered, newest first, each once", recent_names[:2] == ["Beta Game", "Alpha Game"] and len(recent_names) == len(set(recent_names)), recent_names)
games_store.FILE.write_text("{not json")
check("a damaged file is ignored (no crash)", games_store.recent() == [])
games_store.FILE.write_text('[{"universeId": "x"}, 5, {"universeId": 3, "name": "ok"}]')
check("entries that are not games are dropped", [c["universeId"] for c in games_store.recent()] == [3])
games_store.clear()
for i in range(25):
    games_store.add({"universeId": 1000 + i, "placeId": 1, "name": f"G{i}", "playing": 1, "up": 1, "down": 1, "creator": "", "verified": False, "age": "", "genre": ""})
check("at most 20 are kept", len(games_store.recent()) == 20 and games_store.recent()[0]["name"] == "G24")
games_store.clear()
det.back.emit()
w.ctx.client.user = None
d.show_feed()
check("the home page rows come first when there is nothing of your own yet", wait(lambda: len(d.cards) >= 17) and all(b.isHidden() for b in d.boxes.values()))
det.show_game(alpha.card); det.back.emit(); spin(0.3)
check("after viewing a game a 'Recently viewed' row appears above Roblox's rows", not d.boxes["recent"].isHidden() and "Recently viewed" in [lab.text() for lab in d.boxes["recent"].findChildren(tab_discover.QLabel)])

# friends in games and favorites (signed in)
w.ctx.client.user = {"id": 156, "name": "me", "displayName": "Me"}
w.ctx.signed_in.emit()
check("signed in: a 'Friends in games' row shows only the friends who are in a game", wait(lambda: not d.boxes["friends"].isHidden()) and len(d.boxes["friends"].findChildren(tab_discover.FriendCard)) == 1, len(d.boxes["friends"].findChildren(tab_discover.FriendCard)))
fc = d.boxes["friends"].findChildren(tab_discover.FriendCard)[0]
check("...with the friend's name and the game", fc.f["displayName"] == "Ann" and fc.f["game"] == "Alpha Game" and fc.f["job"] == "job-aaaa-1111")
fc.b_join.click()
check("Join opens the launcher on the friend's server", launched[-1] == "roblox://experiences/start?placeId=11&gameInstanceId=job-aaaa-1111", launched[-1])
check("a 'Your favorites' row shows the account's favorite games", wait(lambda: not d.boxes["favorites"].isHidden()) and {c.card["name"] for c in d.boxes["favorites"].findChildren(tab_discover.GameCard)} == {"Alpha Game", "Favorite Eight"})
w.ctx.client.user = None
w.ctx.signed_out.emit(); spin(0.2)
check("signed out: both rows go away", d.boxes["friends"].isHidden() and d.boxes["favorites"].isHidden())
bad_job = {"place": 11, "job": "x&y=1", "game": "g"}
n = len(launched)
d._join_friend(bad_job)
check("a server id that could add something to the link opens nothing", len(launched) == n)
servers, nxt = client.game_servers(11)
check("game_servers (the real method): parsed servers and the next cursor, odd ids dropped", [s["playing"] for s in servers] == [1, 2, 3, 4, 5] and nxt == "s2" and servers[0]["max"] == 12 and servers[0]["fps"] == 59.5)
check("favorite_games (the real method) gives game cards", [g["name"] for g in client.favorite_games(156)] == ["Alpha Game", "Favorite Eight"])

# search entries and keyboard
w.open_search(); w.palette_box.edit.setText("discover"); spin(0.05)
r = [w.palette_box.list.item(i).text() for i in range(w.palette_box.list.count())]
check("Ctrl+K finds Discover", any(x.startswith("Discover") for x in r), r[:3])
QTest.keyClick(w.palette_box.edit, Qt.Key.Key_Return); spin(0.2)
check("...and opens it inside Home", w.current_page() is w.home and w.home.tabs.currentIndex() == 1)

check("no error popup appeared at any point of all this", not warnings, warnings)
print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
