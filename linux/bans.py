"""The ban list: Roblox user ids that may not use this app. The maintainer publishes it as a signed file in the update repository
(dist/bans.json + dist/bans.json.sig); every start, every sign-in and every ten minutes the app fetches it, and an account on it is signed out
and forgotten at once, also in the middle of a session.

  * The list is only believed if it carries a valid signature of the release key (built into this file), so nobody else can ban anyone.
  * A newer list (higher "serial") replaces an older one; an older list is never accepted again.
  * The last good list is kept on disk and applies even without a network. If the list cannot be fetched at all, nobody is locked out.
  * Nothing about you is sent: it is a plain download of a public file.
This is a client-side check in open-source code: it keeps honest users honest and stops casual misuse, it cannot stop someone who edits the program.
"""
import base64
import json
import urllib.request

import plat
import sshsig

BASE_URL = "https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/"
NAMESPACE = "roblox-manager-bans"
# the release key (public); the same key signs the updates
TRUSTED = "release@roblox-manager.local ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOIrL6gArNibpgZ32RNQts1DOPQlWn6y0pvEDlGPzQmG\n"
MAX_BYTES = 300_000
REFRESH_SECONDS = 600


def _cache_file():
    return plat.state_dir() / "bans.cache.json"           # the list and its signature together, written in one step


def _http_get(url, limit=MAX_BYTES, timeout=15):
    if not url.startswith("https://"):
        raise OSError("not https")
    req = urllib.request.Request(url, headers={"User-Agent": "RobloxManager-bans"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise OSError("too large")
    return data


def parse(data, sig_text, trusted=None):
    """(serial, {user id: reason}) if `data` is a list signed by the trusted key, else None."""
    if sshsig.verify(data, sig_text, trusted if trusted is not None else TRUSTED, NAMESPACE) is None:
        return None
    try:
        d = json.loads(data.decode("utf-8"))
        return int(d["serial"]), {int(b["id"]): str(b.get("reason") or "")[:200] for b in d.get("bans", [])}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def load():
    """The last good list from disk, checked again every time: (serial, {user id: reason}); (0, {}) if there is none."""
    try:
        c = json.loads(_cache_file().read_text(encoding="utf-8"))
        got = parse(base64.b64decode(c["data"]), c["sig"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0, {}
    return got or (0, {})


def banned(user_id):
    """The reason (possibly empty text) if this Roblox user id is banned, otherwise None."""
    try:
        return load()[1].get(int(user_id))
    except (ValueError, TypeError):
        return None


def refresh(get=None, base=None):
    """Download the list, and keep it if it is signed and not older than the one we have. True if the list changed, False if not, None if it
    could not be fetched or was refused (nothing is changed then). Never raises."""
    get = get or _http_get
    base = base or BASE_URL
    try:
        data = get(base + "bans.json")
        sig = get(base + "bans.json.sig", limit=20_000).decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    except Exception:                                    # noqa: BLE001 - any network problem just means "could not fetch"
        return None
    got = parse(data, sig)
    if got is None:
        return None
    have_serial, have = load()
    if got[0] < have_serial or (got[0] == have_serial and got[1] == have):
        return False
    try:
        f = _cache_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"data": base64.b64encode(data).decode(), "sig": sig}), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        return None
    return True


def entries():
    """The full entries of the last good list from disk ({'id', 'reason', 'since', 'by', 'rank'}), for the Admin tab; [] if there is none."""
    try:
        c = json.loads(_cache_file().read_text(encoding="utf-8"))
        data = base64.b64decode(c["data"])
        if parse(data, c["sig"]) is None:
            return []
        return json.loads(data.decode("utf-8")).get("bans", [])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
