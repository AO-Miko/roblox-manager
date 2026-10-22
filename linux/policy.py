"""Forced updates: a version that is too far behind may no longer be used.

The maintainer publishes a small signed file next to the ban list (dist/policy.json + dist/policy.json.sig, signed with the release key):

    {"serial": 12, "limit": 2, "stable": ["1.8.0.0.0", "1.9.0.0.0", "1.9.2.0.0"]}

"stable" lists every version that was released to everybody (not the betas). An app that is `limit` versions or more behind the newest one (the default is 2: it
has missed two updates) cannot be used at all: a page covers the whole window, says so, and has a button that updates it. (Nobody is signed out and nothing is deleted.)

Each channel counts the updates of its own channel. An app on the Stable channel counts the "stable" list, read from the `release` branch. An app on the Beta channel counts the
"beta" list (every release, betas included), read from the `beta` branch, where every beta release writes it; without a "beta" list it counts "stable". A version that is newer than the
list is never behind. As with the ban list: only a valid signature is believed, a newer serial replaces an older one, the last good file is kept for offline use (one file per
channel, their serials are independent), and if nothing was ever downloaded (or the server is unreachable) nobody is locked out.
"""
import base64
import json
import re

import bans
import plat
import sshsig
import updater

NAMESPACE = "roblox-manager-policy"
DEFAULT_LIMIT = 2
RELEASES_URL = "https://github.com/AO-Miko/roblox-manager/releases/latest"
RELEASES_ALL_URL = "https://github.com/AO-Miko/roblox-manager/releases"          # (the Beta channel: the newest version may be a pre-release)
BASES = {"stable": bans.BASE_URL, "beta": bans.BASE_URL.replace("/release/dist/", "/beta/dist/")}


def current_channel():
    """The channel this app follows (Settings > Updates): 'stable' or 'beta'."""
    try:
        return updater.load_config().get("channel") or "stable"
    except Exception:                                    # noqa: BLE001 - never lock or crash over this
        return "stable"


def releases_url():
    """The page to download the newest version from: the latest release, or on the Beta channel the list of all releases."""
    return RELEASES_ALL_URL if current_channel() == "beta" else RELEASES_URL


def _cache_file(channel="stable"):
    return plat.state_dir() / ("policy.cache.json" if channel == "stable" else f"policy.cache.{channel}.json")


def parse(data, sig_text, trusted=None, channel="stable"):
    """(serial, limit, [versions]) if `data` is a policy signed by the trusted key, else None. The versions are the channel's: 'beta' uses the "beta" list when there is one."""
    if sshsig.verify(data, sig_text, trusted if trusted is not None else bans.TRUSTED, NAMESPACE) is None:
        return None
    try:
        d = json.loads(data.decode("utf-8"))
        versions = [str(v) for v in (d["beta"] if channel == "beta" and isinstance(d.get("beta"), list) else d.get("stable", []))]
        if not all(re.fullmatch(r"\d+(\.\d+){1,4}", v) for v in versions):
            return None
        limit = int(d.get("limit", DEFAULT_LIMIT))
        return int(d["serial"]), max(1, limit), versions
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def load(channel=None):
    """The last good policy of a channel from disk, checked again every time: (serial, limit, [versions]); (0, DEFAULT_LIMIT, []) if there is none."""
    channel = channel or current_channel()
    try:
        c = json.loads(_cache_file(channel).read_text(encoding="utf-8"))
        got = parse(base64.b64decode(c["data"]), c["sig"], channel=channel)
    except (OSError, ValueError, KeyError, TypeError):
        return 0, DEFAULT_LIMIT, []
    return got or (0, DEFAULT_LIMIT, [])


def status(installed=None, channel=None):
    """{'blocked', 'behind', 'limit', 'latest', 'installed'}: how many released versions of the channel are newer than the installed one."""
    installed = installed or updater.version()
    _, limit, versions = load(channel)
    key = updater.version_key(installed)
    newer = {updater.version_key(v): v for v in versions if updater.version_key(v) > key}          # (1.9.0.0 and 1.9.0.0.0 count once)
    latest = max(newer.items())[1] if newer else installed
    return {"blocked": len(newer) >= limit, "behind": len(newer), "limit": limit, "latest": latest, "installed": installed}


def refresh(get=None, base=None, channel=None):
    """Download the policy of a channel; True if it changed, False if not, None if it could not be fetched or was refused. Never raises."""
    get = get or bans._http_get
    channel = channel or current_channel()
    base = base or BASES.get(channel, bans.BASE_URL)
    try:
        data = get(base + "policy.json")
        sig = get(base + "policy.json.sig", limit=20_000).decode("utf-8", "replace")
    except Exception:                                    # noqa: BLE001 - any network problem just means "could not fetch"
        return None
    got = parse(data, sig, channel=channel)
    if got is None:
        return None
    have = load(channel)
    if got[0] < have[0] or got == have:
        return False
    try:
        f = _cache_file(channel)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"data": base64.b64encode(data).decode(), "sig": sig}), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        return None
    return True
