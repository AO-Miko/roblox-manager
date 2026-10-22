"""The games you looked at lately, kept on this computer (nothing is sent anywhere): the 'Recently viewed' row of Discover."""
import json
import os

import rbx

LIMIT = 20
FILE = rbx.STATE_DIR / "recent_games.json"


def recent():
    """[game cards], newest first."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for c in data if isinstance(data, list) else []:
        if isinstance(c, dict) and isinstance(c.get("universeId"), int) and isinstance(c.get("name"), str):
            out.append({"universeId": c["universeId"], "placeId": c.get("placeId") if isinstance(c.get("placeId"), int) else None, "name": c["name"][:120],
                        "playing": int(c.get("playing") or 0), "up": int(c.get("up") or 0), "down": int(c.get("down") or 0), "creator": str(c.get("creator") or "")[:60],
                        "verified": bool(c.get("verified")), "age": str(c.get("age") or ""), "genre": str(c.get("genre") or "")})
    return out[:LIMIT]


def add(card):
    """Put a game first in the list (it moves up if it was there already)."""
    keep = [c for c in recent() if c["universeId"] != card["universeId"]]
    items = [card] + keep
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items[:LIMIT], f)
        tmp.replace(FILE)
    except OSError:
        pass
    return items[:LIMIT]


def clear():
    try:
        FILE.unlink()
    except OSError:
        pass
