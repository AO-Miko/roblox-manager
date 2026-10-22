"""Test of: what you share with a person (mutual friends, friends since), where a friend request came from, voice chat and age verification on the Account page, the Developer Exchange line
on Money, and RoSeal's links to game wikis (checked links, asked first). Real client methods run against a fake Roblox. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_features.py"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="features-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtWidgets import QApplication, QMessageBox, QPlainTextEdit

app = QApplication(sys.argv)
import geo
import rbx
import relation
import roseal_links
import settings
import tab_account
import tab_money
import tab_people
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:260]) if e else ""))


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


NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
SINCE_MS = int(datetime(2021, 3, 12, 8, 0, tzinfo=timezone.utc).timestamp() * 1000)
INSIGHTS = {"userInsights": [
    {"targetUser": 201, "profileInsights": [
        {"mutualFriendInsight": {"mutualFriends": {"301": {"username": "zed", "displayName": "Zed"}, "302": {"username": "amy", "displayName": "amy"}, "x": {"username": "bad"}, "303": "junk"}, "insightCase": 1},
         "insightCase": 1},
        {"friendshipAgeInsight": {"friendsSinceDateTime": {"seconds": str(SINCE_MS // 1000)}}},
        {"offlineFrequentsInsight": {"havePlayedTogether": True}, "insightCase": 3}, "junk", {"friendshipAgeInsight": {"friendsSinceDateTime": {"seconds": "soon"}}}]},
    {"targetUser": 202, "profileInsights": []},
    {"targetUser": "bad"}, {"targetUser": 203, "profileInsights": None}, "junk"]}


class FakeRoblox(rbx.Client):
    log = []
    voice = {"isVoiceEnabled": True, "isUserOptIn": True, "isUserEligible": True, "isBanned": False, "bannedUntil": None, "isVerifiedForVoice": True}
    age = {"isVerified": True, "verifiedAge": 22, "isSeventeenPlus": False}
    devex_eligible = {"eligibleRobux": 4214, "updatedUtc": "2026-10-20T00:00:00Z"}
    devex_info = {"minRobuxToCashOut": 30000, "canProceedToCashout": False, "isDevExSuspended": False, "isAtRiskOfSuspension": False}
    refuse = set()

    def get(self, url, params=None, **kw):
        FakeRoblox.log.append(("GET", url))
        for key in FakeRoblox.refuse:
            if key in url:
                raise rbx.RobloxError(403, "refused")
        if re_friends(url):
            return {"data": [{"id": 201, "name": "ann", "displayName": "Ann"}, {"id": 202, "name": "bob", "displayName": "Bob"}, {"id": 203, "name": "cy", "displayName": "Cy"}]}
        if url.endswith("/my/friends/requests"):
            return {"data": [{"friendRequest": {"sentAt": "2026-09-07T07:15:15.592Z", "senderId": 401, "originSourceType": "InGame"}, "mutualFriendsList": ["Zed", "amy"], "id": 401},
                             {"friendRequest": {"sentAt": "2026-10-07T04:21:54.997Z", "senderId": 402, "originSourceType": "WeirdNewKind<b>"}, "mutualFriendsList": [], "id": 402},
                             {"friendRequest": {"sentAt": "2026-10-08T04:21:54.997Z", "senderId": 403, "originSourceType": None}, "mutualFriendsList": [], "id": 403}], "nextPageCursor": None}
        if url.endswith("/voice/v1/settings") or "voice.roblox.com/v1/settings" in url:
            return FakeRoblox.voice
        if "verified-age" in url:
            return FakeRoblox.age
        if "devexEligibleRobux" in url:
            return FakeRoblox.devex_eligible
        if "developer-exchange/info" in url:
            return FakeRoblox.devex_info
        if url.endswith("/v1/user/currency"):
            return {"robux": 4214}
        if "transaction-totals" in url:
            return {}
        if "/v2/users/156/transactions" in url:
            return {"data": [], "nextPageCursor": None}
        if "/groups/roles" in url:
            return {"data": []}
        if url.endswith("/v1/users/156"):
            return {"id": 156, "name": "me", "displayName": "Me", "created": "2015-01-01T00:00:00Z"}
        if "usernames/users" in url or url.endswith("/v1/users") or "my-private-servers" in url:
            return {"data": []}
        raise rbx.RobloxError(404, "not faked: " + url)

    def post(self, url, body=None, **kw):
        FakeRoblox.log.append(("POST", url, json.dumps(body, sort_keys=True)))
        if "multiProfileInsights" in url:
            return INSIGHTS
        if "get-profiles" in url:
            who = {201: "ann", 202: "bob", 203: "cy", 401: "dee", 402: "eve", 403: "fay"}
            return {"profileDetails": [{"userId": i, "names": {"username": who.get(i, f"u{i}"), "displayName": who.get(i, f"u{i}").title()}, "isVerified": False} for i in body["userIds"]]}
        if "presence" in url:
            return {"userPresences": []}
        if url.endswith("/v1/users") or "usernames/users" in url:
            return {"data": []}
        raise rbx.RobloxError(404, "not faked: " + url)


def re_friends(url):
    return "friends.roblox.com/v1/users/156/friends" in url and not url.endswith(("followers", "followings"))


# ================================================================ the client calls
c = FakeRoblox()
c.user = {"id": 156, "name": "me", "displayName": "Me"}
ins = c.profile_insights([201, 202, 203, 204, 201])
check("the insights call is one request with the ids as text, each once", [x for x in FakeRoblox.log if "multiProfileInsights" in x[1]] == [("POST", "https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights", json.dumps({"userIds": ["201", "202", "203", "204"]}))])
check("a friend's insights give the mutual friends (names), since when you are friends and whether you played together",
      sorted(m["id"] for m in ins[201]["mutual"]) == [301, 302] and ins[201]["friends_since_ms"] == SINCE_MS and ins[201]["played_together"] is True, ins.get(201))
check("a person with nothing in common is there with empty values; broken entries are dropped", ins[202] == {"mutual": [], "friends_since_ms": None, "played_together": False} and set(ins) == {201, 202, 203}, set(ins))
check("an empty list asks nothing", c.profile_insights([]) == {} and len([x for x in FakeRoblox.log if "multiProfileInsights" in x[1]]) == 1)
check("at most 50 people are asked about at once", len(json.loads([x for x in (c.profile_insights(list(range(1, 80))) and FakeRoblox.log) if "multiProfileInsights" in x[1]][-1][2])["userIds"]) == 50)
check("voice chat: on and verified", c.voice_status() == {"enabled": True, "eligible": True, "opted_in": True, "banned": False, "banned_until": None, "verified": True})
FakeRoblox.voice = {"isVoiceEnabled": True, "isUserEligible": True, "isUserOptIn": False, "isBanned": True, "bannedUntil": {"Seconds": 1800000000}}
check("voice chat: a suspension and its end", c.voice_status()["banned"] is True and c.voice_status()["banned_until"] == "1800000000")
check("age verification: verified with an age", c.verified_age() == {"verified": True, "age": 22})
FakeRoblox.age = {"isVerified": False, "verifiedAge": "x"}
check("...an odd age is left out", c.verified_age() == {"verified": False, "age": None})
check("DevEx: what can be cashed out and what stands in the way", c.devex_status() == {"eligible_robux": 4214, "updated": "2026-10-20T00:00:00Z", "min_cash_out": 30000, "can_cash_out": False, "suspended": False, "at_risk": False}, c.devex_status())
FakeRoblox.refuse = {"devexEligibleRobux"}
d = c.devex_status()
check("...a call that Roblox refuses leaves its values empty (the other still shows)", d["eligible_robux"] is None and d["min_cash_out"] == 30000, d)
FakeRoblox.refuse = {"devexEligibleRobux", "developer-exchange"}
check("...both refused: nothing, no error", set(c.devex_status().values()) == {None})
FakeRoblox.refuse = set()

# ================================================================ the words
check("how long ago: years and months", relation.years_text(SINCE_MS, NOW) == "5 years, 7 months" and relation.years_text(int(NOW.timestamp() * 1000) - 5 * 86400000, NOW) == "under a month"
      and relation.years_text(int(datetime(2025, 10, 22, tzinfo=timezone.utc).timestamp() * 1000), NOW) == "1 year", relation.years_text(SINCE_MS, NOW))
txt = relation.describe(ins[201], "Ann", NOW)
check("what you share is written plainly: friends since, played together, the mutual friends by name", "Friends since 2021-03-12 (5 years, 7 months)." in txt and "You have played together." in txt
      and "2 mutual friends:" in txt and "  amy" in txt and "  Zed  (@zed)" in txt and txt.index("amy") < txt.index("Zed"), txt)
check("a stranger: no date, no mutual friends", "does not say since when" in relation.describe(ins[202], "Bob", NOW) and "No mutual friends." in relation.describe(ins[202], "Bob", NOW))
check("nothing from Roblox is said so", "gave nothing" in relation.describe(None, "Cy", NOW))
check("a name that looks like HTML stays text (the dialog shows plain text)", "<b>x</b>" in relation.describe({"mutual": [{"id": 1, "username": "u", "displayName": "<b>x</b>"}], "friends_since_ms": None, "played_together": False}, "n", NOW))
check("voice chat words", [tab_account.voice_text(v) for v in ({"banned": True, "banned_until": "2027-01-02T03"}, {"banned": True}, {"eligible": False}, {"eligible": True, "enabled": False},
                                                              {"eligible": True, "enabled": True, "opted_in": True, "verified": True}, {"eligible": True, "enabled": True})]
      == ["suspended until 2027-01-02", "suspended", "not available for this account", "off", "on, verified", "available, not switched on"])
check("age verification words", [tab_account.age_verification_text(a) for a in ({"verified": False}, {"verified": True}, {"verified": True, "age": 22})] == ["not verified", "verified", "verified (age 22)"])
check("DevEx words", tab_money.devex_text({"eligible_robux": 4214, "updated": "2026-10-20T00:00:00Z", "min_cash_out": 30000, "can_cash_out": False, "suspended": False, "at_risk": False})
      == "DevEx: 4,214 Robux can be cashed out (as of 2026-10-20); minimum 30,000; cashing out is not open to you right now.")
check("...suspended, and not available", tab_money.devex_text({"eligible_robux": 5, "min_cash_out": None, "suspended": True, "can_cash_out": False}) == "DevEx: 5 Robux can be cashed out; DevEx is SUSPENDED."
      and tab_money.devex_text({"eligible_robux": None, "min_cash_out": None}) == "DevEx: not available for this account.")
check("where a friend request came from", [tab_people.origin_text(k) for k in ("InGame", "UserProfile", "WeirdNewKind<b>", None, "")] == ["A game", "Your profile", "WeirdNewKindb", "", ""])

# ================================================================ RoSeal's links to game wikis
check("safe wiki addresses become https links", [roseal_links.safe_url(x) for x in ("adoptme.fandom.com", "Wiki.Example.org/Game_Name", "a-b.example.co.uk/x/y/")]
      == ["https://adoptme.fandom.com", "https://wiki.example.org/Game_Name", "https://a-b.example.co.uk/x/y/"])
bad_urls = ["javascript:alert(1)", "http://evil.example", "https://evil.example", "evil.example:8080", "user@evil.example", "evil.example/a b", "evil.example/../x?y=1", "1.2.3.4", "localhost", "evil", "-a.example.com", "evil.example/%3Cscript",
            "a" * 300 + ".com", "", None, 5, "evil.example#frag", "evil.example\\x", "evil.example/a/b/c/d/e/f/g/h/i/j", "exa mple.com", "evil.com/<b>"]
check("anything else is refused (schemes, ports, logins, addresses, odd characters)", [x for x in bad_urls if roseal_links.safe_url(x)] == ["evil.example/%3Cscript"], [x for x in bad_urls if roseal_links.safe_url(x)])
DATA = [{"universeIds": [11, 12], "links": [{"type": "communityWiki", "url": "game.fandom.com", "locale": "en"}, {"type": "communityWiki", "url": "game.fandom.com"}, {"type": "discord", "url": "discord.gg/x"},
                                          {"type": "communityWiki", "url": "javascript:alert(1)"}]},
        {"universeIds": ["x", True, 13], "links": [{"type": "communityWiki", "url": "other.wiki.org/Page"}]}, {"universeIds": [14], "links": "junk"}, "junk", {"links": []}]
cl = roseal_links.clean(DATA)
check("RoSeal's file is read: only wiki links with a safe address, once each, for real universe ids", cl == {11: [{"type": "communityWiki", "label": "Community wiki", "url": "https://game.fandom.com"}],
                                                                                                           12: [{"type": "communityWiki", "label": "Community wiki", "url": "https://game.fandom.com"}],
                                                                                                           13: [{"type": "communityWiki", "label": "Community wiki", "url": "https://other.wiki.org/Page"}]}, cl)
fetched = []


def fake_links(url):
    fetched.append(url)
    return DATA


check("a game's links come from the list (one plain download)", roseal_links.links_for(11, fake_links, now=10)[0]["url"] == "https://game.fandom.com" and fetched == ["https://data.roseal.live/v2/experience-links.json"], fetched)
check("...a game without links gives none, without a new download (kept 24 hours)", roseal_links.links_for(999, fake_links, now=20) == [] and len(fetched) == 1)
roseal_links.links_for(11, fake_links, now=10 + roseal_links.TTL + 1)
check("...and it is downloaded again after that", len(fetched) == 2)


def down(url):
    raise roseal_links.requests.ConnectionError("down")


check("when it cannot be downloaded, the old list is used", roseal_links.links_for(13, down, now=10 + 5 * roseal_links.TTL)[0]["url"] == "https://other.wiki.org/Page")
roseal_links.FILE.unlink()
for name, fn in (("down", down), ("not a list", lambda u: {"x": 1})):
    try:
        roseal_links.links_for(11, fn, now=5)
        r = "found"
    except geo.GeoError as e:
        r = str(e)
    check(f"with no old list, a failure is said in plain words: {name}", r != "found" and len(r) > 10, r)

# ================================================================ in the windows
warnings, dialogs = [], []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(str(a[2]) if len(a) > 2 else ""))
QMessageBox.information = staticmethod(lambda *a, **k: warnings.append("info: " + (str(a[2]) if len(a) > 2 else "")))
relation.QDialog.exec = lambda self: dialogs.append((self.windowTitle(), self.findChild(QPlainTextEdit).toPlainText())) or 0
client = FakeRoblox()
w = MainWindow(client, auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
w.ctx.confirm = lambda *a, **k: True
w.people.tabs.setCurrentIndex(0)
asked_before = len([x for x in FakeRoblox.log if "multiProfile" in x[1]])
w.people.friends.btn_mutual.click()
check("signed out, 'Mutual friends' opens nothing and asks Roblox nothing", not dialogs and len([x for x in FakeRoblox.log if "multiProfile" in x[1]]) == asked_before)
user = {"id": 156, "name": "me", "displayName": "Me"}
client.user = user
w.account._signed_in(user)
spin(0.3)
check("the Account page shows voice chat and age verification", wait(lambda: w.account.fields["Voice chat"].text() not in ("-", "") and w.account.fields["Age verification"].text() != "-"),
      (w.account.fields["Voice chat"].text(), w.account.fields["Age verification"].text()))
check("...voice chat: suspended (the earlier test state), age: not verified", w.account.fields["Voice chat"].text().startswith("suspended") and w.account.fields["Age verification"].text() == "not verified",
      (w.account.fields["Voice chat"].text(), w.account.fields["Age verification"].text()))
FakeRoblox.voice = {"isVoiceEnabled": True, "isUserOptIn": True, "isUserEligible": True, "isBanned": False, "bannedUntil": None, "isVerifiedForVoice": True}
FakeRoblox.age = {"isVerified": True, "verifiedAge": 22}
w.account._signed_in(user)
check("...and after a new sign-in: on, verified; verified (age 22)", wait(lambda: w.account.fields["Voice chat"].text() == "on, verified" and w.account.fields["Age verification"].text() == "verified (age 22)"),
      (w.account.fields["Voice chat"].text(), w.account.fields["Age verification"].text()))
FakeRoblox.refuse = {"voice.roblox.com", "verified-age"}
w.account._signed_in(user)
check("...if Roblox refuses, they say '(not available)' without a popup", wait(lambda: w.account.fields["Voice chat"].text() == "(not available)" and w.account.fields["Age verification"].text() == "(not available)") and not [x for x in warnings if "refused" in x], warnings[:2])
FakeRoblox.refuse = set()

w.money.load()
check("the Money page shows the Developer Exchange line", wait(lambda: w.money.devex.text().startswith("DevEx: 4,214 Robux")), w.money.devex.text())
FakeRoblox.refuse = {"devexEligibleRobux", "developer-exchange"}
w.money.load()
check("...and says so when it is not available", wait(lambda: w.money.devex.text() == "DevEx: not available for this account."), w.money.devex.text())
FakeRoblox.refuse = set()

fr = w.people.friends
w.people.tabs.setCurrentWidget(fr)
check("the friends are listed", wait(lambda: len(fr.rows) == 3), len(fr.rows))
fr.btn_mutual.click()
check("'Mutual friends' without a selection asks to select a friend and opens nothing", not dialogs and "Select a friend" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
fr.table.selectRow(next(r for r in range(fr.table.rowCount()) if "Ann" in fr.table.item(r, 0).text() or fr.table.item(r, 0).text() == "Ann") if any("Ann" in fr.table.item(r, 0).text() for r in range(fr.table.rowCount())) else 0)
spin(0.05)
sel = fr._selected()
fr.btn_mutual.click()
check("with a friend selected, one request is made and the dialog says what you share", wait(lambda: len(dialogs) == 1) and dialogs[0][0] == f"You and {sel['name']}", dialogs)
if sel["id"] == 201:
    check("...for Ann: friends since 2021-03-12, played together, two mutual friends by name", "Friends since 2021-03-12" in dialogs[0][1] and "You have played together." in dialogs[0][1] and "2 mutual friends:" in dialogs[0][1], dialogs[0][1])
else:
    check("...(the selected friend is not Ann: no shared details)", "No mutual friends." in dialogs[0][1], dialogs[0][1])
reqs = w.people.requests
w.people.tabs.setCurrentWidget(reqs)
check("the requests list is there", wait(lambda: reqs.table.rowCount() == 3), reqs.table.rowCount())
heads = [reqs.table.horizontalHeaderItem(i).text() for i in range(reqs.table.columnCount())]
check("...with a column for where the request came from", heads == ["Name", "Username", "Sent", "Mutual friends", "Found you via"], heads)
cells = {tab_people.row_key(reqs.table, r): [reqs.table.item(r, c).text() for c in (3, 4)] for r in range(3)}
check("...'A game' for an in-game request, the odd kind shown as plain letters, nothing when Roblox says nothing", [cells[i][1] for i in (401, 402, 403)] == ["A game", "WeirdNewKindb", ""]
      and cells[401][0] == "2" and cells[402][0] == "", cells)
reqs.table.selectRow(0)
dialogs.clear()
reqs.relationship()
check("'Mutual friends' works on the requests list too", wait(lambda: len(dialogs) == 1) and dialogs[0][0].startswith("You and "), dialogs)
find = w.people.find
find.results = [{"id": 202, "name": "bob", "displayName": "Bob"}]
tab_people.fill_table(find.table, [["Bob", "@bob", 202, ""]], keys=[202])
find.table.selectRow(0)
dialogs.clear()
find.relationship()
check("...and on a person found by search", wait(lambda: len(dialogs) == 1) and dialogs[0][0] == "You and Bob" and "No mutual friends." in dialogs[0][1], dialogs)
check("no error popup appeared at any point of all this", not [x for x in warnings if not x.startswith("info:")], warnings)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
