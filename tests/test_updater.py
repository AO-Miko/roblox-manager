"""Tests for linux/updater.py with a throw-away update server. Run: python3 tests/test_updater.py"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linux"))
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


base = Path(tempfile.mkdtemp(prefix="updtest-"))


def sh(*a, cwd=None):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{a}: {r.stderr}")
    return r.stdout.strip()


def keygen(name):
    k = base / name
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(k))
    return k


good, evil = keygen("good"), keygen("evil")
signers = base / "allowed_signers"
signers.write_text('release@test namespaces="git" ' + " ".join(open(str(good) + ".pub").read().split()[:2]) + "\n")

server = base / "server.git"
sh("git", "init", "-q", "--bare", "-b", "release", str(server))
dev = base / "dev"
sh("git", "clone", "-q", str(server), str(dev))


def conf(key):
    for k, v in (("user.name", "t"), ("user.email", "release@test"), ("gpg.format", "ssh"), ("user.signingkey", str(key) + ".pub"), ("commit.gpgsign", "true")):
        sh("git", "config", k, v, cwd=dev)


conf(good)


def release(version, app="print('hi')\n", extra=None, key=None, sign=True, message=None):
    d = dev / "linux"
    d.mkdir(exist_ok=True)
    (d / "app.py").write_text(app)
    (d / "VERSION").write_text(version + "\n")
    for n, t in (extra or {}).items():
        (d / n).write_text(t)
    sh("git", "add", "-A", cwd=dev)
    if key:
        conf(key)
    sh("git", "-c", f"commit.gpgsign={'true' if sign else 'false'}", "commit", "-q", "-m", message or f"release {version}", cwd=dev)
    if key:
        conf(good)
    sh("git", "push", "-q", "-f", "origin", "release", cwd=dev)         # (forced: the tests rewind their own throw-away server)
    return sh("git", "rev-parse", "HEAD", cwd=dev)


def setup_install(commit_sha, version="1.0.0"):
    """A fresh installed app and a config pointing at the test server."""
    home = Path(tempfile.mkdtemp(dir=base))
    app = home / "share" / "roblox-manager"
    app.mkdir(parents=True)
    (app / "app.py").write_text("print('v1')\n")
    (app / "VERSION").write_text(version + "\n")
    (app / ".installed.json").write_text(json.dumps({"commit": commit_sha, "version": version}))
    cfgd = home / "config"
    cfgd.mkdir()
    shutil.copy(signers, cfgd / "trusted_signers")
    (cfgd / "update.json").write_text(json.dumps({"repo": str(server), "branch": "release", "auto": True, "require_signature": True}))
    os.environ.update({"ROBLOX_MANAGER_APP_DIR": str(app), "ROBLOX_MANAGER_CONFIG": str(cfgd), "ROBLOX_MANAGER_STATE": str(home / "state"),
                       "ROBLOX_MANAGER_UPDATE_CACHE": str(home / "cache")})
    import updater
    importlib.reload(updater)
    return updater, app, home


v1 = release("1.0.0")
u, app, home = setup_install(v1)
r = u.check()
check("when the installed commit is the newest, it says up to date", r["status"] == "up-to-date", r)
r = u.apply()
check("...and applying does nothing", r["status"] == "up-to-date" and (app / "VERSION").read_text().strip() == "1.0.0")

v2 = release("1.1.0", app="print('v2')\n", extra={"new_module.py": "X = 1\n"})
r = u.check()
check("a newer commit on the server is noticed", r["status"] == "available" and r["remote"] == v2, r)
r = u.apply()
check("a newer commit signed by the trusted key is installed", r["status"] == "updated" and r["version"] == "1.1.0" and (app / "app.py").read_text() == "print('v2')\n" and (app / "new_module.py").exists(), r)
check("...the marker records the new commit and the signer is reported", u.installed()["commit"] == v2 and r["signer"] == "release@test", (u.installed(), r.get("signer")))
check("...the old version is kept as .previous", (app.with_name("roblox-manager.previous") / "app.py").read_text() == "print('v1')\n")
check("...checking again says up to date", u.check()["status"] == "up-to-date")
r = u.rollback()
check("rolling back puts the previous version back", r["status"] == "rolled-back" and (app / "app.py").read_text() == "print('v1')\n", r)
r = u.rollback()
check("...and rolling back again returns to the newer one", (app / "app.py").read_text() == "print('v2')\n")
u.MARKER.write_text(json.dumps({"commit": v2, "version": "1.1.0"}))

# ---- refusals
v3 = release("1.2.0", app="print('unsigned')\n", sign=False)
r = u.apply()
check("an UNSIGNED newer commit is refused", r["status"] == "refused" and "not signed" in r["message"] and (app / "app.py").read_text() == "print('v2')\n", r)
v4 = release("1.3.0", app="print('evil')\n", key=evil)
r = u.apply()
check("a commit signed with a key that is not trusted is refused", r["status"] == "refused" and "not signed with a key you trust" in r["message"] and (app / "app.py").read_text() == "print('v2')\n", r)
check("...the refusals are written to the update log", "refused" in u.LOG_FILE.read_text())
# the server goes back to a trusted commit that is NOT a continuation (a rollback attack)
sh("git", "checkout", "-q", "-b", "other", v1, cwd=dev)
(dev / "linux" / "VERSION").write_text("0.9.0\n")
sh("git", "add", "-A", cwd=dev)
sh("git", "commit", "-q", "-m", "old but signed", cwd=dev)
sh("git", "push", "-q", "-f", "origin", "other:release", cwd=dev)
r = u.apply()
check("a signed commit that does not continue what is installed (a step back) is refused", r["status"] == "refused" and "step back" in r["message"] and (app / "app.py").read_text() == "print('v2')\n", r)
sh("git", "checkout", "-q", "release", cwd=dev)
sh("git", "reset", "-q", "--hard", v2, cwd=dev)
v5 = release("1.4.0", app="def broken(:\n")
r = u.apply()
check("a signed update whose Python does not even compile is refused, and the app is unchanged", r["status"] == "refused" and "broken file" in r["message"] and (app / "app.py").read_text() == "print('v2')\n", r)
sh("git", "reset", "-q", "--hard", v2, cwd=dev)
v6 = release("1.5.0", app="print('v6')\n", message="fixed")
r = u.apply()
check("after a refused update, the next good signed one is installed normally", r["status"] == "updated" and (app / "app.py").read_text() == "print('v6')\n", r)
leftover = [p.name for p in app.parent.iterdir()]
check("no half-unpacked folders are left behind", not [n for n in leftover if ".new-" in n], leftover)

# ---- trust file missing, and signatures not required
(Path(os.environ["ROBLOX_MANAGER_CONFIG"]) / "trusted_signers").unlink()
v7 = release("1.6.0", app="print('v7')\n")
r = u.apply()
check("with no trusted keys at all, nothing is installed", r["status"] == "refused", r)
cfg = u.load_config()
cfg["require_signature"] = False
u.save_config(cfg)
r = u.apply()
check("(only if you switch the signature requirement off) the update installs", r["status"] == "updated" and (app / "app.py").read_text() == "print('v7')\n", r)

# ---- offline and not set up
cfg = u.load_config()
cfg["repo"] = str(base / "does-not-exist.git")
u.save_config(cfg)
t0 = time.time()
r = u.check()
check("an unreachable server is reported, quickly, without a crash", r["status"] == "error" and time.time() - t0 < 10, (r, round(time.time() - t0, 1)))
u.boot()
check("boot() never raises when the server is unreachable", True)
cfg["repo"] = ""
u.save_config(cfg)
check("with no server set, updating is disabled", u.check()["status"] == "disabled")

# ---- boot()
cfg["repo"] = str(server)
cfg["require_signature"] = True
u.save_config(cfg)
shutil.copy(signers, Path(os.environ["ROBLOX_MANAGER_CONFIG"]) / "trusted_signers")
u.MARKER.write_text(json.dumps({"commit": v6, "version": "1.5.0"}))
sh("git", "reset", "-q", "--hard", v7, cwd=dev)
v8 = release("1.7.0", app="print('v8')\n")
u.boot()
check("boot() installs a newer trusted version by itself", (app / "app.py").read_text() == "print('v8')\n" and u.installed()["version"] == "1.7.0")
cfg["auto"] = False
u.save_config(cfg)
v9 = release("1.8.0", app="print('v9')\n")
u.boot()
check("with automatic updates off, boot() leaves everything as it is", (app / "app.py").read_text() == "print('v8')\n")
print("\n%d/%d checks passed" % (sum(res), len(res)))
shutil.rmtree(base, ignore_errors=True)
