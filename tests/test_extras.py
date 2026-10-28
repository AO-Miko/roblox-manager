"""Test of friend alerts, the join requests of all groups in one list, and the backup. The real client methods run against a fake Roblox.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_extras.py"""
import json
import os
import sys
import tempfile
import time
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="extras-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

app = QApplication(sys.argv)
import alerts
import backup
import games_store
import notify_status
import rbx
import settings
import tab_group_requests
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


# ================================================================ the rules of the alerts
O, ON, G, S = alerts.OFFLINE, alerts.ONLINE, alerts.IN_GAME, alerts.IN_STUDIO
names = {1: "Ann", 2: "Bob"}
check("the first look reports nothing (it only learns who is where)", alerts.news({}, {1: (ON, None, "")}, names) == [])
check("offline -> online is news", alerts.news({1: (O, None, "")}, {1: (ON, None, "")}, names) == [(1, "online", "Ann is online")])
check("online -> in game is news with the game's name", alerts.news({1: (ON, None, "")}, {1: (G, 11, "Alpha")}, names) == [(1, "ingame", "Ann joined Alpha")])
check("offline -> in game is one piece of news (joined), not two", alerts.news({1: (O, None, "")}, {1: (G, 11, "Alpha")}, names) == [(1, "ingame", "Ann joined Alpha")])
check("staying in the same game is not news", alerts.news({1: (G, 11, "Alpha")}, {1: (G, 11, "Alpha")}, names) == [])
check("moving to another game is news", alerts.news({1: (G, 11, "Alpha")}, {1: (G, 22, "Beta")}, names) == [(1, "ingame", "Ann joined Beta")])
check("going offline, or from a game to the website, is not news", alerts.news({1: (G, 11, "A")}, {1: (O, None, "")}, names) == [] and alerts.news({1: (G, 11, "A")}, {1: (ON, None, "")}, names) == [])
check("'online' can be switched off", alerts.news({1: (O, None, "")}, {1: (ON, None, "")}, names, online=False) == [])
check("'joins a game' can be switched off (a friend who is in a game is still online news)", alerts.news({1: (ON, None, "")}, {1: (G, 11, "A")}, names, ingame=False) == []
      and alerts.news({1: (O, None, "")}, {1: (G, 11, "A")}, names, ingame=False) == [(1, "online", "Ann is online")])
check("a friend without a saved name is still named", alerts.news({7: (O, None, "")}, {7: (ON, None, "")}, {}) == [(7, "online", "User 7 is online")])
snap = alerts.snapshot([{"userId": 1, "userPresenceType": 2, "rootPlaceId": 11, "placeId": 12, "lastLocation": "Alpha"}, {"userId": 2, "userPresenceType": 9}, {"userPresenceType": 1}, "junk"])
check("the presence answer becomes a snapshot (root place first, odd types are offline, broken entries dropped)", snap == {1: (2, 11, "Alpha"), 2: (0, None, "")}, snap)
check("alert settings read from anywhere are cleaned", alerts.clean({"enabled": 1, "watch": {"5": {"7": "x" * 99, "bad": "y"}, "bad": {"1": "z"}, "6": "not a dict"}, "evil": 1})
      == {"enabled": True, "online": True, "ingame": True, "watch": {"5": {"7": "x" * 60}}})
check("junk is read as the defaults", alerts.clean("junk") == alerts.default() and alerts.clean(None) == alerts.default())


# ================================================================ a fake Roblox
class State:
    presence = [{"userId": 201, "userPresenceType": 0}, {"userId": 202, "userPresenceType": 0}, {"userId": 203, "userPresenceType": 0}]
    log = []
    requests = {1: [{"requester": {"userId": 301 + i, "username": f"u{301 + i}", "displayName": f"User {301 + i}"}, "created": "2026-10-01T10:00:00Z"} for i in range(3)],
                3: [{"requester": {"userId": 401, "username": "owner_req", "displayName": "Owner Req"}, "created": "2026-10-02T10:00:00Z"}],
                4: [{"requester": {"userId": 501, "username": "nope", "displayName": "Nope"}}]}


def role(rank):
    return {"id": rank, "name": f"Rank{rank}", "rank": rank}


GROUPS = [{"group": {"id": 1, "name": "Alpha Group", "memberCount": 10}, "role": role(200)},
          {"group": {"id": 2, "name": "Plain Group", "memberCount": 99}, "role": role(1)},
          {"group": {"id": 3, "name": "My Own Group", "memberCount": 5}, "role": role(255)},
          {"group": {"id": 4, "name": "Broken Group", "memberCount": 5}, "role": role(100)}]
CAN = {1: True, 2: False, 3: True, 4: True}


class FakeRoblox(rbx.Client):
    def get(self, url, params=None, **kw):
        State.log.append(("GET", url))
        if "friends.roblox.com/v1/users/156/friends" in url:
            return {"data": [{"id": 201, "name": "ann", "displayName": "Ann"}, {"id": 202, "name": "bob", "displayName": "Bob"}, {"id": 203, "name": "cy", "displayName": "Cy"}]}
        if url.endswith("/followers"):
            return {"data": [{"id": 601, "name": "fan", "displayName": "Fan"}], "nextPageCursor": None}
        if url.endswith("/followings"):
            return {"data": [{"id": 701, "name": "idol", "displayName": "Idol"}], "nextPageCursor": None}
        if "/users/156/groups/roles" in url:
            return {"data": GROUPS}
        if url.endswith("/membership"):
            gid = int(url.split("/groups/")[1].split("/")[0])
            return {"permissions": {"groupMembershipPermissions": {"inviteMembers": CAN[gid]}}, "userRole": {"role": {"rank": 1}}}
        if "/join-requests" in url:
            gid = int(url.split("/groups/")[1].split("/")[0])
            if gid == 4:
                raise rbx.RobloxError("boom", 500)
            items = State.requests.get(gid, [])
            if (params or {}).get("cursor") == "p2":
                return {"data": items[2:], "nextPageCursor": None}
            return {"data": items[:2], "nextPageCursor": "p2" if len(items) > 2 else None}
        if "my-private-servers" in url:
            return {"data": []}
        if "avatar-headshot" in url:
            return {"data": []}
        raise rbx.RobloxError("not faked: " + url, 404)

    def post(self, url, body=None, **kw):
        State.log.append(("POST", url, json.dumps(body, sort_keys=True)))
        if urlparse(url).hostname == "presence.roblox.com":
            wanted = set(body["userIds"])
            return {"userPresences": [p for p in State.presence if p["userId"] in wanted]}
        if "/join-requests" in url:
            return {}
        if "get-profiles" in url:
            who = {201: "ann", 202: "bob", 203: "cy", 601: "fan", 701: "idol"}
            return {"profileDetails": [{"userId": i, "names": {"username": who.get(i, f"u{i}"), "displayName": who.get(i, f"u{i}").title()}, "isVerified": False} for i in body["userIds"]]}
        if url.endswith("/v1/users") or "usernames/users" in url:
            return {"data": []}
        raise rbx.RobloxError("not faked: " + url, 404)

    def delete(self, url, body=None, **kw):
        State.log.append(("DELETE", url, json.dumps(body, sort_keys=True)))
        return {}


warnings, shown = [], []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(str(a[2]) if len(a) > 2 else ""))
QMessageBox.information = staticmethod(lambda *a, **k: warnings.append("info: " + (str(a[2]) if len(a) > 2 else "")))
client = FakeRoblox()
w = MainWindow(client, auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
w.ctx.confirm = lambda *a, **k: True
notes = []
w.ctx.notify = lambda title, text: notes.append(text)
alerts_tab = w.people.alerts


def poll_now():
    wait(lambda: not alerts_tab._polling)
    alerts_tab.poll()


check("People has an Alerts page", [w.people.tabs.tabText(i) for i in range(w.people.tabs.count())][-1] == "Alerts")


def sign_in():
    client.user = {"id": 156, "name": "me", "displayName": "Me"}
    w.ctx.signed_in.emit()
    spin(0.3)


# ================================================================ the Alerts page
check("before signing in nothing is asked of Roblox", not State.log, State.log[:2])
sign_in()
w.people.tabs.setCurrentWidget(alerts_tab)
check("the friends are listed when the page is opened", wait(lambda: alerts_tab.table.rowCount() == 3), (alerts_tab.table.rowCount(), alerts_tab._loading, alerts_tab.friends, State.log[-3:], warnings))
check("...none is watched at first, and alerts are off", all(alerts_tab.table.item(r, 0).checkState() == Qt.CheckState.Unchecked for r in range(3)) and not alerts_tab.on.isChecked())
alerts_tab.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
alerts_tab.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
spin(0.1)
check("ticking a friend watches them (saved on disk, under this account)", set(alerts.load()["watch"].get("156", {})) == {"201", "202"}, alerts.load())
check("...with their name", alerts.load()["watch"]["156"]["201"] == "Ann")
before = len([x for x in State.log if "presence" in x[1]])
poll_now()
spin(0.3)
check("while alerts are off nothing is looked up", len([x for x in State.log if "presence" in x[1]]) == before)
alerts_tab.on.setChecked(True)
check("switching alerts on takes the first look (the watched friends only)", wait(lambda: len([x for x in State.log if "presence" in x[1]]) == before + 1))
pres = [x for x in State.log if "presence" in x[1]][-1]
check("...asking about 201 and 202, not 203", json.loads(pres[2])["userIds"] == [201, 202], pres)
wait(lambda: not alerts_tab._polling)
check("...which gives no news yet", notes == [], notes)
State.presence[0] = {"userId": 201, "userPresenceType": 1}
poll_now()
check("Ann coming online shows a notification", wait(lambda: notes == ["Ann is online"]), notes)
check("...and is listed in the latest news", alerts_tab.news.count() == 1 and "Ann is online" in alerts_tab.news.item(0).text())
State.presence[0] = {"userId": 201, "userPresenceType": 2, "lastLocation": "Alpha Game", "rootPlaceId": 11}
poll_now()
check("Ann joining a game shows a notification with the game", wait(lambda: notes[-1] == "Ann joined Alpha Game"), notes)
n = len(notes)
poll_now(); spin(0.3)
check("the same state again is not news", len(notes) == n)
State.presence[1] = {"userId": 202, "userPresenceType": 1}
alerts_tab.c_online.setChecked(False)
poll_now(); spin(0.3)
check("with 'comes online' off, Bob coming online is not news", len(notes) == n, notes)
check("the Now column shows where watched friends are", alerts_tab.table.item(0, 3).text() == "In game" and alerts_tab.table.item(1, 3).text() == "Online", [alerts_tab.table.item(r, 3).text() for r in range(3)])
alerts_tab.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
check("unticking stops watching", set(alerts.load()["watch"]["156"]) == {"201"})
alerts_tab.filter.setText("cy"); spin(0.05)
check("the filter narrows the list", alerts_tab.table.rowCount() == 1)
alerts_tab.filter.setText("")
alerts_tab._watch_shown(True); alerts_tab.show_friends()
check("'Watch all shown' watches everyone in the list", set(alerts.load()["watch"]["156"]) == {"201", "202", "203"})
alerts_tab._watch_shown(False)
check("'Watch none' clears them", alerts.load()["watch"]["156"] == {})
alerts_tab.test()
check("the test button shows a notification", notes[-1] == "This is how a friend alert looks.")
pr = notify_status.problem
check("Windows with notifications switched off says so", pr("win32", True, False) == notify_status.WINDOWS_OFF)
check("Windows with notifications on and a tray is fine", pr("win32", True, True) is None)
check("Windows without a tray that can show messages says so", pr("win32", False, True) == notify_status.NONE_AVAILABLE)
check("Linux with a tray that shows messages is fine", pr("linux", True, None, False) is None)
check("Linux without a tray but with a notification service is fine", pr("linux", False, None, True) is None)
check("Linux with neither says so", pr("linux", False, None, False) == notify_status.NONE_AVAILABLE)
check("the answer is a plain sentence that says the app still shows the alert", "still appear at the bottom of the app" in notify_status.NONE_AVAILABLE)
notify_status.problem = lambda *a, **k: "Windows notifications are switched off."
alerts_tab.refresh_system()
check("the Alerts page warns when the system will not show notifications", not alerts_tab.sys_note.isHidden() and "switched off" in alerts_tab.sys_note.text())
alerts_tab.on.setChecked(False); alerts_tab.on.setChecked(True)
check("...and switching alerts on says so in the status line", "Alerts are on, but windows notifications" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
notify_status.problem = lambda *a, **k: None
alerts_tab.refresh_system()
check("the warning goes away when the system allows notifications", alerts_tab.sys_note.isHidden())
notify_status.problem = pr
sc = w.settings_tab.c_alerts
check("Settings has a switch for friend alerts, and it shows they are on", sc.isChecked() and alerts_tab.on.isChecked())
alerts_tab.watched()["201"] = "Ann"
sc.setChecked(False)
check("switching alerts off in Settings switches them off on the Alerts page and on disk", not alerts_tab.on.isChecked() and alerts.load()["enabled"] is False)
mark = len([x for x in State.log if "presence" in x[1]])
alerts_tab.poll(); spin(0.3)
check("...and nothing is looked up any more", len([x for x in State.log if "presence" in x[1]]) == mark)
alerts_tab.on.setChecked(True)
check("switching them on on the Alerts page shows in Settings", sc.isChecked() and alerts.load()["enabled"] is True)
sc.setChecked(False); sc.setChecked(True)
check("...and switching on from Settings looks at the friends at once", wait(lambda: len([x for x in State.log if "presence" in x[1]]) > mark))
alerts_tab.watched().pop("201", None)
check("the setting is kept on disk (0600)", (alerts.FILE.stat().st_mode & 0o777) == 0o600 if os.name == "posix" else True)
client.user = None; w.ctx.signed_out.emit(); spin(0.1)
n = len(State.log)
alerts_tab.poll(); spin(0.2)
check("signed out: nothing is looked up", len(State.log) == n)

# ================================================================ join requests of all groups
sign_in()
w.groups._groups(GROUPS)
w.groups.all_requests()
dlg = w.groups.requests_dialog
check("the list opens and checks the groups", wait(lambda: not dlg.busy and dlg.table.rowCount() > 0), dlg.note.text())
rows = [[dlg.table.item(r, c).text() for c in range(2)] for r in range(dlg.table.rowCount())]
check("requests of the groups where you may answer are listed (3 + 1; the plain member group is skipped)", len(rows) == 4 and {r[0] for r in rows} == {"Alpha Group", "My Own Group"}, rows)
check("...including the second page of a group's requests", any(r[1] == "User 303" for r in rows), rows)
check("the note says how many groups can be answered in, and that one could not be checked", "may answer requests in 3 of your 4" in dlg.note.text() and "Broken Group" in dlg.note.text(), dlg.note.text())
check("the plain group's requests were not even asked for", not any("/groups/2/join-requests" in x[1] for x in State.log))
dlg.table.selectRow(next(r for r in range(dlg.table.rowCount()) if dlg.table.item(r, 1).text() == "User 301"))
mark = len(State.log)
dlg.answer(True)
check("accepting the selected request sends it to its own group", wait(lambda: any(x[0] == "POST" and "/join-requests" in x[1] for x in State.log[mark:])), State.log[mark:])
sent = [x for x in State.log[mark:] if x[0] == "POST" and "/join-requests" in x[1]]
check("...one request, for the right person", len(sent) == 1 and sent[0][1].endswith("/groups/1/join-requests") and json.loads(sent[0][2]) == {"UserIds": [301]}, sent)
check("...and it leaves the list", wait(lambda: dlg.table.rowCount() == 3) and "Accepted 1" in dlg.note.text(), dlg.note.text())
dlg.table.selectAll()
mark = len(State.log)
dlg.answer(False)
check("declining everything answers each group once", wait(lambda: dlg.table.rowCount() == 0), dlg.note.text())
dec = [x for x in State.log[mark:] if x[0] == "DELETE"]
check("...with the people of that group only", sorted((x[1].split("/groups/")[1].split("/")[0], tuple(json.loads(x[2])["UserIds"])) for x in dec) == [("1", (302, 303)), ("3", (401,))], dec)
check("...and says it declined 3", "Declined 3" in dlg.note.text(), dlg.note.text())
mark = len(State.log)
dlg.answer(True)
check("nothing selected: nothing is sent", not [x for x in State.log[mark:] if x[0] in ("POST", "DELETE")])
asked = []
QInputDialog.getText = staticmethod(lambda *a, **k: (asked.append(a[2]) or "9", True))
dlg.rows = [{"gid": 1, "group": "Alpha Group", "id": 900 + i, "username": f"x{i}", "display": f"X{i}", "created": None} for i in range(6)]
dlg.show_rows(); dlg.table.selectAll()
mark = len(State.log)
dlg.answer(True)
spin(0.3)
check("a large batch asks you to type the number, and a wrong number cancels it", asked and not [x for x in State.log[mark:] if x[0] == "POST"], asked)
dlg.close()
check("the dialog is reachable from the Groups page by a button", any(b.text().startswith("All join requests") for b in w.groups.findChildren(type(w.groups.b_leave))))

# ================================================================ backup
settings.set("log.keep_rows", 777)
alerts.save({"enabled": True, "online": False, "ingame": True, "watch": {"156": {"201": "Ann"}}})
games_store.add({"universeId": 1, "placeId": 11, "name": "Alpha", "playing": 1, "up": 2, "down": 3, "creator": "M", "verified": True, "age": "", "genre": ""})
games_store.add({"universeId": 2, "placeId": 22, "name": "Beta", "playing": 1, "up": 2, "down": 3, "creator": "M", "verified": False, "age": "", "genre": ""})
tab = w.settings_tab
out = tmp / "b.json"
tab.c_lists.setChecked(True)
tab.save_backup(str(out))
check("a backup is written", wait(lambda: out.exists() and "Saved" in tab.backup_note.text()), tab.backup_note.text())
data = json.loads(out.read_text(encoding="utf-8"))
check("...with the settings, alerts and recent games", data["settings"]["log.keep_rows"] == 777 and data["alerts"]["watch"] == {"156": {"201": "Ann"}} and [g["name"] for g in data["recent_games"]] == ["Beta", "Alpha"], list(data))
check("...and, because you are signed in, your lists", [p["id"] for p in data["friends"]] == [201, 202, 203] and data["followers"][0]["id"] == 601 and data["following"][0]["id"] == 701
      and [g["id"] for g in data["groups"]] == [1, 2, 3, 4] and data["account"]["id"] == 156, list(data))
check("a backup file is private (0600)", (out.stat().st_mode & 0o777) == 0o600 if os.name == "posix" else True)
raw = out.read_text(encoding="utf-8").lower()
check("no sign-in is in the backup (nothing with 'cookie' or 'roblosecurity')", "cookie" not in raw and "roblosecurity" not in raw and "_|warning" not in raw)
tab.c_lists.setChecked(False)
tab.save_backup(str(tmp / "b2.json"))
wait(lambda: (tmp / "b2.json").exists())
d2 = json.loads((tmp / "b2.json").read_text(encoding="utf-8"))
check("without the lists box they are left out", "friends" not in d2 and "groups" not in d2 and "settings" in d2, list(d2))

settings.set("log.keep_rows", 100)
alerts.save(alerts.default())
games_store.clear()
tab.restore_backup(str(out))
check("restoring brings back the settings", settings.get("log.keep_rows") == 777)
check("...the alerts", alerts.load()["watch"] == {"156": {"201": "Ann"}} and alerts.load()["online"] is False and alerts.load()["enabled"] is True)
check("...and the recent games in the same order", [g["name"] for g in games_store.recent()] == ["Beta", "Alpha"], games_store.recent())
check("...and says what it restored", "Restored" in tab.backup_note.text() and "1 watched" in tab.backup_note.text() and "2 recent" in tab.backup_note.text(), tab.backup_note.text())
check("the Alerts page shows the restored alerts", alerts_tab.on.isChecked() and not alerts_tab.c_online.isChecked())

bad = {}
(tmp / "x1.json").write_text("not json")
(tmp / "x2.json").write_text(json.dumps({"app": "something-else", "format": 1}))
(tmp / "x3.json").write_text(json.dumps({"app": "roblox-manager", "format": 99}))
(tmp / "x4.json").write_text(json.dumps([1, 2]))
(tmp / "x5.json").write_text(" " * (backup.MAX_BYTES + 10))
for k in ("x1", "x2", "x3", "x4", "x5", "missing"):
    try:
        backup.read(str(tmp / (k + ".json")))
        bad[k] = "accepted"
    except backup.BackupError as e:
        bad[k] = str(e)
check("files that are not backups are refused with a plain message", all(v != "accepted" and len(v) > 10 for v in bad.values()), bad)
check("a newer backup says to update the app", "newer version" in bad["x3"], bad["x3"])
hostile = {"app": "roblox-manager", "format": 1, "settings": {"log.keep_rows": 10 ** 12, "rate.read_burst": "x", "evil": 5, "ui.rate_notes": False},
           "alerts": {"enabled": True, "watch": {"../etc": {"1": "x"}, "156": {"../../x": "y", "5": "ok"}}},
           "recent_games": [{"universeId": "7", "name": "bad"}, {"universeId": 8, "name": "Good<img>", "playing": "lots", "up": -5}, "junk"]}
(tmp / "h.json").write_text(json.dumps(hostile))
done = backup.restore(backup.read(str(tmp / "h.json")))
check("a hostile backup is cleaned: values are limited to their range and unknown keys ignored", settings.get("log.keep_rows") == 10000 and settings.get("rate.read_burst") == 50 and settings.get("ui.rate_notes") is False, settings.get("log.keep_rows"))
check("...only well-formed watch entries and games are kept", alerts.load()["watch"] == {"156": {"5": "ok"}} and [g["name"] for g in games_store.recent()][0] == "Good<img>" and games_store.recent()[0]["playing"] == 0 and games_store.recent()[0]["up"] == 0, (alerts.load(), games_store.recent()[:1]))

check("no error popup appeared at any point of all this", not warnings, warnings)
print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
