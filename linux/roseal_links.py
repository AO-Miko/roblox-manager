"""Links to a game's community wiki, from RoSeal's public data (data.roseal.live/v2/experience-links.json).

Nothing is contacted unless the person allowed RoSeal's data service in Settings (the caller asks). It is one plain download (no cookie, nothing about the person or the game they look at),
kept 24 hours on the device. Every link is checked before it can be opened: only https, only a plain host name with an optional path, no addresses, ports or logins."""
import json
import os
import re
import time

import requests

import geo
import rbx

URL = "https://data.roseal.live/v2/experience-links.json"
FILE = rbx.STATE_DIR / "roseal_links.json"
TTL = 24 * 3600
MAX_BYTES = 400_000                  # the real file is about 115,000
TYPES = {"communityWiki": "Community wiki"}
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\.)+[a-z]{2,24}$")
_PATH = re.compile(r"^(?:/[A-Za-z0-9._~%+\-]{0,100}){0,8}/?$")


def safe_url(text):
    """'adoptme.fandom.com' or 'wiki.example.org/Game' -> 'https://...', or None if it is anything else than a plain host (and a path)."""
    if not isinstance(text, str) or len(text) > 200 or any(c in text for c in " \t\r\n\\@:?#&=\"'<>"):
        return None
    text = text.strip()
    host, slash, rest = text.partition("/")
    host = host.lower()
    if not _HOST.match(host) or re.fullmatch(r"[0-9.]+", host):
        return None
    path = slash + rest
    return f"https://{host}{path}" if _PATH.match(path) else None


def clean(data):
    """RoSeal's file -> {universe id: [{'type', 'label', 'url'}]}, keeping only the known kinds of link with a safe address."""
    out = {}
    for e in (data if isinstance(data, list) else [])[:5000]:
        if not isinstance(e, dict):
            continue
        links = []
        for l in (e.get("links") or [])[:20]:
            if isinstance(l, dict) and l.get("type") in TYPES:
                url = safe_url(l.get("url"))
                if url and not any(x["url"] == url for x in links):
                    links.append({"type": l["type"], "label": TYPES[l["type"]], "url": url})
        if links:
            for u in (e.get("universeIds") or [])[:50]:
                if isinstance(u, int) and not isinstance(u, bool):
                    out.setdefault(u, []).extend(links)
    return out


def _fetch(url):
    r = requests.get(url, timeout=10, allow_redirects=False, headers={"User-Agent": "RobloxManager"}, stream=True)
    try:
        r.raise_for_status()
        body = r.raw.read(MAX_BYTES + 1, decode_content=True)
    finally:
        r.close()
    if len(body) > MAX_BYTES:
        raise geo.GeoError("RoSeal's list of game links was too big")
    return json.loads(body)


def links_for(universe_id, fetch=None, now=None):
    """The links known for a game: [{'type', 'label', 'url'}] (possibly none). geo.GeoError says in plain words why the list could not be had."""
    now = time.time() if now is None else now
    kept = None
    try:
        kept = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    table = None
    if isinstance(kept, dict) and now - kept.get("t", 0) < TTL:
        table = clean(kept.get("links"))
    if table is None:
        try:
            data = (fetch or _fetch)(URL)
        except geo.GeoError:
            raise
        except (requests.RequestException, ValueError, OSError) as e:
            old = clean(kept.get("links")) if isinstance(kept, dict) else {}
            if old:
                return old.get(int(universe_id), [])
            raise geo.GeoError("RoSeal's list of game links could not be downloaded") from e
        if not isinstance(data, list):
            raise geo.GeoError("RoSeal's list of game links did not look right")
        table = clean(data)
        try:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"t": now, "links": data}, f)
            tmp.replace(FILE)
        except OSError:
            pass
    return table.get(int(universe_id), [])
