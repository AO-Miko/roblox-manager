"""Test of the update channels (stable / beta) in linux/updater.py, with a throw-away git server and a fake GitHub. Run: python3 tests/test_channels.py"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linux"))
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


base = Path(tempfile.mkdtemp(prefix="chan-"))


def sh(*a, cwd=None):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{a}: {r.stderr}")
    return r.stdout.strip()


key = base / "good"
sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "good", "-f", str(key))
signers = base / "allowed_signers"
signers.write_text('release@test namespaces="git" ' + " ".join(open(str(key) + ".pub").read().split()[:2]) + "\n")
server = base / "server.git"
sh("git", "init", "-q", "--bare", "-b", "release", str(server))
dev = base / "dev"
sh("git", "clone", "-q", str(server), str(dev))
for k, v in (("user.name", "t"), ("user.email", "release@test"), ("gpg.format", "ssh"), ("user.signingkey", str(key) + ".pub"), ("commit.gpgsign", "true")):
    sh("git", "config", k, v, cwd=dev)


def commit(version, branch):
    d = dev / "linux"
    d.mkdir(exist_ok=True)
    (d / "app.py").write_text(f"print('{version}')\n")
    (d / "VERSION").write_text(version + "\n")
    sh("git", "add", "-A", cwd=dev)
    sh("git", "commit", "-q", "-m", f"release {version}", cwd=dev)
    sh("git", "push", "-q", "origin", branch, cwd=dev)
    return sh("git", "rev-parse", "HEAD", cwd=dev)


stable1 = commit("1.0.0.0.0", "release")
sh("git", "checkout", "-q", "-b", "beta", cwd=dev)
beta1 = commit("1.1.0.0.0", "beta")
home = Path(tempfile.mkdtemp(dir=base))
app = home / "share" / "roblox-manager"
app.mkdir(parents=True)
(app / "app.py").write_text("print('installed')\n")
(app / "VERSION").write_text("1.0.0.0.0\n")
(app / ".installed.json").write_text(json.dumps({"commit": stable1, "version": "1.0.0.0.0"}))
cfgd = home / "config"
cfgd.mkdir()
shutil.copy(signers, cfgd / "trusted_signers")
os.environ.update({"ROBLOX_MANAGER_APP_DIR": str(app), "ROBLOX_MANAGER_CONFIG": str(cfgd), "ROBLOX_MANAGER_STATE": str(home / "state"),
                   "ROBLOX_MANAGER_UPDATE_CACHE": str(home / "cache")})
import updater
importlib.reload(updater)


def write_cfg(**kw):
    c = {"repo": str(server), "branch": "release", "auto": True, "require_signature": True}
    c.update(kw)
    (cfgd / "update.json").write_text(json.dumps(c))
    return updater.load_config()


# ---------------------------------------------------------------- the setting
check("the default channel is stable", write_cfg()["channel"] == "stable" and updater.branch_of(updater.load_config()) == "release")
check("a channel that does not exist becomes stable", write_cfg(channel="nightly")["channel"] == "stable")
check("beta follows the beta branch, stable the configured branch", updater.branch_of(write_cfg(channel="beta")) == "beta" and updater.branch_of(write_cfg(channel="stable", branch="main")) == "main")
updater.save_config(dict(updater.load_config(), channel="beta"))
check("the channel is saved", json.loads((cfgd / "update.json").read_text())["channel"] == "beta")

# ---------------------------------------------------------------- git backend (Linux)
updater.plat.update_backend = lambda: "git"            # (Windows would use the release backend; this part tests the git one)
cfg = write_cfg(channel="stable")
check("stable: the installed commit is the newest on release", updater.check(cfg)["status"] == "up-to-date")
cfg = write_cfg(channel="beta")
r = updater.check(cfg)
check("beta: a newer version is waiting on the beta branch", r["status"] == "available" and r["remote"] == beta1, r)
r = updater.apply(cfg)
check("beta: the update is installed (signed commit, continues the stable one)", r["status"] == "updated" and (app / "VERSION").read_text().strip() == "1.1.0.0.0", r)
cfg = write_cfg(channel="stable")
r = updater.apply(cfg)
check("back on stable: nothing is installed, the newer version is kept (the numbers never go down)",
      r["status"] == "up-to-date" and (app / "VERSION").read_text().strip() == "1.1.0.0.0" and "newer" in r["message"], r)
stable2 = None
sh("git", "checkout", "-q", "release", cwd=dev)
stable2 = commit("1.1.0.0.0", "release")
sh("git", "checkout", "-q", "beta", cwd=dev)
sh("git", "merge", "-q", "--no-edit", "release", cwd=dev)
check("(the stable branch catches up later: the same version is already installed)", updater.check(updater.load_config())["status"] in ("available", "up-to-date"))

# ---------------------------------------------------------------- release backend (Windows): a fake GitHub
updater.plat.update_backend = lambda: "release"
sent = []


def release_json(tag, prerelease=False, draft=False, package=True):
    ver = tag.lstrip("v")
    assets = []
    if package:
        assets = [{"name": f"roblox-manager-app-{ver}.tar.gz", "browser_download_url": f"https://x.test/{ver}.tar.gz"},
                  {"name": f"roblox-manager-app-{ver}.tar.gz.sig", "browser_download_url": f"https://x.test/{ver}.sig"}]
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets}


github = {"latest": release_json("v1.8.0.0.0"),
          "list": [release_json("v1.9.0.0.0", prerelease=True), release_json("v1.8.0.0.0"), release_json("v2.0.0.0.0", prerelease=True, draft=True),
                   release_json("v1.10.0.0.0", prerelease=True, package=False)]}


def fake_http(url, limit=0, timeout=0):
    sent.append(url)
    return json.dumps(github["latest"] if url.endswith("/latest") else github["list"]).encode()


updater._http_get = fake_http
rcfg = write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="stable")
rel = updater.release_latest(rcfg)
check("stable: the release GitHub calls latest, with its five-number version", rel["version"] == "1.8.0.0.0" and sent[-1].endswith("/releases/latest"), rel)
rcfg = write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="beta")
rel = updater.release_latest(rcfg)
check("beta: the highest version of all releases, pre-releases included (drafts and releases without a package are skipped)",
      rel["version"] == "1.9.0.0.0" and rel["prerelease"] and "per_page" in sent[-1], rel)
github["list"] = [release_json("v1.8.0.0.0"), release_json("v1.8.1.0.0")]
check("beta: a stable release that is newer than every pre-release is used too", updater.release_latest(rcfg)["version"] == "1.8.1.0.0")
github["list"] = [release_json("v1.9.0.0.0", package=False)]
try:
    updater.release_latest(rcfg)
    ok = False
except updater.UpdateError as e:
    ok = "no beta release" in str(e)
check("beta: no usable release says so", ok)
github["latest"] = release_json("v1.8.0.0.0", package=False)
try:
    updater.release_latest(write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="stable"))
    ok = False
except updater.UpdateError as e:
    ok = "no signed update package" in str(e)
check("stable: a latest release without a package says so", ok)
for tag, usable in (("v1.8.0.0.0", True), ("v1.8.0.0", True), ("v1.8.0", True), ("v1.8.0.0.0.0", False), ("beta-1", False), ("v1", False)):
    check(f"release tag {tag}: {'usable' if usable else 'not usable'} (up to five numbers)", (updater._release_info(release_json(tag)) is not None) == usable)
check("the update bridge for older Windows installs: 1.9.0.0 is the same version as 1.9.0.0.0", updater.version_key("1.9.0.0") == updater.version_key("1.9.0.0.0"))


# ---- the messages say which channel they are about (so "nothing newer on Beta" is not mistaken for a broken check)
github["latest"] = release_json("v1.8.0.0.0")
github["list"] = [release_json("v1.8.0.0.0"), release_json("v1.7.0")]
(app / "VERSION").write_text("1.8.0.0.0\n")
write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="stable")
r = updater.check()
check("stable, up to date: the message names the version and the channel", r["status"] == "up-to-date" and "(1.8.0.0.0)" in r["message"] and "Stable channel" in r["message"], r["message"])
write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="beta")
r = updater.check()
check("beta with nothing newer than stable says so instead of just 'newest'", r["status"] == "up-to-date" and "Beta channel" in r["message"] and "No beta is newer than the stable version" in r["message"], r["message"])
github["list"] = [release_json("v1.9.0.0.0", prerelease=True), release_json("v1.8.0.0.0")]
r = updater.check()
check("beta with a newer pre-release: available, and the message names the version and the channel", r["status"] == "available" and "1.9.0.0.0" in r["message"] and "Beta channel" in r["message"] and r["release"]["prerelease"], r)
write_cfg(repo="https://github.com/AO-Miko/roblox-manager", channel="stable")
r = updater.check()
check("the same list on stable: the pre-release is not offered", r["status"] == "up-to-date" and "Stable channel" in r["message"], r["message"])
print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
