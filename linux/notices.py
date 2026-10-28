"""Notifications from the developer to everybody who uses the app. They are a signed file in the update repository
(dist/notifications.json + dist/notifications.json.sig, made by tools/notify.sh); the app fetches it at every start and every ten minutes, and
shows a red number in the side bar for the ones you have not read.

  * The list is only believed if it carries a valid signature of the release key (the same one the ban list and the updates use), so nobody
    else can put a message into your app.
  * A newer list (higher "serial") replaces an older one; an older list is never accepted again. The last good list is kept on disk.
  * Everything in it is shown as plain text. A link is only kept if it starts with https://.
  * Nothing about you is sent: it is a plain download of a public file.

File format: {"serial": 7, "notifications": [{"id": "2026-10-28-new-look", "date": "2026-10-28", "title": "...", "body": "...", "level": "info" | "important" | "warning",
"link": "https://...", "channel": "all" | "beta" | "stable", "expires": "2026-12-31"}]}, newest first. Only id, title and body are required."""
import base64
import datetime
import json
import re

import bans
import plat
import sshsig

BASE_URL = bans.BASE_URL
NAMESPACE = "roblox-manager-notifications"
TRUSTED = bans.TRUSTED                    # the release key (public)
MAX_BYTES = 300_000
MAX_ITEMS = 50
REFRESH_SECONDS = 600
LEVELS = ("info", "important", "warning")
CHANNELS = ("all", "beta", "stable")
_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _cache_file():
    return plat.state_dir() / "notices.cache.json"          # the list and its signature together, written in one step


def _state_file():
    return plat.state_dir() / "notices.state.json"          # which notifications were read, and which were already announced


def clean(e):
    """One entry made safe: the entry as a dict with every field in its place, or None when it is not usable."""
    if not isinstance(e, dict):
        return None
    nid = e.get("id")
    if not isinstance(nid, str) or not _ID.match(nid):
        return None
    title, body = e.get("title"), e.get("body")
    if not isinstance(title, str) or not title.strip():
        return None
    link = e.get("link")
    link = link.strip()[:300] if isinstance(link, str) and link.strip().lower().startswith("https://") else ""
    day = lambda v: v if isinstance(v, str) and _DAY.match(v) else ""
    channel = e.get("channel") if e.get("channel") in CHANNELS else "all"
    return {"id": nid, "date": day(e.get("date")), "title": title.strip()[:80], "body": body.strip()[:1000] if isinstance(body, str) else "",
            "level": e.get("level") if e.get("level") in LEVELS else "info", "link": link, "channel": channel, "expires": day(e.get("expires"))}


def parse(data, sig_text, trusted=None):
    """(serial, [entries]) if `data` is a list signed by the trusted key, else None. Bad entries and repeated ids are dropped, at most MAX_ITEMS are kept."""
    if sshsig.verify(data, sig_text, trusted if trusted is not None else TRUSTED, NAMESPACE) is None:
        return None
    try:
        d = json.loads(data.decode("utf-8"))
        serial = int(d["serial"])
        raw = d.get("notifications", [])
        if not isinstance(raw, list):
            return None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    out, seen = [], set()
    for e in raw:
        c = clean(e)
        if c and c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return serial, out[:MAX_ITEMS]


def load():
    """The last good list from disk, checked again every time: (serial, [entries]); (0, []) if there is none."""
    try:
        c = json.loads(_cache_file().read_text(encoding="utf-8"))
        got = parse(base64.b64decode(c["data"]), c["sig"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0, []
    return got or (0, [])


def refresh(get=None, base=None):
    """Download the list and keep it if it is signed and not older than the one we have. True if the list changed, False if not, None if it
    could not be fetched or was refused (nothing is changed then). Never raises."""
    get = get or bans._http_get
    base = base or BASE_URL
    try:
        data = get(base + "notifications.json", limit=MAX_BYTES)
        sig = get(base + "notifications.json.sig", limit=20_000).decode("utf-8", "replace")
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


def visible(items, channel, today=None):
    """What this app shows: the entries for everybody or for its update channel ('beta' or 'stable') that have not expired."""
    today = (today or datetime.date.today()).isoformat()
    return [e for e in items if e["channel"] in ("all", channel) and not (e["expires"] and e["expires"] < today)]


def current(channel, today=None):
    """The notifications to show now, newest first as published."""
    return visible(load()[1], channel, today)


# ------------------------------------------------------------------ what was read
def _state():
    try:
        s = json.loads(_state_file().read_text(encoding="utf-8"))
        return {"read": [i for i in s.get("read", []) if isinstance(i, str)], "seen": s.get("seen") if isinstance(s.get("seen"), list) else None}
    except (OSError, ValueError, AttributeError):
        return {"read": [], "seen": None}


def _save(s):
    try:
        f = _state_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"read": s["read"][-200:], "seen": (s["seen"] or [])[-200:] if s["seen"] is not None else None}), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


def read_ids():
    return set(_state()["read"])


def unread(channel, today=None):
    r = read_ids()
    return [e for e in current(channel, today) if e["id"] not in r]


def mark_read(*ids):
    s = _state()
    s["read"] += [i for i in ids if i not in s["read"]]
    _save(s)


def mark_all_read(channel, today=None):
    mark_read(*[e["id"] for e in current(channel, today)])


def fresh(channel, today=None):
    """The notifications that were never announced before (for a pop-up), and from now on they count as announced. The first time ever it announces
    nothing: a new installation does not get a pop-up for every old message."""
    s = _state()
    now = current(channel, today)
    if s["seen"] is None:
        s["seen"] = [e["id"] for e in now]
        _save(s)
        return []
    new = [e for e in now if e["id"] not in s["seen"]]
    if new:
        s["seen"] += [e["id"] for e in new]
        _save(s)
    return new
