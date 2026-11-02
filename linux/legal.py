"""The Terms of use and the Privacy policy: which version of them each account accepted.

Every Roblox account is asked once, at its first sign-in on this device, and again whenever the texts change (VERSION is the
date of TERMS.md and PRIVACY.md; a test keeps them equal). Without the acceptance that account is signed out."""
import json
import time

import rbx

VERSION = "2026-11-02"                      # the "Last updated" date of TERMS.md and PRIVACY.md
TERMS_URL = "https://github.com/AO-Miko/roblox-manager/blob/main/TERMS.md"
PRIVACY_URL = "https://github.com/AO-Miko/roblox-manager/blob/main/PRIVACY.md"
FILE = rbx.CONFIG_DIR / "legal.json"


def _load():
    try:
        data = json.loads(FILE.read_text())
        return data["accounts"] if isinstance(data.get("accounts"), dict) else {}
    except (OSError, ValueError, AttributeError, KeyError):
        return {}


def accepted(user_id):
    """True if this account accepted this version of both texts on this device."""
    entry = _load().get(str(user_id))
    return isinstance(entry, dict) and entry.get("version") == VERSION


def accept(user_id):
    data = _load()
    data[str(user_id)] = {"version": VERSION, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        FILE.write_text(json.dumps({"accounts": data}, indent=1))
    except OSError:
        pass


def forget(user_id=None):
    """Takes back one account's acceptance (or all of them): it is asked again at its next sign-in."""
    data = {} if user_id is None else {k: v for k, v in _load().items() if k != str(user_id)}
    try:
        FILE.write_text(json.dumps({"accounts": data}, indent=1))
    except OSError:
        pass
