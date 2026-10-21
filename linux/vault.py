"""Keeps sign-in cookies encrypted, in the system wallet (KDE Wallet / any Secret Service) through the `secret-tool` program.

The cookie is passed to secret-tool on its standard input, never on the command line, so it does not show up in the process list.
If the wallet cannot be used (not installed, locked and not unlocked in time ...), the cookie falls back to a private file
(owner-only permissions) and `plaintext_in_use()` says so, so the app can warn. A cookie already sitting in a plain file is moved into
the wallet the first time it is read, and the file is overwritten and deleted.
"""
import os
import shutil
import subprocess

TOOL = shutil.which("secret-tool")
TIMEOUT = 30            # a locked wallet shows a password prompt; give the person time, but never hang for ever

_state = {"ok": None}


def _app():
    # an isolated namespace when a different config directory is used (tests), so they never touch the real entries
    cfg = os.environ.get("ROBLOX_MANAGER_CONFIG")
    return "roblox-manager" + (":" + cfg if cfg else "")


def _run(args, value=None):
    try:
        return subprocess.run([TOOL, *args], input=value, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None


def available(refresh=False):
    """True if a wallet answers. (A missing entry is an ordinary 'not found'; an unreachable service prints an error.)"""
    if os.environ.get("ROBLOX_MANAGER_VAULT") == "off" or not TOOL:
        return False
    if _state["ok"] is None or refresh:
        r = _run(["lookup", "application", _app(), "account", "__probe__"])
        _state["ok"] = bool(r is not None and r.returncode in (0, 1) and not (r.stderr or "").strip())
    return _state["ok"]


def get(key):
    if not available():
        return ""
    r = _run(["lookup", "application", _app(), "account", key])
    return r.stdout.strip() if r is not None and r.returncode == 0 else ""


def put(key, value, label="Roblox Manager sign-in"):
    if not available():
        return False
    r = _run(["store", "--label", label, "application", _app(), "account", key], value)
    ok = r is not None and r.returncode == 0
    if not ok:
        _state["ok"] = None             # check again next time (the wallet may have been locked)
    return ok


def delete(key):
    if available():
        _run(["clear", "application", _app(), "account", key])


def wipe(path):
    """Overwrite a file with zeros, then delete it (best effort: an SSD may still keep old blocks)."""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(b"\0" * size)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(path, 0o600)


def read(key, path):
    """The secret `key`: from the wallet, or (and migrated into it) from the old plain file."""
    v = get(key)
    if v:
        return v
    try:
        v = path.read_text().strip()
    except OSError:
        return ""
    if v and put(key, v):
        wipe(path)                      # moved into the wallet; the plain copy is destroyed
    return v


def write(key, path, value):
    """Store a secret encrypted if possible. Returns True if it is now encrypted, False if it had to go in a plain private file."""
    if put(key, value):
        if path.exists():
            wipe(path)
        return True
    _write_file(path, value)
    return False


def remove(key, path):
    delete(key)
    if path.exists():
        wipe(path)


def plaintext_in_use(paths):
    """True if any of these files still holds a secret in plain text."""
    return any(p.exists() and p.stat().st_size > 0 for p in paths)
