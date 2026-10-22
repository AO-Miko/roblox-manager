"""Friend alerts: which friends you watch, and what counts as news about them (came online, joined a game).

This file only decides; the tab asks Roblox for the presence of the watched friends now and then and shows the news as a notification.
"""
import json
import os

import rbx

FILE = rbx.CONFIG_DIR / "alerts.json"
INTERVAL_S = 90          # how often the watched friends are looked at (one request for up to 100 people)
MAX_WATCHED = 200        # per account
KEEP_NEWS = 30

OFFLINE, ONLINE, IN_GAME, IN_STUDIO = 0, 1, 2, 3


def default():
    return {"enabled": False, "online": True, "ingame": True, "watch": {}}


def clean(data):
    """A settings dictionary from anything read from disk or from a backup: only the known keys, with the right types and sizes."""
    out = default()
    if not isinstance(data, dict):
        return out
    out["enabled"] = bool(data.get("enabled", False))
    out["online"] = bool(data.get("online", True))
    out["ingame"] = bool(data.get("ingame", True))
    watch = data.get("watch")
    if isinstance(watch, dict):
        for acc, friends in list(watch.items())[:50]:
            if not (isinstance(acc, str) and acc.isdigit() and isinstance(friends, dict)):
                continue
            keep = {}
            for fid, name in list(friends.items())[:MAX_WATCHED]:
                if isinstance(fid, str) and fid.isdigit():
                    keep[fid] = str(name)[:60]
            out["watch"][acc] = keep
    return out


def load():
    try:
        return clean(json.loads(FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return default()


def save(data):
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clean(data), f, indent=1)
        tmp.replace(FILE)
    except OSError:
        pass


def snapshot(presences):
    """Roblox's presence answer -> {user id: (type, place id, game name)}."""
    out = {}
    for p in presences if isinstance(presences, list) else []:
        if not isinstance(p, dict):
            continue
        uid = p.get("userId")
        if not isinstance(uid, int):
            continue
        kind = p.get("userPresenceType")
        kind = kind if kind in (OFFLINE, ONLINE, IN_GAME, IN_STUDIO) else OFFLINE
        place = p.get("rootPlaceId") or p.get("placeId")
        out[uid] = (kind, place if isinstance(place, int) else None, str(p.get("lastLocation") or "")[:80])
    return out


def news(prev, now, names, online=True, ingame=True):
    """What is new between two snapshots: [(user id, 'online' | 'ingame', text)].
    Nothing is reported for a friend that was not in the earlier snapshot (the first look only learns who is where)."""
    out = []
    for uid, (kind, place, game) in now.items():
        if uid not in prev:
            continue
        pk, pplace, _ = prev[uid]
        who = names.get(uid) or f"User {uid}"
        if kind == IN_GAME and ingame and (pk != IN_GAME or pplace != place):
            out.append((uid, "ingame", f"{who} joined {game or 'a game'}"))
        elif online and pk == OFFLINE and kind in (ONLINE, IN_STUDIO):
            out.append((uid, "online", f"{who} is online"))
        elif online and pk == OFFLINE and kind == IN_GAME and not ingame:
            out.append((uid, "online", f"{who} is online"))
    return out
