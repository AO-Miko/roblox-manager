"""Notifications from the developer: the signed list, the cache, what was read, tools/notify.sh, and the page with its red number. Real ssh-keygen signatures.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_notices.py   (needs git, bash and ssh-keygen)"""
import base64
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="notices-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_UPDATE_BACKEND": "off", "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.6.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

app = QApplication(sys.argv)
import notices
import rbx
import theme
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


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def keygen(name):
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(tmp / name))
    return " ".join((tmp / (name + ".pub")).read_text().split()[:2])


def sign(name, data, ns=notices.NAMESPACE):
    f = tmp / ("f-" + name)
    f.write_bytes(data)
    (tmp / ("f-" + name + ".sig")).unlink(missing_ok=True)
    sh("ssh-keygen", "-q", "-Y", "sign", "-f", str(tmp / name), "-n", ns, str(f))
    return (tmp / ("f-" + name + ".sig")).read_text()


def lst(serial, *items):
    return json.dumps({"serial": serial, "notifications": list(items)}).encode()


def n(i, title="Hello", **kw):
    return dict({"id": i, "title": title, "body": "text of " + i, "date": "2026-10-28"}, **kw)


KEY = "k1"
TRUSTED = "release@test " + keygen(KEY) + "\n"
notices.TRUSTED = TRUSTED
other = keygen("k2")
today = datetime.date(2026, 10, 28)

# ---------------------------------------------------------------- the signature
d1 = lst(1, n("a"), n("b"))
s1 = sign(KEY, d1)
check("a list signed with the release key is read", notices.parse(d1, s1)[0] == 1 and [e["id"] for e in notices.parse(d1, s1)[1]] == ["a", "b"])
check("a list signed with another key is refused", notices.parse(d1, sign("k2", d1)) is None)
check("a list that was changed after signing is refused", notices.parse(d1.replace(b"Hello", b"Hacked"), s1) is None)
check("a signature for another purpose (the ban list's) is refused", notices.parse(d1, sign(KEY, d1, "roblox-manager-bans")) is None)
check("no signature at all is refused", notices.parse(d1, "") is None)
check("a signed list that is not valid JSON is refused", notices.parse(b"{nope", sign(KEY, b"{nope")) is None)
check("a signed list without a serial is refused", notices.parse(b'{"notifications": []}', sign(KEY, b'{"notifications": []}')) is None)

# ---------------------------------------------------------------- what is kept of each entry
big = lst(5, n("ok", level="important", link="https://example.com/x", channel="beta", expires="2030-01-01"),
          n("bad id!"), n("../x"), n(""), n("long", "T" * 200, body="B" * 5000), n("http", link="http://example.com"), n("js", link="javascript:alert(1)"),
          n("lvl", level="supercritical"), n("chan", channel="martians"), n("a"), n("a", "again"), {"id": "notitle"}, "junk", 7, {"id": "day", "title": "t", "date": "tomorrow"})
got = notices.parse(big, sign(KEY, big))[1]
by = {e["id"]: e for e in got}
check("bad ids, missing titles and junk entries are dropped, repeated ids keep the first", set(by) == {"ok", "long", "http", "js", "lvl", "chan", "a", "day"} and by["a"]["title"] == "Hello", sorted(by))
check("long text is trimmed (title 80, text 1000)", len(by["long"]["title"]) == 80 and len(by["long"]["body"]) == 1000)
check("a link that is not https is dropped, an https one is kept", by["http"]["link"] == "" and by["js"]["link"] == "" and by["ok"]["link"] == "https://example.com/x")
check("an unknown level is 'info', an unknown channel is 'all', a bad date is empty", by["lvl"]["level"] == "info" and by["chan"]["channel"] == "all" and by["day"]["date"] == "")
many = lst(1, *[n(f"x{i}") for i in range(80)])
check("at most 50 are kept", len(notices.parse(many, sign(KEY, many))[1]) == 50)

# ---------------------------------------------------------------- the channel and the expiry
items = [notices.clean(x) for x in (n("all"), n("b", channel="beta"), n("s", channel="stable"), n("old", expires="2026-10-27"), n("last", expires="2026-10-28"))]
check("the Beta app sees what is for everybody and for beta", [e["id"] for e in notices.visible(items, "beta", today)] == ["all", "b", "last"])
check("the Stable app sees what is for everybody and for stable", [e["id"] for e in notices.visible(items, "stable", today)] == ["all", "s", "last"])
check("an entry is hidden the day after it expires, not on the day", "old" not in [e["id"] for e in notices.visible(items, "stable", today)] and "last" in [e["id"] for e in notices.visible(items, "stable", today)])

# ---------------------------------------------------------------- download, cache, serials
served = {}


def get(url, limit=0, timeout=0):
    name = url.rsplit("/", 1)[1]
    if name not in served:
        raise OSError("404")
    return served[name]


def serve(data, sig):
    served["notifications.json"], served["notifications.json.sig"] = data, sig.encode()


check("with nothing saved the list is empty", notices.load() == (0, []))
check("a failed download changes nothing and does not raise", notices.refresh(get) is None and notices.load() == (0, []))
serve(d1, s1)
check("a signed list is downloaded and kept", notices.refresh(get) is True and notices.load()[0] == 1 and len(notices.load()[1]) == 2)
check("the same list again is 'no change'", notices.refresh(get) is False)
d2 = lst(2, n("c"), n("a"), n("b"))
serve(d2, sign(KEY, d2))
check("a newer list replaces it", notices.refresh(get) is True and [e["id"] for e in notices.load()[1]] == ["c", "a", "b"])
serve(d1, s1)
check("an older list is never accepted again", notices.refresh(get) is False and notices.load()[0] == 2)
serve(lst(9, n("evil")), sign("k2", lst(9, n("evil"))))
check("a list signed by someone else is refused and the good list stays", notices.refresh(get) is None and notices.load()[0] == 2)
serve(lst(9, n("evil")), "garbage")
check("a list with a broken signature is refused", notices.refresh(get) is None and notices.load()[0] == 2)
cache = notices._cache_file()
c = json.loads(cache.read_text())
c["data"] = base64.b64encode(lst(2, n("planted"))).decode()
cache.write_text(json.dumps(c))
check("a saved list that was edited on the disk is not believed", notices.load() == (0, []))
serve(d2, sign(KEY, d2))
notices.refresh(get)
check("...and the next download puts the good one back", [e["id"] for e in notices.load()[1]] == ["c", "a", "b"])

# ---------------------------------------------------------------- read and announced
check("nothing is read yet: all three are unread", [e["id"] for e in notices.unread("stable", today)] == ["c", "a", "b"])
notices.mark_read("a")
check("a read one is no longer unread", [e["id"] for e in notices.unread("stable", today)] == ["c", "b"] and notices.read_ids() == {"a"})
notices.mark_read("a")
check("marking twice changes nothing", json.loads(notices._state_file().read_text())["read"] == ["a"])
notices.mark_all_read("stable", today)
check("'mark all as read' reads everything", notices.unread("stable", today) == [])
check("the first time nothing is announced (a new installation gets no pop-up for old news)", notices.fresh("stable", today) == [])
d3 = lst(3, n("d", "News"), n("c"), n("a"), n("b"))
serve(d3, sign(KEY, d3))
notices.refresh(get)
check("a new notification is announced once", [e["id"] for e in notices.fresh("stable", today)] == ["d"] and notices.fresh("stable", today) == [])
check("...and is unread", [e["id"] for e in notices.unread("stable", today)] == ["d"])

# ---------------------------------------------------------------- tools/notify.sh in a throw-away repository
# (the shell script is a Linux tool, like ban.sh: on Windows 'bash' may be the WSL stub, so this part runs on Linux only)
if os.name == "nt":
    print("SKIP tools/notify.sh (Linux only)")
else:
    repo = tmp / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "dist").mkdir()
    shutil.copy(ROOT / "tools" / "notify.sh", repo / "tools" / "notify.sh")
    (tmp / "allowed").write_text(f"release@test namespaces=\"git,{notices.NAMESPACE}\" {TRUSTED.split(' ', 1)[1]}")
    sh("git", "init", "-q", "-b", "release", cwd=repo)
    for k, v in (("user.name", "t"), ("user.email", "t@t"), ("gpg.format", "ssh"), ("user.signingkey", str(tmp / KEY)), ("commit.gpgsign", "true"),
                 ("gpg.ssh.allowedSignersFile", str(tmp / "allowed"))):
        sh("git", "config", k, v, cwd=repo)
    (repo / "README").write_text("x")
    sh("git", "add", "-A", cwd=repo)
    check("the test repository is ready", sh("git", "commit", "-q", "-m", "start", cwd=repo).returncode == 0)
    os.environ["ROBLOX_MANAGER_SIGNING_KEY"] = str(tmp / KEY)


    def notify(*args):
        return sh("bash", "tools/notify.sh", *args, cwd=repo)


    def published():
        data = (repo / "dist" / "notifications.json").read_bytes()
        return notices.parse(data, (repo / "dist" / "notifications.json.sig").read_text())


    r = notify("send", "Big news", "Please update.", "--level", "important", "--link", "https://example.com/news")
    check("send makes a signed list that the app accepts", r.returncode == 0 and published() is not None and published()[0] == 1, r.stderr + r.stdout)
    e = published()[1][0]
    check("...with the title, text, level and link", (e["title"], e["body"], e["level"], e["link"]) == ("Big news", "Please update.", "important", "https://example.com/news"), e)
    check("...an id made from the date and the title", e["id"] == datetime.date.today().isoformat() + "-big-news", e["id"])
    check("...as a signed commit", sh("git", "verify-commit", "HEAD", cwd=repo).returncode == 0 and "Notifications" in sh("git", "log", "-1", "--format=%s", cwd=repo).stdout)
    notify("send", "Second", "Only for the beta.", "--channel", "beta", "--expires", "2030-01-01", "--id", "beta-note")
    got = published()
    check("a second one goes first, the serial goes up, channel and expiry are kept", got[0] == 2 and [x["id"] for x in got[1]][0] == "beta-note" and got[1][0]["channel"] == "beta" and got[1][0]["expires"] == "2030-01-01", got)
    notify("send", "Second again", "Replaced.", "--id", "beta-note")
    check("the same id replaces the old notification", [x["id"] for x in published()[1]].count("beta-note") == 1 and published()[1][0]["body"] == "Replaced.")
    before = published()[0]
    for why, args in (("a title that is too long", ("send", "T" * 81, "x")), ("a link that is not https", ("send", "t", "x", "--link", "http://x.example")),
                      ("an unknown level", ("send", "t", "x", "--level", "loud")), ("an unknown channel", ("send", "t", "x", "--channel", "mars")),
                      ("a bad id", ("send", "t", "x", "--id", "no spaces")), ("a text that is too long", ("send", "t", "x" * 1001)), ("a bad expiry day", ("send", "t", "x", "--expires", "soon"))):
        r = notify(*args)
        check(f"{why} is refused and nothing is published", r.returncode != 0 and published()[0] == before, r.stderr[:100])
    r = notify("remove", "beta-note")
    check("remove takes it away (a new signed list)", r.returncode == 0 and "beta-note" not in [x["id"] for x in published()[1]] and published()[0] == before + 1, r.stderr)
    check("removing one that does not exist is refused", notify("remove", "nope").returncode != 0)
    check("list shows what is published", "Big news" in notify("list").stdout)
    sh("git", "checkout", "-q", "-b", "other", cwd=repo)
    check("it only runs on the release branch", notify("send", "t", "x").returncode != 0)
    sh("git", "checkout", "-q", "release", cwd=repo)

# ---------------------------------------------------------------- the page and the red number
notices._cache_file().unlink(missing_ok=True)
notices._state_file().unlink(missing_ok=True)
now = lst(1, n("u1", "First <b>bold</b>", body="<i>text</i> https://x.example", level="warning", link="https://example.com/a"), n("u2", "Second"), n("bt", "For beta", channel="beta"))
(tmp / "state").mkdir(exist_ok=True)
notices._cache_file().write_text(json.dumps({"data": base64.b64encode(now).decode(), "sig": sign(KEY, now)}))
w = MainWindow(rbx.Client(), auto_login=False)
w.show()
spin(0.2)
shown = []
w.ctx.notify = lambda title, text: shown.append((title, text))
page = w.notices
idx = w.tabs.indexOf(w.holders[page])
check("the page is in the side bar, just before Settings", w.tabs.tabText(w.tabs.count() - 2).startswith("Notifications") and idx == w.tabs.count() - 2)
check("two unread (the one for beta is not for this app): the tab says so", w.tabs.tabText(idx) == "Notifications (2)", w.tabs.tabText(idx))
item = next(i for i in w.sidebar.items if i.title == "Notifications")
check("the side bar shows the red number", item.badge == "2" and item.isVisible())
check("the window title carries the number", w.windowTitle().startswith("(2) "), w.windowTitle())
check("the red is a red that white text can be read on", theme.contrast(theme.T["on_accent"], theme.T["badge"]) >= 4.5, theme.contrast(theme.T["on_accent"], theme.T["badge"]))
for mode in ("dark", "light"):
    theme.choose(mode)
    check(f"...also in the {mode} theme", theme.contrast(theme.T["on_accent"], theme.T["badge"]) >= 4.5)
theme.choose("dark")
w.tabs.setCurrentIndex(idx)
spin(0.2)
check("the page lists both, newest first, unread marked", list(page.cards) == ["u1", "u2"] and page.cards["u1"].property("unread") is True)
labels = [l.text() for l in page.findChildren(QLabel)]
check("HTML in a title or text is shown as plain text, not interpreted", "First <b>bold</b>" in labels and "<i>text</i> https://x.example" in labels and
      all(l.textFormat() == Qt.TextFormat.PlainText for l in page.cards["u1"].findChildren(QLabel) if "<" in l.text()))
btns = {b.text(): b for b in page.findChildren(QPushButton)}
check("a notification with a link has an 'Open link' button", "Open link" in btns)
opened = []
import tab_notices
tab_notices.open_url = opened.append
btns["Open link"].click()
check("...that opens the https link", opened == ["https://example.com/a"], opened)
check("the summary says how many are unread", page.summary.text() == "2 unread of 2", page.summary.text())
page.read_one("u1")
spin(0.1)
check("reading one lowers the number everywhere", w.tabs.tabText(idx) == "Notifications (1)" and item.badge == "1" and w.windowTitle().startswith("(1) ") and
      page.cards["u1"].property("unread") is False, (w.tabs.tabText(idx), w.windowTitle()))
page.b_all.click()
spin(0.1)
check("'Mark all as read' removes the number", w.tabs.tabText(idx) == "Notifications" and item.badge == "" and not w.windowTitle().startswith("(") and not page.b_all.isEnabled())
# a new list arrives while the app is open
fresh = lst(2, n("u3", "Brand new"), n("u1", "First"), n("u2", "Second"))
notices._state_file().write_text(json.dumps({"read": ["u1", "u2"], "seen": ["u1", "u2"]}))       # (what the app has seen and read so far)
notices._cache_file().write_text(json.dumps({"data": base64.b64encode(fresh).decode(), "sig": sign(KEY, fresh)}))
page.reload(announce=True)
spin(0.1)
check("a new notification: the number comes back and a pop-up announces it", w.tabs.tabText(idx) == "Notifications (1)" and shown and shown[-1][1] == "Brand new", (w.tabs.tabText(idx), shown))
page.reload(announce=True)
check("...only once", len(shown) == 1)
check("with no notifications the page says so", (notices._cache_file().unlink() or True) and (page.reload() or True) and any(l.text() == "No notifications." for l in page.findChildren(QLabel)))

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
