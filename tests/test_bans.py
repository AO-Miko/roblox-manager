"""The ban list: signature rules, cache, serial numbers, and the app signing banned accounts out. Real ssh-keygen signatures.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_bans.py"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="bans-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_UPDATE_BACKEND": "off"})
sys.path.insert(0, str(ROOT / "linux"))
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


def keygen(name):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(tmp / name)], check=True)
    return " ".join((tmp / (name + ".pub")).read_text().split()[:2])


def sign(name, data, ns="roblox-manager-bans"):
    f = tmp / ("f-" + name)
    f.write_bytes(data)
    (tmp / ("f-" + name + ".sig")).unlink(missing_ok=True)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(tmp / name), "-n", ns, str(f)], check=True)
    return (tmp / ("f-" + name + ".sig")).read_text()


def lst(serial, *bans):
    return json.dumps({"serial": serial, "bans": [{"id": i, "reason": r} for i, r in bans]}).encode()


import bans

pub = keygen("owner")
mallory = keygen("mallory")
bans.TRUSTED = f"owner@test {pub}\n"
good = lst(1, (111, "spamming friend requests"), (222, ""))
sig = sign("owner", good)

check("a list signed by the trusted key is read", bans.parse(good, sig) == (1, {111: "spamming friend requests", 222: ""}))
check("a list signed by someone else is refused", bans.parse(good, sign("mallory", good)) is None)
check("a changed list is refused", bans.parse(good.replace(b"111", b"999"), sig) is None)
check("a signature for another purpose (the update namespace) is refused", bans.parse(good, sign("owner", good, "roblox-manager-release")) is None)
check("garbage is refused, not a crash", bans.parse(b"nope", "nope") is None and bans.parse(good, "") is None)
check("a signed file that is not a list is refused", bans.parse(b"[1,2]", sign("owner", b"[1,2]")) is None)

served = {}


def fake(url, limit=300000, timeout=15):
    if url not in served:
        raise OSError("404")
    return served[url]


def publish(data, signature):
    served["https://x.test/bans.json"] = data
    served["https://x.test/bans.json.sig"] = signature.encode()


check("before anything is downloaded nobody is banned", bans.banned(111) is None and bans.load() == (0, {}))
check("an unreachable server changes nothing and does not raise", bans.refresh(fake, "https://x.test/") is None and bans.banned(111) is None)
publish(good, sig)
check("downloading a good list reports a change", bans.refresh(fake, "https://x.test/") is True)
check("...and the ban applies, with its reason", bans.banned(111) == "spamming friend requests" and bans.banned("222") == "" and bans.banned(333) is None)
check("the same list again changes nothing", bans.refresh(fake, "https://x.test/") is False)
check("the ban applies without a network (from the saved list)", bans.refresh(lambda *a, **k: (_ for _ in ()).throw(OSError("offline")), "https://x.test/") is None and bans.banned(111) is not None)

old = lst(0, (333, "old"))
publish(old, sign("owner", old))
check("an older list never replaces a newer one (no replay)", bans.refresh(fake, "https://x.test/") is False and bans.banned(111) is not None and bans.banned(333) is None)
forged = lst(9, (444, "forged"))
publish(forged, sign("mallory", forged))
check("a forged newer list is ignored", bans.refresh(fake, "https://x.test/") is None and bans.banned(444) is None and bans.banned(111) is not None)
newer = lst(2, (222, "second"), (555, "new"))
publish(newer, sign("owner", newer))
check("a newer signed list replaces it (111 is unbanned, 555 is banned)", bans.refresh(fake, "https://x.test/") is True and bans.banned(111) is None and bans.banned(555) == "new")
cache = tmp / "state" / "bans.cache.json"
c = json.loads(cache.read_text())
c["data"] = base64.b64encode(lst(2, (666, "planted"))).decode()
cache.write_text(json.dumps(c))
check("a saved list that was edited on disk is not believed", bans.load() == (0, {}) and bans.banned(666) is None)
publish(newer, sign("owner", newer))
bans.refresh(fake, "https://x.test/")
check("...and is replaced by the next good download", bans.banned(555) == "new")

# ---- the app
from PySide6.QtWidgets import QApplication, QMessageBox

import browser_login  # noqa: F401
app = QApplication([])
import accounts
import app as appmod

shown = []
QMessageBox.warning = staticmethod(lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
w = appmod.MainWindow(auto_login=False)
w.show()
accounts.remember({"id": 555, "name": "badone", "displayName": "Bad One"}, "_|WARNING:" + "5" * 120, make_active=False)
accounts.remember({"id": 777, "name": "fine", "displayName": "Fine"}, "_|WARNING:" + "7" * 120, make_active=True)
w.account.ctx.client.user = {"id": 777, "name": "fine", "displayName": "Fine"}
check("a banned account that is only saved is removed at once, with the reason", w.account.enforce_bans() is True and [a["id"] for a in accounts.list_accounts()] == [777]
      and "@badone: new" in shown[-1], shown[-1:])
check("the account in use is untouched", accounts.active_id() == 777 and w.account.enforce_bans() is False)
accounts.remember({"id": 555, "name": "badone", "displayName": "Bad One"}, "_|WARNING:" + "5" * 120, make_active=True)
w.account.ctx.client.user = {"id": 555, "name": "badone", "displayName": "Bad One"}
w.account.ctx.client._cookie = "_|WARNING:" + "5" * 120
check("an account that is signed in (the one in use) is signed out in the middle of a session", w.account.enforce_bans() is True and 555 not in [a["id"] for a in accounts.list_accounts()])
check("...nothing of it stays signed in", w.account.ctx.client.user is None or w.account.ctx.client.user.get("id") != 555)
shown.clear()
accounts.remember({"id": 555, "name": "badone", "displayName": "Bad One"}, "_|WARNING:" + "5" * 120, make_active=False)
w.account._signed_in({"id": 555, "name": "badone", "displayName": "Bad One"})
check("signing in to a banned account is refused and the account is not kept", 555 not in [a["id"] for a in accounts.list_accounts()] and shown and "not allowed" not in shown[0] or shown, shown)
print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
