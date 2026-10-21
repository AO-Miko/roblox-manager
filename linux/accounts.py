"""Several Roblox accounts signed in at once.

Each account's sign-in cookie is kept encrypted in the system wallet (see vault.py; if no wallet is available it falls back to its own
owner-only file accounts/<user id>.cookie). accounts.json lists who is saved and which one is active, and holds no secrets. The
active account's cookie is also kept under the name "active" (the plain `cookie` file only if there is no wallet), which is where the
rest of the app reads it.
"""
import json
import os

import rbx
import vault

DIR = rbx.CONFIG_DIR / "accounts"
INDEX = rbx.CONFIG_DIR / "accounts.json"


def _write_private(path, text):
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _index():
    try:
        d = json.loads(INDEX.read_text())
        return {"accounts": list(d.get("accounts", [])), "active": d.get("active")}
    except (OSError, ValueError):
        return {"accounts": [], "active": None}


def _save_index(d):
    _write_private(INDEX, json.dumps(d, indent=1))


def _cookie_path(uid):
    return DIR / f"{int(uid)}.cookie"


def list_accounts():
    """[{'id', 'name', 'displayName'}] in the order they were added."""
    return _index()["accounts"]


def active_id():
    return _index()["active"]


def get(uid):
    return next((a for a in list_accounts() if a["id"] == uid), None)


def _key(uid):
    return f"acct-{int(uid)}"


def cookie_of(uid):
    return rbx.normalise_cookie(vault.read(_key(uid), _cookie_path(uid)))


def migrate():
    """Move any sign-in still in a plain file into the wallet (reading it does that)."""
    rbx.load_cookie()
    for a in list_accounts():
        cookie_of(a["id"])


def storage_status():
    """('encrypted' | 'plain' | 'none', how many plain files hold a sign-in)."""
    files = [rbx.COOKIE_FILE] + [_cookie_path(a["id"]) for a in list_accounts()]
    plain = sum(1 for f in files if f.exists() and f.stat().st_size > 0)
    if plain:
        return "plain", plain
    return ("encrypted", 0) if (rbx.COOKIE_FILE.parent.exists() and vault.available()) else ("none", 0)


def remember(user, cookie, make_active=True):
    """Save (or update) an account after Roblox said who the cookie belongs to. Returns the account entry."""
    value = rbx.normalise_cookie(cookie)
    if not rbx.cookie_looks_valid(value):
        raise ValueError("That does not look like a .ROBLOSECURITY cookie.")
    uid = int(user["id"])
    vault.write(_key(uid), _cookie_path(uid), value)
    idx = _index()
    entry = {"id": uid, "name": user.get("name", ""), "displayName": user.get("displayName") or user.get("name", "")}
    if any(a["id"] == uid for a in idx["accounts"]):
        idx["accounts"] = [entry if a["id"] == uid else a for a in idx["accounts"]]
    else:
        idx["accounts"].append(entry)
    if make_active:
        idx["active"] = uid
    _save_index(idx)
    if make_active:
        rbx.save_cookie(value)       # the plain cookie file always belongs to the active account
    return entry


def activate(uid):
    """Make a saved account the active one. Returns its cookie (and mirrors it to the plain cookie file)."""
    value = cookie_of(uid)
    if not value:
        raise KeyError(uid)
    idx = _index()
    idx["active"] = uid
    _save_index(idx)
    rbx.save_cookie(value)
    return value


def remove(uid):
    """Forget an account: its cookie file goes. Returns the id of the account that became active (or None)."""
    vault.remove(_key(uid), _cookie_path(uid))
    idx = _index()
    idx["accounts"] = [a for a in idx["accounts"] if a["id"] != uid]
    if idx["active"] == uid:
        idx["active"] = idx["accounts"][0]["id"] if idx["accounts"] else None
    _save_index(idx)
    if idx["active"] is not None and cookie_of(idx["active"]):
        rbx.save_cookie(cookie_of(idx["active"]))
    elif idx["active"] is None:
        rbx.delete_cookie()
    return idx["active"]
