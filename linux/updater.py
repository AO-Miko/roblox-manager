#!/usr/bin/env python3
"""Keeps the app up to date from its git repository.

At every start the launcher runs `updater.py --boot`. It asks the repository for the newest commit; if there is one, it is fetched and
applied ONLY if all of this is true:
  * the commit is signed with a key you trust (~/.config/roblox-manager/trusted_signers, created when the app was installed and never
    changed by an update), so nobody who merely gets write access to the repository can run code on this PC;
  * it continues the installed version (no going back to an older, possibly vulnerable one);
  * the new files are only the `linux/` folder of the repository, are unpacked safely, and every Python file in them at least compiles.
The previous version is kept next to the app, so `--rollback` can put it back. Nothing here ever stops the app from starting: any
problem is written to update.log and the installed version is used as it is.

  updater.py --boot       check and apply quietly (used by the launcher)
  updater.py --check      only say whether there is an update
  updater.py --apply      check and apply, print the result
  updater.py --rollback   go back to the previous version
  updater.py --status     print what is installed, as JSON
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))        # (python -I does not add the script's own folder)
import plat

APP_DIR = Path(os.environ.get("ROBLOX_MANAGER_APP_DIR") or Path(__file__).resolve().parent)
CONFIG_DIR = plat.config_dir()
STATE_DIR = plat.state_dir()
CACHE_DIR = plat.cache_dir()
RELEASE_NAMESPACE = "roblox-manager-release"     # what the release packages are signed for (see tools/release.sh)
API = "https://api.github.com"
CONFIG_FILE = CONFIG_DIR / "update.json"
TRUST_FILE = CONFIG_DIR / "trusted_signers"
MARKER = APP_DIR / ".installed.json"
LOG_FILE = STATE_DIR / "update.log"
SUBDIR = "linux"                        # the folder of the repository that is the desktop app
MAX_BYTES = 60 * 1024 * 1024            # an update larger than this is refused
GIT_TIMEOUT = 25
DEFAULTS = {"repo": "", "branch": "release", "auto": True, "require_signature": True, "channel": "stable"}
CHANNELS = ("stable", "beta")           # beta: the `beta` branch / GitHub pre-releases, which get every update before it goes to stable
BETA_BRANCH = "beta"


class UpdateError(Exception):
    """Something is wrong with an update; str() says what, in plain words."""


# ------------------------------------------------------------------ settings and state
def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update({k: v for k, v in json.loads(CONFIG_FILE.read_text()).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if cfg.get("channel") not in CHANNELS:
        cfg["channel"] = "stable"
    return cfg


def branch_of(cfg):
    """The branch to follow: `beta` on the beta channel, otherwise the configured branch (release)."""
    return BETA_BRANCH if cfg.get("channel") == "beta" else cfg["branch"]


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {k: cfg[k] for k in DEFAULTS if k in cfg}
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(CONFIG_FILE)


def installed():
    try:
        return json.loads(MARKER.read_text())
    except (OSError, ValueError):
        return {}


def version():
    try:
        return (APP_DIR / "VERSION").read_text().strip()
    except OSError:
        return "unknown"


def log(message):
    if os.environ.get("ROBLOX_MANAGER_DEBUG"):
        print("update:", message, file=sys.stderr)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        if LOG_FILE.stat().st_size > 200_000:                    # keep it small
            LOG_FILE.write_text("".join(LOG_FILE.read_text().splitlines(True)[-300:]))
    except OSError:
        pass


# ------------------------------------------------------------------ git
def _git(*args, cwd=None, timeout=GIT_TIMEOUT):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="true", LC_ALL="C",
               GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new")
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError:
        raise UpdateError("git is not installed")
    except subprocess.TimeoutExpired:
        raise UpdateError("the update server did not answer in time")
    return r


def _last_line(r):
    lines = (r.stderr.strip() or r.stdout.strip()).splitlines()
    return (lines[-1] if lines else "unknown error")[:160]


def remote_head(cfg):
    """The newest commit of the configured branch on the server."""
    if not cfg["repo"]:
        raise UpdateError("no update server is set")
    r = _git("ls-remote", "--", cfg["repo"], f"refs/heads/{branch_of(cfg)}")
    if r.returncode != 0:
        raise UpdateError("could not reach the update server: " + _last_line(r))
    line = r.stdout.strip().split("\n")[0].split()
    if not line or len(line[0]) < 40:
        raise UpdateError(f"the update server has no branch '{branch_of(cfg)}'")
    return line[0]


def _fetch(cfg, sha):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not (CACHE_DIR / "HEAD").exists():
        _git("init", "--bare", "-q", str(CACHE_DIR))
    r = _git("fetch", "--quiet", "--no-tags", "--", cfg["repo"], f"+refs/heads/{branch_of(cfg)}:refs/remotes/update/{branch_of(cfg)}", cwd=CACHE_DIR, timeout=120)
    if r.returncode != 0:
        raise UpdateError("could not download the update: " + _last_line(r))
    if _git("cat-file", "-e", f"{sha}^{{commit}}", cwd=CACHE_DIR).returncode != 0:
        raise UpdateError("the server changed while updating; it will be tried again next time")


def signer_of(sha):
    """Who signed this commit, if it is signed by a trusted key; None if not."""
    if not TRUST_FILE.exists() or TRUST_FILE.stat().st_size == 0:
        return None
    r = _git("-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={TRUST_FILE}", "verify-commit", sha, cwd=CACHE_DIR)
    text = r.stderr + r.stdout
    if r.returncode == 0 and "Good" in text:
        for line in text.splitlines():
            if "Good" in line and " for " in line:                  # Good "git" signature for release@host with ED25519 key SHA256:...
                return line.split(" for ", 1)[1].split(" with ")[0].strip() or "trusted key"
        return "trusted key"
    return None


def is_continuation(old, new):
    if not old:
        return True                                        # nothing recorded yet (first update of an older install)
    if _git("cat-file", "-e", f"{old}^{{commit}}", cwd=CACHE_DIR).returncode != 0:
        return False
    return _git("merge-base", "--is-ancestor", old, new, cwd=CACHE_DIR).returncode == 0


# ------------------------------------------------------------------ unpacking and checking
def _export(sha, dest):
    """The linux/ folder of a commit, unpacked into dest with no links, no odd paths and a size limit."""
    r = subprocess.run(["git", "archive", "--format=tar", sha, SUBDIR], cwd=CACHE_DIR, capture_output=True, timeout=120)
    if r.returncode != 0 or not r.stdout:
        raise UpdateError(f"the update has no '{SUBDIR}' folder")
    _unpack(r.stdout, dest)


def _unpack(data, dest):
    """Unpack a tar (or tar.gz) of the linux/ folder into dest with no links, no odd paths and a size limit."""
    if len(data) > MAX_BYTES:
        raise UpdateError("the update is unexpectedly large")
    fd, name = tempfile.mkstemp(suffix=".tar")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        with tarfile.open(tmp) as tf:
            total, members = 0, []
            for m in tf.getmembers():
                p = Path(m.name)
                if not p.parts or p.parts[0] != SUBDIR or ".." in p.parts or p.is_absolute():
                    raise UpdateError("the update contains a file in a place it should not")
                if m.issym() or m.islnk() or m.isdev():
                    raise UpdateError("the update contains a link or device file, which is not allowed")
                total += m.size
                if len(p.parts) > 1:
                    m.name = str(Path(*p.parts[1:]))              # linux/app.py -> app.py
                    members.append(m)
            if total > MAX_BYTES:
                raise UpdateError("the update is unexpectedly large")
            tf.extractall(dest, members=members, filter="data")
    finally:
        tmp.unlink(missing_ok=True)


def _validate(dest):
    if not (dest / "app.py").is_file():
        raise UpdateError("the update does not contain the app")
    if not (dest / "VERSION").is_file():
        raise UpdateError("the update has no version")
    for py in dest.rglob("*.py"):
        try:
            compile(py.read_bytes(), str(py), "exec", dont_inherit=True)       # only checks the syntax: nothing is run or written
        except (SyntaxError, ValueError) as e:
            raise UpdateError(f"the update has a broken file ({py.name}): {str(e)[:120]}")


def _swap(dest, sha):
    """Put the new folder in place of the app; the old one becomes .previous (one generation is kept)."""
    previous = APP_DIR.with_name(APP_DIR.name + ".previous")
    marker = {"commit": sha, "version": (dest / "VERSION").read_text().strip(), "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    (dest / ".installed.json").write_text(json.dumps(marker))
    if previous.exists():
        shutil.rmtree(previous)
    try:
        os.rename(APP_DIR, previous)
    except OSError:                                            # (Windows: a file of the running app is still open)
        raise UpdateError("could not replace the app folder; close the app and try again")
    try:
        os.rename(dest, APP_DIR)
    except OSError:
        os.rename(previous, APP_DIR)                           # could not put the new one in: the old one stays
        raise UpdateError("could not put the update in place")
    return marker


# ------------------------------------------------------------------ releases (no git needed: used on Windows)
def _net(*args):
    """Tell the app debug log about a download (when this runs inside the app; the launcher and the tests may not have it)."""
    try:
        import debuglog
        debuglog.net(*args)
    except Exception:           # noqa: BLE001
        pass


def _http_get(url, limit=MAX_BYTES, timeout=25):
    """The bytes at an https address (the update server and its download links only; nothing about you is sent)."""
    if not url.startswith("https://"):
        raise UpdateError("refusing an address that is not https")
    req = urllib.request.Request(url, headers={"User-Agent": "RobloxManager-updater", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
            _net("GET", url, getattr(r, "status", 200), len(data))
    except Exception as e:                                       # noqa: BLE001 - any network problem is just "could not reach"
        _net("GET", url, getattr(e, "code", None), 0, e.__class__.__name__)
        raise UpdateError(f"could not reach the update server ({e.__class__.__name__})")
    if len(data) > limit:
        raise UpdateError("the download is unexpectedly large")
    return data


def version_key(v):
    """Versions compare as numbers, number by number. R.B.S.F.D has five (see tools/version.py); an older 1.7.0 counts as 1.7.0.0.0."""
    nums = [int(n) for n in re.findall(r"\d+", str(v))] or [0]
    return tuple(nums + [0] * (5 - len(nums)))


def _release_info(d):
    """{'version', 'tag', 'tar_url', 'sig_url'} for one GitHub release (as the API describes it), or None if it has no usable signed package."""
    tag = str(d.get("tag_name") or "")
    ver = tag.lstrip("v")
    if d.get("draft") or not re.fullmatch(r"\d+(\.\d+){1,4}", ver):               # (R.B.S.F.D has up to five numbers)
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in d.get("assets", []) if isinstance(a, dict)}
    name = f"roblox-manager-app-{ver}.tar.gz"
    if name not in assets or name + ".sig" not in assets:
        return None
    return {"version": ver, "tag": tag, "tar_url": assets[name], "sig_url": assets[name + ".sig"], "prerelease": bool(d.get("prerelease"))}


def release_latest(cfg):
    """The newest GitHub release of the repository in cfg['repo']: on the stable channel the one GitHub calls latest, on the beta channel the highest
    version of all releases, pre-releases included."""
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", cfg["repo"] or "")
    if not m:
        raise UpdateError("the update server is not a GitHub repository address")
    base = f"{API}/repos/{m.group(1)}/{m.group(2)}/releases"
    try:
        if cfg.get("channel") == "beta":
            found = [r for r in (_release_info(d) for d in json.loads(_http_get(base + "?per_page=20", limit=4_000_000)) if isinstance(d, dict)) if r]
            if not found:
                raise UpdateError("there is no beta release with a signed update package yet")
            return max(found, key=lambda r: version_key(r["version"]))
        d = json.loads(_http_get(base + "/latest", limit=2_000_000))
    except ValueError:
        raise UpdateError("the update server sent something unexpected")
    info = _release_info(d)
    if info is None:
        tag = str(d.get("tag_name") or "")
        if not re.fullmatch(r"\d+(\.\d+){1,4}", tag.lstrip("v")):
            raise UpdateError("the newest release has no usable version")
        raise UpdateError(f"the newest release ({tag.lstrip('v')}) has no signed update package yet")
    return info


# ------------------------------------------------------------------ the public steps
def check(cfg=None):
    """{'status': 'disabled'|'up-to-date'|'available'|'error', ...} without changing anything."""
    cfg = cfg or load_config()
    out = {"installed": installed().get("commit", ""), "version": version()}
    if not cfg["repo"]:
        return dict(out, status="disabled", message="No update server is set.")
    if plat.update_backend() == "release":
        try:
            rel = release_latest(cfg)
        except UpdateError as e:
            return dict(out, status="error", message=str(e))
        channel = "Beta" if cfg.get("channel") == "beta" else "Stable"
        if version_key(rel["version"]) <= version_key(out["version"]):
            note = " No beta is newer than the stable version at the moment." if channel == "Beta" and not rel.get("prerelease") else ""
            return dict(out, status="up-to-date", remote=rel["tag"], channel=channel.lower(),
                        message=f"You have the newest version ({out['version']}) on the {channel} channel.{note}")
        return dict(out, status="available", remote=rel["tag"], release=rel, channel=channel.lower(),
                    message=f"A newer version ({rel['version']}) is available on the {channel} channel.")
    try:
        head = remote_head(cfg)
    except UpdateError as e:
        return dict(out, status="error", message=str(e))
    channel = "Beta" if cfg.get("channel") == "beta" else "Stable"
    if head == out["installed"]:
        return dict(out, status="up-to-date", remote=head, channel=channel.lower(), message=f"You have the newest version ({out['version']}) on the {channel} channel.")
    return dict(out, status="available", remote=head, channel=channel.lower(), message=f"A newer version is available on the {channel} channel.")


def apply(cfg=None):
    """Check and, if there is a newer trusted version, install it. Returns a dict with 'status' (and 'message')."""
    cfg = cfg or load_config()
    res = check(cfg)
    if res["status"] != "available":
        return res
    head, old = res["remote"], res["installed"]
    release = res.get("release")
    staging = None
    try:
        if release:                                                    # Windows: a signed package from the newest GitHub release
            data = _http_get(release["tar_url"])
            sig = _http_get(release["sig_url"], limit=20_000).decode("utf-8", "replace")
            trust = TRUST_FILE.read_text() if TRUST_FILE.exists() else ""
            who = None
            if trust.strip():
                import sshsig
                who = sshsig.verify(data, sig, trust, RELEASE_NAMESPACE)
            if cfg["require_signature"] and not who:
                raise UpdateError("the newest version is not signed with a key you trust, so it was NOT installed")
            staging = Path(tempfile.mkdtemp(prefix=APP_DIR.name + ".new-", dir=APP_DIR.parent))
            _unpack(data, staging)
            _validate(staging)
            if version_key((staging / "VERSION").read_text()) != version_key(release["version"]):
                raise UpdateError("the package does not match the release it came with, so it was NOT installed")
        else:                                                          # Linux: the newest signed commit of the repository
            _fetch(cfg, head)
            who = signer_of(head)
            if cfg["require_signature"] and not who:
                raise UpdateError("the newest version is not signed with a key you trust, so it was NOT installed")
            if old and _git("merge-base", "--is-ancestor", head, old, cwd=CACHE_DIR).returncode == 0:
                return dict(res, status="up-to-date", message="You have a newer version than this channel has so far, so nothing was changed.")
            if not is_continuation(old, head):
                raise UpdateError("the newest version does not continue the one you have (it would be a step back), so it was NOT installed")
            staging = Path(tempfile.mkdtemp(prefix=APP_DIR.name + ".new-", dir=APP_DIR.parent))
            _export(head, staging)
            _validate(staging)
        marker = _swap(staging, head)
    except UpdateError as e:
        log(f"update to {head[:10]} refused: {e}")
        return dict(res, status="refused", message=str(e))
    except Exception as e:                          # noqa: BLE001 - an update must never be able to break the start
        import traceback
        log(f"update to {head[:10]} failed: {e.__class__.__name__}: {e} | {' / '.join(traceback.format_exc().strip().splitlines()[-4:])}")
        return dict(res, status="error", message=f"the update failed ({e.__class__.__name__}); the installed version is unchanged")
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    log(f"updated {old[:10] or '-'} -> {head[:10]} (version {marker['version']}, signed by {who or 'nobody (signatures not required)'})")
    return dict(res, status="updated", version=marker["version"], installed=head, signer=who,
                message=f"Updated to version {marker['version']}. Restart the app to use it.")


def rollback():
    previous = APP_DIR.with_name(APP_DIR.name + ".previous")
    if not previous.exists():
        return {"status": "error", "message": "There is no previous version to go back to."}
    old = APP_DIR.with_name(APP_DIR.name + ".replaced")
    if old.exists():
        shutil.rmtree(old)
    os.rename(APP_DIR, old)
    os.rename(previous, APP_DIR)
    os.rename(old, previous)                                    # (the two swap places, so rolling back twice returns to the newer one)
    log("rolled back to the previous version")
    return {"status": "rolled-back", "version": version(), "message": f"Back to version {version()}. Restart the app to use it."}


def boot():
    """Used by the launcher at every start: quiet, quick, and never an obstacle."""
    cfg = load_config()
    if not cfg["auto"] or not cfg["repo"]:
        return None
    try:
        res = apply(cfg)
        if res["status"] not in ("up-to-date", "disabled"):
            log(f"boot: {res['status']}: {res.get('message', '')}")
        return res                                               # (the launcher asks for a restart when this says 'updated')
    except Exception as e:                                       # noqa: BLE001
        log(f"boot: failed: {e.__class__.__name__}: {e}")
        return None


def main(argv):
    arg = argv[1] if len(argv) > 1 else "--status"
    if arg == "--boot":
        boot()
    elif arg == "--check":
        print(json.dumps(check(), indent=1))
    elif arg == "--apply":
        print(json.dumps(apply(), indent=1))
    elif arg == "--rollback":
        print(json.dumps(rollback(), indent=1))
    elif arg == "--status":
        print(json.dumps({"version": version(), "installed": installed(), "config": load_config()}, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
