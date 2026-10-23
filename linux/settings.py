"""The app's settings: a few choices kept in settings.json (in the config folder), applied at once when they change."""
import json
import os

import rbx

FILE = rbx.CONFIG_DIR / "settings.json"

# key: (default, minimum, maximum)  -- booleans have no range
DEFAULTS = {
    "rate.read_burst": (50, 0, 100),         # % of a route's limit a read may use back to back; the rest is spread over the window
    "log.requests": (True, None, None),      # write every request to requests.log
    "log.debug": (True, None, None),         # write the app debug log (everything that happens, private things hidden) to debug.log
    "log.keep_rows": (1500, 100, 10000),     # rows kept in the Requests tab's list
    "cache.avatar_days": (7, 1, 90),         # how long saved pictures are reused
    "cache.names_days": (30, 1, 365),        # how long saved names are reused
    "confirm.typed_from": (5, 2, 100),       # changing at least this many people/groups at once asks you to type the number
    "ui.remember_window": (True, None, None),
    "geo.roseal": (False, None, None),       # the person allows downloading RoSeal's public data files (data.roseal.live): data centres for server locations, links to game wikis
    "geo.auto": (False, None, None),         # look up the location and uptime of servers by themselves when they are listed (one request to Roblox per server)
    "geo.allowed": (False, None, None),      # the person allows asking ipwho.is where a server's public address is (the address is sent there)
    "ui.rate_notes": (True, None, None),     # the orange 'waiting for Roblox's limit' notes
}

_values = {k: v[0] for k, v in DEFAULTS.items()}
_listeners = []


def load():
    try:
        saved = json.loads(FILE.read_text())
    except (OSError, ValueError):
        saved = {}
    for k, (default, lo, hi) in DEFAULTS.items():
        _values[k] = _coerce(k, saved.get(k, default))
    apply()


def _coerce(key, value):
    default, lo, hi = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def get(key):
    return _values[key]


def set(key, value):          # noqa: A001 - reads naturally as settings.set(...)
    value = _coerce(key, value)
    if _values[key] == value:
        return value
    _values[key] = value
    save()
    apply()
    try:
        import debuglog
        debuglog.event("settings", f"{key} = {value}")
    except ImportError:
        pass
    for fn in list(_listeners):
        fn(key, value)
    return value


def reset():
    for k, (default, _, _) in DEFAULTS.items():
        _values[k] = default
    save()
    apply()
    for fn in list(_listeners):
        fn(None, None)


def on_change(fn):
    _listeners.append(fn)


def save():
    try:
        fd = os.open(FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(_values, f, indent=1)
    except OSError:
        pass


def apply():
    """Push the values into the parts of the app that use them."""
    rbx.Client.READ_BURST = _values["rate.read_burst"] / 100
    rbx.LOG_REQUESTS = _values["log.requests"]
    try:
        import debuglog
        debuglog.ENABLED = _values["log.debug"]
    except ImportError:
        pass
    rbx.AVATAR_MAX_AGE = _values["cache.avatar_days"] * 24 * 3600
    rbx.NameCache.TTL = _values["cache.names_days"] * 24 * 3600


def typed_from():
    """How many changes at once make the app ask you to type the number."""
    return _values["confirm.typed_from"]


load()
