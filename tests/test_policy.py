"""Test of forced updates (linux/policy.py + the 'Update required' page): a version that is 2 or more updates behind covers the whole window until it is updated.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_policy.py   (needs ssh-keygen)"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="policy-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.7.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import bans
import policy
import rbx
import update_required
import updater
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:220]) if e else ""))


def spin(s=0.1):
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(fn, t=6):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        if fn():
            return True
        time.sleep(0.02)
    return False


key = tmp / "key"
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", "t"], check=True)
pub = (tmp / "key.pub").read_text().split()
trusted = f"t {pub[0]} {pub[1]}\n"
bans.TRUSTED = trusted                                   # from here on the test key is the one that is trusted


def sign(obj, namespace="roblox-manager-policy"):
    f = tmp / "p.json"
    f.write_text(json.dumps(obj))
    (tmp / "p.json.sig").unlink(missing_ok=True)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", namespace, str(f)], check=True)
    return f.read_bytes(), (tmp / "p.json.sig").read_text()


served = {}


def fake_get(url, limit=0, timeout=0):
    name = url.rsplit("/", 1)[1]
    if name not in served:
        raise OSError("down")
    return served[name]


def publish(stable, serial, limit=None, namespace="roblox-manager-policy"):
    obj = {"serial": serial, "stable": stable}
    if limit:
        obj["limit"] = limit
    data, sig = sign(obj, namespace)
    served.clear()
    served.update({"policy.json": data, "policy.json.sig": sig.encode()})
    return policy.refresh(get=fake_get)


STABLE = ["1.8.0.0.0", "1.9.0.0.0", "1.9.0.0"]          # (1.9.0.0 is the same version spelled with four numbers: it counts once)

# ---------------------------------------------------------------- the file
data, sig = sign({"serial": 3, "limit": 2, "stable": STABLE})
check("a signed policy is read", policy.parse(data, sig, trusted) == (3, 2, STABLE))
check("a changed policy is refused", policy.parse(data.replace(b"1.8.0.0.0", b"1.7.0.0.0"), sig, trusted) is None)
data2, sig2 = sign({"serial": 3, "stable": STABLE}, "roblox-manager-bans")
check("a policy signed for another purpose (the ban list's namespace) is refused", policy.parse(data2, sig2, trusted) is None)
data3, sig3 = sign({"serial": 3, "stable": ["not-a-version"]})
check("a policy with something that is not a version is refused", policy.parse(data3, sig3, trusted) is None)
check("without a limit it is 2", policy.parse(*sign({"serial": 1, "stable": []}), trusted)[1] == 2)

# ---------------------------------------------------------------- how far behind
check("before anything is downloaded nobody is blocked", policy.status("1.0.0")["blocked"] is False and policy.status("1.0.0")["behind"] == 0)
check("refresh stores a valid policy", publish(STABLE, 1) is True)
s = policy.status("1.7.0")
check("two updates behind (1.7.0 with 1.8.0.0.0 and 1.9.0.0.0 out): blocked, newest named", s["blocked"] and s["behind"] == 2 and s["latest"] in ("1.9.0.0.0", "1.9.0.0"), s)
s = policy.status("1.8.0.0.0")
check("one update behind: not blocked", not s["blocked"] and s["behind"] == 1, s)
check("on the newest: not behind", policy.status("1.9.0.0.0")["behind"] == 0 and policy.status("1.9.0.0")["behind"] == 0)
check("a beta that is newer than every stable version is never behind", not policy.status("1.9.1.1.1")["blocked"] and policy.status("1.9.1.1.1")["behind"] == 0)
check("old three-number versions compare as five (1.8.0 = 1.8.0.0.0)", policy.status("1.8.0")["behind"] == 1)
check("...far behind: 1.0.0", policy.status("1.0.0")["blocked"] and policy.status("1.0.0")["behind"] == 2)
check("the same list again changes nothing", publish(STABLE, 1) is False)
served["policy.json"] = served["policy.json"].replace(b"1.8.0.0.0", b"1.0.0.0.0")
check("a tampered policy is refused and the old one stays", policy.refresh(get=fake_get) is None and policy.status("1.7.0")["blocked"])
check("an older policy is not taken back", publish(["1.8.0.0.0"], 0) is False and policy.status("1.7.0")["blocked"])
served.clear()
check("no network changes nothing (the last good policy still applies offline)", policy.refresh(get=fake_get) is None and policy.status("1.7.0")["blocked"])
check("the limit comes from the policy: with 3, two updates behind is fine", publish(STABLE, 2, limit=3) is True and not policy.status("1.7.0")["blocked"])
check("...and 1 locks even one update behind", publish(STABLE, 3, limit=1) is True and policy.status("1.8.0.0.0")["blocked"] and not policy.status("1.9.0.0.0")["blocked"])
publish(STABLE, 4, limit=2)

# ---------------------------------------------------------------- the channels count their own updates
BETAS = STABLE + ["1.9.1.0.0", "1.9.2.0.0", "1.9.3.0.0"]


def publish_beta(beta, serial, stable=STABLE):
    obj = {"serial": serial, "limit": 2, "stable": stable}
    if beta is not None:
        obj["beta"] = beta
    data, sig = sign(obj)
    served.clear()
    served.update({"policy.json": data, "policy.json.sig": sig.encode()})
    return policy.refresh(get=fake_get, channel="beta")


check("the Stable channel reads the release branch and the Beta channel the beta branch", policy.BASES["stable"].endswith("/release/dist/") and policy.BASES["beta"].endswith("/beta/dist/")
      and policy.BASES["beta"].replace("/beta/", "/release/") == policy.BASES["stable"])
check("a beta policy is stored on its own (serial 1 is accepted although the stable one is further on)", publish_beta(BETAS, 1) is True and policy.load("beta")[0] == 1 and policy.load("stable")[0] == 4)
check("...in its own file", (tmp / "state" / "policy.cache.beta.json").exists() and (tmp / "state" / "policy.cache.json").exists())
check("the Stable channel ignores the beta list: 1.9.0.0.0 is the newest stable, so nobody on stable is behind", policy.status("1.9.0.0.0", "stable")["behind"] == 0 and not policy.status("1.9.0.0.0", "stable")["blocked"])
sb = policy.status("1.9.0.0.0", "beta")
check("the Beta channel counts every release: 1.9.0.0.0 has three newer ones, so it is blocked and told the newest", sb["blocked"] and sb["behind"] == 3 and sb["latest"] == "1.9.3.0.0", sb)
check("...one behind is fine, and the newest is not behind", not policy.status("1.9.2.0.0", "beta")["blocked"] and policy.status("1.9.2.0.0", "beta")["behind"] == 1 and policy.status("1.9.3.0.0", "beta")["behind"] == 0)
check("...exactly two behind is blocked", policy.status("1.9.1.0.0", "beta")["blocked"] and policy.status("1.9.1.0.0", "beta")["behind"] == 2)
check("a version newer than every release is never behind", policy.status("1.9.9.0.0", "beta")["behind"] == 0)
check("a beta policy without a beta list counts the stable one", publish_beta(None, 2) is True and policy.status("1.7.0", "beta")["behind"] == 2 and policy.status("1.9.0.0.0", "beta")["behind"] == 0)
publish_beta(BETAS, 3)
def set_channel(name):
    cfg = updater.load_config()
    cfg["channel"] = name
    updater.save_config(cfg)


set_channel("beta")
check("the channel is read from the app's settings: a beta app uses the beta list", policy.current_channel() == "beta" and policy.status("1.9.0.0.0")["blocked"] and policy.status("1.9.0.0.0")["behind"] == 3)
set_channel("stable")
check("...and back on stable it does not", policy.current_channel() == "stable" and not policy.status("1.9.0.0.0")["blocked"])
bad = sign({"serial": 9, "stable": STABLE, "beta": ["x"]})
served.clear(); served.update({"policy.json": bad[0], "policy.json.sig": bad[1].encode()})
check("a beta list with something that is not a version is refused", policy.refresh(get=fake_get, channel="beta") is None and policy.load("beta")[0] == 3)
publish(STABLE, 4, limit=2)

# ---------------------------------------------------------------- the window
w = MainWindow(rbx.Client(), auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
w.ctx.client.user = {"id": 5, "name": "me", "displayName": "Me"}
check("the installed version is read from the app folder", updater.version() == "1.7.0" and policy.status()["blocked"])
check("before the policy is applied the app is normal", w.stack.currentIndex() == 0 and not w.locked)
check("the policy locks the window: the update page covers everything", w.enforce_policy() is True and w.stack.currentIndex() == 1 and w.locked and w.lock_page.isVisible() and not w.tabs.isVisible())
check("...it says which version this is, how far behind, and the newest", "1.7.0" in w.lock_page.text.text() and "2 updates behind" in w.lock_page.text.text() and "1.9.0.0" in w.lock_page.text.text(), w.lock_page.text.text())
check("...nothing is lost: the account is still there (no logout)", w.ctx.client.user and w.ctx.client.user["id"] == 5 and "saved accounts" in w.lock_page.text.text())
QTest.keyClick(w, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier); spin(0.1)
QTest.keyClick(w, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier); spin(0.1)
w.open_search(); spin(0.1)
check("...and nothing else can be used: no search, no shortcuts", not w.palette_box.isVisible() and w.tabs.currentIndex() == 0 and not any(s.isEnabled() for s in w._shortcuts))
check("...the page has an Update now button and a download page button", w.lock_page.b_update.isVisible() and w.lock_page.b_update.text() == "Update now" and w.lock_page.b_page.isVisible())
opened = []
update_required.open_url = lambda url: opened.append(url)
w.lock_page.b_page.click()
check("the download page button opens the releases page", opened == [policy.RELEASES_URL] and "github.com/AO-Miko/roblox-manager/releases" in opened[0], opened)

updater.apply = lambda cfg=None: {"status": "error", "message": "could not reach the update server"}
w.lock_page.b_update.click()
check("an update that fails says why and the button works again", wait(lambda: "could not reach" in w.lock_page.status.text() and w.lock_page.b_update.isEnabled()), w.lock_page.status.text())
updater.apply = lambda cfg=None: {"status": "refused", "message": "the newest version is not signed with a key you trust, so it was NOT installed"}
w.lock_page.b_update.click()
check("a refused update says so", wait(lambda: "NOT installed" in w.lock_page.status.text() and w.lock_page.b_update.isEnabled()))
updater.apply = lambda cfg=None: {"status": "updated", "version": "1.9.0.0.0", "message": "Updated to version 1.9.0.0.0. Restart the app to use it."}
restarted = []
w.lock_page.restart = lambda: restarted.append(1)
w.lock_page.b_update.click()
check("a successful update offers Restart now", wait(lambda: w.lock_page.b_restart.isVisible() and not w.lock_page.b_update.isVisible()) and "Updated to version 1.9.0.0.0" in w.lock_page.status.text())
w.lock_page.b_restart.click()
check("...which restarts the app", restarted == [1])

# the new version is not behind: the lock is gone (also after a new policy)
(tmp / "app" / "VERSION").write_text("1.9.0.0.0\n")
check("once updated (or on a newer policy) the window is free again", w.enforce_policy() is False and w.stack.currentIndex() == 0 and all(s.isEnabled() for s in w._shortcuts))
QTest.keyClick(w, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier); spin(0.1)
check("...and works as before", w.tabs.currentIndex() == 1)
(tmp / "app" / "VERSION").write_text("1.7.0\n")
publish(STABLE, 5, limit=3)
check("a policy that loosens the limit unlocks it", w.enforce_policy() is False and w.stack.currentIndex() == 0)
publish(STABLE, 6, limit=2)
check("...and a stricter one locks it again", w.enforce_policy() is True and w.stack.currentIndex() == 1)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
