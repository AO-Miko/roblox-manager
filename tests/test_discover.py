"""Test of Discover (inside Home): the home page rows, the search, a game's page with its stats and the Play button (launcher links, VIP servers). The real client methods run
against a fake Roblox that answers with the real response shapes. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_discover.py"""
import os
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
        if "/vip-servers/" in url:
            return {}                                       # (a server whose join link Roblox does not give)
        if "usernames/users" in url:
            return {"data": []}
        if "avatar-headshot" in url:
            return {"data": [{"targetId": int(i), "imageUrl": f"https://tr.rbxcdn.com/head/{i}.png", "state": "Completed"} for i in params["userIds"].split(",")]}
        raise rbx.RobloxError("not faked: " + url, 404)

    def post(self, url, body=None, **kw):
        log.append((url, dict(body or {})))
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

# search entries and keyboard
w.open_search(); w.palette_box.edit.setText("discover"); spin(0.05)
r = [w.palette_box.list.item(i).text() for i in range(w.palette_box.list.count())]
check("Ctrl+K finds Discover", any(x.startswith("Discover") for x in r), r[:3])
QTest.keyClick(w.palette_box.edit, Qt.Key.Key_Return); spin(0.2)
check("...and opens it inside Home", w.current_page() is w.home and w.home.tabs.currentIndex() == 1)

check("no error popup appeared at any point of all this", not warnings, warnings)
print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
