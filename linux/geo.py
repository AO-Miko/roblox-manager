"""Where a Roblox server is: the public address of a server (from Roblox's join answer) is looked up on ipwho.is, which says which city it is in.

Only the address of a Roblox server is sent to ipwho.is (never a name, a cookie or an account), and answers are kept for 30 days by the first three numbers of the
address, because Roblox puts a whole block of addresses in one data centre. Looking up is always started by the person (the Locate button)."""
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
        place = clean({"success": True, "city": hit.get("city"), "region": hit.get("region"), "country": hit.get("country"), "country_code": hit.get("cc"),
                       "latitude": hit.get("lat"), "longitude": hit.get("lon")})
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
