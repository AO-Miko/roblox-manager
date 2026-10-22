"""Where a Roblox server is. Roblox's join answer gives the id of the server's data centre and its public address. Two services can say where that is, and each one is used
only if the person agreed to it (Settings): RoSeal's public list of Roblox data centres (data.roseal.live: one plain download, nothing about the person or the server is sent),
and ipwho.is (the server's public address is sent, nothing else). What they said is kept on the device: by data centre for 30 days, and for ipwho.is by the first three numbers
of the address (Roblox puts a whole block of addresses in one data centre). Looking up is always started by the person (the Locate button)."""
import ipaddress
import json
import os
import time

import requests

import rbx

CACHE_FILE = rbx.STATE_DIR / "server_places.json"
URL = "https://ipwho.is/{ip}"
FIELDS = "success,country,country_code,region,city,latitude,longitude"
TTL = 30 * 24 * 3600
MAX_CACHED = 500
MAX_ANSWER = 20_000            # bytes: the real answer is about 400
ROSEAL_URL = "https://data.roseal.live/v2/grouped-datacenters.json"
ROSEAL_FILE = rbx.STATE_DIR / "roseal_datacenters.json"
ROSEAL_TTL = 6 * 3600
ROSEAL_MAX = 200_000           # bytes: the real list is about 13,000


class GeoError(Exception):
    pass


def public_ipv4(text):
    """The address as text when it is a public IPv4 address (the only kind that is ever looked up), else None."""
    try:
        ip = ipaddress.ip_address(str(text).strip())
    except ValueError:
        return None
    return str(ip) if ip.version == 4 and ip.is_global else None


def block_of(ip):
    """'128.116.44.33' -> '128.116.44' (Roblox puts a whole block of addresses in one place)."""
    return ".".join(ip.split(".")[:3])


def clean(d):
    """ipwho.is's answer -> {'city', 'region', 'country', 'cc', 'lat', 'lon'}, or None when it does not look right."""
    if not isinstance(d, dict) or d.get("success") is False:
        return None
    lat, lon = d.get("latitude"), d.get("longitude")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"city": str(d.get("city") or "")[:60], "region": str(d.get("region") or "")[:60], "country": str(d.get("country") or "")[:60],
            "cc": str(d.get("country_code") or "")[:2].upper(), "lat": round(float(lat), 3), "lon": round(float(lon), 3)}


def label(place):
    """'Frankfurt am Main, Germany' (or what is known)."""
    return ", ".join(x for x in (place.get("city"), place.get("country") or place.get("cc")) if x) or "Unknown"


def _read_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(cache):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        keep = dict(sorted(cache.items(), key=lambda kv: kv[1].get("t", 0), reverse=True)[:MAX_CACHED])
        tmp = CACHE_FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(keep, f)
        tmp.replace(CACHE_FILE)
    except OSError:
        pass


def _fetch(url):
    r = requests.get(url, params={"fields": FIELDS}, timeout=10, allow_redirects=False, headers={"User-Agent": "RobloxManager"}, stream=True)
    try:
        r.raise_for_status()
        body = r.raw.read(MAX_ANSWER + 1, decode_content=True)
    finally:
        r.close()
    if len(body) > MAX_ANSWER:
        raise GeoError("The answer was too big")
    return json.loads(body)


def _fetch_roseal(url):
    r = requests.get(url, timeout=10, allow_redirects=False, headers={"User-Agent": "RobloxManager"}, stream=True)
    try:
        r.raise_for_status()
        body = r.raw.read(ROSEAL_MAX + 1, decode_content=True)
    finally:
        r.close()
    if len(body) > ROSEAL_MAX:
        raise GeoError("RoSeal's list was too big")
    return json.loads(body)


def clean_groups(data):
    """RoSeal's list -> [{'ids': set of data centre ids, 'city', 'region', 'cc', 'lat', 'lon'}], keeping only well-formed groups."""
    out = []
    for g in (data if isinstance(data, list) else [])[:200]:
        if not isinstance(g, dict) or not isinstance(g.get("location"), dict):
            continue
        loc = g["location"]
        try:
            lat, lon = (float(v) for v in loc.get("latLong"))
        except (TypeError, ValueError):
            continue
        ids = {i for i in (g.get("dataCenterIds") or [])[:2000] if isinstance(i, int) and not isinstance(i, bool)}
        if ids and -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append({"ids": ids, "city": str(loc.get("city") or "")[:60], "region": str(loc.get("region") or "")[:60], "cc": str(loc.get("country") or "")[:2].upper(),
                        "lat": round(lat, 3), "lon": round(lon, 3)})
    return out


def roseal_groups(fetch=None, now=None):
    """The data centre groups of RoSeal's list (kept 6 hours on the device). GeoError if it cannot be had at all."""
    now = time.time() if now is None else now
    kept = None
    try:
        kept = json.loads(ROSEAL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if isinstance(kept, dict) and now - kept.get("t", 0) < ROSEAL_TTL:
        groups = clean_groups(kept.get("groups"))
        if groups:
            return groups
    try:
        data = (fetch or _fetch_roseal)(ROSEAL_URL)
    except GeoError:
        raise
    except (requests.RequestException, ValueError, OSError) as e:
        old = clean_groups(kept.get("groups")) if isinstance(kept, dict) else []
        if old:
            return old                                    # (an old list is better than none)
        raise GeoError("RoSeal's list of data centres could not be downloaded") from e
    groups = clean_groups(data)
    if not groups:
        old = clean_groups(kept.get("groups")) if isinstance(kept, dict) else []
        if old:
            return old
        raise GeoError("RoSeal's list of data centres did not look right")
    try:
        ROSEAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = ROSEAL_FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"t": now, "groups": data}, f)
        tmp.replace(ROSEAL_FILE)
    except OSError:
        pass
    return groups


def place_for_dc(dc, fetch=None, now=None):
    """The place of a data centre id according to RoSeal's list, or None when the list does not have it."""
    for g in roseal_groups(fetch, now):
        if dc in g["ids"]:
            return {"city": g["city"], "region": g["region"], "country": "", "cc": g["cc"], "lat": g["lat"], "lon": g["lon"]}
    return None


def resolve(info, use_roseal, use_ipwho, roseal_fetch=None, ip_fetch=None, now=None):
    """The place of a server (info: what Roblox's join answer said: address and dc). Kept answers first, then RoSeal's list, then ipwho.is: each only if allowed.
    GeoError says in plain words why a place could not be found."""
    now = time.time() if now is None else now
    dc = info.get("dc")
    key = f"dc:{dc}"
    if dc:
        hit = _read_cache().get(key)
        if isinstance(hit, dict) and now - hit.get("t", 0) < TTL:
            place = _kept(hit)
            if place:
                return place
    if not use_roseal and not use_ipwho:
        raise GeoError("Server locations are switched off in Settings")
    why = []
    place = None
    if use_roseal and not dc:
        why.append("RoSeal's list cannot place a server without its data centre id")
    if use_roseal and dc:
        try:
            place = place_for_dc(dc, roseal_fetch, now)
            if place is None:
                why.append("RoSeal's list does not know this data centre")
        except GeoError as e:
            why.append(str(e))
    if place is None and use_ipwho:
        place = lookup(info["address"], ip_fetch, now)
    if place is None:
        raise GeoError(". ".join(why) + (" (and ipwho.is is switched off in Settings)" if not use_ipwho else ""))
    if dc:
        cache = _read_cache()
        cache[key] = dict(place, t=now)
        _write_cache(cache)
    return place


def _kept(hit):
    return clean({"success": True, "city": hit.get("city"), "region": hit.get("region"), "country": hit.get("country"), "country_code": hit.get("cc"),
                  "latitude": hit.get("lat"), "longitude": hit.get("lon")})


def lookup(address, fetch=None, now=None):
    """The place of a public address: {'city', 'region', 'country', 'cc', 'lat', 'lon'}. GeoError says in plain words what went wrong."""
    ip = public_ipv4(address)
    if not ip:
        raise GeoError("That is not a public address")
    now = time.time() if now is None else now
    key = block_of(ip)
    cache = _read_cache()
    hit = cache.get(key)
    if isinstance(hit, dict) and now - hit.get("t", 0) < TTL:
        place = _kept(hit)
        if place:
            return place
    try:
        answer = (fetch or _fetch)(URL.format(ip=ip))
    except GeoError:
        raise
    except (requests.RequestException, ValueError, OSError) as e:
        raise GeoError("The location service could not be reached") from e
    place = clean(answer)
    if not place:
        raise GeoError("The location service did not know that address")
    cache[key] = dict(place, t=now)
    _write_cache(cache)
    return place
