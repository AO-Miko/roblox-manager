"""Test of the app debug log (debuglog.py and the App debug view in the Request log tab): everything that happens is recorded with its output, and nothing private survives:
cookies, tokens, passwords, codes, e-mail addresses, phone numbers, IP addresses, the names and id of the accounts, the names of people in answers, folder names.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_debug.py"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="debug-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

app = QApplication(sys.argv)
import logging

import debuglog
import requests
import rbx
import settings
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:300]) if e else ""))


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


COOKIE = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_ABCDEF0123456789"
EMAIL = "secret.person@example.org"
IPV4 = "203.0.113.77"
IPV6 = "2001:db8:85a3::8a2e:370:7334"
PHONE = "+34 612 345 678"
TOKEN = "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLL"
SECRETS = [COOKIE.split("|_")[1], "ABCDEF0123456789", EMAIL, IPV4, "8a2e:370:7334", "612 345 678", TOKEN, "hunter2", "JohnnyPrivate", "Johnny Display", "424242",
           "AliceFriendName", "Alice Friend Display", "Bobby Secret Description"]

# ---------------------------------------------------------------- hiding
debuglog.set_identity({"id": 424242, "name": "JohnnyPrivate", "displayName": "Johnny Display"})
S = debuglog.scrub
check("a cookie is hidden", "ABCDEF0123456789" not in S(f"cookie sent: .ROBLOSECURITY={COOKIE} end") and "[cookie]" in S(f".ROBLOSECURITY={COOKIE}"), S(f".ROBLOSECURITY={COOKIE}"))
check("an e-mail address, a phone number and IP addresses (4 and 6) are hidden", all(s not in S(f"mail {EMAIL} phone {PHONE} v4 {IPV4} v6 {IPV6}") for s in (EMAIL, "612 345 678", IPV4, "370:7334")), S(f"mail {EMAIL} phone {PHONE} v4 {IPV4} v6 {IPV6}"))
check("values of secret-looking keys are hidden in json, in a query and in headers", "hunter2" not in S('{"password": "hunter2"}') and "abcd" not in S("?token=abcd&limit=3") and "limit=3" in S("?token=abcd&limit=3")
      and "secretvalue" not in S("Authorization: Bearer secretvalue123") and "shortcsrf" not in S("x-csrf-token: shortcsrf"), S('{"password": "hunter2"}'))
check("a long opaque string is hidden", TOKEN not in S("value " + TOKEN) and "[token]" in S("value " + TOKEN))
check("the account's name (any case) and id are hidden", "JohnnyPrivate" not in S("acct=johnnyprivate user JohnnyPrivate") and "424242" not in S("/v1/users/424242/friends") and "<my id>" in S("/v1/users/424242/friends")
      and "Johnny Display" not in S("hello Johnny Display"), S("acct=johnnyprivate /users/424242"))
check("your home folder is shown as ~", str(Path.home()) not in S(f"file {Path.home()}/x/y.json") and "~/x/y.json" in S(f"file {Path.home()}/x/y.json"), S(f"file {Path.home()}/x/y.json"))
check("what is useful stays: numbers, a server id, ping, error codes, plain words", S("server 3f2a9c1e-1111-2222-3333-444455556666 ping 45 fps 60 code=5 limit=10 12:30:45") == "server 3f2a9c1e-1111-2222-3333-444455556666 ping 45 fps 60 code=5 limit=10 12:30:45", S("server 3f2a9c1e-1111-2222-3333-444455556666 ping 45 fps 60 code=5 limit=10 12:30:45"))
check("a six-digit code in a key is hidden", "123456" not in S('{"code": "123456"}') and "123456" not in S("code=123456"), S("code=123456"))
check("a long text is shortened with a note", S("word " * 1000, 100).endswith("more characters]") and len(S("word " * 1000, 100)) < 160)
pv = debuglog.preview({"data": [{"id": 5, "name": "AliceFriendName", "displayName": "Alice Friend Display", "isOnline": True, "description": "Bobby Secret Description", "ping": 33}] * 9, "email": EMAIL,
                       "nextPageCursor": None})
check("an answer is shown with names, descriptions and e-mail hidden, ids and numbers kept, long lists cut", all(s not in pv for s in ("AliceFriendName", "Alice Friend Display", "Bobby Secret Description", EMAIL))
      and '"isOnline": true' in pv and '"ping": 33' in pv and "more" in pv and '"nextPageCursor": null' in pv, pv[:300])
check("an answer given as text or bytes is understood too", '"***"' in debuglog.preview(b'{"name":"AliceFriendName","id":1}') and "AliceFriendName" not in debuglog.preview('{"name": "AliceFriendName"}')
      and "not json" in debuglog.preview("not json at all") and "AliceFriendName" not in debuglog.preview('{"name": "AliceFriendName", "x": [1,'), debuglog.preview('{"name": "AliceFriendName", "x": [1,'))

# ---------------------------------------------------------------- events
debuglog.clear()
e = debuglog.event("test", f"hello {EMAIL}", "warning", f"output with {IPV4}\nsecond line")
check("an event keeps its area, level and output, hidden", e["area"] == "test" and e["level"] == "warning" and EMAIL not in e["message"] and IPV4 not in e["detail"] and "second line" in e["detail"], e)
debuglog.event("test", "plain info")
debuglog.event("other", "an error", "error", "trace")
check("filters: by level, by area, by words (also in the output)", [x["message"] for x in debuglog.snapshot("warning")] == ["hello [email]", "an error"] and len(debuglog.snapshot(area="other")) == 1
      and len(debuglog.snapshot(text="second line")) == 1 and len(debuglog.snapshot(text="plain nothing")) == 0, [x["message"] for x in debuglog.snapshot("warning")])
txt = debuglog.export_text()
check("the export has a header (version, system, what is hidden) and every event with its output", txt.startswith("Roblox Manager debug log") and f"app {(ROOT / 'linux' / 'VERSION').read_text().strip()}" in txt and "hidden" in txt and "    second line" in txt and EMAIL not in txt, txt[:300])
f = debuglog.FILE
check("events are written to debug.log (private state folder), hidden", f.exists() and "plain info" in f.read_text(encoding="utf-8") and EMAIL not in f.read_text(encoding="utf-8"))
debuglog.ENABLED = False
debuglog.event("test", "not written to the file")
debuglog.ENABLED = True
check("switched off (Settings), nothing more goes to the file, but the list still has it", "not written to the file" not in f.read_text(encoding="utf-8") and any(x["message"] == "not written to the file" for x in debuglog.EVENTS))
check("the setting 'log.debug' exists, is on by default and drives the file", settings.DEFAULTS["log.debug"][0] is True)
settings.set("log.debug", False)
check("...switching it off in Settings stops the file", debuglog.ENABLED is False)
settings.set("log.debug", True)
check("...and on again starts it; the change itself is an event", debuglog.ENABLED is True and any(x["area"] == "settings" and "log.debug" in x["message"] for x in debuglog.EVENTS))

# ---------------------------------------------------------------- requests, with what was sent and what came back
debuglog.clear()
c = rbx.Client()


def fake_request(method, url, **kw):
    r = requests.Response()
    r.status_code = 200
    r._content = ('{"data":[{"id":7,"name":"AliceFriendName","displayName":"Alice Friend Display"}],"email":"%s","ip":"%s"}' % (EMAIL, IPV4)).encode()
    r.headers["content-type"] = "application/json"
    r.headers["set-cookie"] = ".ROBLOSECURITY=" + COOKIE
    r.url = url
    return r


c.session.request = fake_request
c._pace = lambda *a, **k: None
data = c.get("https://friends.roblox.com/v1/users/424242/friends", {"limit": 10, "cursor": TOKEN}, auth=False)
evs = [x for x in debuglog.EVENTS if x["area"] == "http"]
check("a request becomes an http event with the answer's output, and the real data is still returned unhidden", len(evs) == 1 and data["data"][0]["name"] == "AliceFriendName", (evs, data))
check("...the line says what was asked and how Roblox answered (account id and secrets hidden)", evs and "GET friends.roblox.com/v1/users/<my id>/friends" in evs[0]["message"] and "-> 200" in evs[0]["message"] and TOKEN not in evs[0]["message"], evs[0]["message"] if evs else "")
check("...the output shows the answer's status, size and a cut-down body with names, e-mail and address hidden", evs and "answer: HTTP 200" in evs[0]["detail"] and "bytes" in evs[0]["detail"] and all(s not in evs[0]["detail"] for s in ("AliceFriendName", EMAIL, IPV4, "ABCDEF0123456789")), evs[0]["detail"] if evs else "")
debuglog.clear()
c.post("https://friends.roblox.com/v1/users/55/unfriend", {"password": "hunter2", "reason": "x"}, auth=False)
evs = [x for x in debuglog.EVENTS if x["area"] == "http"]
check("what was sent is shown too, with passwords hidden", evs and "sent:" in evs[0]["detail"] and "hunter2" not in evs[0]["detail"] and '"reason": "x"' in evs[0]["detail"], evs[0]["detail"] if evs else "")


def failing(method, url, **kw):
    r = requests.Response()
    r.status_code = 404
    r._content = b'{"errors":[{"code":2,"message":"User not found"}]}'
    r.headers["content-type"] = "application/json"
    return r


c.session.request = failing
debuglog.clear()
try:
    c.get("https://users.roblox.com/v1/users/1", auth=False)
except rbx.RobloxError:
    pass
evs = [x for x in debuglog.EVENTS if x["area"] == "http"]
check("an error answer is a warning with Roblox's own message in the output", evs and evs[0]["level"] == "warning" and "User not found" in evs[0]["detail"], evs[0] if evs else "")


def broken(method, url, **kw):
    raise requests.ConnectionError("dns " + IPV4)


c.session.request = broken
debuglog.clear()
try:
    c.get("https://users.roblox.com/v1/users/1", auth=False, retries=0)
except rbx.RobloxError:
    pass
evs = [x for x in debuglog.EVENTS if x["area"] == "http"]
check("a network failure is an error event (no answer)", evs and evs[0]["level"] == "error" and "no answer" in evs[0]["message"], evs[0] if evs else "")

# ---------------------------------------------------------------- catching everything
debuglog.install()
debuglog.install()
check("installing twice does not double anything", sum(1 for h in logging.getLogger().handlers if h.__class__.__name__ == "_Handler") == 1)
debuglog.clear()
logging.getLogger("somelib").warning("library says %s", EMAIL)
rbx.log.info("app logger says hi from %s", IPV4)
check("every logging record becomes an event (the app's and the libraries'), hidden", any(x["area"] == "log:somelib" and x["level"] == "warning" and EMAIL not in x["message"] for x in debuglog.EVENTS)
      and any(x["area"] == "app" and "says hi" in x["message"] and IPV4 not in x["message"] for x in debuglog.EVENTS), [x["area"] + x["message"] for x in debuglog.EVENTS])
print("printed line with", EMAIL)
print("to stderr", file=sys.stderr)
check("what the program prints (stdout and stderr) becomes events, hidden", any(x["area"] == "output" and x["level"] == "info" and "printed line" in x["message"] and EMAIL not in x["message"] for x in debuglog.EVENTS)
      and any(x["area"] == "output" and x["level"] == "warning" and "to stderr" in x["message"] for x in debuglog.EVENTS))


def boom():
    raise ValueError("thread problem " + IPV4)


t = threading.Thread(target=boom, name="worker-x")
t.start()
t.join()
spin(0.1)
ev = next((x for x in debuglog.EVENTS if x["area"] == "crash"), None)
check("an error nobody caught in a thread is recorded with its trace, hidden", ev and ev["level"] == "error" and "worker-x" in ev["message"] and "ValueError" in ev["detail"] and IPV4 not in ev["message"] + ev["detail"], ev)

# ---------------------------------------------------------------- the window
w = MainWindow(client=c, auto_login=False)
w.show()
spin(0.3)
rq = w.requests
check("the Request log has two views: Requests and App debug", [rq.views.tabText(i) for i in range(rq.views.count())] == ["Requests", "App debug"])
dv = rq.debug
check("the old Requests view is untouched (table, limits, filters)", rq.table.columnCount() == 8 and rq.limits.columnCount() == 5 and rq.filter is not None)
debuglog.clear()
dv.clear()
spin(0.6)
w.ctx.status("Hello from the status line for " + EMAIL)
w.tabs.setCurrentIndex(1)
w.tabs.setCurrentIndex(0)
spin(0.6)
msgs = [x["message"] for x in debuglog.EVENTS]
check("the status line, and each page that is opened, are events", any("status line: Hello" in m and EMAIL not in m for m in msgs) and any("opened page" in m for m in msgs), msgs[:6])
btn = w.findChildren(QPushButton)[0]
btn.show()
before = len(debuglog.EVENTS)
QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
spin(0.2)
check("a button press is an event with the button's text and the page", any(x["area"] == "click" for x in list(debuglog.EVENTS)[before:]), [x["message"] for x in list(debuglog.EVENTS)[before:]])
settings.set("ui.rate_notes", False)
settings.set("ui.rate_notes", True)
check("a changed setting is an event", any(x["area"] == "settings" and "ui.rate_notes = False" in x["message"] for x in debuglog.EVENTS))
done = []
w.ctx.async_.run(lambda: {"name": "AliceFriendName", "count": 3}, lambda r: done.append(r))
wait(lambda: done)
tk = [x for x in debuglog.EVENTS if x["area"] == "task"]
check("a background task is started and finished, with its output (names hidden)", len(tk) >= 2 and any("finished" in x["message"] and '"count": 3' in x["detail"] and "AliceFriendName" not in x["detail"] for x in tk), tk[-2:])
failed = []


def bad():
    raise RuntimeError("it broke for " + EMAIL)


w.ctx.async_.run(bad, None, lambda e: failed.append(e))
wait(lambda: failed)
tk = [x for x in debuglog.EVENTS if x["area"] == "task" and "failed" in x["message"]]
check("a failing task is an error event with the full trace, hidden", tk and tk[0]["level"] == "error" and "RuntimeError" in tk[0]["detail"] and "Traceback" in tk[0]["detail"] and EMAIL not in tk[0]["detail"] + tk[0]["message"], tk)
w.ctx.client.user = {"id": 424242, "name": "JohnnyPrivate", "displayName": "Johnny Display"}
w.ctx.signed_in.emit()
w.ctx.status("Signed in as JohnnyPrivate (424242)")
spin(0.5)
check("signing in is an event, and the account's name and id never show afterwards", any(x["area"] == "account" and x["message"] == "signed in" for x in debuglog.EVENTS)
      and not any("JohnnyPrivate" in x["message"] + x["detail"] or "424242" in x["message"] + x["detail"] for x in debuglog.EVENTS), [x["message"] for x in debuglog.EVENTS if "<me>" in x["message"]])

# the view
spin(0.8)
check("the view lists the events (newest at the bottom) and counts them", dv.table.rowCount() >= 6 and "events since the app started" in dv.count.text(), (dv.table.rowCount(), dv.count.text()))
check("...the area list holds the kinds of event that happened", {"task", "settings", "page", "ui"} <= {dv.area.itemData(i) for i in range(dv.area.count())}, [dv.area.itemText(i) for i in range(dv.area.count())])
row = next(r for r in range(dv.table.rowCount()) if "[+ output]" in dv.table.item(r, 3).text())
dv.table.selectRow(row)
spin(0.1)
check("selecting an event shows its output below", dv.detail.toPlainText() and dv.rows[row]["message"] in dv.detail.toPlainText() and dv.rows[row]["detail"].splitlines()[0] in dv.detail.toPlainText(), dv.detail.toPlainText()[:200])
dv.level.setCurrentIndex(dv.level.findData("error"))
spin(0.1)
check("'Errors only' shows only errors", dv.table.rowCount() >= 1 and all(dv.table.item(r, 1).text() == "error" for r in range(dv.table.rowCount())), dv.table.rowCount())
dv.level.setCurrentIndex(0)
dv.area.setCurrentIndex(dv.area.findData("settings"))
spin(0.1)
check("one area only", dv.table.rowCount() >= 2 and all(dv.table.item(r, 2).text() == "settings" for r in range(dv.table.rowCount())))
dv.area.setCurrentIndex(0)
dv.filter.setText("rate_notes")
spin(0.1)
check("the filter finds words in the lines", 1 <= dv.table.rowCount() <= 3 and all("rate_notes" in dv.table.item(r, 3).text() for r in range(dv.table.rowCount())), dv.table.rowCount())
dv.filter.setText("")
spin(0.1)
dv.pause.setChecked(True)
n = dv.table.rowCount()
debuglog.event("test", "added while paused")
spin(0.8)
check("Pause keeps the list still", dv.table.rowCount() == n)
dv.pause.setChecked(False)
dv.rebuild()
check("...and the event is there after pausing", any("added while paused" in dv.table.item(r, 3).text() for r in range(dv.table.rowCount())))
dv.copy()
clip = QGuiApplication.clipboard().text()
check("Copy puts the shown events, with output, on the clipboard", clip.startswith("Roblox Manager debug log") and "added while paused" in clip, clip[:120])
out = tmp / "saved.txt"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), "Text (*.txt)"))
dv.save()
check("Save as text writes the same", out.exists() and out.read_text(encoding="utf-8").startswith("Roblox Manager debug log"))
dv.clear()
check("Clear list empties the list and the kept events", dv.table.rowCount() == 0 and len(debuglog.EVENTS) == 0)

# nothing private anywhere
debuglog.event("final", "marker")
spin(0.5)
text_all = debuglog.export_text() + (debuglog.FILE.read_text(encoding="utf-8") if debuglog.FILE.exists() else "")
for p in (tmp / "state").glob("debug.log*"):
    text_all += p.read_text(encoding="utf-8", errors="replace")
leaks = [s for s in SECRETS if s in text_all]
check("after all this no secret appears in the events, the export or debug.log", not leaks, leaks)
check("debug.log is private to this user (where files have Unix permissions)", sys.platform == "win32" or (debuglog.FILE.stat().st_mode & 0o077) == 0, oct(debuglog.FILE.stat().st_mode))

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
