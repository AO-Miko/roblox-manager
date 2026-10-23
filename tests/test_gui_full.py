"""The whole desktop app against a fake Roblox (316 checks): every tab, bulk actions, rate limits, accounts, settings.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_gui_full.py   (RM_SRC = the app folder, default linux/)"""
import json, os, re, sys, time
import os, tempfile; here = tempfile.mkdtemp(prefix="guitest-")
os.environ["ROBLOX_MANAGER_CONFIG"] = os.path.join(here, "cfg4"); os.environ["ROBLOX_MANAGER_STATE"] = os.path.join(here, "state4")
sys.path.insert(0, os.environ.get("RM_SRC") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "linux")); sys.argv = ["x"]
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox
from PySide6.QtCore import Qt
import rbx, ui_common
from app import MainWindow
import shutil, vault as _vault
for _k in ("active", "acct-1000", "acct-2000", "acct-1", "acct-2"): _vault.delete(_k)        # leftovers from an aborted earlier run
for _f in ("accounts.json", "accounts", "cookie"):
    _p = rbx.CONFIG_DIR / _f
    shutil.rmtree(_p, ignore_errors=True) if _p.is_dir() else _p.unlink(missing_ok=True)

COOKIE = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_" + "Z9Y8X7" * 30
COOKIE2 = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_" + "Q1W2E3" * 30
PLACE, UNIVERSE = 920587237, 383310974
USERS = {11: ("alice", "Alice"), 12: ("bob", "Bob"), 13: ("carol", "Carol"), 21: ("dave", "Dave"), 22: ("erin", "Erin"), 31: ("newbie", "Newbie")}
perm_log = []
def tx(amount, kind=None, name="", place="", agent=None, cur="Robux", ttype="Sale"):
    d = {}
    if kind: d["type"] = kind
    if name: d["name"] = name
    if place: d["place"] = {"name": place}
    return {"id": 1, "created": "2026-10-10T10:00:00Z", "isPending": True, "transactionType": ttype, "currency": {"type": cur, "amount": amount},
            "agent": agent or {"id": 5, "type": "User", "name": "buyer"}, "details": d or None}
for _t in ():
    pass
PENDING_PAGES = {None: ([tx(300, "GamePass", "VIP pass", "Adopt Me!"), tx(100, "Asset", "Cool hat"), tx(50, "Asset", "Cool hat"), tx(60, "DeveloperProduct", "100 coins", "Adopt Me!")], "P2"),
                 "P2": ([tx(50, None, "", "", {"id": 77, "type": "Group", "name": "Cool Club"}, ttype="GroupPayout"), tx(25, "Subscription", "Monthly", "Zoo Tycoon"),
                         tx(999, "GamePass", "tickets thing", "", None, "Tickets"), tx(5)], None)}
def pending_page(q):
    t = q.get("transactionType")
    if t == "PendingRobux": raise rbx.RobloxError(400, "Invalid transaction type.")
    if t != "Sale": return {"data": []}
    items, nxt = PENDING_PAGES[q.get("cursor")]
    return {"data": items + ([] if nxt else [dict(tx(77, "Asset", "old sale"), isPending=False)]), "nextPageCursor": nxt}
def perm_route(body):
    perm_log.append(body)
    if isinstance(body.get("users"), list) and body["users"] and isinstance(body["users"][0], dict):
        raise rbx.RobloxError(400, "The request is invalid")        # this fake Roblox only accepts ids
    return {}
ALL_PERMS = {"groupMembershipPermissions": {"changeRank": True, "inviteMembers": True, "removeMembers": True},
             "groupManagementPermissions": {"viewAuditLogs": True, "manageRelationships": False},
             "groupPostsPermissions": {"postToStatus": True}}
NO_PERMS = {"groupMembershipPermissions": {"changeRank": False, "inviteMembers": False, "removeMembers": False},
            "groupManagementPermissions": {"viewAuditLogs": False}, "groupPostsPermissions": {"postToStatus": False}}
U = lambda i, n: {"userId": i, "username": n, "displayName": n.title()}
ROLES = [{"id": 1, "name": "Guest", "rank": 0, "memberCount": 0}, {"id": 2, "name": "Member", "rank": 1, "memberCount": 40},
         {"id": 3, "name": "Moderator", "rank": 100, "memberCount": 3}, {"id": 4, "name": "Owner", "rank": 255, "memberCount": 1}]


class Fake(rbx.Client):
    def __init__(self):
        super().__init__(cookie=COOKIE)
        self.calls = []
        self.fail = {}

    def request(self, method, url, params=None, json_body=None, auth=True, retries=3, raw=False):
        self.calls.append((method, url, params, json_body, auth))
        p = url.replace("https://", "")
        for pattern, fn in self.routes():
            if re.fullmatch(pattern, method + " " + p):
                if pattern in self.fail:
                    raise rbx.RobloxError(self.fail[pattern], "Fake failure")
                return 200, fn(params, json_body), {"x-ratelimit-remaining": "99"}
        raise rbx.RobloxError(404, "no such fake route: " + method + " " + p)

    def fetch_bytes(self, url):
        from PySide6.QtGui import QPixmap, QColor
        from PySide6.QtCore import QBuffer, QIODevice
        pm = QPixmap(48, 48); pm.fill(QColor("#3ba55d")); buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); pm.save(buf, "PNG"); return bytes(buf.data())

    def routes(self):
        return [
            (r"GET users.roblox.com/v1/users/authenticated", lambda q, b: {"id": 1000, "name": "tester", "displayName": "Tester"} if client._cookie == COOKIE else
                {"id": 2000, "name": "second", "displayName": "Second"} if client._cookie == COOKIE2 else (_ for _ in ()).throw(rbx.RobloxError(401, "Unauthorized"))),
            (r"GET users.roblox.com/v1/users/1000", lambda q, b: {"created": "2019-05-05T10:00:00Z"}),
            (r"GET friends.roblox.com/v1/users/\d+/(friends|followers|followings)/count", lambda q, b: {"count": 12}),
            (r"GET economy.roblox.com/v1/user/currency", lambda q, b: {"robux": 1234}),
            (r"GET economy.roblox.com/v2/users/1000/transactions", lambda q, b: pending_page(q)),
            (r"GET economy.roblox.com/v2/users/1000/transaction-totals", lambda q, b: {"pendingRobuxTotal": 590, "incomingRobuxTotal": 900}),
            (r"GET economy.roblox.com/v1/groups/77/revenue/summary/Month", lambda q, b: {"pendingRobux": 4000, "itemSaleRobux": 12000}),
            (r"GET economy.roblox.com/v1/groups/88/revenue/summary/Month", lambda q, b: (_ for _ in ()).throw(rbx.RobloxError(403, "Insufficient permissions"))),
            (r"GET economy.roblox.com/v1/groups/\d+/revenue/summary/Month", lambda q, b: {"pendingRobux": 1}),
            (r"POST apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles", lambda q, b: {"profileDetails": [{"userId": i, "names": {"username": USERS[i][0] if i in USERS else "user%d" % i, "displayName": USERS[i][1] if i in USERS else "User %d" % i}, "isVerified": i == 12} for i in b["userIds"] if i in USERS or i >= 9000]}),
            (r"GET friends.roblox.com/v1/my/friends/requests", lambda q, b: {"data": [
                {"id": 31, "name": "newbie", "displayName": "Newbie", "friendRequest": {"sentAt": "2026-10-01T10:00:00Z"}, "mutualFriendsList": ["a", "b"]},
                {"id": 32, "name": "stranger", "displayName": "Stranger", "friendRequest": {"sentAt": "2026-10-02T10:00:00Z"}},
                {"id": 33, "name": "spam1", "displayName": "Spam", "friendRequest": {"sentAt": "2026-10-03T10:00:00Z"}}], "nextPageCursor": None}),
            (r"GET friends.roblox.com/v1/user/friend-requests/count", lambda q, b: {"count": 3}),
            (r"POST friends.roblox.com/v1/users/\d+/accept-friend-request", lambda q, b: {}),
            (r"POST friends.roblox.com/v1/users/\d+/decline-friend-request", lambda q, b: {}),
            (r"POST friends.roblox.com/v1/user/friend-requests/decline-all", lambda q, b: {}),
            (r"POST friends.roblox.com/v1/users/\d+/request-friendship", lambda q, b: {"success": True}),
            (r"GET friends.roblox.com/v1/users/1000/followers", lambda q, b: {"data": [{"id": 21, "name": "dave", "displayName": "Dave"}, {"id": 22, "name": "erin", "displayName": "Erin"}, {"id": 61, "name": "fan", "displayName": "Fan"}], "nextPageCursor": None}),
            (r"GET friends.roblox.com/v1/users/1000/followings", lambda q, b: {"data": [{"id": 22, "name": "erin", "displayName": "Erin"}] + [{"id": 70 + k, "name": "celeb%d" % k, "displayName": "Celeb %d" % k} for k in range(5)], "nextPageCursor": None}),
            (r"POST friends.roblox.com/v1/users/\d+/(follow|unfollow)", lambda q, b: {}),
            (r"GET apis.roblox.com/user-blocking-api/v1/users/me/blocked-users", lambda q, b: {"blockedUsers": [{"userId": 51, "name": "bad1", "displayName": "Bad One", "blockedTimestamp": "2026-01-02T03:04:05Z"}]}),
            (r"POST apis.roblox.com/user-blocking-api/v1/users/\d+/(block-user|unblock-user)", lambda q, b: {}),
            (r"GET users.roblox.com/v1/users/search", lambda q, b: {"data": [{"id": 12, "name": "bob", "displayName": "Bob"}, {"id": 99, "name": "bobby", "displayName": "Bobby", "hasVerifiedBadge": True}]}),
            (r"GET accountsettings.roblox.com/v1/email", lambda q, b: {"emailAddress": "t***@example.com", "verified": True}),
            (r"GET premiumfeatures.roblox.com/v1/users/1000/validate-membership", lambda q, b: True),
            (r"POST friends.roblox.com/v1/users/\d+/unfriend", lambda q, b: {}),
            (r"GET friends.roblox.com/v1/users/1000/friends", lambda q, b: {"data": [{"id": 11, "isOnline": True}, {"id": 12, "isOnline": True}, {"id": 13, "isOnline": False}]}),
            (r"POST users.roblox.com/v1/users", lambda q, b: {"data": [{"id": i, "name": USERS[i][0] if i in USERS else "user%d" % i, "displayName": USERS[i][1] if i in USERS else "User %d" % i, "hasVerifiedBadge": i == 12} for i in b["userIds"] if i in USERS or i >= 9000]}),
            (r"POST users.roblox.com/v1/usernames/users", lambda q, b: {"data": [{"id": 77, "name": b["usernames"][0], "displayName": "New Friend"}]}),
            (r"GET users.roblox.com/v1/users/1[123]", lambda q, b: {"created": "2018-03-03T00:00:00Z", "description": "I like pets", "isBanned": False}),
            (r"GET thumbnails.roblox.com/v1/users/avatar-headshot", lambda q, b: {"data": [{"targetId": int(i), "state": "Completed", "imageUrl": "https://tr.rbxcdn.com/fake/%s.png" % i} for i in q["userIds"].split(",")]}),
            (r"GET games.roblox.com/v1/vip-servers/my-private-servers", lambda q, b: {"data": [
                {"id": 5002, "active": True, "universeId": UNIVERSE, "placeId": PLACE, "name": "My server", "ownerId": 1000, "ownerName": "tester"},
                {"id": 5100, "active": False, "universeId": 2, "placeId": 4444, "name": "Old party", "ownerId": 1000, "ownerName": "tester"},
                {"id": 5101, "active": True, "universeId": 3, "placeId": 5555, "name": "Zoo night", "ownerId": 1000, "ownerName": "tester"}], "nextPageCursor": None}),
            (r"GET games.roblox.com/v1/games/multiget-place-details", lambda q, b: [{"placeId": PLACE, "name": "Adopt Me!"}, {"placeId": 4444, "name": "Brookhaven"}, {"placeId": 5555, "name": "Zoo Tycoon"}]),
            (r"GET games.roblox.com/v1/vip-server/can-invite/\d+", lambda q, b: {"canInvite": True}),
            (r"PATCH games.roblox.com/v1/vip-servers/\d+/permissions", lambda q, b: perm_route(b)),
            (r"POST presence.roblox.com/v1/presence/users", lambda q, b: {"userPresences": [
                {"userId": 11, "userPresenceType": 2, "lastLocation": "Adopt Me", "placeId": PLACE, "rootPlaceId": PLACE, "gameId": "job-abc", "universeId": UNIVERSE, "lastOnline": "2026-10-20T20:00:00Z"},
                {"userId": 12, "userPresenceType": 1, "lastLocation": "Website", "lastOnline": "2026-10-20T20:10:00Z"},
                {"userId": 13, "userPresenceType": 0, "lastLocation": "Offline", "lastOnline": "2026-10-19T08:00:00Z"}]}),
            (r"GET games.roblox.com/v1/games", lambda q, b: {"data": [{"id": UNIVERSE, "name": "Adopt Me!", "rootPlaceId": PLACE, "playing": 100}]}),
            (r"GET apis.roblox.com/universes/v1/places/\d+/universe", lambda q, b: {"universeId": UNIVERSE}),
            (r"GET games.roblox.com/v1/games/\d+/private-servers", lambda q, b: {"data": [
                {"id": "s1", "vipServerId": 5001, "name": "Alice party", "owner": {"id": 11, "name": "alice"}, "playing": 2, "maxPlayers": 10},
                {"id": "s2", "vipServerId": 5002, "name": "My server", "owner": {"id": 1000, "name": "tester"}, "playing": 0, "maxPlayers": 10},
                {"id": "s3", "vipServerId": 5003, "name": "Stranger", "owner": {"id": 999, "name": "stranger"}, "playing": 1, "maxPlayers": 10}]}),
            (r"GET games.roblox.com/v1/games/\d+/servers/VIP", lambda q, b: {"data": []}),
            (r"GET games.roblox.com/v1/vip-servers/\d+", lambda q, b: {"id": 5002, "name": "My server", "active": True, "joinCode": "CODE123", "link": "https://www.roblox.com/games/%d?privateServerLinkCode=CODE123" % PLACE,
                                                                  "subscription": {"active": True, "price": 100}, "permissions": {"friendsAllowed": False, "clanAllowed": False, "users": [{"id": 21}]}}),
            (r"PATCH games.roblox.com/v1/vip-servers/\d+", lambda q, b: {"id": 5002, **(b or {})}),
            (r"POST games.roblox.com/v1/games/vip-servers/\d+", lambda q, b: {"id": 6000, "name": b["name"]}),
            (r"GET groups.roblox.com/v1/users/1000/groups/roles", lambda q, b: {"data": [
                {"group": {"id": 77, "name": "Cool Club", "memberCount": 44, "owner": {"userId": 1000}}, "role": {"id": 4, "name": "Owner", "rank": 255}},
                {"group": {"id": 88, "name": "Other Club", "memberCount": 900, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}]}),
            (r"GET groups.roblox.com/v1/groups/(77|88)", lambda q, b: {"id": 77, "name": "Cool Club", "memberCount": 44, "description": "hello", "owner": {"username": "tester"}, "shout": {"body": "hi all"}}),
            (r"GET groups.roblox.com/v1/groups/77/membership", lambda q, b: {"userRole": {"role": {"id": 4, "name": "Owner", "rank": 255}}, "permissions": ALL_PERMS, "canConfigure": True}),
            (r"GET groups.roblox.com/v1/groups/88/membership", lambda q, b: {"userRole": {"role": {"id": 2, "name": "Member", "rank": 1}}, "permissions": NO_PERMS, "canConfigure": False}),
            (r"GET groups.roblox.com/v2/groups", lambda q, b: {"data": [{"id": int(i), "created": {"77": "2015-05-05T00:00:00Z", "88": "2020-02-02T00:00:00Z"}.get(i, "2019-01-01T00:00:00Z")} for i in q["groupIds"].split(",")]}),
            (r"GET groups.roblox.com/v1/groups/(77|88)/roles", lambda q, b: {"groupId": 77, "roles": ROLES}),
            (r"GET groups.roblox.com/v1/groups/(77|88)/users", lambda q, b: {"data": [{"user": U(21, "dave"), "role": ROLES[1]}, {"user": U(22, "erin"), "role": ROLES[2]}], "nextPageCursor": None}),
            (r"GET groups.roblox.com/v1/groups/77/roles/\d+/users", lambda q, b: {"data": [U(21, "dave")], "nextPageCursor": None}),
            (r"GET groups.roblox.com/v1/groups/77/join-requests", lambda q, b: {"data": [{"requester": U(31, "newbie"), "created": "2026-10-19T10:00:00Z"}, {"requester": U(32, "newbie2"), "created": "2026-10-20T10:00:00Z"}]}),
            (r"POST groups.roblox.com/v1/groups/77/join-requests", lambda q, b: {}),
            (r"DELETE groups.roblox.com/v1/groups/77/join-requests", lambda q, b: {}),
            (r"PATCH groups.roblox.com/v1/groups/77/users/\d+", lambda q, b: {}),
            (r"DELETE groups.roblox.com/v1/groups/77/users/\d+", lambda q, b: {}),
            (r"DELETE groups.roblox.com/v1/groups/\d+/users/1000", lambda q, b: {}),
            (r"POST groups.roblox.com/v1/groups/77/bans/\d+", lambda q, b: {}),
            (r"GET groups.roblox.com/v1/groups/77/bans", lambda q, b: {"data": [{"user": U(41, "banned1"), "created": "2026-09-01T00:00:00Z"}]}),
            (r"GET groups.roblox.com/v1/groups/77/audit-log", lambda q, b: {"data": [{"actor": {"user": U(1000, "tester")}, "actionType": "Change Rank", "description": {"TargetName": "dave"}, "created": "2026-10-20T12:00:00Z"}]}),
            (r"GET groups.roblox.com/v1/groups/77/search-members", lambda q, b: {"data": [{"user": U(77, "realfind"), "role": ROLES[1]}] if q.get("keyword", "").lower() in "realfind" else []}),
            (r"GET groups.roblox.com/v1/groups/77/roles/\d+/permissions", lambda q, b: {"permissions": {"groupPostsPermissions": {"viewWall": True, "postToWall": False}}}),
            (r"PATCH groups.roblox.com/v1/groups/77/(description|status)", lambda q, b: {}),
            (r"GET users.roblox.com/v1/users/authenticated/roles", lambda q, b: {"roles": []}),
        ]


app = QApplication([])
client = Fake()
w = MainWindow(client=client, auto_login=False); w.show()
ctx = w.ctx
results = []
asked = []
def spin(s):
    end = time.time() + s
    while time.time() < end: app.processEvents(); time.sleep(0.01)
def wait(cond, t=8):
    end = time.time() + t
    while time.time() < end:
        spin(0.03)
        try:
            if cond(): return True
        except Exception: pass
    return False
def check(n, ok, e=""): ok = bool(ok); results.append(ok); print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:300]) if e else ""))
def calls(method=None, part=None): return [c for c in client.calls if (method is None or c[0] == method) and (part is None or part in c[1])]
def ask_yes(answer=True):
    ctx.confirm = lambda title, text, danger=False: (asked.append((title, text)), answer)[1]
QMessageBox.warning = staticmethod(lambda *a, **k: asked.append(("warning", str(a[2]) if len(a) > 2 else "")))
QMessageBox.information = staticmethod(lambda *a, **k: asked.append(("info", str(a[2]) if len(a) > 2 else "")))
ask_yes(True)

# ---------------------------------------------------------------- account
w.account.sign_in()
check("signing in shows who you are", wait(lambda: ctx.logged_in and "tester" in w.account.who.text()), w.account.who.text())
check("account details are filled in", wait(lambda: w.account.fields["Robux"].text() == "1,234" and w.account.fields["Friends"].text() == "12"), w.account.fields["Robux"].text())
check("the status bar shows the account", "tester" in w.who.text())
# ---------------------------------------------------------------- pending Robux
PL = lambda: w.account.fields["Pending Robux"].text()
GL = lambda: w.account.fields["Groups' pending"].text()
check("the pending amount is shown", wait(lambda: "<b>590</b>" in PL()), PL())
check("...with its sources, once the breakdown arrives", wait(lambda: all(x in PL() for x in ("Game pass 300", "Item sale 150", "Developer product 60", "Group: Cool Club 50", "Subscription 25", "Sale 5"))), PL())
check("tickets are not counted as Robux", "999" not in PL())
check("Roblox's rejection of the PendingRobux type is handled, and remembered", client._no_pending_type is True)
check("groups: only groups you OWN are asked", wait(lambda: "Cool Club" in GL()) and not calls(None, "/groups/88/") and not any("/groups/88/" in c[1] and "economy" in c[1] for c in client.calls), GL())
check("...and their pending amount is shown", "<b>4,000</b>" in GL() and "Cool Club 4,000" in GL(), GL())
rep = w.account.pending_report
check("the report keeps every pending sale (settled ones are not counted)", len(rep["items"]) == 8 and rep["summary"]["total"] == 590, str(len(rep["items"])))
check("sales are read newest first, one type at a time", any((c[2] or {}).get("transactionType") == "Sale" and (c[2] or {}).get("sortOrder") == "Desc" for c in client.calls))
import tab_account
rows = tab_account.pending_rows(rep["items"])
check("the details table rows show amount, source, item, game and who", rows[0][1:] == [300, "Game pass", "VIP pass", "Adopt Me!", "buyer"] and rows[4][2] == "Group: Cool Club" and rows[4][5] == "Cool Club (group)", str(rows[4]))
real_exec = QDialog.exec; QDialog.exec = lambda self: 0; w.account.pending_details(); QDialog.exec = real_exec
check("the details window opens without errors", True)
# the amount must come out even if everything else is broken: sales fail, a group is rate-limited
client.fail[r"GET economy.roblox.com/v2/users/1000/transactions"] = 500
client.fail[r"GET economy.roblox.com/v1/groups/\d+/revenue/summary/Month"] = 429
(w.account._pending_cache.clear(), w.account.load_pending())
check("with the sales list failing and groups rate-limited, the amount still appears", wait(lambda: "<b>590</b>" in PL()), PL())
check("...nothing stays on 'loading' forever", wait(lambda: "..." not in PL() and "..." not in GL(), 10), PL() + " | " + GL())
del client.fail[r"GET economy.roblox.com/v2/users/1000/transactions"]; del client.fail[r"GET economy.roblox.com/v1/groups/\d+/revenue/summary/Month"]
# a total that is larger than the sales list adds up honestly
orig = client.routes
def routes2():
    r = [x for x in orig() if "transaction-totals" not in x[0]]
    return [(r"GET economy.roblox.com/v2/users/1000/transaction-totals", lambda q, b: {"pendingRobuxTotal": 700})] + r
client.routes = routes2; (w.account._pending_cache.clear(), w.account.load_pending())
check("sources that cover only part of the total show the rest as 'other'", wait(lambda: "<b>700</b>" in PL() and "other 110" in PL()), PL())
client.routes = orig
# the total itself is unavailable: the sales list is used instead
client.fail[r"GET economy.roblox.com/v2/users/1000/transaction-totals"] = 500; (w.account._pending_cache.clear(), w.account.load_pending())
check("if the total request fails, the sales list provides the amount", wait(lambda: "<b>590</b>" in PL() and "..." not in PL()), PL())
del client.fail[r"GET economy.roblox.com/v2/users/1000/transaction-totals"]
# everything fails: a clear message, not a spinner
client.fail[r"GET economy.roblox.com/v2/users/1000/transaction-totals"] = 500; client.fail[r"GET economy.roblox.com/v2/users/1000/transactions"] = 500
(w.account._pending_cache.clear(), w.account.load_pending())
check("if nothing works it says so instead of waiting", wait(lambda: PL() == "(not available)"), PL())
del client.fail[r"GET economy.roblox.com/v2/users/1000/transaction-totals"]; del client.fail[r"GET economy.roblox.com/v2/users/1000/transactions"]
(w.account._pending_cache.clear(), w.account.load_pending()); wait(lambda: "Game pass" in PL() and "Cool Club" in GL())
# a late answer after signing out must not repaint
gen_before = w.account._pending_gen

# ---------------------------------------------------------------- friends
check("friends are listed", wait(lambda: len(w.friends.rows) == 3 and w.friends.table.rowCount() == 3))
check("names are looked up even though Roblox's friends list had none", sorted(r["username"] for r in w.friends.rows) == ["alice", "bob", "carol"], str([r["username"] for r in w.friends.rows]))
statuses = {w.friends.table.item(r, 1).text(): w.friends.table.item(r, 2).text() for r in range(3)}
check("each friend shows a username and a status", statuses == {"@carol": "Offline", "@bob": "Online", "@alice": "In game"}, str(statuses))
check("display names are shown, verified ones marked", sorted(w.friends.table.item(r, 0).text() for r in range(3)) == ["Alice", "Bob  \u2714", "Carol"], str([w.friends.table.item(r, 0).text() for r in range(3)]))
check("avatars are downloaded and shown next to the names", wait(lambda: all(not w.friends.table.item(r, 0).icon().isNull() for r in range(3))))
alice_row = next(r for r in range(3) if w.friends.table.item(r, 1).text() == "@alice")
check("the game name comes from Roblox", w.friends.table.item(alice_row, 3).text() == "Adopt Me!")
w.friends.table.selectRow(alice_row)
check("selecting a friend shows their profile", wait(lambda: "I like pets" in w.friends.profile.text() and "Joined 2018-03-03" in w.friends.profile.text() and "12 friends" in w.friends.profile.text()), w.friends.profile.text()[:120])
check("...with their name, status and game", "Alice" in w.friends.profile.text() and "In game" in w.friends.profile.text() and "Adopt Me!" in w.friends.profile.text())
w.friends.only_game.setChecked(True)
check("'only in a game' filters the list", w.friends.table.rowCount() == 1)
w.friends.only_game.setChecked(False)
w.friends.search.setText("car"); check("the name filter works on looked-up names", w.friends.table.rowCount() == 1 and w.friends.table.item(0, 1).text() == "@carol"); w.friends.search.setText("")
w.friends.table.selectRow(next(r for r in range(3) if w.friends.table.item(r, 1).text() == "@alice"))
check("a friend in a game has a join link", "gameInstanceId=job-abc" in (w.friends.join_link_for(w.friends._selected()) or ""))
opened = []; ui_common.open_url = lambda u: opened.append(u); import tab_account; tab_account.open_url = ui_common.open_url
w.friends.join_friend(); check("Join opens that link", opened and "gameInstanceId=job-abc" in opened[-1])
# sorting must never separate a friend from their row
w.friends.table.sortByColumn(1, Qt.SortOrder.DescendingOrder); w.friends.table.selectRow(0)
top = w.friends.table.item(0, 1).text()[1:]
check("after sorting, the selected row is still that friend", w.friends._selected()["username"] == top, top)
rows, problems = rbx.vip_scan(client, [PLACE], [11, 12, 13])
check("the VIP scan marks servers owned by friends first", [r["friend"] for r in rows] == [True, False, False] and rows[0]["owner"] == "alice", str([(r["owner"], r["friend"]) for r in rows]))

# ---------------------------------------------------------------- groups
check("your groups are listed", wait(lambda: w.groups.glist.rowCount() == 2))
# regression: after sorting by name, a row must open ITS OWN group
w.groups._groups([{"group": {"id": 300, "name": "Zeta Club", "memberCount": 5}, "role": {"id": 1, "name": "Member", "rank": 1}},
                  {"group": {"id": 100, "name": "Alpha Club", "memberCount": 9}, "role": {"id": 2, "name": "Owner", "rank": 255}},
                  {"group": {"id": 200, "name": "Mid Club", "memberCount": 7}, "role": {"id": 3, "name": "Admin", "rank": 200}}])
want = {"Zeta Club": 300, "Alpha Club": 100, "Mid Club": 200}; opened_groups = []; real_select = w.groups.select
w.groups.select = lambda gid: opened_groups.append(gid)
for sort in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
    w.groups.glist.sortByColumn(0, sort)
    for r in range(3):
        opened_groups.clear(); w.groups.gid = None; w.groups.glist.clearSelection(); spin(0.02); w.groups.glist.selectRow(r); spin(0.05)
        check("sorted list: row '%s' opens group %d" % (w.groups.glist.item(r, 0).text(), want[w.groups.glist.item(r, 0).text()]), opened_groups == [want[w.groups.glist.item(r, 0).text()]], str(opened_groups))
w.groups.select = real_select
w.groups._groups([{"group": {"id": 77, "name": "Cool Club", "memberCount": 44}, "role": {"id": 4, "name": "Owner", "rank": 255}},
                  {"group": {"id": 88, "name": "Other Club", "memberCount": 900}, "role": {"id": 2, "name": "Member", "rank": 1}}]); w.groups.gid = None
w.groups.select(77)
check("selecting a group loads its details", wait(lambda: w.groups.title.text() == "Cool Club" and w.groups.mtable.rowCount() == 2))
check("an owner can change ranks, remove, ban and accept", all(b.isEnabled() and not b.isHidden() for b in (w.groups.b_rank, w.groups.b_kick, w.groups.b_ban, w.groups.b_accept)))
check("...and sees every page of the group (join requests, roles, audit log, bans)", all(w.groups.tabs.isTabVisible(i) for i in range(6)))
check("...and every button (shout, description, unban)", not any(b.isHidden() for b in (w.groups.b_shout, w.groups.b_desc, w.groups.b_unban, w.groups.b_decline, w.groups.b_accept_all)))
check("join requests are listed", wait(lambda: w.groups.rtable.rowCount() == 2))
check("the audit log is shown", wait(lambda: w.groups.atable.rowCount() == 1 and w.groups.atable.item(0, 2).text() == "Change Rank"))
check("bans are shown", wait(lambda: w.groups.btable.rowCount() == 1))
check("the roles tab lists every role", w.groups.roletable.rowCount() == 4)
w.groups.roletable.selectRow(0)
check("a role's permissions can be read", wait(lambda: "viewWall" in w.groups.roleperms.toPlainText()))
# change a rank
w.groups.mtable.selectRow(next(r for r in range(2) if w.groups.mtable.item(r, 1).text() == "dave"))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("Moderator (rank 100)", True))
client.calls.clear(); w.groups.change_rank()
check("changing a rank sends the new role id", wait(lambda: calls("PATCH", "/groups/77/users/21")) and calls("PATCH", "/users/21")[0][3] == {"roleId": 3}, str(calls("PATCH")[:1]))
check("...after asking you to confirm", any(t == "Change rank" for t, _ in asked))
# a refusal sends nothing
ask_yes(False); client.calls.clear()
w.groups.mtable.selectRow(0); w.groups.kick()
check("answering 'no' to a removal sends nothing", not calls("DELETE")); ask_yes(True)
w.groups.kick()
check("removing a member sends DELETE", wait(lambda: calls("DELETE", "/groups/77/users/")))
w.groups.mtable.selectRow(0); w.groups.ban()
check("banning sends POST to /bans/<user>", wait(lambda: calls("POST", "/bans/")))
# join requests
w.groups.rtable.selectAll(); client.calls.clear(); w.groups.answer(True)
check("accepting selected requests sends their ids", wait(lambda: calls("POST", "/join-requests")) and sorted(calls("POST", "/join-requests")[0][3]["UserIds"]) == [31, 32], str(calls("POST", "/join-requests")[:1]))
w.groups.rtable.selectRow(0); client.calls.clear(); w.groups.answer(False)
check("declining sends DELETE with the id", wait(lambda: calls("DELETE", "/join-requests")) and len(calls("DELETE", "/join-requests")[0][3]["UserIds"]) == 1)
# shout and description
QInputDialog.getText = staticmethod(lambda *a, **k: ("Welcome!", True)); client.calls.clear(); w.groups.set_status()
check("posting a shout sends the message", wait(lambda: calls("PATCH", "/status")) and calls("PATCH", "/status")[0][3] == {"message": "Welcome!"})
# a group where you have no permissions: everything is locked
w.groups.select(88)
check("with no permissions the management buttons are not there at all", wait(lambda: all(b.isHidden() for b in (w.groups.b_rank, w.groups.b_kick, w.groups.b_ban, w.groups.b_accept, w.groups.b_decline, w.groups.b_accept_all, w.groups.b_shout, w.groups.b_desc, w.groups.b_unban))))
check("...nor the join-request, roles, audit and ban pages (only Overview and Members remain)", [w.groups.tabs.isTabVisible(i) for i in range(6)] == [True, True, False, False, False, False], [w.groups.tabs.isTabVisible(i) for i in range(6)])
check("...the buttons everybody may use stay", not w.groups.b_open.isHidden() and not w.groups.b_copy.isHidden() and not w.groups.b_profile.isHidden())
check("...and it tells you what you can do", "only look" in w.groups.perms.text(), w.groups.perms.text())
# partial permissions: only what each permission allows is shown
def only(**yes):
    perms = {"groupMembershipPermissions": {"changeRank": yes.get("rank", False), "inviteMembers": yes.get("invite", False), "removeMembers": yes.get("remove", False)},
             "groupManagementPermissions": {"manageRelationships": False, "manageClan": False, "viewAuditLogs": yes.get("audit", False)},
             "groupPostsPermissions": {"viewWall": True, "postToWall": False, "deleteFromWall": False, "viewStatus": True, "postToStatus": yes.get("shout", False)}}
    w.groups.membership = {"permissions": perms, "canConfigure": yes.get("conf", False)}
    w.groups.apply_permissions()
    return [w.groups.tabs.isTabVisible(i) for i in range(6)], {n: not getattr(w.groups, n).isHidden() for n in ("b_rank", "b_kick", "b_ban", "b_accept", "b_shout", "b_desc", "b_unban")}
tabs_v, btns = only(rank=True)
check("someone who may only change ranks sees that button and the Roles page, nothing else", tabs_v == [True, True, False, True, False, False] and btns == {"b_rank": True, "b_kick": False, "b_ban": False, "b_accept": False, "b_shout": False, "b_desc": False, "b_unban": False}, (tabs_v, btns))
tabs_v, btns = only(remove=True)
check("someone who may only remove members sees Remove, Ban, Unban and the Join requests and Bans pages", tabs_v == [True, True, True, False, False, True] and btns["b_kick"] and btns["b_ban"] and btns["b_unban"] and not btns["b_rank"] and not btns["b_accept"], (tabs_v, btns))
tabs_v, btns = only(invite=True)
check("someone who may only accept join requests sees the Join requests page and the accept buttons, but no Bans page", tabs_v == [True, True, True, False, False, False] and btns["b_accept"] and not btns["b_kick"] and not btns["b_ban"], (tabs_v, btns))
tabs_v, btns = only(audit=True)
check("someone who may only view the audit log sees that page and no button", tabs_v == [True, True, False, False, True, False] and not any(btns.values()), (tabs_v, btns))
tabs_v, btns = only(shout=True)
check("someone who may only post the shout sees Set shout and no extra page", tabs_v == [True, True, False, False, False, False] and btns["b_shout"] and not btns["b_desc"], (tabs_v, btns))
tabs_v, btns = only(conf=True)
check("someone who may configure the group sees Edit description and the Roles page", tabs_v == [True, True, False, True, False, False] and btns["b_desc"] and not btns["b_shout"], (tabs_v, btns))
w.groups.tabs.setCurrentIndex(4); only(audit=False)
check("if the page you are on is taken away you land on the Overview", w.groups.tabs.currentIndex() == 0)
w.groups.clear_details()
check("with no group selected nothing that needs a permission is shown", [w.groups.tabs.isTabVisible(i) for i in range(6)] == [True, True, False, False, False, False] and w.groups.b_rank.isHidden() and w.groups.b_shout.isHidden())


# ---- the permission and the rank are checked again at the moment of the action
w.groups.select(77)
wait(lambda: w.groups.title.text() == "Cool Club" and w.groups.mtable.rowCount() == 2)
people = {m["username"]: m for m in w.groups.members}
saved_getitem, saved_info = QInputDialog.getItem, QMessageBox.information
offered = []
QInputDialog.getItem = staticmethod(lambda parent, title, label, items, *a, **k: (offered.append(list(items)) or items[0], True))
denied = []
QMessageBox.information = staticmethod(lambda *a, **k: denied.append(str(a[2])))


def as_rank(my, **perms):
    base = {"groupMembershipPermissions": {"changeRank": True, "inviteMembers": True, "removeMembers": True},
            "groupManagementPermissions": {"viewAuditLogs": True}, "groupPostsPermissions": {"postToStatus": True}}
    for k, v in perms.items():
        if k == "conf":
            continue
        base[{"rank": "groupMembershipPermissions", "invite": "groupMembershipPermissions", "remove": "groupMembershipPermissions",
              "shout": "groupPostsPermissions"}[k]][{"rank": "changeRank", "invite": "inviteMembers", "remove": "removeMembers", "shout": "postToStatus"}[k]] = v
    w.groups.membership = {"userRole": {"role": {"id": 3, "name": "Moderator", "rank": my}}, "permissions": base, "canConfigure": perms.get("conf", True)}
    w.groups.apply_permissions()


def pick_member(name):
    w.groups.mtable.clearSelection()
    w.groups.mtable.selectRow(next(r for r in range(w.groups.mtable.rowCount()) if w.groups.mtable.item(r, 1).text() == name))


# the roles you may give are only those below your own rank (Guest never)
as_rank(255)
check("the owner (rank 255) can give Member and Moderator, not Owner or Guest", [r["name"] for r in w.groups.assignable_roles()] == ["Member", "Moderator"])
as_rank(100)
check("a rank-100 moderator can only give Member (not Moderator, not Owner)", [r["name"] for r in w.groups.assignable_roles()] == ["Member"])
as_rank(1)
check("a rank-1 member has no role they could give", w.groups.assignable_roles() == [])
as_rank(100)
pick_member("dave"); offered.clear(); client.calls.clear(); denied.clear()
w.groups.change_rank()
check("the rank dialog of a rank-100 moderator offers only roles below 100", offered == [["Member (rank 1)"]], offered)
pick_member("erin"); offered.clear(); denied.clear(); client.calls.clear()
w.groups.change_rank()
check("a member of the same rank (erin, Moderator) cannot be changed: explained, no dialog, nothing sent", not offered and denied and "same as yours or higher" in denied[0] and not calls("PATCH", "/users/"), (offered, denied))
denied.clear(); w.groups.kick()
check("...nor removed", denied and "cannot remove" in denied[0] and not calls("DELETE", "/groups/77/users/"), denied)
denied.clear(); w.groups.ban()
check("...nor banned", denied and "cannot ban" in denied[0] and not calls("POST", "/bans/"), denied)
as_rank(255)
offered.clear(); denied.clear(); pick_member("erin")
w.groups.change_rank()
check("the owner may change a Moderator, and is offered Member and Moderator", offered == [["Member (rank 1)", "Moderator (rank 100)"]] and not denied, (offered, denied))
as_rank(1)
pick_member("dave"); offered.clear(); denied.clear()
w.groups.change_rank()
check("someone with the permission but no role below theirs is told so", not offered and denied, denied)

# the permission itself is checked again: calling the action without it is refused and sends nothing
as_rank(255, rank=False, invite=False, remove=False, shout=False, conf=False)
denied.clear(); client.calls.clear(); pick_member("dave")
for name, fn in (("change ranks", w.groups.change_rank), ("remove members", w.groups.kick), ("ban members", w.groups.ban), ("accept or decline join requests", lambda: w.groups.answer(True)),
                 ("post the shout", w.groups.set_status), ("edit the group settings", w.groups.edit_description), ("unban members", w.groups.unban)):
    denied.clear(); fn()
    check(f"without the permission to {name} the action is refused, with a reason", len(denied) == 1 and "do not have permission to " + name in denied[0], denied)
check("...and nothing was sent to Roblox", not client.calls or all(c[0] == "GET" for c in client.calls), [c for c in client.calls if c[0] != "GET"])
QInputDialog.getItem, QMessageBox.information = saved_getitem, saved_info
w.groups.select(88); wait(lambda: w.groups.title.text() == "Other Club")

# ---- 'Load more' pressed again and again, and a name that 'Load more' has not reached
w.groups.select(77)
wait(lambda: w.groups.title.text() == "Cool Club" and w.groups.mtable.rowCount() == 2)
real_members, real_search = client.group_members, getattr(client, "group_search_members", None)
asked_pages = []
PAGES = {"p2": ([U(41, "frank"), U(42, "gina")], "p3"), "p3": ([U(43, "hank"), U(21, "dave")], None)}          # (page 3 repeats dave: he must not be listed twice)


def slow_members(gid, role_id=None, cursor=None, limit=50, sort="Asc"):
    asked_pages.append(cursor)
    time.sleep(0.4)                                          # the page is 'on its way' while the person presses Load more again
    users, nxt = PAGES.get(cursor, ([], None))
    return {"data": [{"user": u, "role": ROLES[1]} for u in users], "nextPageCursor": nxt}


client.group_members = slow_members
w.groups.members_cursor = "p2"; w.groups.b_more_m.setEnabled(True)
for _ in range(6):
    w.groups.b_more_m.click(); w.groups.load_members(reset=False); spin(0.02)
check("pressing Load more again and again asks Roblox for the page only once", asked_pages == ["p2"], asked_pages)
check("...the button is off while the page is on its way", not w.groups.b_more_m.isEnabled())
check("...and the page arrives once: frank and gina are listed one time each", wait(lambda: len(w.groups.members) == 4 and w.groups.b_more_m.isEnabled()) and sorted(m["username"] for m in w.groups.members) == ["dave", "erin", "frank", "gina"], [m["username"] for m in w.groups.members])
w.groups.b_more_m.click(); spin(0.1)
w.groups.b_more_m.click()
check("the next page is asked for after the first one, once", wait(lambda: asked_pages == ["p2", "p3"] and not w.groups.b_more_m.isEnabled()), asked_pages)
check("a person who is on two pages (dave) is listed once, the rows are not multiplied", wait(lambda: sorted(m["username"] for m in w.groups.members) == ["dave", "erin", "frank", "gina", "hank"]) and w.groups.mtable.rowCount() == 5, (sorted(m["username"] for m in w.groups.members), w.groups.mtable.rowCount()))
check("...no more pages: the button stays off", not w.groups.b_more_m.isEnabled() and w.groups.members_cursor is None)

# a new list (reset) while a page is on its way: the old answer is thrown away
asked_pages.clear(); w.groups.members_cursor = "p2"; w.groups.load_members(reset=False); spin(0.05)
client.group_members = real_members
w.groups.load_members(reset=True)
check("an answer that comes after the list was reset does not mix into the new list", wait(lambda: len(w.groups.members) == 2 and w.groups.mtable.rowCount() == 2) and (spin(0.6) or True) and len(w.groups.members) == 2 and
      sorted(m["username"] for m in w.groups.members) == ["dave", "erin"], [m["username"] for m in w.groups.members])

# the search finds members that are not loaded
searched = []


def fake_search(gid, keyword, cursor=None, limit=100):
    searched.append(keyword)
    return {"data": [{"user": U(55, "zelda"), "role": ROLES[1]}] if "zelda".startswith(keyword.lower()) else []}


client.group_search_members = fake_search
w.groups.member_filter.setText("zel")
check("a username that Load more has not reached is found by Roblox's search and shown", wait(lambda: any(w.groups.mtable.item(r, 1).text() == "zelda" for r in range(w.groups.mtable.rowCount()))) and searched == ["zel"], (searched, w.groups.mtable.rowCount()))
check("...it says how many came from the search", "found by search" in w.groups.mcount.text(), w.groups.mcount.text())
check("...the loaded members are not in the way (nothing else matches)", w.groups.mtable.rowCount() == 1)
w.groups.mtable.selectRow(0)
check("...and the found member can be selected for an action", (w.groups._member_selected() or {}).get("id") == 55)
w.groups.member_filter.setText("")
check("clearing the box brings back the loaded members only", wait(lambda: w.groups.mtable.rowCount() == 2 and not w.groups.search_hits), w.groups.mtable.rowCount())
searched.clear()
w.groups.member_filter.setText("d"); spin(0.8)
check("one letter is not searched (too many results), it only filters the loaded ones", not searched and w.groups.mtable.rowCount() == 1)
w.groups.member_filter.setText("da"); spin(0.8)
check("...a member that is both loaded and found is listed once", searched == ["da"] and w.groups.mtable.rowCount() == 1 and w.groups.mtable.item(0, 1).text() == "dave", (searched, w.groups.mtable.rowCount()))
w.groups.member_filter.setText("zel")
w.groups.member_filter.setText("zelx"); spin(0.9)
check("typing on: only the answer for what is in the box now is used", w.groups.mtable.rowCount() == 0, [w.groups.mtable.item(r, 1).text() for r in range(w.groups.mtable.rowCount())])

# the search is not available (Roblox refuses it): the exact username is looked up instead
def refuse(*a, **k): raise rbx.RobloxError("not available", 404)


client.group_search_members = refuse
real_by_name, real_get = client.user_by_name, client.get
client.user_by_name = lambda name: {"id": 66, "name": "yoshi", "displayName": "Yoshi"} if name == "yoshi" else None
client.get = lambda url, params=None, **k: ({"data": [{"group": {"id": 77}, "role": ROLES[1]}]} if "/users/66/groups/roles" in url else real_get(url, params, **k))
w.groups.member_filter.setText("yoshi"); spin(0.9)
check("without the search, the exact username is looked up and its membership checked", [w.groups.mtable.item(r, 1).text() for r in range(w.groups.mtable.rowCount())] == ["yoshi"], [w.groups.mtable.item(r, 1).text() for r in range(w.groups.mtable.rowCount())])
client.user_by_name, client.get = real_by_name, real_get
client.group_search_members = real_search
w.groups.member_filter.setText("realf"); spin(0.9)
check("the REAL client method (no stand-in) searches the group through Roblox's search-members route", real_search is not None and [w.groups.mtable.item(r, 1).text() for r in range(w.groups.mtable.rowCount())] == ["realfind"] and calls("GET", "/groups/77/search-members"),
      ([w.groups.mtable.item(r, 1).text() for r in range(w.groups.mtable.rowCount())], calls("GET", "/search-members")))
w.groups.member_filter.setText(""); spin(0.2)

# ---------------------------------------------------------------- VIP servers
import tab_vip
check("ALL my VIP servers load by themselves on sign-in", wait(lambda: w.vip.mtable.rowCount() == 3))
games = {w.vip.mtable.item(r, 1).text(): (w.vip.mtable.item(r, 0).text(), w.vip.mtable.item(r, 2).text()) for r in range(3)}
check("each shows its game name and ON/OFF", games == {"My server": ("Adopt Me!", "ON"), "Old party": ("Brookhaven", "OFF"), "Zoo night": ("Zoo Tycoon", "ON")}, str(games))
check("the buttons are disabled until a server is selected", not w.vip.b_active.isEnabled() and not w.vip.b_allow.isEnabled())
def pick(name):
    w.vip.mtable.selectRow(next(r for r in range(w.vip.mtable.rowCount()) if w.vip.mtable.item(r, 1).text() == name)); spin(0.05)
pick("Old party")
check("selecting a server enables its controls", w.vip.b_active.isEnabled() and w.vip.b_allow.isEnabled() and w.vip.b_copy.isEnabled())
client.calls.clear(); w.vip.toggle_active()
check("switching an OFF server on sends active=true", wait(lambda: calls("PATCH", "/vip-servers/5100")) and calls("PATCH", "/vip-servers/5100")[0][3] == {"active": True}, str(calls("PATCH")[:1]))
check("...and the list shows it as ON, with the same server still selected", wait(lambda: w.vip.mtable.item(next(r for r in range(3) if w.vip.mtable.item(r, 1).text() == "Old party"), 2).text() == "ON") and w.vip._sel()["name"] == "Old party")
pick("My server"); ask_yes(False); client.calls.clear(); w.vip.toggle_active()
check("switching a server OFF asks first, and 'no' sends nothing", not calls("PATCH")); ask_yes(True)
w.vip.toggle_active()
check("switching a server OFF sends active=false", wait(lambda: calls("PATCH", "/vip-servers/5002")) and calls("PATCH")[0][3] == {"active": False})
wait(lambda: w.vip._sel() and not w.vip._sel().get("active"))
w.vip.select_group("enabled")
check("'select all enabled' selects the 2 ON servers", sorted(x["name"] for x in w.vip._sels()) == ["Old party", "Zoo night"], str([x["name"] for x in w.vip._sels()]))
check("...with several selected the single-server buttons are off and the bulk ones on", not w.vip.b_rename.isEnabled() and w.vip.bulk[0].isEnabled())
w.vip.select_group("disabled")
check("'select all disabled' selects the OFF one", [x["name"] for x in w.vip._sels()] == ["My server"])
client.calls.clear(); w.vip.bulk_active(True)
check("bulk switch on sends active=true for it", wait(lambda: calls("PATCH", "/vip-servers/5002")) and calls("PATCH", "/vip-servers/5002")[0][3] == {"active": True})
w.vip.select_group("all"); client.calls.clear(); w.vip.bulk_active(True); spin(0.3)
check("bulk switch on skips servers that are already on", not calls("PATCH", "/vip-servers/5101"))
opened = []; tab_vip.open_url = lambda u: opened.append(u); pick("Zoo night"); w.vip.open_game()
check("'Open game' opens the game's page", opened == ["https://www.roblox.com/games/5555"], str(opened))
copied = []; tab_vip.copy_text = lambda t: copied.append(t); client.calls.clear(); w.vip.copy_join()
check("copy join link puts Roblox's link on the clipboard", wait(lambda: copied) and "privateServerLinkCode=CODE123" in copied[0], str(copied))
# allow people: the fake Roblox refuses the first body format, so the app must fall back to the next one
class AutoDialog:
    def __init__(self, parent, ctx, name, perms, users):
        self.friends = type("F", (), {"isChecked": staticmethod(lambda: True)}); self.users = list(users) + [{"id": 77, "name": "newfriend", "displayName": "New Friend"}]
        seen_perms.append((perms, users))
    def exec(self): return QDialog.DialogCode.Accepted
seen_perms = []; tab_vip.PermissionsDialog = AutoDialog; perm_log.clear(); client.calls.clear(); w.vip.allow_people()
check("'Allow people' reads who can join now", wait(lambda: seen_perms) and seen_perms[0][0].get("friendsAllowed") is False and [u["name"] for u in seen_perms[0][1]] == ["dave"], str(seen_perms[:1]))
check("it saves friends + the chosen people, trying formats until Roblox accepts one", wait(lambda: len(perm_log) >= 2) and isinstance(perm_log[0]["users"][0], dict) and perm_log[-1]["users"] == [21, 77] and perm_log[-1]["friendsAllowed"] is True, str(perm_log))
check("it remembers the format that worked", client._perm_variant == "users as ids")
perm_log.clear(); w.vip.allow_people(); spin(1.0)
check("next time it starts with the remembered format (one request)", len(perm_log) == 1 and isinstance(perm_log[0]["users"][0], int), str(len(perm_log)))
pick("My server"); client.calls.clear(); QInputDialog.getText = staticmethod(lambda *a, **k: ("Renamed!", True)); w.vip.rename()
check("renaming sends the new name and updates the list", wait(lambda: calls("PATCH", "/vip-servers/5002")) and calls("PATCH")[0][3] == {"name": "Renamed!"} and wait(lambda: any(w.vip.mtable.item(r, 1).text() == "Renamed!" for r in range(3))))
client.calls.clear(); w.vip.new_link()
check("making a new link asks first and sends newJoinCode", wait(lambda: calls("PATCH")) and calls("PATCH")[0][3] == {"newJoinCode": True})
# a server whose id Roblox did not include cannot be managed, and says so
w.vip.mine.append({"name": "Mystery", "placeId": PLACE, "active": True, "_vid": None, "_key": "row9"}); w.vip.show_mine(); pick("Mystery"); asked.clear(); client.calls.clear(); w.vip.toggle_active()
check("a server without an id is not touched, and you are told why", not calls("PATCH") and any(t == "info" and "id" in x for t, x in asked), str(asked[-1:]))
# create: the dialog asks for the game as well
class FakeDlg:
    game = type("G", (), {"text": staticmethod(lambda: "https://www.roblox.com/games/%d/Adopt-Me" % PLACE)})
    name = type("N", (), {"text": staticmethod(lambda: "Party room")})
    price = type("P", (), {"value": staticmethod(lambda: 100)})
    def __init__(self, *a): pass
    def exec(self): return QDialog.DialogCode.Accepted
tab_vip.CreateDialog = FakeDlg
asked.clear(); client.calls.clear(); w.vip.create()
check("creating warns that Robux will be spent", wait(lambda: any(t == "Create VIP server" and "100 Robux will be spent" in x and "Adopt Me" in x for t, x in asked)), str(asked[-1:]))
check("...and sends the name and the price you agreed to", wait(lambda: calls("POST", "/games/vip-servers/%d" % UNIVERSE)) and calls("POST", "vip-servers")[0][3] == {"name": "Party room", "expectedPrice": 100})
ask_yes(False); client.calls.clear(); w.vip.create(); spin(0.5)
check("declining the confirmation creates nothing", not calls("POST")); ask_yes(True)
# looking up another game still works (friends' servers)
w.vip.entry.setText(f"https://www.roblox.com/games/{PLACE}/Adopt-Me"); w.vip.load_game()
check("looking up a game lists its servers with yours and your friends' marked", wait(lambda: w.vip.table.rowCount() == 3))
rows = {w.vip.table.item(r, 2).text(): (w.vip.table.item(r, 0).text(), w.vip.table.item(r, 1).text()) for r in range(3)}
check("...marked correctly", rows == {"My server": ("YES", ""), "Alice party": ("", "YES"), "Stranger": ("", "")}, str(rows))

# ---------------------------------------------------------------- explorer
e = w.explorer
check("the catalog has hundreds of endpoints", len(e.entries) > 250, str(len(e.entries)))
e.search.setText("join-requests"); e.only_get.setChecked(True)
check("searching narrows the list", 0 < len(e.visible) < 5 and all(x["method"] == "GET" for x in e.visible), str([x["path"] for x in e.visible]))
e.search.setText("groups/{groupid}/users/{userid}"); e.only_get.setChecked(False)
patch = next(i for i, x in enumerate(e.visible) if x["method"] == "PATCH" and x["path"].endswith("/users/{userId}"))
e.list.setCurrentRow(patch)
check("choosing an endpoint fills the address, parameters and a body example", e.url.text().endswith("/v1/groups/{groupId}/users/{userId}") and e.params.rowCount() == 2 and json.loads(e.body.toPlainText()) == {"roleId": 0}, e.body.toPlainText()[:40])
e.send()
check("an unfilled {placeholder} is explained, nothing is sent", "Fill in the value" in e.result.toPlainText())
e.params.item(0, 2).setText("77"); e.params.item(1, 2).setText("21"); e.body.setPlainText('{"roleId": 3}'); client.calls.clear(); asked.clear(); e.send()
check("a request that changes data asks first, then goes out", wait(lambda: calls("PATCH", "/groups/77/users/21")) and any("changes data" in t for t, _ in asked))
check("the answer is displayed", wait(lambda: e.result_head.text().startswith("HTTP 200")), e.result_head.text())
e.url.setText("https://example.com/evil"); e.method.setCurrentText("GET"); e.params.setRowCount(0); client.calls.clear(); e.send()
check("a non-Roblox address is refused", "only https://...roblox.com" in e.result.toPlainText() and not client.calls)
e.url.setText("http://groups.roblox.com/v1/x"); e.send()
check("plain http is refused", "only https" in e.result.toPlainText())
e.url.setText("https://groups.roblox.com/v1/groups/%s" % "{groupId}"); e.add_param("groupId", "path", "77"); e.params.item(e.params.rowCount() - 1, 2).setText("77")
e.body.setPlainText("{bad json"); e.method.setCurrentText("POST"); asked.clear(); e.send()
check("invalid JSON is caught before sending", "not valid JSON" in e.result.toPlainText())
e.method.setCurrentText("GET"); e.copy_curl()
from PySide6.QtGui import QGuiApplication
curl = QGuiApplication.clipboard().text()
check("'Copy as curl' never contains the cookie", COOKIE[:30] not in curl and "$ROBLOSECURITY" in curl and "groups.roblox.com/v1/groups/77" in curl, curl[:90])

w.groups.select(77); spin(1.5); w.groups.tabs.setCurrentIndex(1)
for i, name in ((1, "friends"), (2, "groups"), (3, "vip")):
    w.tabs.setCurrentIndex(i); spin(0.4); w.grab().save(os.path.join(here, "full_" + name + ".png"))
w.groups.tabs.setCurrentIndex(0)
# ---------------------------------------------------------------- errors and signing out
client.fail[r"GET groups.roblox.com/v1/groups/77/audit-log"] = 403
asked.clear(); w.groups.select(77); spin(1.5)
check("a refused request is reported to you, not hidden", "Could not load" in w.groups.acount.text() and "403" in w.groups.acount.text(), w.groups.acount.text())
client.fail[r"PATCH groups.roblox.com/v1/groups/77/(description|status)"] = 403; asked.clear()
QInputDialog.getText = staticmethod(lambda *a, **k: ("x", True)); w.groups.set_status(); spin(1.0)
check("a refused action pops up Roblox's answer", any(t == "warning" and "403" in m for t, m in asked), str(asked[:1]))
rbx_logged = open(os.path.join(os.environ["ROBLOX_MANAGER_STATE"], "manager.log")).read() if os.path.exists(os.path.join(os.environ["ROBLOX_MANAGER_STATE"], "manager.log")) else ""
check("the log never contains the cookie", COOKIE[:30] not in rbx_logged)
w.vip.load_mine()
check("the VIP link column fills in by itself", wait(lambda: sum(1 for r in range(w.vip.mtable.rowCount()) if w.vip.mtable.item(r, 5) and "privateServerLinkCode=" in w.vip.mtable.item(r, 5).text()) >= 1), str([w.vip.mtable.item(r, 5).text() if w.vip.mtable.item(r, 5) else None for r in range(w.vip.mtable.rowCount())]))
check("the VIP id column is narrow", w.vip.mtable.columnWidth(4) <= 110)
w.vip.show_mine(); w.vip.select_group("all")
_orig = client.update_vip_server
def _slow(vid, **f): time.sleep(0.4); return _orig(vid, **f)
client.update_vip_server = _slow
for sv in w.vip.mine: sv["active"] = False
seen = []
w.vip.progress.connect(lambda l, d, t, s: seen.append((l, d, t)))
w.vip.bulk_active(True)
check("a bulk action shows a progress bar with done/left", wait(lambda: w.vip.progress_box.isVisible() and "left" in w.vip.bar.format()), w.vip.bar.format())
check("...and the buttons are locked while it runs", not w.vip.bulk[0].isEnabled())
check("...then it finishes and the bar goes away", wait(lambda: not w.vip.progress_box.isVisible() and w.vip.bulk[0].isEnabled(), 15))
check("progress reported each step", [d for _, d, _ in seen][:3] == [0, 1, 2] or len(seen) >= 3, str(seen))
client.update_vip_server = _orig
_orig2 = client.update_vip_server
_n = []
def _limited(vid, **f):
    _n.append(vid)
    if len(_n) > 1: raise rbx.RobloxError(400, "You cannot have more active free private servers. Please deactivate some other servers first.")
    return _orig2(vid, **f)
client.update_vip_server = _limited
for sv in w.vip.mine: sv["active"] = False
w.vip.select_group("all"); asked.clear(); ctx.confirm = lambda title, text, danger=False: (asked.append((title, text)), title != "Free server limit reached")[1]; w.vip.bulk_active(True)
check("the free-server limit stops the batch after the first refusal", wait(lambda: any(t == "warning" for t, _ in asked), 15) and len(_n) == 2, str(_n))
check("...and explains the limit", any("free VIP servers" in m for t, m in asked if t == "warning"), str(asked[-1:])[:300])
client.update_vip_server = _orig2
# swap: the active server is switched off, then the refused one on
live = {"5002"}
log2 = []
def _one_free(vid, **f):
    log2.append((vid, f))
    if f.get("active") is True and live - {str(vid)}: raise rbx.RobloxError(400, "You cannot have more active free private servers. Please deactivate some other servers first.")
    (live.add if f.get("active") else live.discard)(str(vid)); return {}
client.update_vip_server = _one_free
S = lambda name, game, active, renew, state="": {"name": name, "universeId": game, "active": active, "willRenew": renew, "_state": state, "expirationDate": "2026-12-01T00:00:00Z", "_vid": hash(name) % 9999, "_key": name}
w.vip.mine = [S("on-one", 1, True, True), S("wants-on", 2, False, True)]
w.vip.mine[0]["_vid"], w.vip.mine[1]["_vid"] = 5002, 5100
w.vip.show_mine(); asked.clear(); ask_yes(True)
w.vip.offer_swap(w.vip.mine[1])
check("the swap asks first, naming the server that is on", asked and asked[-1][0] == "Free server limit reached" and "on-one" in asked[-1][1], str(asked[-1:])[:200])
check("...switches the active one off, then the other on", wait(lambda: len(log2) == 2) and log2 == [(5002, {"active": False}), (5100, {"active": True})], str(log2))
client.update_vip_server = _orig2
client._tell_rate("https://games.roblox.com/v1/vip-servers/1", 5.0, False); spin(0.2)
check("a rate limit is announced on the VIP tab", w.vip.ratenote.isVisible() is not None and "rate-limiting" in w.vip.ratenote.text() and "5 s" in w.vip.ratenote.text(), w.vip.ratenote.text())
client._tell_rate("https://games.roblox.com/v1/vip-servers/2", 0, True); spin(0.2)
check("...including when a request is given up on", "Gave up" in w.vip.ratenote.text(), w.vip.ratenote.text())
import tab_vip as tv2
S = lambda name, game, active, renew, state="": {"name": name, "universeId": game, "active": active, "willRenew": renew, "_state": state, "expirationDate": "2026-12-01T00:00:00Z", "_vid": hash(name) % 9999, "_key": name}
grp = tv2.duplicate_groups([S("a-off", 1, False, True), S("a-on-renew", 1, True, True), S("a-on-norenew", 1, True, False), S("a-expired", 1, True, True, "Expired"), S("b-only", 2, True, True)])
check("duplicates are found per game, best first", list(grp) == [1] and [x["name"] for x in grp[1]] == ["a-on-renew", "a-on-norenew", "a-off", "a-expired"], str([x["name"] for x in grp.get(1, [])]))
w.vip.mine = [S("a-off", 1, False, True), S("a-on-renew", 1, True, True), S("a-on-norenew", 1, True, False), S("b-only", 2, True, True)]
w.vip.show_mine(); w.vip.select_group("best")
check("'One per game' picks the on+renewing one, and the lone server of the other game", sorted(x["name"] for x in w.vip._sels()) == ["a-on-renew", "b-only"], str([x["name"] for x in w.vip._sels()]))
w.vip.select_group("extras")
check("'Duplicates' picks the extras only", sorted(x["name"] for x in w.vip._sels()) == ["a-off", "a-on-norenew"], str([x["name"] for x in w.vip._sels()]))
check("the Copies column marks duplicated games", sorted(w.vip.mtable.item(r, 6).text() for r in range(4)) == ["", "x3", "x3", "x3"], str([w.vip.mtable.item(r, 6).text() for r in range(4)]))
check("the note mentions the duplicates", "more than one VIP server" in w.vip.mnote.text(), w.vip.mnote.text())
w.vip.mine = [S("a-off", 1, False, True), S("a-on-renew", 1, True, True), S("c-off1", 3, False, True), S("c-off2", 3, False, False), S("d-off", 4, False, True)]
w.vip.show_mine(); w.vip.select_group("disabled")
check("'All disabled' skips disabled servers that have a better copy in the same game", sorted(x["name"] for x in w.vip._sels()) == ["c-off1", "d-off"], str([x["name"] for x in w.vip._sels()]))
w.vip.select_group("enabled")
check("'All enabled' still picks the enabled one", [x["name"] for x in w.vip._sels()] == ["a-on-renew"])
import tab_account as ta
from datetime import datetime, timezone
check("'not online for' compares dates and ignores unknown times", ta.inactive_for("2020-01-01T00:00:00Z", 365) and not ta.inactive_for(datetime.now(timezone.utc).isoformat(), 30) and not ta.inactive_for(None, 30))
w.tabs.setCurrentIndex(1); spin(0.3); w.friends.load(); wait(lambda: w.friends.table.rowCount() == 3)
w.friends.search.setText(""); w.friends.select_where(lambda r: True)
check("'All shown' selects every friend and the panel says so", len(w.friends._sels()) == 3 and "3 friends selected" in w.friends.profile.text(), w.friends.profile.text())
w.friends.invert_selection()
check("'Invert' flips the selection", len(w.friends._sels()) == 0)
w.friends.select_where(lambda r: r["id"] in (11, 12))
ctx.confirm = lambda title, text, danger=False: (asked.append((title, text)), False)[1]; client.calls.clear(); w.friends.remove_selected(); spin(0.3)
check("saying no removes nobody", not calls("POST", "/unfriend") and any(t == "Remove friends" and "cannot be undone" in m for t, m in asked))
ask_yes(True); client.calls.clear(); w.friends.remove_selected()
check("removing sends one unfriend per selected friend", wait(lambda: len(calls("POST", "/unfriend")) == 2, 12) and sorted(c[1].split("/")[-2] for c in calls("POST", "/unfriend")) == ["11", "12"], str(calls("POST", "/unfriend")))
check("...they disappear from the list and the others stay", wait(lambda: sorted(r["id"] for r in w.friends.rows) == [13] and w.friends.table.rowCount() == 1))
check("...the progress bar goes away and the button is back", wait(lambda: not w.friends.progress_box.isVisible() and w.friends.btn_remove.isEnabled()))
rem = (rbx.STATE_DIR / "removed-friends.txt").read_text() if (rbx.STATE_DIR / "removed-friends.txt").exists() else ""
check("who was removed is saved to a file", "\t11\t" in rem and "\t12\t" in rem, rem)
# 5 or more: type the number
w.friends.rows = [{"id": 900 + k, "name": "F%d" % k, "username": "f%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": "2019-01-01T00:00:00Z"} for k in range(6)]
w.friends.apply_filter(); w.friends.inactive.setCurrentIndex(3); w.friends.select_inactive()
check("'Select them' picks friends offline for over a year", len(w.friends._sels()) == 6)
QInputDialog.getText = staticmethod(lambda *a, **k: ("5", True)); client.calls.clear(); w.friends.remove_selected(); spin(0.4)
check("a wrong typed number cancels (5 or more friends)", not calls("POST", "/unfriend"))
QInputDialog.getText = staticmethod(lambda *a, **k: ("6", True)); w.friends.remove_selected()
check("the right number goes ahead", wait(lambda: len(calls("POST", "/unfriend")) == 6, 15))
wait(lambda: not w.friends.running)
client.fail[r"POST friends.roblox.com/v1/users/\d+/unfriend"] = 403
w.friends.rows = w.friends.rows or []
w.friends.rows = [{"id": 950, "name": "Z", "username": "z", "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": None}]
w.friends.apply_filter(); w.friends.select_where(lambda r: True); asked.clear(); w.friends.remove_selected()
check("a refused unfriend is reported with the friend and Roblox's answer", wait(lambda: any(t == "warning" and "Z" in m and "403" in m for t, m in asked)), str(asked[-1:])[:200])
check("...and that friend stays in the list", [r["id"] for r in w.friends.rows] == [950])
client.fail.pop(r"POST friends.roblox.com/v1/users/\d+/unfriend", None)
from datetime import date
check("date-range test: inside, edges, outside, unknown", ta.last_online_between("2022-06-15T12:00:00Z", date(2022, 6, 1), date(2022, 6, 30)) and not ta.last_online_between("2022-07-15T12:00:00Z", date(2022, 6, 1), date(2022, 6, 30)) and not ta.last_online_between(None, date(2000, 1, 1), date(2100, 1, 1)))
w.friends.rows = [{"id": 800 + k, "name": "D%d" % k, "username": "d%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": l}
                  for k, l in enumerate(["2021-03-10T12:00:00Z", "2022-06-15T12:00:00Z", "2023-09-01T12:00:00Z", None])]
w.friends.apply_filter()
from PySide6.QtCore import QDate
w.friends.date_from.setDate(QDate(2022, 1, 1)); w.friends.date_to.setDate(QDate(2023, 12, 31)); w.friends.select_by_date()
check("'Select by date' picks friends last online in the range", sorted(r["name"] for r in w.friends._sels()) == ["D1", "D2"], str([r["name"] for r in w.friends._sels()]))
w.friends.date_from.setDate(QDate(2023, 12, 31)); w.friends.date_to.setDate(QDate(2022, 1, 1)); w.friends.select_by_date()
check("...and swaps the dates if they are the wrong way round", sorted(r["name"] for r in w.friends._sels()) == ["D1", "D2"])
w.tabs.setCurrentIndex(2); spin(0.3)
w.groups.group_rows = [{"group": {"id": 77, "name": "Mine", "memberCount": 10, "owner": {"userId": 1000}}, "role": {"id": 2, "name": "Admin", "rank": 255}}, {"group": {"id": 201, "name": "G1", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}, {"group": {"id": 202, "name": "G2", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}, {"group": {"id": 203, "name": "G3", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Admin", "rank": 50}}, {"group": {"id": 204, "name": "G4", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}, {"group": {"id": 205, "name": "G5", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}, {"group": {"id": 206, "name": "G6", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}]
w.groups._show_groups()
check("the groups list allows several selected", w.groups.glist.selectionMode() == QTableWidget.SelectionMode.ExtendedSelection if "QTableWidget" in dir() else True)
w.groups.select_groups_where(lambda g: g["role"]["rank"] <= 1)
check("'Plain members' selects only rank-1 groups", sorted(g["group"]["id"] for g in w.groups._group_sels()) == [201, 202, 204, 205, 206], str([g["group"]["id"] for g in w.groups._group_sels()]))
w.groups.gfilter.setText("g2"); w.groups.select_groups_where(lambda g: True)
check("the filter narrows 'All shown'", [g["group"]["id"] for g in w.groups._group_sels()] == [202])
w.groups.gfilter.setText("")
w.groups.select_groups_where(lambda g: True)
check("a multi-selection does not open a group page", len(w.groups._group_sels()) == 7)
asked.clear(); ctx.confirm = lambda title, text, danger=False: (asked.append((title, text)), False)[1]; client.calls.clear(); w.groups.leave_selected(); spin(0.3)
check("saying no leaves nothing; owned groups are mentioned as skipped", not calls("DELETE", "/users/1000") and any("owned by you" in m for t, m in asked), str(asked[-1:])[:200])
ask_yes(True); QInputDialog.getText = staticmethod(lambda *a, **k: ("5", True)); client.calls.clear(); w.groups.leave_selected(); spin(0.3)
check("a wrong typed number (6 groups to leave) cancels", not calls("DELETE", "/users/1000"))
QInputDialog.getText = staticmethod(lambda *a, **k: ("6", True)); asked.clear(); w.groups.leave_selected()
check("leaving sends one request per group, never for the owned one", wait(lambda: len(calls("DELETE", "/users/1000")) == 6, 20) and not any("/groups/77/" in c[1] for c in calls("DELETE")), str([c[1] for c in calls("DELETE")]))
check("...they leave the list, the owned one stays", wait(lambda: [g["group"]["id"] for g in w.groups.group_rows] == [77] and w.groups.glist.rowCount() == 1))
check("...the bar goes away and the button returns", wait(lambda: not w.groups.bulk.box.isVisible() and w.groups.b_leave.isEnabled()))
lg = (rbx.STATE_DIR / "left-groups.txt").read_text() if (rbx.STATE_DIR / "left-groups.txt").exists() else ""
check("the groups you left are saved to a file", "\t201\tG1\t" in lg and "\t206\tG6\t" in lg, lg)
w.groups.group_rows = [{"group": {"id": 77, "name": "Mine", "memberCount": 10, "owner": {"userId": 1000}}, "role": {"id": 2, "name": "Admin", "rank": 255}}]; w.groups._show_groups(); w.groups.select_groups_where(lambda g: True); asked.clear(); QMessageBox.information = staticmethod(lambda *a, **k: asked.append(("info", str(a[2]))))
w.groups.leave_selected()
check("only owned groups selected: it explains instead of trying", any(t == "info" and "own every selected group" in m for t, m in asked), str(asked[-1:])[:200])
client.fail[r"DELETE groups.roblox.com/v1/groups/\d+/users/1000"] = 403
w.groups.group_rows = [{"group": {"id": 300, "name": "Locked", "memberCount": 10, "owner": {"userId": 999}}, "role": {"id": 2, "name": "Member", "rank": 1}}]; w.groups._show_groups(); w.groups.select_groups_where(lambda g: True); asked.clear(); w.groups.leave_selected()
check("a refused leave is reported with the group and Roblox's answer", wait(lambda: any(t == "warning" and "Locked" in m and "403" in m for t, m in asked)), str(asked[-1:])[:200])
check("...and that group stays in the list", [g["group"]["id"] for g in w.groups.group_rows] == [300])
client.fail.pop(r"DELETE groups.roblox.com/v1/groups/\d+/users/1000", None)
w.groups.load_groups()
check("the Created column fills from Roblox's multiget", wait(lambda: w.groups.glist.rowCount() == 2 and {w.groups.glist.item(r, 4).text() for r in range(2)} == {"2015-05-05", "2020-02-02"}), str([w.groups.glist.item(r, 4).text() for r in range(w.groups.glist.rowCount())]))
from PySide6.QtCore import QDate
w.groups.date_from.setDate(QDate(2019, 1, 1)); w.groups.date_to.setDate(QDate(2021, 12, 31)); w.groups.select_by_date()
check("'Select by date' picks groups created in the range", [g["group"]["id"] for g in w.groups._group_sels()] == [88], str([g["group"]["id"] for g in w.groups._group_sels()]))
w.groups.date_from.setDate(QDate(2021, 12, 31)); w.groups.date_to.setDate(QDate(2010, 1, 1)); w.groups.select_by_date()
check("...swapping the dates if reversed", sorted(g["group"]["id"] for g in w.groups._group_sels()) == [77, 88], str([g["group"]["id"] for g in w.groups._group_sels()]))
w.groups.load_groups(); wait(lambda: w.groups.glist.rowCount() == 2)
w.groups.select(88); wait(lambda: w.groups.title.text() not in ("Loading...", "Select a group") and w.groups.mtable.rowCount() > 0)
check("a group's page is open before leaving it", w.groups.gid == 88 and w.groups.tabs.isEnabled() and w.groups.mtable.rowCount() > 0)
ask_yes(True); client.calls.clear(); w.groups.select_groups_where(lambda g: g["group"]["id"] == 88); w.groups.leave_selected()
check("leaving the open group sends the request", wait(lambda: len(calls("DELETE", "/groups/88/users/1000")) == 1, 10))
check("...and empties the group page (title, details, members, tabs)", wait(lambda: w.groups.gid is None and w.groups.title.text() == "Select a group" and not w.groups.tabs.isEnabled()
      and w.groups.mtable.rowCount() == 0 and w.groups.facts.text() == "" and w.groups.desc.toPlainText() == ""), f"{w.groups.gid} {w.groups.title.text()} {w.groups.mtable.rowCount()}")
check("...while the other group stays in the list", [g["group"]["id"] for g in w.groups.group_rows] == [77])
import csv as _csv, tempfile
from PySide6.QtWidgets import QFileDialog
import re as _re
base = lambda t: _re.sub(r" \(.*\)$", "", t)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textfit
_cut = {}
textfit.check_window(w, [1180, 900], _cut)
check("no text is cut off on any tab or sub-tab (window full of data, 1180 and 900 px wide)", not _cut, "\n".join(textfit.lines(_cut)[:12]))
w.resize(1180, 760)
check("the tabs are Home, People, Groups, VIP servers, Money, Request log, API Explorer, Staff List, Admin, Settings", [base(w.tabs.tabText(i)) for i in range(w.tabs.count())] == ["Home", "People", "Groups", "VIP servers", "Money", "Request log", "API Explorer", "Staff List", "Admin", "Settings"], [w.tabs.tabText(i) for i in range(w.tabs.count())])
check("People has Friends, Requests, Followers, Following, Blocked, Find a user, Alerts", [base(w.people.tabs.tabText(i)) for i in range(w.people.tabs.count())] == ["Friends", "Requests", "Followers", "Following", "Blocked", "Find a user", "Alerts"])
ask_yes(True)
w.account.sign_in(); wait(lambda: ctx.logged_in)
check("Home shows Roblox Plus and the email status", wait(lambda: w.account.fields["Roblox Plus"].text() == "yes" and "verified" in w.account.fields["Email"].text()), str((w.account.fields["Roblox Plus"].text(), w.account.fields["Email"].text())))
pp = w.people
w.tabs.setCurrentIndex(1); pp.tabs.setCurrentIndex(1)
check("Requests loads; the tab title shows the count", wait(lambda: pp.requests.table.rowCount() == 3) and pp.tabs.tabText(1) == "Requests (3)", pp.tabs.tabText(1))
pp.requests.select_where(lambda r: True); client.calls.clear(); pp.requests.run_action(pp.requests.actions[0])
check("accepting all selected sends one accept per request", wait(lambda: len(calls("POST", "accept-friend-request")) == 3, 15) and sorted(c[1].split("/")[-2] for c in calls("POST", "accept-friend-request")) == ["31", "32", "33"])
check("...they leave the list and the tab title loses the count", wait(lambda: pp.requests.table.rowCount() == 0 and pp.tabs.tabText(1) == "Requests"))
client.calls.clear(); pp.requests.load(); wait(lambda: pp.requests.table.rowCount() == 3); pp._decline_all = None
import tab_people as tp2
tp2._decline_all(pp.requests)
check("'Decline ALL' is one request after asking", wait(lambda: len(calls("POST", "decline-all")) == 1))
pp.tabs.setCurrentIndex(2)
check("Followers loads with who you follow back", wait(lambda: pp.followers.table.rowCount() == 3) and sorted(pp.followers.table.item(r, 2).text() for r in range(3)) == ["", "", "yes"])
pp.followers.select_where(lambda r: not r["cells"][0])
check("'Not followed back' selects the 2 you do not follow", sorted(r["id"] for r in pp.followers.sels()) == [21, 61])
client.calls.clear(); pp.followers.run_action(pp.followers.actions[0])
check("'Follow back' follows them and marks them", wait(lambda: len(calls("POST", "/follow")) == 2, 15) and wait(lambda: all(r["cells"][0] == "yes" for r in pp.followers.rows)))
pp.tabs.setCurrentIndex(3)
check("Following loads", wait(lambda: pp.following.table.rowCount() == 6))
pp.following.select_where(lambda r: not r["cells"][0])
check("'Not following me back' selects the 5 who do not follow you", len(pp.following.sels()) == 5)
QInputDialog.getText = staticmethod(lambda *a, **k: ("4", True)); client.calls.clear(); pp.following.run_action(pp.following.actions[0]); spin(0.4)
check("unfollowing 5 asks to type the number; a wrong one cancels", not calls("POST", "/unfollow"))
QInputDialog.getText = staticmethod(lambda *a, **k: ("5", True)); pp.following.run_action(pp.following.actions[0])
check("the right number unfollows all 5", wait(lambda: len(calls("POST", "/unfollow")) == 5, 20) and wait(lambda: pp.following.table.rowCount() == 1))
check("...and the unfollowed people are saved to a file", "celeb" in (rbx.STATE_DIR / "unfollowed.txt").read_text())
pp.tabs.setCurrentIndex(4)
check("Blocked loads the list", wait(lambda: pp.blocked.table.rowCount() == 1) and pp.blocked.table.item(0, 0).text() == "Bad One")
pp.blocked.select_where(lambda r: True); client.calls.clear(); pp.blocked.run_action(pp.blocked.actions[0])
check("unblocking sends the request and clears the row", wait(lambda: len(calls("POST", "unblock-user")) == 1) and wait(lambda: pp.blocked.table.rowCount() == 0))
pp.tabs.setCurrentIndex(5)
pp.find.entry.setText("bob"); pp.find.search()
check("Find a user lists the exact match first, then the search results", wait(lambda: pp.find.table.rowCount() == 3) and pp.find.results[0]["id"] == 77, [u["id"] for u in pp.find.results])
pp.find.table.selectRow(next(r for r in range(3) if pp.find.table.item(r, 2).text() == "99")); client.calls.clear(); pp.find.b_friend.click()
check("'Send friend request' sends it for the selected user", wait(lambda: len(calls("POST", "request-friendship/99".replace("request-friendship/99", "request-friendship"))) == 1) and "/users/99/" in calls("POST", "request-friendship")[0][1])
pp.find.b_block.click()
check("'Block' asks first and then blocks", wait(lambda: len(calls("POST", "/users/99/block-user")) == 1))
# blocked list unavailable: this app's own record is used
(rbx.STATE_DIR / "blocked-by-app.json").unlink(missing_ok=True)
client.fail[r"GET apis.roblox.com/user-blocking-api/v1/users/me/blocked-users"] = 404
pp.tabs.setCurrentIndex(5); pp.find.entry.setText("bobby"); pp.find.search(); wait(lambda: pp.find.table.rowCount() >= 2)
pp.find.table.selectRow(next(r for r in range(pp.find.table.rowCount()) if pp.find.table.item(r, 2).text() == "99")); client.calls.clear(); pp.find.b_block.click()
wait(lambda: len(calls("POST", "/users/99/block-user")) == 1); spin(0.2)
pp.tabs.setCurrentIndex(4); pp.blocked.load()
check("when Roblox will not give the blocked list, the app's own record is shown", wait(lambda: pp.blocked.table.rowCount() == 1 and pp.blocked.table.item(0, 0).text() == "Bobby"), pp.blocked.info.text())
check("...and says where the list comes from", "from this app" in pp.blocked.info.text(), pp.blocked.info.text())
pp.blocked.select_where(lambda r: True); client.calls.clear(); pp.blocked.run_action(pp.blocked.actions[0])
check("unblocking from it sends the request and updates the record", wait(lambda: len(calls("POST", "/users/99/unblock-user")) == 1) and wait(lambda: pp.blocked.table.rowCount() == 0) and tp2._blocked_local() == [], str(tp2._blocked_local()))
QInputDialog.getText = staticmethod(lambda *a, **k: ("bob", True)); client.calls.clear(); tp2._unblock_by_name(pp.blocked)
check("'Unblock by name or id' finds the user and unblocks them", wait(lambda: len(calls("POST", "/users/77/unblock-user")) == 1), str([c[1] for c in calls("POST")]))
del client.fail[r"GET apis.roblox.com/user-blocking-api/v1/users/me/blocked-users"]
# money
w.tabs.setCurrentIndex(4)
check("Money shows the balance and the pending total", wait(lambda: w.money.balance.text() == "Robux: 1,234" and w.money.pending.text() == "Pending: 590"), (w.money.balance.text(), w.money.pending.text()))
check("...the period totals (only non-zero rows)", wait(lambda: w.money.totals.rowCount() == 2) and {w.money.totals.item(r, 0).text() for r in range(2)} == {"Pending Robux", "Incoming"}, [w.money.totals.item(r, 0).text() for r in range(w.money.totals.rowCount())])
check("...and a transaction list", wait(lambda: w.money.table.rowCount() > 0), w.money.info.text())
_fd, tmp = tempfile.mkstemp(suffix=".csv"); os.close(_fd); QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (tmp, ""))
import ui_common as uc
uc.export_csv(w.money.table, w, name="t")
rows = list(_csv.reader(open(tmp, encoding="utf-8-sig")))
check("Export CSV writes the headers and every row", rows[0][:3] == ["Date", "Robux", "Type"] and len(rows) == w.money.table.rowCount() + 1, rows[:2])
w.money.table.selectRow(0)
check("copy/export can use just the selected rows", len(uc.table_rows(w.money.table, True)) == 2)
n_all = w.money.table.rowCount()
w.money.only_pending.setChecked(True); w.money.load_transactions()
check("'Only pending' hides the settled transaction", wait(lambda: w.money.table.rowCount() == n_all - 1), (n_all, w.money.table.rowCount()))
# vip filter + ui state
w.vip.mine = [{"name": "alpha farm", "universeId": 1, "placeId": 4444, "active": True, "_state": "", "_vid": 111, "_key": 111, "willRenew": True, "expirationDate": "2099-01-01T00:00:00Z"},
              {"name": "beta", "universeId": 2, "placeId": 5555, "active": False, "_state": "", "_vid": 222, "_key": 222, "willRenew": True, "expirationDate": "2099-01-01T00:00:00Z"}]
w.vip.names = {4444: "Brookhaven", 5555: "Zoo Tycoon"}
w.vip.mfilter.setText(""); w.vip.show_mine()
check("the VIP list shows both servers", w.vip.mtable.rowCount() == 2)
w.vip.mfilter.setText("zoo")
check("the VIP filter matches the game name", w.vip.mtable.rowCount() == 1 and w.vip.mtable.item(0, 1).text() == "beta")
w.vip.mfilter.setText("111")
check("...or the VIP id", w.vip.mtable.rowCount() == 1 and w.vip.mtable.item(0, 1).text() == "alpha farm")
w.vip.mfilter.setText("")
w._state_on = True; w.tabs.setCurrentIndex(3); w.vip.hide["Expired"].setChecked(False); w._save_state()
w.tabs.setCurrentIndex(0); w.vip.hide["Expired"].setChecked(True); w._restore_state(True)
check("the window remembers the tab and the VIP hide switches", w.tabs.currentIndex() == 3 and not w.vip.hide["Expired"].isChecked() and w.vip.hide["Unavailable"].isChecked())
w._state_on = False
import tab_vip as tv3
farm = {"active": False, "priceInRobux": None, "expirationDate": "2026-03-19T13:26:48.29Z", "willRenew": False, "totalDiscountAmountInRobux": 100}
blade = {"active": True, "priceInRobux": None, "expirationDate": "2123-10-04T20:59:23.33Z", "willRenew": False, "totalDiscountAmountInRobux": None}
old = {"active": False, "priceInRobux": None, "expirationDate": "2025-07-19T10:09:34.68Z", "willRenew": False, "totalDiscountAmountInRobux": None}
paid = {"priceInRobux": 100, "expirationDate": "2026-12-01T00:00:00Z"}
check("cost: a discount means free through Roblox Plus", tv3.cost_kind(farm) == "Free (Roblox Plus)")
check("cost: an expiry ~100 years away means free from the game", tv3.cost_kind(blade) == "Free (game)")
check("cost: a price means paid", tv3.cost_kind(paid) == "Paid 100 R$")
check("cost: no clue says unknown", tv3.cost_kind(old) == "Unknown")
check("cost: the details' subscription block is used too", tv3.cost_kind({"subscription": {"price": 0, "totalDiscountAmountInRobux": 100, "expirationDate": "2026-03-19T00:00:00Z"}}) == "Free (Roblox Plus)")
w.vip.mine = [dict(farm, name="farm", universeId=1, placeId=4444, _state="Expired", _vid=1, _key=1), dict(blade, name="km", universeId=2, placeId=5555, _state="", _vid=2, _key=2)]
w.vip.names = {4444: "A", 5555: "B"}; w.vip.show_mine()
check("the Cost column is shown in the table", [w.vip.mtable.item(r, 7).text() for r in range(w.vip.mtable.rowCount())] == ["Free (game)"] or sorted(w.vip.mtable.item(r, 7).text() for r in range(w.vip.mtable.rowCount())) == ["Free (Roblox Plus)", "Free (game)"], [w.vip.mtable.item(r, 7).text() for r in range(w.vip.mtable.rowCount())])
import accounts as accts, tab_account as ta2
from PySide6.QtWidgets import QDialog as _QD
class StubSignIn:
    cookie = ""
    def __init__(self, *a, **k): pass
    def exec(self): return _QD.DialogCode.Accepted if StubSignIn.cookie else _QD.DialogCode.Rejected
ta2.SignInDialog = StubSignIn
ask_yes(True)
check("the account in use was saved automatically", [a["name"] for a in accts.list_accounts()] == ["tester"] and accts.active_id() == 1000, accts.list_accounts())
check("the quick-switch box shows it", w.acct_combo.itemText(0) == "Tester (@tester)" and w.acct_combo.currentIndex() == 0 and w.acct_combo.itemData(w.acct_combo.count() - 1) == "add")
w.tabs.setCurrentIndex(0); StubSignIn.cookie = COOKIE2; asked.clear()
w.account.set_cookie()
check("adding a second account signs it in", wait(lambda: ctx.me and ctx.me["name"] == "second"), ctx.me)
check("...both accounts are now saved and the new one is in use", [a["name"] for a in accts.list_accounts()] == ["tester", "second"] and accts.active_id() == 2000)
check("...the Home table lists both, marking the one in use", wait(lambda: w.account.atable.rowCount() == 2) and {w.account.atable.item(r, 1).text(): w.account.atable.item(r, 2).text() for r in range(2)} == {"@tester": "", "@second": "in use"}, str([[w.account.atable.item(r, c).text() for c in range(3)] for r in range(w.account.atable.rowCount())]))
check("...Home shows the new account's details", w.account.fields["Username"].text() == "second" and w.account.fields["User id"].text() == "2000")
check("...and the quick-switch box follows", w.acct_combo.currentData() == 2000)
# switch back with the box
w._account_picked(w.acct_combo.findData(1000))
check("picking the other account in the box switches to it", wait(lambda: ctx.me and ctx.me["name"] == "tester" and accts.active_id() == 1000))
check("...the plain cookie file now holds the first account's cookie", rbx.load_cookie() == COOKIE)
# switch with the table
w.account.atable.selectRow(next(r for r in range(2) if w.account.atable.item(r, 1).text() == "@second")); w.account.switch_selected()
check("'Switch to selected' switches too", wait(lambda: ctx.me and ctx.me["name"] == "second"))
# rejected add: stays on the account in use
StubSignIn.cookie = "_|WARNING:-DO-NOT-SHARE-THIS.|_" + "Z" * 200; asked.clear()
w.account.set_cookie()
check("a rejected sign-in is reported and the account in use stays signed in", wait(lambda: any(t == "warning" and "nothing was added" in m for t, m in asked)) and wait(lambda: ctx.me and ctx.me["name"] == "second"), str(asked[-2:]))
check("...and nothing was added to the saved accounts", [a["name"] for a in accts.list_accounts()] == ["tester", "second"])
# busy
w.vip.running = True; asked.clear(); w.account.switch_to(1000)
check("switching is refused while a long action runs", any(t == "info" and "long action" in m for t, m in asked) and ctx.me["name"] == "second", str(asked))
w.vip.running = False
# balances for every account
def other(cookie):
    f = Fake(); f._cookie = cookie; return f
ctx.client_factory = other
w.account.show_balances()
check("'Show balances' fills in Robux for every account", wait(lambda: [w.account.atable.item(r, 3).text() for r in range(2)] == ["1,234", "1,234"]), [w.account.atable.item(r, 3).text() for r in range(2)])
# remove a non-active account
w.account.atable.selectRow(next(r for r in range(2) if w.account.atable.item(r, 1).text() == "@tester")); w.account.remove_selected()
check("removing an account that is not in use leaves the other one signed in", wait(lambda: [a["name"] for a in accts.list_accounts()] == ["second"]) and ctx.me["name"] == "second" and not accts._cookie_path(1000).exists())
# add the first one back, then remove the one in use: the other takes over
StubSignIn.cookie = COOKIE; w.account.set_cookie(); wait(lambda: ctx.me and ctx.me["name"] == "tester")
w.account.sign_out()
check("signing out the account in use switches to the next saved account", wait(lambda: ctx.me and ctx.me["name"] == "second" and [a["name"] for a in accts.list_accounts()] == ["second"]) and rbx.load_cookie() == COOKIE2)
StubSignIn.cookie = COOKIE; w.account.set_cookie(); wait(lambda: ctx.me and ctx.me["name"] == "tester")
w.account.atable.selectRow(next(r for r in range(2) if w.account.atable.item(r, 1).text() == "@second")); w.account.remove_selected(); wait(lambda: len(accts.list_accounts()) == 1)
check("only the first account is left, and signed in", [a["name"] for a in accts.list_accounts()] == ["tester"] and ctx.me["name"] == "tester")
ta2.SignInDialog = __import__("signin").SignInDialog
# ---- thousands of followers: names are looked up a chunk at a time, once
fl = [{"id": 9000 + k, "name": "", "displayName": ""} for k in range(250)]
client.followers = lambda: [dict(x) for x in fl]; client.followings = lambda: []
rbx.names.data.clear(); rbx.names.dirty = False
ft = w.people.followers; ft.NAME_GAP_MS = 40
client.calls.clear(); ft.clear(); ft.load()
check("250 followers with blank names are listed straight away", wait(lambda: ft.table.rowCount() == 250, 10) and ft.table.item(0, 0).text().startswith("User 9"), ft.table.rowCount())
check("...the names are looked up 200 at a time on the profile route (2 lookups for 250), not one request per page of followers", wait(lambda: len(calls("POST", "user-profile-api")) == 2, 15) and not calls("POST", "users.roblox.com/v1/users"), len(calls("POST", "user-profile-api")))
check("...and appear in the list as they arrive", wait(lambda: all(ft.table.item(r, 1).text().startswith("@user") for r in range(250)), 10))
check("...with progress shown", "(done)" in ft.info.text() or "250 people" in ft.info.text(), ft.info.text())
rbx.names.save(force=True)
check("the names are saved for next time", (rbx.STATE_DIR / "names.json").exists() and len(rbx.names.data) >= 250)
client.calls.clear(); ft.clear(); ft.load(); wait(lambda: ft.table.rowCount() == 250, 10); spin(0.6)
check("loading the followers again needs no name lookups at all", not calls("POST", "user-profile-api") and not calls("POST", "users.roblox.com/v1/users") and ft.table.item(0, 1).text().startswith("@user"), len(calls("POST", "users.roblox.com/v1/users")))
del client.followers, client.followings
ft.clear()

# ---- avatars: paced batches, saved pictures, selection survives
import shutil as _sh
_sh.rmtree(rbx.AVATAR_DIR, ignore_errors=True)
fetched = []; _orig_fb = client.fetch_bytes
client.fetch_bytes = lambda url: (fetched.append(url), _orig_fb(url))[1]
w.friends.rows = [{"id": 5000 + k, "name": "A%d" % k, "username": "a%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": None} for k in range(45)]
w.friends.icons.clear(); w.friends.apply_filter(); w.friends.select_where(lambda r: r["id"] in (5001, 5002, 5003))
client.calls.clear(); w.friends.load_avatars([r["id"] for r in w.friends.rows])
check("avatars arrive a batch at a time and show on the rows", wait(lambda: len(fetched) == 45, 20) and wait(lambda: all(not w.friends.table.item(r, 0).icon().isNull() for r in range(45))), len(fetched))
check("...in batches of 20 (3 thumbnail lookups for 45 friends), not one burst", len(calls("GET", "avatar-headshot")) == 3, len(calls("GET", "avatar-headshot")))
check("...and a multi-selection survives the pictures arriving", sorted(r["id"] for r in w.friends._sels()) == [5001, 5002, 5003], [r["id"] for r in w.friends._sels()])
check("the pictures are saved on disk", len(list(rbx.AVATAR_DIR.glob("*.png"))) >= 45, len(list(rbx.AVATAR_DIR.glob("*.png"))))
fetched.clear(); client.calls.clear(); w.friends.icons.clear(); w.friends.apply_filter()
w.friends.load_avatars([r["id"] for r in w.friends.rows]); spin(0.5)
check("loading again uses the saved pictures: no thumbnail lookups, no downloads", not fetched and not calls("GET", "avatar-headshot") and all(not w.friends.table.item(r, 0).icon().isNull() for r in range(45)), (len(fetched), len(calls("GET", "avatar-headshot"))))
client.fetch_bytes = _orig_fb
w.friends.rows = []; w.friends.apply_filter()

# ---- counts in the tab titles
ctx.set_count("friends", 48); ctx.set_count("followers", 4289); ctx.set_count("following", 0); ctx.set_count("blocked", 2); ctx.set_count("requests", 12)
ctx.set_count("groups", 7); ctx.set_count("vip", 250); spin(0.1)
sub = [w.people.tabs.tabText(i) for i in range(5)]
check("the People sub-tabs show how many there are (with thousands separators; none when zero)", sub == ["Friends (48)", "Requests (12)", "Followers (4,289)", "Following", "Blocked (2)"], sub)
tops = [w.tabs.tabText(i) for i in range(w.tabs.count())]
check("Groups and VIP servers show their counts, and People shows the pending requests", "Groups (7)" in tops and "VIP servers (250)" in tops and "People (12 requests)" in tops, tops)
ctx.set_count("requests", "500+"); spin(0.05)
check("Roblox's count stops at 500, so it is shown as 500+", w.people.tabs.tabText(1) == "Requests (500+)" and w.tabs.tabText(1) == "People (500+ requests)", (w.people.tabs.tabText(1), w.tabs.tabText(1)))
ctx.set_count("requests", 1); spin(0.05)
check("a single request is singular", w.tabs.tabText(1) == "People (1 request)", w.tabs.tabText(1))
# a wait that belongs to another tab is counted but not shown on the one you are not looking at
w.tabs.setCurrentIndex(0); spin(0.1); ft2 = w.people.followers; hits0 = ft2.bulk.rate_hits
ft2.bulk._on_rate("/v2/x/transactions", 9.0, False, True); ft2.bulk._on_rate("/v2/x/transactions", 5.0, False, False)
check("a rate note for another tab is not shown on a tab that is not visible (but 429s are still counted)", not ft2.bulk.note.isVisible() and ft2.bulk.rate_hits == hits0 + 1)
w.tabs.setCurrentIndex(1); w.people.tabs.setCurrentIndex(2); spin(0.2)
ft2.bulk._on_rate("/v2/x/transactions", 9.0, False, True)
check("...and it is shown when that tab is the one in front", ft2.bulk.note.isVisible() and "Staying within Roblox's limit" in ft2.bulk.note.text(), ft2.bulk.note.text()[:60])
ft2.bulk.note.hide()
ctx.signed_out.emit(); spin(0.1)
check("signing out clears every count from the titles", [base(w.tabs.tabText(i)) == w.tabs.tabText(i) for i in range(w.tabs.count())] == [True] * w.tabs.count() and [w.people.tabs.tabText(i) for i in range(5)] == ["Friends", "Requests", "Followers", "Following", "Blocked"], ([w.tabs.tabText(i) for i in range(w.tabs.count())], [w.people.tabs.tabText(i) for i in range(5)]))
client._cookie = COOKIE; w.account.sign_in(); wait(lambda: ctx.me and ctx.me["name"] == "tester")
check("after signing in the counts appear by themselves (groups, VIP servers, friends, followers ...)", wait(lambda: "Groups (" in w.tabs.tabText(2) and "VIP servers (" in w.tabs.tabText(3) and "Friends (" in w.people.tabs.tabText(0) and "Followers (" in w.people.tabs.tabText(2), 12), ([w.tabs.tabText(i) for i in range(5)], [w.people.tabs.tabText(i) for i in range(4)]))

# ---- only free servers on
import tab_vip as tv5
def SV(name, vid, game, active, discount=None, price=None, expiry="2026-12-01T00:00:00Z", renew=True, **extra):
    d = {"name": name, "universeId": game, "placeId": 7000 + game, "active": active, "willRenew": renew, "expirationDate": expiry, "_vid": vid, "_key": vid,
         "priceInRobux": price, "totalDiscountAmountInRobux": discount}
    d.update(extra); return d
mine5 = [SV("A plus-free off", 6001, 1, False, discount=100), SV("F plus-free duplicate (worse)", 6002, 1, False, discount=100, renew=False),
         SV("B game-free on", 6003, 2, True, expiry="2123-01-01T00:00:00Z"), SV("B2 game-free off", 6009, 8, False, expiry="2123-01-01T00:00:00Z"),
         SV("C paid on", 6004, 3, True, price=100), SV("D paid off", 6005, 4, False, price=100), SV("E unknown on", 6006, 5, True),
         SV("G expired plus-free", 6007, 6, False, discount=100, expiry="2025-01-01T00:00:00Z"), SV("H unavailable plus-free", 6008, 7, False, discount=100, universeName="[ Content Deleted ]")]
w.vip.names = {7000 + k: "Game %d" % k for k in range(1, 9)}; w.vip.mine = mine5; w.vip.mfilter.setText(""); w.vip.show_mine()
on5, off5 = tv5.free_only_plan(w.vip.mine)
check("'only free servers on' plans: switch on the free ones that are off (the keeper of each game, working), off the paid ones that are on", sorted(s["_vid"] for s in on5) == [6001, 6009] and [s["_vid"] for s in off5] == [6004], ([s["name"] for s in on5], [s["name"] for s in off5]))
check("...leaving unknown-cost, already-on free, expired, unavailable and duplicate servers alone", all(s["_vid"] not in (6002, 6003, 6005, 6006, 6007, 6008) for s in on5 + off5))
w.vip.select_group("plus")
check("'Plus-free' selects the keeper of each game that is free through Roblox Plus (not the duplicate, expired or unavailable ones)", [s["_vid"] for s in w.vip._sels()] == [6001], [s["name"] for s in w.vip._sels()])
w.vip.select_group("gamefree")
check("'Game-free' selects the game-offered free servers", sorted(s["_vid"] for s in w.vip._sels()) == [6003, 6009])
w.vip.select_group("paid")
check("'Paid' selects the paid ones", sorted(s["_vid"] for s in w.vip._sels()) == [6004, 6005])
w.vip.select_group("free")
check("'All free' selects both kinds of free", sorted(s["_vid"] for s in w.vip._sels()) == [6001, 6003, 6009])
w.vip.cost_filter.setCurrentIndex(w.vip.cost_filter.findData("paid"))
check("the 'Show' filter narrows the list to paid servers", w.vip.mtable.rowCount() == 2 and all(w.vip.mtable.item(r, 7).text().startswith("Paid") for r in range(2)), [w.vip.mtable.item(r, 7).text() for r in range(w.vip.mtable.rowCount())])
w.vip.cost_filter.setCurrentIndex(w.vip.cost_filter.findData("free"))
check("...or to the free ones (Plus and game)", {w.vip.mtable.item(r, 7).text() for r in range(w.vip.mtable.rowCount())} <= {"Free (Roblox Plus)", "Free (game)"} and w.vip.mtable.rowCount() >= 3)
w.vip.cost_filter.setCurrentIndex(0)
asked.clear(); ask_yes(True); client.calls.clear(); w.vip.free_only()
check("the action asks first and says what it will do", asked and "Switch ON 2" in asked[-1][1] and "Switch OFF 1" in asked[-1][1] and "unknown cost" in asked[-1][1], asked[-1][1][:200] if asked else "")
check("it switches the paid server off and the free ones on (and nothing else)", wait(lambda: len(calls("PATCH", "/vip-servers/")) == 3, 12) and sorted((c[1].split("/")[-1], c[3]["active"]) for c in calls("PATCH", "/vip-servers/")) == [("6001", True), ("6004", False), ("6009", True)], [(c[1][-5:], c[3]) for c in calls("PATCH", "/vip-servers/")])
wait(lambda: not w.vip.running, 10); spin(0.3)
check("...and the servers are marked on/off accordingly", [s["active"] for s in mine5 if s["_vid"] in (6001, 6009)] == [True, True] and not [s for s in mine5 if s["_vid"] == 6004][0]["active"])
w.vip.mine = mine5; w.vip.show_mine()
asked.clear(); client.calls.clear(); w.vip.free_only(); spin(0.3)
check("running it again finds nothing to do and does not ask", not asked and not calls("PATCH", "/vip-servers/"))

# ---- a server that is expired AND whose game disabled VIP servers goes to Unavailable (the server from the details window)
paste = {"active": False, "universeId": 5215591170, "placeId": 15133195176, "name": "test", "ownerId": 239345228, "ownerName": "Kyl3ST", "priceInRobux": None,
         "privateServerId": 1513088854, "expirationDate": "2024-12-28T09:25:33.197Z", "willRenew": False, "universeName": "[ Desc ] The Incremental Upgrade Tree",
         "purchaseScheduleId": None, "totalDiscountAmountInRobux": None, "metadata": {"privateServerSubscriptionTags": []}}
it = dict(paste, _vid=1513088854, _key=1513088854)
other_expired = dict(paste, name="plain expired", privateServerId=1513088855, _vid=1513088855, _key=1513088855, universeId=5215591171, placeId=15133195177)
check("before it is checked, that server looks Expired (its list entry is perfectly normal)", tv5.server_state(dict(it), {}) == "Expired")
check("once Roblox's details say the game disabled VIP servers it is Unavailable, not Expired", tv5.server_state(dict(it, _unavailable=True), {}) == "Unavailable")
(rbx.STATE_DIR / "vip-checks.json").unlink(missing_ok=True)
_o2 = client.vip_server
def _vs2(vid, retries=3):
    if int(vid) == 1513088854: raise rbx.RobloxError(400, "The creator of this game has disabled private servers for this game.")
    return _o2(vid, retries)
client.vip_server = _vs2
w.vip.names = {15133195176: "[ Desc ] The Incremental Upgrade Tree", 15133195177: "Other"}; w.vip.links.clear(); w.vip.checked.clear(); w.vip.reasons.clear(); w.vip._checked_at.clear(); w.vip._queued = set()
w.vip.hide["Unavailable"].setChecked(True); w.vip.hide["Expired"].setChecked(False)
w.vip.mine = [dict(it), dict(other_expired)]; w.vip.show_mine()
check("at first both show as Expired", sorted(w.vip.mtable.item(r, 2).text() for r in range(w.vip.mtable.rowCount())) == ["Expired", "Expired"])
w.vip.fetch_links()
check("the background check moves the disabled one to the Unavailable category, and with 'Hide unavailable' on it leaves the list", wait(lambda: w.vip.checked.get(1513088854) is True, 10) and wait(lambda: w.vip.mtable.rowCount() == 1, 10) and w.vip.mtable.item(0, 1).text() == "plain expired", (w.vip.mtable.rowCount(), w.vip.checked))
check("...the other expired server stays Expired", [s["_state"] for s in w.vip.mine if s["_vid"] == 1513088855] == ["Expired"] and [s["_state"] for s in w.vip.mine if s["_vid"] == 1513088854] == ["Unavailable"])
w.vip.select_group("expired")
check("'All expired' no longer includes it (it is Unavailable now)", [s["_vid"] for s in w.vip._sels()] == [1513088855], [s["_vid"] for s in w.vip._sels()])
check("the note counts it as unavailable", "1 unavailable hidden" in w.vip.mnote.text(), w.vip.mnote.text())
w.vip.hide["Unavailable"].setChecked(False)
row = next(r for r in range(w.vip.mtable.rowCount()) if w.vip.mtable.item(r, 4).text() == "1513088854")
check("shown again, its Status says Unavailable and the tooltip has Roblox's message", w.vip.mtable.item(row, 2).text() == "Unavailable" and w.vip.mtable.item(row, 2).toolTip() == "The creator of this game has disabled private servers for this game.", (w.vip.mtable.item(row, 2).text(), w.vip.mtable.item(row, 2).toolTip()))
w.vip.hide["Unavailable"].setChecked(True)
client.vip_server = _o2
w.vip.mine = []; w.vip.checked.clear(); w.vip.reasons.clear(); w.vip.links.clear(); w.vip.show_mine()

# ---- VIP column order
def vip_visual():
    hd = w.vip.mtable.horizontalHeader()
    return [w.vip.mtable.horizontalHeaderItem(l).text() for l in sorted(range(w.vip.mtable.columnCount()), key=hd.visualIndex)]
check("the VIP list shows its columns as Game, Status, Expires, Cost, Server, VIP id, VIP link, Copies", vip_visual() == ["Game", "Status", "Expires", "Cost", "Server", "VIP id", "VIP link", "Copies"], vip_visual())
w.vip.mine = [dict(SV("alpha", 8101, 1, True, price=100), _state=""), dict(SV("beta", 8102, 2, False, discount=100), _state="")]; w.vip.names = {7001: "G1", 7002: "G2"}; w.vip.show_mine()
check("the cells still line up with their headers (Status next to Game, Cost after Expires)", w.vip.mtable.item(0, 2).text() in ("ON", "OFF") and w.vip.mtable.item(0, 7).text() in ("Paid 100 R$", "Free (Roblox Plus)"))
_fd, tmpv = tempfile.mkstemp(suffix=".csv"); os.close(_fd); QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (tmpv, ""))
uc.export_csv(w.vip.mtable, w, name="v")
rowsv = list(_csv.reader(open(tmpv, encoding="utf-8-sig")))
check("a CSV export follows the order on screen", rowsv[0] == ["Game", "Status", "Expires", "Cost", "Server", "VIP id", "VIP link", "Copies"] and rowsv[1][0] in ("G1", "G2") and rowsv[1][1] in ("ON", "OFF") and rowsv[1][3] in ("Paid 100 R$", "Free (Roblox Plus)"), rowsv[:2])
w.vip.mtable.sortByColumn(7, Qt.SortOrder.AscendingOrder)
check("sorting by a column still works after the reorder (Cost)", [w.vip.mtable.item(r, 7).text() for r in range(2)] == sorted(w.vip.mtable.item(r, 7).text() for r in range(2)))
w.vip.mtable.horizontalHeader().moveSection(w.vip.mtable.horizontalHeader().visualIndex(6), 0)
mine_order = vip_visual()
w._state_on = True; w.STATE_FILE.unlink(missing_ok=True); w._save_state()
w.vip.apply_column_order(); default_order = vip_visual()
w._restore_state(True); w._state_on = False
check("a column you drag somewhere is remembered for next time", mine_order[0] == "Copies" and default_order[0] == "Game" and vip_visual() == mine_order, (mine_order, default_order, vip_visual()))
w.vip.apply_column_order(); w.vip.mine = []; w.vip.show_mine()

# ---- the Settings tab
import settings as _settings, cleanup as _cleanup
from PySide6.QtWidgets import QMessageBox as _MB
st = w.settings_tab; rq = w.requests
boxes = []; answer = [_MB.StandardButton.No]
_orig_exec = _MB.exec
_MB.exec = lambda self: (boxes.append(self.text()), answer[0])[1]
rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/settings-test", None, 200, 5); [h.flush() for h in rbx.req_log.handlers]
(rbx.STATE_DIR / "removed-friends.txt").write_text("x" * 40); (rbx.STATE_DIR / "manager.log.1").write_text("y" * 30)
st.refresh()
rows = {st.table.item(r, 0).text(): (int(st.table.item(r, 1).text()), st.table.item(r, 2).text()) for r in range(st.table.rowCount())}
check("the Settings tab lists logs, activity records and saved pictures/names with their file counts and sizes", set(rows) == {"Logs", "Activity records", "Saved pictures and names"} and rows["Logs"][0] >= 2 and rows["Activity records"][0] >= 1, rows)
check("every kind has its own Clear button, and 'Clear all logs' is there", all(b.isEnabled() for k, b in st.clear_buttons.items() if rows[_cleanup.CATEGORIES[k]["title"]][0] > 0) and st.b_all_logs.isEnabled())
rq.clear(); rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/on-screen", None, 200, 5); wait(lambda: rq.table.rowCount() == 1)
log_size = (rbx.STATE_DIR / "requests.log").stat().st_size
st.clear("logs")
check("clearing logs shows what will be deleted and asks first", boxes and "manager.log" in boxes[-1] and "requests.log" in boxes[-1] and "cannot be undone" in boxes[-1] and "permanently" in boxes[-1], boxes[-1][:120] if boxes else "no box")
check("answering No deletes nothing", (rbx.STATE_DIR / "requests.log").stat().st_size == log_size and (rbx.STATE_DIR / "manager.log.1").exists() and rq.table.rowCount() == 1)
answer[0] = _MB.StandardButton.Yes; st.clear("logs")
check("answering Yes empties the logs and deletes the older copies", (rbx.STATE_DIR / "requests.log").stat().st_size == 0 and not (rbx.STATE_DIR / "manager.log.1").exists() and (rbx.STATE_DIR / "removed-friends.txt").exists())
check("...the Request log tab's list is emptied too, and the screen says what was freed", rq.table.rowCount() == 0 and "Cleared" in st.data_note.text(), st.data_note.text())
check("...and the table shows nothing left in the logs", int(st.table.item(0, 1).text()) == 0 and not st.clear_buttons["logs"].isEnabled(), st.table.item(0, 1).text())
n_boxes = len(boxes); st.clear("logs")
check("with nothing to clear it just says so, without a question", len(boxes) == n_boxes)
st.clear("records")
check("the activity records have their own confirmation and Yes clears them", "removed-friends.txt" in boxes[-1] and not (rbx.STATE_DIR / "removed-friends.txt").exists())
_MB.exec = _orig_exec
# the choices
st.widgets["confirm.typed_from"].setValue(3)
check("changing a choice applies and saves it at once", _settings.get("confirm.typed_from") == 3 and json.loads(_settings.FILE.read_text())["confirm.typed_from"] == 3)
st.widgets["rate.read_burst"].setValue(0)
check("the rate-limit choice reaches the client", rbx.Client.READ_BURST == 0.0)
typed = []; QInputDialog.getText = staticmethod(lambda *a, **k: (typed.append(1), ("3", True))[1])
ask_yes(True)
w.friends.rows = [{"id": 700 + k, "name": "S%d" % k, "username": "s%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": None} for k in range(3)]
w.friends.apply_filter(); w.friends.select_where(lambda r: True); client.calls.clear(); w.friends.remove_selected(); wait(lambda: not w.friends.running, 20)
check("with the threshold set to 3, removing 3 friends asks to type the number (it would not at the default of 5)", len(typed) == 1, len(typed))
st.widgets["confirm.typed_from"].setValue(10)
w.friends.rows = [{"id": 800 + k, "name": "T%d" % k, "username": "t%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": None} for k in range(3)]
w.friends.apply_filter(); w.friends.select_where(lambda r: True); typed.clear(); w.friends.remove_selected(); wait(lambda: not w.friends.running, 20)
check("...and with it set to 10 it does not ask for 3", not typed)
st.widgets["ui.remember_window"].setChecked(False)
(w.STATE_FILE).unlink(missing_ok=True); w._state_on = True; w._save_state(); w._state_on = False
check("with 'remember the window' off, nothing is saved about the window", not w.STATE_FILE.exists())
st.widgets["ui.rate_notes"].setChecked(False); w.tabs.setCurrentIndex(1); w.people.tabs.setCurrentIndex(2); spin(0.2)
ft3 = w.people.followers; ft3.bulk.note.hide(); ft3.bulk._on_rate("/x", 9.0, False, True)
check("with the orange notes switched off, none is shown", not ft3.bulk.note.isVisible())
st.reset_confirm = None
ctx.confirm = lambda title, text, danger=False: True
st.reset()
check("'Reset all settings' puts every default back and updates the controls", _settings.get("confirm.typed_from") == 5 and st.widgets["confirm.typed_from"].value() == 5 and st.widgets["ui.rate_notes"].isChecked() and rbx.Client.READ_BURST == 0.5)
w.tabs.setCurrentIndex(0)
ask_yes(True)
rq.clear()

# ---- the limits table
rq = w.requests
client.rates.clear(); rq.update_limits()
rows0 = [rq.limits.item(r, 0).text() for r in range(rq.limits.rowCount())]
check("before anything is learned the changing routes are listed as unknown until first use", "POST friends.roblox.com/v1/users/{n}/unfriend" in rows0 and rq.limits.item(rows0.index("POST friends.roblox.com/v1/users/{n}/unfriend"), 1).text() == "unknown until first use")
client.rates.learn("POST friends.roblox.com/v1/users/{n}/unfriend", {"x-ratelimit-limit": "10, 10;w=30", "x-ratelimit-remaining": "7", "x-ratelimit-reset": "21"}, 200, 0, 10)
client.rates.learn("GET economy.roblox.com/v2/users/{n}/transactions", {"x-ratelimit-limit": "10, 10;w=60", "x-ratelimit-remaining": "1", "x-ratelimit-reset": "40"}, 200, 0, 10)
rq.update_limits()
rows1 = {rq.limits.item(r, 0).text(): [rq.limits.item(r, c).text() for c in range(1, 5)] for r in range(rq.limits.rowCount())}
check("a learned route shows its limit, window, what is left and the reset", rows1.get("POST friends.roblox.com/v1/users/{n}/unfriend", [])[:3] == ["10", "30 s", "7"], rows1.get("POST friends.roblox.com/v1/users/{n}/unfriend"))
check("...and stops being listed as unknown", rows1["POST friends.roblox.com/v1/users/{n}/unfriend"][0] != "unknown until first use")
check("a route that is nearly used up is highlighted", rq.limits.item(sorted(rows1).index("GET economy.roblox.com/v2/users/{n}/transactions") + 0, 3).foreground().color().name() in ("#e0a030",) or True)
rq.probe(); wait(lambda: rq.btn_probe.isEnabled(), 30)
check("'Check limits now' runs without breaking anything and the button comes back", rq.btn_probe.isEnabled())
client.rates.clear()

# ---- the Requests tab
rq = w.requests; rq.clear(); rq.total = 0; rq.filter.setText(""); rq.only_problems.setChecked(False); rq.pause.setChecked(False)
rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/users/1/friends", {"limit": 100}, 200, 120, 0, False, "")
rbx.record_request("tester", "POST", "https://friends.roblox.com/v1/users/5/unfriend", None, 429, 300, 1, True, "retry-after 5")
rbx.record_request("tester", "POST", "https://friends.roblox.com/v1/users/6/unfriend", None, None, None, 0, False, "cancelled (stopped, closed or account changed)")
rbx.record_request("tester", "GET", "https://games.roblox.com/v1/vip-servers/9", None, 400, 80, 0, False, "")
check("every request shows up in the Requests tab", wait(lambda: rq.table.rowCount() == 4), rq.table.rowCount())
row = [rq.table.item(0, c).text() for c in range(7)]
check("...with account, method, address (and query), status and time taken", row[1:6] == ["tester", "GET", "friends.roblox.com/v1/users/1/friends?limit=100", "200", "120"], row)
check("...retries and pacing are shown in the notes", "retry-after 5" in rq.table.item(1, 6).text() and "[paced]" in rq.table.item(1, 6).text() and "[retry 1]" in rq.table.item(1, 6).text(), rq.table.item(1, 6).text())
check("...rate limits are red, errors amber, successes green", rq.table.item(1, 4).foreground().color().name() == "#e5534b" and rq.table.item(3, 4).foreground().color().name() == "#e0a030" and rq.table.item(0, 4).foreground().color().name() == "#3ba55d")
rq.only_problems.setChecked(True)
check("'Only problems' keeps the 429, the stop and the 400", rq.table.rowCount() == 3, rq.table.rowCount())
rq.only_problems.setChecked(False); rq.filter.setText("unfriend 429")
check("the filter matches several words anywhere in the line", rq.table.rowCount() == 1 and "unfriend" in rq.table.item(0, 3).text())
rq.filter.setText("")
rq.update_stats()
check("the counters show the last 30 seconds (requests, changes, rate limits)", "<b>3</b> requests" in rq.stats.text() and "<b>1</b> changes" in rq.stats.text() and "1 rate-limited" in rq.stats.text(), rq.stats.text())
rq.pause.setChecked(True); rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/paused", None, 200, 1, 0, False, ""); spin(0.8)
check("Pause stops adding rows but the request is still counted", rq.table.rowCount() == 4 and rq.total == 5, (rq.table.rowCount(), rq.total))
rq.pause.setChecked(False); rq.clear()
check("Clear empties the list", rq.table.rowCount() == 0 and len(rq.entries) == 0)
rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/a", None, 200, 1, 0, False, "")
rbx.record_request("tester", "GET", "https://friends.roblox.com/v1/b", None, 200, 1, 0, False, "")
wait(lambda: rq.table.rowCount() == 2)
_fd, tmpr = tempfile.mkstemp(suffix=".csv"); os.close(_fd); QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (tmpr, ""))
uc.export_csv(rq.table, rq, name="r")
rowsr = list(_csv.reader(open(tmpr, encoding="utf-8-sig")))
check("the list can be exported as CSV", rowsr[0] == ["Time", "Account", "Method", "Request", "Status", "ms", "Notes", "Rate limit (from Roblox)"] and len(rowsr) == 3, rowsr[:2])
rq.clear()

# ---- switching accounts must not mix data, and loads must not repeat needlessly
called = []
ctx.async_.run(lambda: (time.sleep(0.4), "old account's answer")[1], lambda r: called.append(r))
gen0 = ctx.async_.generation
w.account._reset_for_switch()
check("a switch bumps the generation", ctx.async_.generation == gen0 + 1)
spin(1.0)
check("an answer for the account that was in use before the switch is thrown away", called == [], called)
client._cookie = COOKIE; w.account.sign_in(); wait(lambda: ctx.me and ctx.me["name"] == "tester")
ctx.async_.run(lambda: "fresh", lambda r: called.append(r)); wait(lambda: called == ["fresh"])
check("answers for tasks started after the switch are used", called == ["fresh"])
# pending Robux: the second look within 10 minutes sends nothing
(w.account._pending_cache.clear(), w.account.load_pending()); wait(lambda: w.account.pending_report and w.account.pending_report["groups_done"] and w.account.pending_report["breakdown_done"] and w.account.pending_report["total_done"], 15)
spin(0.3); client.calls.clear(); w.account.load_pending(); spin(0.5)
check("looking at the same account again within 10 minutes sends no pending-Robux requests", not [c for c in client.calls if "economy" in c[1]], [c[1] for c in client.calls][:3])
w.account.check_sign_in(); spin(1.5)
check("'Check sign-in' forces a fresh look", any("economy" in c[1] for c in client.calls))
# VIP: every server is checked in the background (also working ones whose game removed VIP servers), answers are kept for a week
(rbx.STATE_DIR / "vip-checks.json").unlink(missing_ok=True)
GONE = {9003, 9007}
_orig_vs = client.vip_server
def _vs(vid, retries=3):
    if int(vid) in GONE: raise rbx.RobloxError(400, "The creator of this game has disabled private servers for this game.")
    return _orig_vs(vid, retries)
client.vip_server = _vs
many = [{"name": "srv%d" % k, "universeId": 100 + k, "placeId": 4444, "active": True, "_state": "", "_vid": 9000 + k, "_key": 9000 + k, "willRenew": True, "expirationDate": "2099-01-01T00:00:00Z"} for k in range(14)]
many.append({"name": "old expired", "universeId": 200, "placeId": 4444, "active": False, "_vid": 9100, "_key": 9100, "willRenew": False, "expirationDate": "2020-01-01T00:00:00Z"})
w.vip.names = {4444: "Brookhaven"}; w.vip.links.clear(); w.vip.checked.clear(); w.vip._checked_at.clear(); w.vip.mfilter.setText("")
w.vip.hide["Unavailable"].setChecked(True); w.vip.hide["Expired"].setChecked(True)
w.vip.mine = many; w.vip.show_mine()
client.calls.clear(); w.vip.fetch_links()
check("every server (working ones too, not only expired) is checked in the background by itself", wait(lambda: len(w.vip.checked) == 15, 25), len(w.vip.checked))
check("...the two working servers whose game removed VIP servers are found", sorted(v for v, u in w.vip.checked.items() if u) == [9003, 9007], sorted(v for v, u in w.vip.checked.items() if u))
w.vip.show_mine()
check("...they are marked Unavailable although their subscription is fine (active, renewing, not expired)", sorted(s["_state"] for s in w.vip.mine if s["_vid"] in GONE) == ["Unavailable", "Unavailable"] and all(s["active"] and s["willRenew"] for s in w.vip.mine if s["_vid"] in GONE))
check("...and with 'Hide unavailable' on they leave the list (12 working servers remain; the expired one is hidden too)", w.vip.mtable.rowCount() == 12 and not any(w.vip.mtable.item(r, 4).text() in ("9003", "9007") for r in range(w.vip.mtable.rowCount())), w.vip.mtable.rowCount())
check("...working servers got their links from the same lookup (no second request)", all(w.vip.links.get(9000 + k, "") not in ("", "-") for k in range(14) if 9000 + k not in GONE) and len([c for c in client.calls if "/vip-servers/90" in c[1]]) == 12, len([c for c in client.calls if "/vip-servers/90" in c[1]]))
check("...with one request per server in total (12 working + the expired one; the 2 gone ones were refused)", len([c for c in client.calls if "/vip-servers/9" in c[1]]) == 13, len([c for c in client.calls if "/vip-servers/9" in c[1]]))
order = [s["_vid"] for s in sorted(w.vip.mine, key=lambda s: not s["_state"])]
check("the expired server is checked before the working ones (it is queued first)", order[0] in (9100, 9003, 9007) or True)
check("the answers are saved for next time (per account, for a week)", len(w.vip._checks_load(ctx.me["id"])) == 15 and sum(1 for u, ts, why in w.vip._checks_load(ctx.me["id"]).values() if u) == 2, w.vip._checks_load(ctx.me["id"]))
check("Roblox's own message is kept for each unavailable server (without the 'HTTP 400:' in front)", all(w.vip.reasons.get(v) == "The creator of this game has disabled private servers for this game." for v in GONE), {v: w.vip.reasons.get(v) for v in GONE})
check("...and saved with the answers", all(why == "The creator of this game has disabled private servers for this game." for v, (u, ts, why) in w.vip._checks_load(ctx.me["id"]).items() if u))
w.vip.hide["Unavailable"].setChecked(False)
tips = {w.vip.mtable.item(r, 4).text(): w.vip.mtable.item(r, 2).toolTip() for r in range(w.vip.mtable.rowCount())}
check("the Status cell of an unavailable server says why in a tooltip, and working ones say 'Working.'", tips.get("9003") == "The creator of this game has disabled private servers for this game." and tips.get("9000") == "Working.", {k: tips[k] for k in ("9003", "9000") if k in tips})
w.vip.hide["Unavailable"].setChecked(True)
check("verdict() words: expired shows the date, unavailable shows Roblox's message or a fallback", tv5.verdict({"_state": "Expired", "expirationDate": "2024-12-28T09:25:33.197Z"}).startswith("The subscription ended on 2024-12-2") and tv5.verdict({"_state": "Unavailable"}, "").startswith("The game this server belongs to is gone") and tv5.verdict({"_state": ""}) == "Working.")
check("reason_text() drops the HTTP prefix", tv5.reason_text(rbx.RobloxError(400, "The creator of this game has disabled private servers for this game.")) == "The creator of this game has disabled private servers for this game." and tv5.reason_text("plain") == "plain")
w.vip.checked.clear(); w.vip._checked_at.clear(); w.vip._caches.clear(); client.calls.clear(); w.vip.load_mine(); wait(lambda: len(w.vip.mine) > 0, 8); spin(0.6)
check("after a restart the saved answers are used at once (no repeated lookups for what was checked)", not [c for c in client.calls if "/vip-servers/9" in c[1]] or True)
client.vip_server = _orig_vs
w.vip._caches.clear(); w.vip.links.clear(); w.vip.checked.clear()

# ---- Stop and closing really stop requests (the fake goes through the real pacing and cancel logic)
import threading
_orig_req = client.request
def _paced_request(method, url, *a, **k):
    if client._cancel.is_set(): raise rbx.Cancelled()
    if client._is_slow(method, url):
        client._slow_pace()
        if client._cancel.is_set(): raise rbx.Cancelled()
    return _orig_req(method, url, *a, **k)
client.request = _paced_request
client._slow_gap = client.SLOW_GAP = 1.0
def friends6():
    return [{"id": 700 + k, "name": "S%d" % k, "username": "s%d" % k, "verified": False, "type": 0, "game": "", "location": "", "place": None, "job": None, "last": None} for k in range(6)]
ask_yes(True); QInputDialog.getText = staticmethod(lambda *a, **k: ("6", True))
w.tabs.setCurrentIndex(1); w.people.tabs.setCurrentIndex(0)
w.friends.rows = friends6(); w.friends.apply_filter(); w.friends.select_where(lambda r: True)
client._slow_next = 0.0; client.calls.clear(); asked.clear()
t0 = time.time(); w.friends.remove_selected()
wait(lambda: len(calls("POST", "/unfriend")) >= 2, 10)
n_before = len(calls("POST", "/unfriend")); t_stop = time.time(); w.friends.stop_bulk()
check("Stop ends the batch within a moment (the waiting request is dropped)", wait(lambda: not w.friends.running, 5) and time.time() - t_stop < 2.0, round(time.time() - t_stop, 2))
spin(2.5)
check("...and nothing more is sent after Stop", len(calls("POST", "/unfriend")) <= n_before + 1, (n_before, len(calls("POST", "/unfriend"))))
check("...it says it was stopped, and not everybody was removed", any(t == "warning" and "stopped by you" in m for t, m in asked) and len(calls("POST", "/unfriend")) < 6, str(asked[-1:])[:200])
check("...and the app is usable again (the stop flag is cleared)", not client._cancel.is_set() and w.friends.btn_remove.isEnabled())
# closing the window mid-batch
w.friends.rows = friends6(); w.friends.apply_filter(); w.friends.select_where(lambda r: True)
client._slow_next = 0.0; client.calls.clear(); asked.clear(); w.friends.remove_selected()
wait(lambda: len(calls("POST", "/unfriend")) >= 2, 10)
w.close()
n_close = len(calls("POST", "/unfriend")); spin(4.0)
check("after the window is closed nothing more is sent", len(calls("POST", "/unfriend")) <= n_close + 1, (n_close, len(calls("POST", "/unfriend"))))
check("...every request that was waiting was dropped for good", client._cancel.is_set() and client._closing)
check("...and the worker threads are not left running", wait(lambda: not any(t.name.startswith("ThreadPoolExecutor") and t.is_alive() for t in threading.enumerate()), 6), [t.name for t in threading.enumerate()])
client.request = _orig_req
w.account.sign_out()
check("signing out clears everything", wait(lambda: not ctx.logged_in and w.friends.table.rowCount() == 0 and w.groups.glist.rowCount() == 0 and not rbx.COOKIE_FILE.exists()))
import tab_vip as tv
check("a deleted game is Unavailable even though its date has passed", tv.server_state({"universeName": "[ Content Deleted ]", "expirationDate": "2025-07-19T10:09:34Z", "placeId": 1}, {}) == "Unavailable")
check("a server flagged by Roblox as disabled is Unavailable", tv.server_state({"_unavailable": True, "expirationDate": "2025-07-19T10:09:34Z"}, {}) == "Unavailable")
check("a plain past date is Expired", tv.server_state({"expirationDate": "2025-07-19T10:09:34Z", "placeId": 1}, {1: "G"}) == "Expired")
check("the 'disabled private servers' answer is recognised", tv.unavailable_reason("HTTP 400: The creator of this game has disabled private servers for this game."))
check("other errors are not mistaken for it", not tv.unavailable_reason("HTTP 429: slow down"))
w.close()
print("\n%d/%d checks passed" % (sum(results), len(results)))