"""Backup of what is yours in the app, as one readable JSON file: the settings, the friend alerts, the recently viewed games and, when you ask for it,
a copy of your friends, followers, following and groups. Sign-ins (cookies) and the list of accounts are never in it.

Restoring brings back the settings, the friend alerts and the recent games. The copy of your lists is for you to keep: restoring never changes anything on Roblox."""
import json
import os
from datetime import datetime, timezone

import alerts
import games_store
import settings

FORMAT = 1
MAX_BYTES = 5_000_000
APP = "roblox-manager"
PRIVATE = {"geo.allowed", "geo.roseal", "geo.auto"}          # agreements are given on each device, so they are neither saved nor restored


class BackupError(Exception):
    pass


def _person(p):
    return {"id": p.get("id"), "name": str(p.get("name") or "")[:40], "displayName": str(p.get("displayName") or "")[:60]}


def build(version="", account=None, friends=None, followers=None, following=None, groups=None):
    """The backup as a dictionary. The lists are only included when they are given (they need a sign-in)."""
    data = {
        "app": APP, "format": FORMAT, "version": version, "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settings": {k: settings.get(k) for k in settings.DEFAULTS if k not in PRIVATE},
        "alerts": alerts.load(),
        "recent_games": games_store.recent(),
    }
    if account:
        data["account"] = {"id": account.get("id"), "name": str(account.get("name") or ""), "displayName": str(account.get("displayName") or "")}
    for key, items in (("friends", friends), ("followers", followers), ("following", following)):
        if items is not None:
            data[key] = [_person(p) for p in items if isinstance(p, dict) and isinstance(p.get("id"), int)]
    if groups is not None:
        data["groups"] = [{"id": g["group"]["id"], "name": str(g["group"].get("name") or "")[:100], "role": str((g.get("role") or {}).get("name") or "")[:60],
                           "rank": (g.get("role") or {}).get("rank")} for g in groups if isinstance(g, dict) and isinstance(g.get("group"), dict)]
    return data


def save(path, data):
    text = json.dumps(data, indent=1, ensure_ascii=False)
    tmp = f"{path}.part"                          # written aside and then moved into place, so a half-written backup never exists
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return len(text)


def read(path):
    """A backup file as a dictionary; BackupError says in plain words what is wrong with it."""
    try:
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            raise BackupError("That file is too big to be a backup of this app.")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise BackupError(f"The file could not be read: {e.strerror or e}") from e
    except ValueError as e:
        raise BackupError("That file is not a backup of this app (it is not valid JSON).") from e
    if not isinstance(data, dict) or data.get("app") != APP:
        raise BackupError("That file is not a backup of this app.")
    fmt = data.get("format")
    if not isinstance(fmt, int) or fmt < 1:
        raise BackupError("That backup has no version number.")
    if fmt > FORMAT:
        raise BackupError("That backup was made by a newer version of the app. Update the app first.")
    return data


def restore(data):
    """Put the settings, alerts and recent games back. Returns what was restored, e.g. {'settings': 8, 'alerts': 12, 'games': 5}."""
    done = {"settings": 0, "alerts": 0, "games": 0}
    s = data.get("settings")
    if isinstance(s, dict):
        for key in settings.DEFAULTS:
            if key not in PRIVATE and key in s and (isinstance(s[key], (bool, int)) or isinstance(s[key], float)):
                settings.set(key, s[key])
                done["settings"] += 1
    if "alerts" in data:
        clean = alerts.clean(data["alerts"])
        alerts.save(clean)
        done["alerts"] = sum(len(v) for v in clean["watch"].values())
    games = data.get("recent_games")
    if isinstance(games, list):
        keep = []
        for c in games[:games_store.LIMIT]:
            if isinstance(c, dict) and isinstance(c.get("universeId"), int) and isinstance(c.get("name"), str):
                keep.append(c)
        for card in reversed(keep):                # oldest first, so the newest ends up on top
            games_store.add(games_store_card(card))
        done["games"] = len(keep)
    return done


def _n(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def games_store_card(c):
    return {"universeId": c["universeId"], "placeId": c.get("placeId") if isinstance(c.get("placeId"), int) else None, "name": c["name"][:120],
            "playing": _n(c.get("playing")), "up": _n(c.get("up")), "down": _n(c.get("down")), "creator": str(c.get("creator") or "")[:60],
            "verified": bool(c.get("verified")), "age": str(c.get("age") or ""), "genre": str(c.get("genre") or "")}
