"""Security tests: what comes from Roblox is shown as text (never read as HTML), join codes cannot add anything to a launcher link, nothing builds shell text from a path,
folders are private, the Windows build only installs pinned and hashed libraries, the Android manifest and login web view are locked down, and the sources contain none
of the usual dangerous calls. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_security.py"""
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="sec-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache"), "QT_QPA_PLATFORM": "offscreen"})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

app = QApplication(sys.argv)
import rbx
import tab_account
import tab_admin
import tab_discover
import tab_settings
import ui_common
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


def shown(label):
    """What a person SEES in a label: rich text is rendered, plain text is shown as it is."""
    if label.textFormat() == tab_discover.Qt.TextFormat.PlainText:
        return label.text()
    d = QTextDocument()
    d.setHtml(label.text())
    return d.toPlainText()


HOSTILE = '<img src="http://evil.example/a.png"><a href="http://evil.example">click</a> & "quoted" <script>alert(1)</script>'

# ---------------------------------------------------------------- text from Roblox is shown as text
check("esc(): angle brackets, ampersands and quotes are made harmless", ui_common.esc(HOSTILE) == ui_common.esc(HOSTILE) and "<" not in ui_common.esc(HOSTILE) and ui_common.esc(None) == "")
doc = QTextDocument()
doc.setHtml(f"<b>{ui_common.esc(HOSTILE)}</b>")
check("...and shown exactly as it was written", doc.toPlainText() == HOSTILE, doc.toPlainText())

w = MainWindow(rbx.Client(), auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
d = w.discover
d.mode = "search"
d.search.setText("x")
d._people_found("x", ([{"id": 5, "name": "evil", "displayName": HOSTILE}], {}))
labels = [shown(label) for label in d.body.findChildren(QLabel)]
check("a person's display name with HTML in it is shown literally in the search results", HOSTILE in labels, labels)
d._groups_found("x", [{"id": 9, "name": HOSTILE, "memberCount": 3, "description": HOSTILE}])
labels = [shown(label) for label in d.body.findChildren(QLabel)]
check("...and so is a group's name and description", HOSTILE in labels and any(HOSTILE[:40] in s for s in labels), labels)
card = {"universeId": 1, "placeId": 2, "name": HOSTILE, "playing": 1, "up": 1, "down": 1, "creator": HOSTILE, "verified": False, "age": "", "genre": ""}
d.detail.show_game(card)
check("a game's name and creator are shown literally on its page", shown(d.detail.title) == HOSTILE and HOSTILE in shown(d.detail.creator), (shown(d.detail.title), shown(d.detail.creator)))

prof = {"info": {"name": "n", "displayName": HOSTILE, "description": HOSTILE, "created": "2020-01-01T00:00:00Z"}, "counts": {}, "avatar": b""}
bd = tab_admin.BanDialog(w, 5, prof, HOSTILE)
check("the ban question shows the person's name and the reason literally", shown(bd.display) == HOSTILE and HOSTILE in shown(bd.reason) and bd.about.toPlainText() == HOSTILE, (shown(bd.display), shown(bd.reason)))
ud = tab_admin.UnbanDialog(w, 5, prof, {"since": HOSTILE, "by": 7, "rank": 2, "reason": HOSTILE}, HOSTILE)
check("the unban question shows the ban's date, reason and your note literally", shown(ud.reason).count(HOSTILE) == 3, shown(ud.reason))

fr = w.friends
row = {"id": 5, "name": HOSTILE, "username": HOSTILE, "verified": False, "type": 0, "game": HOSTILE, "location": HOSTILE}
fr._render_profile(row, {"description": HOSTILE, "counts": {}, "created": "2020-01-01T00:00:00Z"})
check("a friend's profile shows name, username, game and description literally", shown(fr.profile).count(HOSTILE[:30]) >= 3 and "<script>" in shown(fr.profile), shown(fr.profile)[:200])

# ---------------------------------------------------------------- join codes
check("a normal join code goes into the launcher link", rbx.launcher_url(5, link_code="AbC-123_x") == "roblox://experiences/start?placeId=5&linkCode=AbC-123_x")
bad = 0
for code in ("AB&x=1", "AB CD", "AB;rm", "a" * 65, "é", "A/B", "A?B", "A%26B", "../x", "A\nB", "<x>"):
    try:
        rbx.launcher_url(5, link_code=code)
        bad += 1
    except ValueError:
        pass
check("a code that could add something to the link is refused (11 kinds)", bad == 0, bad)
try:
    rbx.launcher_url(5, job_id="x&y")
    ok = False
except ValueError:
    ok = True
check("...a server id the same", ok)
check("a join link with an odd code gives no code (so no private-server launch)", rbx.link_code_of("https://www.roblox.com/games/5?privateServerLinkCode=A%26B") == (5, None)
      and rbx.link_code_of("https://www.roblox.com/games/5?privateServerLinkCode=AB&x=1") == (5, "AB"), rbx.link_code_of("https://www.roblox.com/games/5?privateServerLinkCode=AB&x=1"))
opened = []
tab_discover.QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
import roblox_launcher
roblox_launcher.status = lambda fresh=False: {"installed": True, "how": "t", "platform": "linux", "command": None, "url": None, "can_install": False}
check("Play refuses an odd code: nothing is opened, the person is told", tab_discover.launch_roblox(w.ctx, 5, "AB&x=1") is False and not opened and "unusual" in w.statusBar().currentMessage(), (opened, w.statusBar().currentMessage()))

# ---------------------------------------------------------------- no shell text built from a path
if os.name == "posix":                                    # (the shell restart is the Linux one; a folder name with quotes cannot even be made on Windows)
    import subprocess
    calls = []
    real_popen = subprocess.Popen
    subprocess.Popen = lambda args, *a, **k: calls.append(args) or type("P", (), {})()
    fake_home = tmp / 'h"; touch PWNED; "$(touch PWNED2)'
    (fake_home / ".local" / "bin").mkdir(parents=True)
    (fake_home / ".local" / "bin" / "roblox-manager").write_text("#!/bin/sh\n")
    real_home, real_quit = Path.home, QApplication.instance().quit
    Path.home = staticmethod(lambda: fake_home)
    QApplication.instance().quit = lambda: None
    import plat
    was_win = plat.IS_WIN
    plat.IS_WIN = False
    tab_settings.plat.IS_WIN = False
    w.settings_tab.restart_app()
    plat.IS_WIN = was_win
    subprocess.Popen = real_popen
    Path.home = real_home
    QApplication.instance().quit = real_quit
    launcher_call = next((c for c in calls if c and c[0] == "sh"), None)
    check("restarting runs a fixed shell text and gives the launcher's path as an argument (a path with quotes and $() in it cannot run anything)",
          launcher_call is not None and launcher_call[2] == 'sleep 1.5; exec "$0"' and launcher_call[3] == str(fake_home / ".local" / "bin" / "roblox-manager") and "PWNED" not in launcher_call[2], launcher_call)


else:
    src = (ROOT / "linux" / "tab_settings.py").read_text(encoding="utf-8")
    check("restarting runs a fixed shell text and gives the launcher's path as an argument (checked in the source on Windows)", """["sh", "-c", 'sleep 1.5; exec "$0"', str(launcher)]""" in src)

# ---------------------------------------------------------------- private folders
if os.name == "posix":
    check("the settings folder is private (only you)", stat.S_IMODE(rbx.CONFIG_DIR.stat().st_mode) == 0o700, oct(stat.S_IMODE(rbx.CONFIG_DIR.stat().st_mode)))
    check("the folder with logs and saved names is private too", stat.S_IMODE(rbx.STATE_DIR.stat().st_mode) == 0o700, oct(stat.S_IMODE(rbx.STATE_DIR.stat().st_mode)))
check("the open window's socket is for this user only", "UserAccessOption" in (ROOT / "linux" / "app.py").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- the Windows build installs only pinned, hashed libraries
lock = (ROOT / "tools" / "windows" / "requirements.lock").read_text(encoding="utf-8").splitlines()
entries = [x for x in lock if x and not x.startswith("#")]
check("the lock pins every library with an exact version and a SHA-256", entries and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][^ ]* --hash=sha256:[0-9a-f]{64}", x) for x in entries), entries[:2])
names = {x.split("==")[0].lower() for x in entries}
check("...including the libraries the two main ones need (requests' and PySide6's)", {"requests", "pyside6", "urllib3", "certifi", "idna", "charset-normalizer", "shiboken6"} <= names, sorted(names))
check("the build installs only from the lock, and demands the hashes", '"--require-hashes"' in (ROOT / "tools" / "build_windows.py").read_text(encoding="utf-8") and "requirements.lock" in (ROOT / "tools" / "build_windows.py").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- Android
manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
check("Android: only the main screen is reachable from other apps (one exported component)", manifest.count('android:exported="true"') == 1 and 'android:name=".MainActivity"' in manifest.split('android:exported="true"')[0][-200:], manifest.count('android:exported="true"'))
check("Android: no backups, no plain http, no extra permissions beyond internet and installing updates", 'android:allowBackup="false"' in manifest and 'usesCleartextTraffic="false"' in manifest
      and sorted(re.findall(r'uses-permission android:name="([^"]+)"', manifest)) == ["android.permission.INTERNET", "android.permission.REQUEST_INSTALL_PACKAGES"])
check("Android: the only package the app asks about is Roblox", re.findall(r'<package android:name="([^"]+)"', manifest) == ["com.roblox.client"])
login = (ROOT / "android/app/src/main/java/app/robloxmanager/ui/LoginScreen.kt").read_text(encoding="utf-8")
check("Android: the login web view reads no files or other apps' content, and only follows https links to Roblox", "allowFileAccess = false" in login and "allowContentAccess = false" in login
      and "MIXED_CONTENT_NEVER_ALLOW" in login and "shouldOverrideUrlLoading" in login and 'u.scheme == "https"' in login and "isRoblox" in login)
check("Android: no JavaScript bridge into the app", "addJavascriptInterface" not in "".join(p.read_text(encoding="utf-8") for p in (ROOT / "android/app/src/main/java").rglob("*.kt")))

# ---------------------------------------------------------------- the sources contain none of the usual dangerous calls
bad_patterns = {r"shell\s*=\s*True": "shell=True", r"\bos\.system\(": "os.system", r"\beval\(": "eval", r"\bexec\((?!\))": "exec of a string", r"verify\s*=\s*False": "verify=False",
                r"\bpickle\b": "pickle", r"yaml\.load\(": "yaml.load", r"tempfile\.mktemp\(": "mktemp", r"\bmarshal\b": "marshal"}
problems = []
for p in sorted((ROOT / "linux").glob("*.py")) + sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "tests").glob("*.py")):
    if p.name == "test_security.py":
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#")[0]
        for pat, name in bad_patterns.items():
            if re.search(pat, code) and not (name == "exec of a string" and (".exec(" in code or "def exec" in code or "app.exec" in code or p.name == "test_launcher_update.py")):
                problems.append(f"{p.name}:{i}: {name}")
check("no shell=True, os.system, eval, verify=False, pickle, yaml.load, mktemp in the code or the tests", not problems, problems[:8])
secrets_in_logs = [f"{p.name}: {m.group(0)}" for p in (ROOT / "linux").glob("*.py")
                   for m in re.finditer(r"log\.(?:info|debug|warning|error)\([^)]*[,(]\s*(?:self\._cookie|self\.cookie|cookie|password|pw|passwd)\s*[,)]", p.read_text(encoding="utf-8"))]
check("no log line is given a cookie or a password variable (the two that mention the cookie only log its length and where it is kept)", not secrets_in_logs, secrets_in_logs)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
