"""Roblox API client for the Roblox Manager.

Safety rules built in:
  * the .ROBLOSECURITY cookie is read from a private file (mode 600) and is only ever sent to https://*.roblox.com
  * it is never logged, never returned by any function and never shown in an error message
  * state-changing calls get Roblox's anti-forgery (CSRF) token automatically
  * rate limits (429) and temporary errors are retried politely
"""
import json
import logging
import os
import re
import threading
import time
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

import requests

import plat
import vault

CONFIG_DIR = plat.config_dir()
STATE_DIR = plat.state_dir()
COOKIE_FILE = CONFIG_DIR / "cookie"
for _d in (CONFIG_DIR, STATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.chmod(0o700)   # holds the cookie: only you may even list this folder
try:
    STATE_DIR.chmod(0o700)    # logs and saved names: not for other users of this computer either
except OSError:
    pass

log = logging.getLogger("roblox-manager")
if not log.handlers:
    log.setLevel(logging.INFO)
    _h = RotatingFileHandler(STATE_DIR / "manager.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(_h)

# ------------------------------------------------------------------ the request log
# Every request this app sends is written to requests.log (and offered to the Requests tab through LISTENERS). It records what was asked
# and how Roblox answered: never the cookie, never a request body, never a header, and the value of anything that looks like a secret
# in the address is hidden.
req_log = logging.getLogger("roblox-manager.requests")
if not req_log.handlers:
    req_log.setLevel(logging.INFO)
    req_log.propagate = False
    _rh = RotatingFileHandler(STATE_DIR / "requests.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    _rh.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%Y-%m-%d %H:%M:%S"))
    req_log.addHandler(_rh)
LOG_REQUESTS = True     # settings: write requests.log (the Requests tab still shows them)
LISTENERS = []          # callables(entry dict), called from whatever thread sent the request
_SECRET_PARAM = re.compile(r"token|code|password|secret|cookie|ticket|auth|session|api[-_]?key|(^|[-_])key$", re.I)


def _query_text(params, url_query=""):
    from urllib.parse import parse_qsl
    pairs = list(parse_qsl(url_query)) + [(str(k), str(v)) for k, v in (params or {}).items() if v is not None]
    return "&".join(f"{k}={'***' if _SECRET_PARAM.search(k) else (v if len(v) <= 40 else v[:37] + '...')}" for k, v in pairs)


def record_request(account, method, url, params=None, status=None, ms=None, attempt=0, paced=False, note="", rate=""):
    """Write one line to the request log and tell the listeners. `status` is None when there was no answer (stopped, network error)."""
    u = urlparse(url)
    entry = {"time": time.time(), "account": account or "-", "method": method, "host": u.hostname or "", "path": u.path,
             "query": _query_text(params, u.query), "status": status, "ms": ms, "attempt": attempt, "paced": paced, "note": note, "rate": rate}
    try:
        line = (f"acct={entry['account']} {method} {entry['host']}{entry['path']}" + (f"?{entry['query']}" if entry["query"] else "")
                + f" -> {status if status is not None else 'no answer'}" + (f" ({note})" if note else "") + (f" {ms} ms" if ms is not None else "")
                + (" paced" if paced else "") + (f" retry#{attempt}" if attempt else "") + (f" | rate: {rate}" if rate else ""))
        if LOG_REQUESTS:
            req_log.info(redact(line))
    except Exception:           # noqa: BLE001 - logging must never break a request
        pass
    for fn in list(LISTENERS):
        try:
            fn(entry)
        except Exception:       # noqa: BLE001
            pass
    return entry


USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) RobloxManager/1.0"
SECRET_RE = re.compile(r"(_\|WARNING:[^;\s]+|\.ROBLOSECURITY=[^;\s]+)")


def redact(text):
    """Remove anything that looks like the cookie from a string before it is logged or shown."""
    return SECRET_RE.sub("[cookie removed]", str(text))


class Cancelled(Exception):
    """Raised inside a request that was stopped (the Stop button, or the window closing). Not an error to show the user."""

    def __str__(self):
        return "Cancelled"


class RobloxError(Exception):
    def __init__(self, status, message, code=None, body=None):
        super().__init__(redact(message))
        self.status, self.code, self.body = status, code, body

    def __str__(self):
        return f"HTTP {self.status}: {super().__str__()}"


# ------------------------------------------------------------------ the cookie file
def normalise_cookie(text):
    """Accept the value pasted in any common form: bare, '.ROBLOSECURITY=...' or with quotes/spaces."""
    t = (text or "").strip().strip('"').strip("'")
    t = re.sub(r"^\.?ROBLOSECURITY\s*=\s*", "", t, flags=re.I).strip().strip(";").strip()
    return t


def cookie_looks_valid(value):
    return bool(value) and len(value) > 100 and re.fullmatch(r"[\w|:\-.=+/%!~*'()]+", value) is not None


def save_cookie(text):
    value = normalise_cookie(text)
    if not cookie_looks_valid(value):
        raise ValueError("That does not look like a .ROBLOSECURITY cookie (it is a long text starting with _|WARNING).")
    encrypted = vault.write("active", COOKIE_FILE, value)
    log.info("cookie saved (%d characters, %s)", len(value), "encrypted in the wallet" if encrypted else "in a private file: the wallet was not available")


def load_cookie():
    try:
        if COOKIE_FILE.stat().st_mode & 0o077:
            os.chmod(COOKIE_FILE, 0o600)  # somebody loosened it: tighten it again
    except OSError:
        pass
    return normalise_cookie(vault.read("active", COOKIE_FILE))


def delete_cookie():
    vault.remove("active", COOKIE_FILE)
    log.info("cookie deleted")


# ------------------------------------------------------------------ names of users (public information, kept between runs)
class NameCache:
    """id -> (username, display name, verified). Looking a name up costs a request to a route with a hidden limit, so every name is looked
    up once and kept for 30 days in names.json (public data, nothing secret)."""
    TTL = 30 * 24 * 3600
    MAX = 60000

    def __init__(self, path=None):
        self.path = path or (STATE_DIR / "names.json")
        self.lock = threading.Lock()
        self.data = {}
        self.dirty = False
        self.last_save = 0.0
        try:
            raw = json.loads(self.path.read_text())
            now = time.time()
            self.data = {int(k): v for k, v in raw.items() if now - v[3] < self.TTL}
        except (OSError, ValueError, IndexError, TypeError):
            self.data = {}

    def get(self, uid):
        v = self.data.get(int(uid))
        return {"id": int(uid), "name": v[0], "displayName": v[1], "hasVerifiedBadge": None if v[2] is None else bool(v[2])} if v else None

    def put_many(self, users):
        now = time.time()
        with self.lock:
            for u in users:
                if u.get("id") and u.get("name"):
                    v = u.get("hasVerifiedBadge")
                    self.data[int(u["id"])] = [u["name"], u.get("displayName") or u["name"], None if v is None else bool(v), now]
                    self.dirty = True
            if len(self.data) > self.MAX:                       # keep the newest
                for k, _ in sorted(self.data.items(), key=lambda kv: kv[1][3])[: len(self.data) - self.MAX]:
                    del self.data[k]
        self.save()

    def save(self, force=False):
        now = time.time()
        if not self.dirty or (not force and now - self.last_save < 5):
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            with self.lock:
                tmp.write_text(json.dumps({str(k): v for k, v in self.data.items()}))
                self.dirty, self.last_save = False, now
            tmp.replace(self.path)
        except OSError:
            pass


names = NameCache()


# ------------------------------------------------------------------ Roblox's own rate limits
class LocalLimit(RobloxError):
    """Not sent: Roblox's own numbers say this route is used up for a while, longer than this request may wait."""
    local = True

    def __init__(self, route, limit, window, wait):
        per = f" per {window:g} s" if window else ""
        super().__init__(429, f"Roblox allows only {limit} of these{per} ({route}); the next one is allowed in {wait:.0f} s")


class RateTable:
    """Every answer from Roblox says how many requests that route allows (x-ratelimit-limit), how many are left (-remaining) and when the
    count starts over (-reset). This keeps that per route, so each route is used right up to its limit and never past it, by every part of
    the app that sends requests."""

    HIDDEN_FLOOR = 4.0        # the gap on such a route never drops below this: the limit is still there, only not shown
    HIDDEN_GAP = 5.5          # first gap between requests on a route found to have a hidden limit (doubled by each further refusal)
    HIDDEN_WAIT = 10          # a 429 although the headers said plenty was left: a limit the headers do not show; wait at least this long
    NOTIFY_AFTER = 5          # seconds: only waits longer than this are announced to the user (shorter ones are just smooth pacing)

    def __init__(self):
        self.routes = {}
        self.lock = threading.Lock()

    @staticmethod
    def key(method, url):
        u = urlparse(url)
        return f"{method} {u.hostname}{re.sub(r'/[0-9]+', '/{n}', u.path)}"

    def known(self, key):
        return key in self.routes

    def clear(self):
        with self.lock:
            self.routes.clear()

    def wait_left(self, key):
        st = self.routes.get(key)
        return max(0.0, st["reset_at"] - time.time()) if st and st["left"] <= 0 else 0.0

    def gate(self, key, sleep, max_wait=None, notify=None, burst=0.0):
        """Wait until one more request on this route is allowed, and reserve it.

        The allowance is spread over the time that is left in the route's window: with 10 requests per 30 s, one goes out about every 3 s
        instead of ten at once followed by a long wait. `burst` is the share of the limit that may be used back to back first (a screen
        that needs a handful of reads at once); a batch of changes uses 0, so it runs evenly from the first request.

        If the route is used up and its reset is further away than `max_wait`, LocalLimit is raised at once instead of making the caller
        sit there."""
        told = False
        while True:
            with self.lock:
                st, now = self.routes.get(key), time.time()
                if st is None:
                    return
                mg = st.get("min_gap", 0.0)                      # set when the route refused us although its headers promised more
                hold = st.get("last_sent", 0.0) + mg - now if mg else 0.0
                if hold > 0:
                    wait = hold
                else:
                    if now >= st["reset_at"]:                    # a new window: full allowance again
                        st["left"], st["reset_at"], st["next_ok"] = st["limit"], now + (st.get("window") or 1), 0.0
                    limit, window = st["limit"], st.get("window")
                    remaining = max(0.0, st["reset_at"] - now)
                    if st["left"] > 0:
                        used, free = limit - st["left"], int(limit * burst)
                        gap_wait = st.get("next_ok", 0.0) - now if used >= free else 0.0
                        if gap_wait <= 0:
                            st["left"] -= 1
                            st["last_sent"] = now
                            # when the free burst is used up, space what is left evenly over what is left of the window
                            st["next_ok"] = now + (remaining / (st["left"] + 1) if used + 1 >= free else 0.0)
                            return
                        wait = gap_wait if max_wait is None else min(gap_wait, max_wait)
                    else:
                        wait = st["reset_at"] - now + 0.2
                        if max_wait is not None and wait > max_wait:
                            raise LocalLimit(key.split(" ", 1)[1], limit, window, wait)
            if notify and wait > self.NOTIFY_AFTER and not told:
                told = True
                notify(wait)
            sleep(wait)

    def learn(self, key, headers, status, attempt, min_wait):
        """Read the limit headers (and a 429's retry-after) of an answer. Returns a short text for the log."""
        h = {k.lower(): v for k, v in headers.items()}
        rem, rst, lim_text = h.get("x-ratelimit-remaining"), h.get("x-ratelimit-reset"), h.get("x-ratelimit-limit", "")
        m = re.match(r"\s*(\d+)", lim_text)
        lim = int(m.group(1)) if m else None
        w = re.search(r";\s*w=(\d+)", lim_text)
        now, text = time.time(), ""
        try:
            with self.lock:
                st = self.routes.get(key)
                if st is None and (rem is not None or status == 429):
                    st = self.routes[key] = {"limit": lim or 10 ** 6, "left": 10 ** 6, "reset_at": 0.0, "window": None, "seen": now}
                if st is None:
                    return ""
                st["seen"] = now
                if lim:
                    st["limit"] = lim
                if w:
                    st["window"] = int(w.group(1))
                if rem is not None and rst is not None:
                    st["left"], st["reset_at"] = int(rem), now + float(rst)
                    text = f"{rem} of {lim or '?'} left, resets in {rst} s"
                hidden = status == 429 and rem is not None and int(rem) > 0
                if status == 429:
                    wait = max(float(h.get("retry-after") or 0), float(rst) if rst is not None else 0.0)
                    if rst is None:
                        wait = max(wait, min_wait * (attempt + 1))
                    if hidden:       # refused although the headers say plenty is left: there is a limit they do not show
                        wait = max(wait, self.HIDDEN_WAIT)
                        st["min_gap"] = min(max(st.get("min_gap", 0.0) * 2, self.HIDDEN_GAP), 30.0)
                        text = (text + "; " if text else "") + f"hidden limit: keeping {st['min_gap']:.0f} s between requests"
                elif st.get("min_gap"):
                    st["min_gap"] = max(st["min_gap"] * 0.95, self.HIDDEN_FLOOR)     # a success: loosen the gap again, slowly (never to nothing)
                if status == 429:
                    st["left"], st["reset_at"] = 0, now + min(wait, 60) + 0.5      # Roblox's latest word beats our own estimate
                    text = (text + "; " if text else "") + f"limited: wait {min(wait, 60):.0f} s"
        except ValueError:
            pass
        return text

    def snapshot(self):
        """[{route, limit, window, left, reset_in, seen}] for the Requests tab."""
        now = time.time()
        with self.lock:
            out = []
            for k, st in self.routes.items():
                active = now < st["reset_at"]
                out.append({"route": k, "limit": st["limit"] if st["limit"] < 10 ** 6 else None, "window": st.get("window"),
                            "left": st["left"] if active and st["left"] < 10 ** 6 else (st["limit"] if st["limit"] < 10 ** 6 else None),
                            "reset_in": max(0.0, st["reset_at"] - now) if active else 0.0, "seen": st.get("seen", 0)})
        return sorted(out, key=lambda r: r["route"])


# ------------------------------------------------------------------ the client
class Client:
    """One logged-in (or anonymous) session. Thread-safe enough for a few worker threads."""

    MIN_GAP = 0.12  # seconds between two requests: well below what Roblox allows, but never a burst

    rate_hook = None         # legacy single callback; see rate_hooks

    # Roblox allows roughly 12 changing requests per 30 s. Anything that changes something (POST/PATCH/DELETE/PUT) and each
    # per-server lookup is spread evenly, a little under that rate, so a long batch never runs into the limit.
    SLOW_GAP = 30 / 12 * 1.15
    SLOW_GAP_MAX = 10.0

    def __init__(self, cookie=None, timeout=20):
        self.rates = RateTable()           # what Roblox's own rate-limit headers say, per route
        self._epoch = 0                    # bumped when the account changes: requests started before that are dropped
        self._cancel = threading.Event()   # set to stop whatever is waiting or about to be sent
        self._closing = False              # the app is shutting down: the stop is permanent
        self.rate_hooks = []     # callbacks(path, seconds_to_wait, gave_up) when Roblox answers 429, called from worker threads
        self._cookie = normalise_cookie(cookie) if cookie is not None else load_cookie()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._csrf = ""
        self._lock = threading.Lock()
        self._slow_lock = threading.Lock()
        self._slow_next = 0.0
        self._slow_gap = self.SLOW_GAP
        self._last = 0.0
        self.user = None            # filled by login()
        self.last_headers = {}

    @property
    def has_cookie(self):
        return bool(self._cookie)

    # -- safety: the cookie only goes to roblox.com
    @staticmethod
    def _is_roblox(url):
        p = urlparse(url)
        host = (p.hostname or "").lower()
        return p.scheme == "https" and (host == "roblox.com" or host.endswith(".roblox.com"))

    def _headers(self, url, auth, method):
        h = {}
        if auth and self._cookie and self._is_roblox(url):
            h["Cookie"] = ".ROBLOSECURITY=" + self._cookie
            if method != "GET" and self._csrf:
                h["X-CSRF-TOKEN"] = self._csrf
        return h

    # ---- stopping: waits are interruptible and nothing new is sent once stopped
    def cancel_pending(self, permanent=False):
        """Stop every request that is waiting (pacing, rate-limit waits, retries) and refuse new ones until clear_cancel()."""
        self._closing = self._closing or permanent
        self._cancel.set()

    def invalidate(self):
        """The account is about to change: every request that is waiting or in flight is dropped (its answer is never used), and the
        pacing starts over for the next account."""
        self._epoch += 1
        self.rates.clear()
        with self._slow_lock:
            self._slow_next, self._slow_gap = 0.0, self.SLOW_GAP
        self._cancel.set()
        self._cancel.clear()

    def clear_cancel(self):
        if not self._closing:
            self._cancel.clear()

    def _sleep(self, seconds):
        if self._cancel.wait(seconds):
            raise Cancelled()

    def _pace(self):
        with self._lock:
            wait = self.MIN_GAP - (time.time() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.time()

    # POST requests that only read (look people up, ask who is online): they are not "changes" and must not be held to the slow pace
    READ_POSTS = ("users.roblox.com/v1/users", "users.roblox.com/v1/usernames/users", "presence.roblox.com/v1/presence/users",
                  "presence.roblox.com/v1/presence/last-online", "friends.roblox.com/v1/user/following-exists",
                  "apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles")

    @classmethod
    def _is_read(cls, method, url):
        if method == "GET":
            return True
        u = urlparse(url)
        return f"{u.hostname}{u.path}" in cls.READ_POSTS

    @classmethod
    def _is_slow(cls, method, url):
        """Requests held to the careful pace until Roblox has reported the route's limits: every change, and per-server lookups."""
        if not cls._is_read(method, url):
            return True
        return re.search(r"/v1/vip-servers/\d+$", urlparse(url).path) is not None

    def _slow_pace(self):
        """Wait for this request's turn: one every `_slow_gap` seconds, shared by all threads."""
        with self._slow_lock:
            now = time.time()
            slot = max(now, self._slow_next)
            self._slow_next = slot + self._slow_gap
        if slot > now:
            self._sleep(slot - now)

    def _slow_backoff(self, wait):
        """Roblox said 429 anyway: hold everything back for its retry-after time and slow the pace down for a while."""
        with self._slow_lock:
            self._slow_gap = min(self.SLOW_GAP_MAX, self._slow_gap * 1.5)
            self._slow_next = max(self._slow_next, time.time() + min(wait, 30) + self._slow_gap)

    RL_MIN_WAIT = 10          # a 429 that says nothing about when it ends: wait at least this long (5 s was not enough), more each time

    READ_BURST = 0.5          # a read route may use this share of its limit back to back; after that the rest is spread over the window

    MAX_WAIT_READ = 20        # a read that would have to wait longer than this for its route's limit is not sent (it fails with a clear message)
    MAX_WAIT_CHANGE = 150     # a change (a batch) may wait much longer; Stop can interrupt it

    COOLDOWN = 45             # seconds to wait when Roblox keeps saying 'too many requests' to a change
    PATIENCE = 2              # how many cool-downs a change gets before the error is passed on

    def _who(self):
        return (self.user or {}).get("name") or ("signing in" if self._cookie else "anonymous")

    def request(self, method, url, params=None, json_body=None, auth=True, retries=3, raw=False):
        """Returns (status, data, headers). Raises RobloxError for HTTP errors (4xx/5xx after retries).
        A change (POST/PATCH/DELETE) that is still refused with 429 after its quick retries is not given up on at once: it waits
        out a cool-down and tries again (twice), so a long batch survives a rate limit instead of stopping at the first refusal."""
        patience = self.PATIENCE if not self._is_read(method.upper(), url) else 0
        for round_ in range(patience + 1):
            try:
                return self._request_once(method, url, params, json_body, auth, retries, raw)
            except Cancelled:
                record_request(self._who(), method.upper(), url, params, None, None, 0, False, "cancelled (stopped, closed or account changed)")
                raise
            except RobloxError as e:
                if e.status != 429 or round_ >= patience or getattr(e, "local", False):
                    raise
                wait = self.COOLDOWN * (round_ + 1)
                log.warning("still rate limited on %s; cooling down for %d s", urlparse(url).path, wait)
                self._tell_rate(url, wait, False)
                self._slow_backoff(wait)
                record_request(self._who(), method.upper(), url, params, None, None, 0, False, f"cool-down: waiting {wait} s after repeated 429")
                self._sleep(wait)

    def _request_once(self, method, url, params=None, json_body=None, auth=True, retries=3, raw=False):
        method = method.upper()
        if not url.startswith("https://"):
            raise ValueError("Only https:// addresses are allowed")
        ep = self._epoch
        if self._cancel.is_set():
            raise Cancelled()
        refreshed_csrf = False
        slow = self._is_slow(method, url)
        key = self.rates.key(method, url)
        for attempt in range(retries + 1):
            if self.rates.known(key):
                read = self._is_read(method, url)
                self.rates.gate(key, self._sleep, self.MAX_WAIT_READ if read else self.MAX_WAIT_CHANGE,
                                lambda w: self._tell_rate(url, w, False, True), burst=self.READ_BURST if read else 0.0)     # Roblox told us this route's limits: follow them exactly
            elif slow:
                self._slow_pace()            # not known yet: the careful fixed pace for the first request on a changing route
            if self._cancel.is_set() or self._epoch != ep:
                raise Cancelled()
            self._pace()
            t_sent = time.time()
            try:
                r = self.session.request(method, url, params=params, json=json_body,
                                         headers=self._headers(url, auth, method), timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as e:
                record_request(self._who(), method, url, params, None, int((time.time() - t_sent) * 1000), attempt, slow, "network error: " + e.__class__.__name__)
                if attempt < retries:
                    self._sleep(1.5 * (attempt + 1))
                    continue
                raise RobloxError(0, "Network error: " + e.__class__.__name__) from None
            note = ""
            if r.status_code == 429:
                note = "retry-after " + str(r.headers.get("retry-after") or "?")
            elif r.status_code == 403 and r.headers.get("x-csrf-token") and method != "GET":
                note = "csrf token refresh"
            rate = self.rates.learn(key, r.headers, r.status_code, attempt, self.RL_MIN_WAIT)
            record_request(self._who(), method, url, params, r.status_code, int((time.time() - t_sent) * 1000), attempt, slow, note, rate)
            if self._epoch != ep:
                raise Cancelled()           # the account changed while this was in flight: its answer must not be used
            self.last_headers = dict(r.headers)
            tok = r.headers.get("x-csrf-token")
            if tok and method != "GET":
                self._csrf = tok
            if r.status_code == 403 and tok and not refreshed_csrf and method != "GET":
                refreshed_csrf = True       # Roblox hands out the token on the first rejected write: just retry
                continue
            if slow and r.status_code == 429:
                self._slow_backoff(float(r.headers.get("retry-after") or 5))
            elif slow and r.status_code < 400:
                self._slow_gap = max(self.SLOW_GAP, self._slow_gap * 0.95)      # recover slowly after having slowed down
            if r.status_code == 429 and attempt < retries:
                known = self.rates.known(key)
                wait = max(1.0, self.rates.wait_left(key)) if known else float(r.headers.get("retry-after") or (2 ** (attempt + 1)))
                log.warning("rate limited on %s; waiting %.0f s", urlparse(url).path, wait)
                self._tell_rate(url, min(wait, 60), False)
                if not known:
                    self._sleep(min(wait, 30))
                continue                     # (with route data, the gate at the top of the loop waits it out)
            if r.status_code == 429:
                self._tell_rate(url, 0, True)
            if r.status_code >= 500 and attempt < retries:
                self._sleep(1.5 * (attempt + 1))
                continue
            break
        try:
            data = r.json() if r.content else None
        except ValueError:
            data = r.text if raw else None
        if r.status_code >= 400:
            msg, code = "", None
            if isinstance(data, dict) and data.get("errors"):
                e0 = data["errors"][0]
                msg, code = e0.get("userFacingMessage") or e0.get("message") or "", e0.get("code")
            log.info("%s %s -> %s %s", method, urlparse(url).path, r.status_code, redact(msg))
            raise RobloxError(r.status_code, msg or r.reason or "request failed", code, data)
        return r.status_code, data, dict(r.headers)

    def _tell_rate(self, url, wait, gave_up, proactive=False):
        """proactive: the app is waiting by itself to stay within Roblox's limit (Roblox did not refuse anything)."""
        for hook in ([self.rate_hook] if self.rate_hook else []) + list(self.rate_hooks):
            try:
                hook(urlparse(url).path, wait, gave_up, proactive)
            except Exception:       # noqa: BLE001 - a display problem must never break a request
                pass

    def get(self, url, params=None, **kw):
        return self.request("GET", url, params=params, **kw)[1]

    def post(self, url, body=None, **kw):
        return self.request("POST", url, json_body=body, **kw)[1]

    def patch(self, url, body=None, **kw):
        return self.request("PATCH", url, json_body=body, **kw)[1]

    def delete(self, url, body=None, **kw):
        return self.request("DELETE", url, json_body=body, **kw)[1]

    # -- login
    def login(self):
        """Check the cookie and remember who it belongs to. Raises RobloxError if it is not valid."""
        self.user = self.get("https://users.roblox.com/v1/users/authenticated")
        log.info("signed in as user %s", self.user.get("id"))
        return self.user

    def logout(self):
        self._cookie, self._csrf, self.user = "", "", None
        self.session.cookies.clear()

    # ============================================================ convenience calls
    def paged(self, url, params=None, limit=100, max_pages=20):
        """Follow nextPageCursor until the end (or max_pages). Yields items."""
        params = dict(params or {})
        params.setdefault("limit", limit)
        for _ in range(max_pages):
            d = self.get(url, params)
            for item in d.get("data", []):
                yield item
            cur = d.get("nextPageCursor")
            if not cur:
                return
            params["cursor"] = cur

    def users_by_ids(self, ids):
        """User dicts (id, name, displayName ...) for ids. Names already known (kept in names.json) are not asked for again; the rest go
        100 per request. Roblox limits this route in a way its headers do not show (see RateTable), so callers with many ids should
        use resolve_names() in small steps instead."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        found = {i: names.get(i) for i in ids}
        for i in ids:
            if found[i] and found[i].get("hasVerifiedBadge") is None:     # saved from the quick lookup: the verified badge is not known
                found[i] = None
        todo = [i for i in ids if not found[i]]
        for k in range(0, len(todo), 100):
            data = self.post("https://users.roblox.com/v1/users", {"userIds": todo[k:k + 100], "excludeBannedUsers": False}).get("data", [])
            names.put_many(data)
            for u in data:
                found[u["id"]] = u
        return [found[i] for i in ids if found.get(i)]

    PROFILES_URL = "https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles"

    def lookup_names(self, ids):
        """Names for many ids, fast: Roblox's profile route takes 200 ids per request and honestly reports its limit (200 requests a
        minute), unlike the older user route. Saved names are not asked for again. Falls back to the older route if this one fails.
        Returns user dicts with name, displayName and hasVerifiedBadge."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        found = {i: names.get(i) for i in ids}
        for i in ids:
            if found[i] and found[i].get("hasVerifiedBadge") is None:       # saved by an older version without the badge: ask again
                found[i] = None
        todo = [i for i in ids if not found[i]]
        for k in range(0, len(todo), 200):
            chunk = todo[k:k + 200]
            got = []
            try:
                d = self.post(self.PROFILES_URL, {"userIds": chunk, "fields": ["names.username", "names.displayName", "isVerified"]})
                for p in (d or {}).get("profileDetails", []):
                    n = p.get("names") or {}
                    if p.get("userId") and n.get("username"):
                        got.append({"id": p["userId"], "name": n["username"], "displayName": n.get("displayName") or n["username"],
                                    "hasVerifiedBadge": bool(p.get("isVerified"))})
            except Cancelled:
                raise
            except RobloxError as e:
                if e.status in (401, 403) or getattr(e, "local", False):
                    raise
            if len(got) < len(chunk) // 2:                      # empty or partial answer: ask the older route (100 per request)
                missing = [i for i in chunk if i not in {g["id"] for g in got}]
                got += [u for u in self.users_by_ids(missing)]
            names.put_many(got)
            for u in got:
                found[u["id"]] = names.get(u["id"]) or u
        return [found[i] for i in ids if found.get(i)]

    def cached_names(self, items):
        """Fill name/displayName of list items from the saved names. Returns the ids that are still unknown."""
        missing = []
        for it in items:
            if it.get("id") and not it.get("name"):
                u = names.get(it["id"])
                if u:
                    it["name"], it["displayName"] = u["name"], u["displayName"]
                else:
                    missing.append(it["id"])
        return missing

    def user_by_name(self, name):
        d = self.post("https://users.roblox.com/v1/usernames/users", {"usernames": [name], "excludeBannedUsers": False}).get("data", [])
        return d[0] if d else None

    def presence(self, ids):
        out = []
        ids = list(dict.fromkeys(ids))
        for i in range(0, len(ids), 100):
            out += self.post("https://presence.roblox.com/v1/presence/users", {"userIds": ids[i:i + 100]}).get("userPresences", [])
        return out

    def friends(self, user_id=None):
        """Friends with their names. The friends list itself may omit names, so they are looked up by id."""
        uid = user_id or self.user["id"]
        items = self.get(f"https://friends.roblox.com/v1/users/{uid}/friends").get("data", [])
        ids = [f["id"] for f in items if f.get("id")]
        info = {u["id"]: u for u in self.lookup_names(ids)} if ids else {}
        out = []
        for f in items:
            u = info.get(f.get("id"), {})
            out.append({"id": f["id"], "name": u.get("name") or f.get("name") or "", "displayName": u.get("displayName") or f.get("displayName") or u.get("name") or "",
                        "hasVerifiedBadge": u.get("hasVerifiedBadge", f.get("hasVerifiedBadge", False)), "isOnline": f.get("isOnline")})
        return out

    # ---- people: requests, followers, blocked, search
    def _people(self, url, max_pages=100, resolve=True):
        """Users from a paged list. Roblox's lists leave the names blank, so they are filled from the saved names; with resolve=True the
        rest are looked up now (fine for a few), with resolve=False they are left blank for the caller to look up gradually."""
        items = list(self.paged(url, limit=100, max_pages=max_pages))
        missing = self.cached_names(items)
        if missing and resolve:
            info = {u["id"]: u for u in self.lookup_names(missing)}
            for i in items:
                u = info.get(i.get("id"), {})
                if not i.get("name"):
                    i["name"], i["displayName"] = u.get("name", ""), u.get("displayName", "")
        return items

    def friend_requests(self):
        return self._people("https://friends.roblox.com/v1/my/friends/requests", resolve=False)      # names are filled in gradually by the list

    def friend_request_count(self):
        return int(self.get("https://friends.roblox.com/v1/user/friend-requests/count").get("count") or 0)

    def accept_friend_request(self, uid):
        return self.post(f"https://friends.roblox.com/v1/users/{int(uid)}/accept-friend-request", None)

    def decline_friend_request(self, uid):
        return self.post(f"https://friends.roblox.com/v1/users/{int(uid)}/decline-friend-request", None)

    def decline_all_friend_requests(self):
        return self.post("https://friends.roblox.com/v1/user/friend-requests/decline-all", None)

    def send_friend_request(self, uid):
        return self.post(f"https://friends.roblox.com/v1/users/{int(uid)}/request-friendship", {"friendshipOriginSourceType": "UserProfile"})

    def followers(self, user_id=None):
        return self._people(f"https://friends.roblox.com/v1/users/{int(user_id or self.user['id'])}/followers", resolve=False)

    def followings(self, user_id=None):
        return self._people(f"https://friends.roblox.com/v1/users/{int(user_id or self.user['id'])}/followings", resolve=False)

    def follow(self, uid):
        return self.post(f"https://friends.roblox.com/v1/users/{int(uid)}/follow", None)

    def unfollow(self, uid):
        return self.post(f"https://friends.roblox.com/v1/users/{int(uid)}/unfollow", None)

    def blocked_users(self):
        """Who you have blocked. Roblox has moved this list around, so the known places are tried in turn."""
        tries = ["https://apis.roblox.com/user-blocking-api/v1/users/me/blocked-users",
                 "https://accountsettings.roblox.com/v1/users/get-detailed-blocked-users",
                 "https://accountsettings.roblox.com/v1/users/blocked-users"]
        last = None
        for url in tries:
            try:
                d = self.get(url, retries=1)
            except RobloxError as e:
                last = e
                if e.status in (401, 403):
                    raise
                continue
            lst = d.get("blockedUsers") or d.get("data") or d.get("users") or (d if isinstance(d, list) else [])
            out = []
            for b in lst:
                uid = b.get("userId") or b.get("id")
                if uid:
                    out.append({"id": int(uid), "name": b.get("name") or b.get("username") or "", "displayName": b.get("displayName") or "",
                                "blockedAt": b.get("blockedTimestamp") or b.get("blockedAt") or ""})
            missing = [o["id"] for o in out if not o["name"]]
            if missing:
                info = {u["id"]: u for u in self.lookup_names(missing)}
                for o in out:
                    u = info.get(o["id"], {})
                    o["name"] = o["name"] or u.get("name", "")
                    o["displayName"] = o["displayName"] or u.get("displayName", "")
            return out
        raise RobloxError(last.status if last else 0, "Roblox did not return your blocked list (it may have moved it)")

    def block_user(self, uid):
        return self.post(f"https://apis.roblox.com/user-blocking-api/v1/users/{int(uid)}/block-user", None)

    def unblock_user(self, uid):
        return self.post(f"https://apis.roblox.com/user-blocking-api/v1/users/{int(uid)}/unblock-user", None)

    def search_users(self, text):
        """Users matching a name: the exact username first, then Roblox's search."""
        text = (text or "").strip()
        out, seen = [], set()
        if text.isdigit():
            try:
                d = self.user_detail(int(text))
                if d and d.get("id"):
                    out.append(d)
                    seen.add(d["id"])
            except RobloxError:
                pass
        exact = self.user_by_name(text) if text and not text.isdigit() else None
        if exact:
            out.append(exact)
            seen.add(exact["id"])
        try:
            for u in self.get("https://users.roblox.com/v1/users/search", {"keyword": text, "limit": 25}, auth=False).get("data", []):
                if u["id"] not in seen:
                    out.append(u)
                    seen.add(u["id"])
        except RobloxError:
            pass
        return out

    def unfriend(self, user_id):
        """Remove one friend. This cannot be undone from here."""
        return self.post(f"https://friends.roblox.com/v1/users/{int(user_id)}/unfriend", None)

    def robux(self):
        return self.get("https://economy.roblox.com/v1/user/currency").get("robux")

    def user_detail(self, uid):
        return self.get(f"https://users.roblox.com/v1/users/{int(uid)}", auth=False)

    def counts(self, uid):
        base = "https://friends.roblox.com/v1/users/%d/%s/count"
        out = {}
        for key, part in (("friends", "friends"), ("followers", "followers"), ("following", "followings")):
            try:
                out[key] = self.get(base % (uid, part), auth=False).get("count")
            except RobloxError:
                out[key] = None
        return out

    def games_by_universe(self, universe_ids):
        ids = [int(i) for i in dict.fromkeys(universe_ids) if i]
        out = {}
        for i in range(0, len(ids), 50):
            for g in self.get("https://games.roblox.com/v1/games", {"universeIds": ",".join(map(str, ids[i:i + 50]))}, auth=False).get("data", []):
                out[g["id"]] = g
        return out

    def place_universe(self, place_id):
        return self.get(f"https://apis.roblox.com/universes/v1/places/{int(place_id)}/universe", auth=False).get("universeId")

    # ---- the home page / search of games (public data: no sign-in needed)
    def omni_search_games(self, text, session_id, token=""):
        """([game cards], next page token) for a search of games."""
        params = {"searchQuery": text, "sessionId": session_id, "pageType": "all"}
        if token:
            params["pageToken"] = token
        d = self.get("https://apis.roblox.com/search-api/omni-search", params, auth=False)
        cards = []
        for g in d.get("searchResults", []):
            if g.get("contentGroupType") == "Game":
                cards += [c for c in (game_card(x) for x in g.get("contents", [])) if c]
        return cards, d.get("nextPageToken") or ""

    def discover_sorts(self, session_id):
        """[{'id', 'name', 'games': [cards]}] the rows of Roblox's own Discover page (Top Trending, Up-and-Coming ...)."""
        d = self.get("https://apis.roblox.com/explore-api/v1/get-sorts", {"sessionId": session_id, "device": "computer", "country": "all"}, auth=False)
        out = []
        for s in d.get("sorts", []):
            if s.get("contentType") != "Games":
                continue
            cards = [c for c in (game_card(x) for x in s.get("games", [])) if c]
            if cards:
                out.append({"id": s.get("sortId") or "", "name": s.get("sortDisplayName") or s.get("sortId") or "", "games": cards})
        return out

    def game_votes(self, universe_ids):
        """{universe id: (likes, dislikes)}"""
        ids = [int(i) for i in dict.fromkeys(universe_ids) if i]
        out = {}
        for i in range(0, len(ids), 100):
            for v in self.get("https://games.roblox.com/v1/games/votes", {"universeIds": ",".join(map(str, ids[i:i + 100]))}, auth=False).get("data", []):
                out[int(v["id"])] = (int(v.get("upVotes") or 0), int(v.get("downVotes") or 0))
        return out

    def game_favorites(self, universe_id):
        return int(self.get(f"https://games.roblox.com/v1/games/{int(universe_id)}/favorites/count", auth=False).get("favoritesCount") or 0)

    def game_icons(self, universe_ids, size="150x150"):
        """{universe id: image url}"""
        ids = [int(i) for i in dict.fromkeys(universe_ids) if i]
        out = {}
        for i in range(0, len(ids), 100):
            try:
                d = self.get("https://thumbnails.roblox.com/v1/games/icons", {"universeIds": ",".join(map(str, ids[i:i + 100])), "size": size, "format": "Png", "isCircular": "false"}, auth=False)
            except RobloxError:
                continue
            for x in d.get("data", []):
                if x.get("imageUrl"):
                    out[int(x["targetId"])] = x["imageUrl"]
        return out

    def game_cover(self, universe_id):
        """The game's first picture (768 x 432) as an image url, or ''."""
        d = self.get("https://thumbnails.roblox.com/v1/games/multiget/thumbnails",
                     {"universeIds": int(universe_id), "size": "768x432", "format": "Png", "count": 1, "isCircular": "false"}, auth=False)
        for g in d.get("data", []):
            for th in g.get("thumbnails", []):
                if th.get("imageUrl"):
                    return th["imageUrl"]
        return ""

    def search_groups(self, text, limit=10):
        return self.get("https://groups.roblox.com/v1/groups/search", {"keyword": text, "limit": limit}, auth=False).get("data", [])

    def game_servers(self, place_id, sort="Asc", cursor=None, limit=50, exclude_full=True):
        """([servers], next cursor): the public servers of a game, fewest players first (Asc) or most (Desc). Public data."""
        params = {"sortOrder": sort, "limit": limit, "excludeFullGames": "true" if exclude_full else "false"}
        if cursor:
            params["cursor"] = cursor
        d = self.get(f"https://games.roblox.com/v1/games/{int(place_id)}/servers/Public", params, auth=False)
        servers = [{"id": s["id"], "playing": int(s.get("playing") or 0), "max": int(s.get("maxPlayers") or 0), "ping": s.get("ping"), "fps": s.get("fps")}
                   for s in d.get("data", []) if isinstance(s, dict) and safe_code(s.get("id"))]
        return servers, d.get("nextPageCursor") or ""

    JOIN_WAIT = 1.25         # seconds between the asks of server_info while Roblox says 'not ready'
    JOIN_RETRY = (0, 2, 22)  # the statuses of a join answer that mean 'ask again'

    def server_info(self, place_id, job_id, tries=8):
        """What Roblox's join answer says about one public server: {'address': its public address, 'started_ms': when it started (Unix milliseconds) or None, 'dc': the id of its
        data centre or None, 'place_version': the version of the place it runs or None}. It is the call the website makes when Play is pressed; nothing is joined. Only these
        values are taken out of the answer: its tickets are never kept or logged. Needs the sign-in. The first answers may say 'not ready', so it asks again a few times."""
        import uuid
        job = safe_code(job_id)
        if not job:
            raise ValueError("odd server id")
        status = None
        for k in range(tries):
            d = self.post("https://gamejoin.roblox.com/v1/join-game-instance",
                          {"placeId": int(place_id), "isTeleport": False, "gameId": job, "gameJoinAttemptId": str(uuid.uuid4())})
            d = d if isinstance(d, dict) else {}
            script = d.get("joinScript")
            if isinstance(script, str):
                try:
                    script = json.loads(script)
                except ValueError:
                    script = None
            if isinstance(script, dict):
                return _join_info(script)
            status = d.get("status")
            if status in self.JOIN_RETRY and k + 1 < tries:
                self._sleep(self.JOIN_WAIT)
                continue
            break
        if status in self.JOIN_RETRY or status is None:
            raise RobloxError(0, "Roblox is still getting this server ready (it may be full or just closed)")
        raise RobloxError(0, f"Roblox would not let this server be looked at (status {status})")

    def game_favorite_state(self, universe_id):
        """True if the account in use has favorited the game (needs the sign-in)."""
        return bool(self.get(f"https://games.roblox.com/v1/games/{int(universe_id)}/favorites").get("isFavorited"))

    def set_game_favorite(self, universe_id, on):
        return self.post(f"https://games.roblox.com/v1/games/{int(universe_id)}/favorites", {"isFavorited": bool(on)})

    def favorite_games(self, user_id=None, limit=50):
        """[game cards] the account's favorite games (as far as its privacy settings show them)."""
        uid = user_id or self.user["id"]
        d = self.get(f"https://games.roblox.com/v2/users/{int(uid)}/favorite/games", {"limit": limit, "sortOrder": "Desc"}, auth=False)
        out = []
        for g in d.get("data", []):
            if isinstance(g, dict) and g.get("id"):
                out.append({"universeId": int(g["id"]), "placeId": (g.get("rootPlace") or {}).get("id"), "name": str(g.get("name") or ""), "playing": 0, "up": 0, "down": 0,
                            "creator": (g.get("creator") or {}).get("name", ""), "verified": False, "age": "", "genre": ""})
        return out

    def friends_in_games(self):
        """[{'id', 'name', 'displayName', 'place', 'job', 'universe', 'game'}] the friends who are in a game right now (and which server they are in)."""
        friends = {f["id"]: f for f in self.friends()}
        out = []
        for p in self.presence(list(friends)):
            place = p.get("rootPlaceId") or p.get("placeId")
            if p.get("userPresenceType") == 2 and place:
                f = friends.get(p.get("userId"), {})
                out.append({"id": p.get("userId"), "name": f.get("name", ""), "displayName": f.get("displayName", ""), "place": place, "job": p.get("gameId"),
                            "universe": p.get("universeId"), "game": p.get("lastLocation") or ""})
        return out

    def game_info(self, universe_id):
        d = self.get("https://games.roblox.com/v1/games", {"universeIds": int(universe_id)}, auth=False).get("data", [])
        return d[0] if d else None

    # -- groups
    def my_groups(self):
        return self.get(f"https://groups.roblox.com/v1/users/{self.user['id']}/groups/roles").get("data", [])

    def group_membership(self, gid):
        return self.get(f"https://groups.roblox.com/v1/groups/{int(gid)}/membership")

    def group_roles(self, gid):
        return self.get(f"https://groups.roblox.com/v1/groups/{int(gid)}/roles").get("roles", [])

    def group_members(self, gid, role_id=None, cursor=None, limit=50, sort="Asc"):
        if role_id:
            url, params = f"https://groups.roblox.com/v1/groups/{int(gid)}/roles/{int(role_id)}/users", {}
        else:
            url, params = f"https://groups.roblox.com/v1/groups/{int(gid)}/users", {}
        params.update({"limit": limit, "sortOrder": sort})
        if cursor:
            params["cursor"] = cursor
        return self.get(url, params)

    def group_search_members(self, gid, keyword, cursor=None, limit=100):
        """Members of a group whose username or display name matches `keyword`, searched by Roblox (so people that 'Load more' has not reached yet are found)."""
        params = {"keyword": keyword, "limit": limit, "sortOrder": "Asc"}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"https://groups.roblox.com/v1/groups/{int(gid)}/search-members", params)

    def group_join_requests(self, gid, cursor=None, limit=50):
        params = {"limit": limit, "sortOrder": "Asc"}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"https://groups.roblox.com/v1/groups/{int(gid)}/join-requests", params)

    def accept_join_requests(self, gid, user_ids):
        return self.post(f"https://groups.roblox.com/v1/groups/{int(gid)}/join-requests", {"UserIds": list(user_ids)})

    def decline_join_requests(self, gid, user_ids):
        return self.delete(f"https://groups.roblox.com/v1/groups/{int(gid)}/join-requests", {"UserIds": list(user_ids)})

    def set_rank(self, gid, user_id, role_id):
        return self.patch(f"https://groups.roblox.com/v1/groups/{int(gid)}/users/{int(user_id)}", {"roleId": int(role_id)})

    def groups_created(self, ids):
        """{group id: ISO creation time} for many groups, 100 per request (public, no sign-in needed)."""
        out, ids = {}, [int(i) for i in ids]
        for k in range(0, len(ids), 100):
            d = self.get("https://groups.roblox.com/v2/groups", {"groupIds": ",".join(map(str, ids[k:k + 100]))}, auth=False)
            for g in (d or {}).get("data", []):
                out[g["id"]] = g.get("created")
        return out

    def leave_group(self, gid):
        """Leave a group (not possible for a group you own)."""
        return self.delete(f"https://groups.roblox.com/v1/groups/{int(gid)}/users/{int(self.user['id'])}")

    def kick(self, gid, user_id):
        return self.delete(f"https://groups.roblox.com/v1/groups/{int(gid)}/users/{int(user_id)}")

    def ban(self, gid, user_id):
        return self.post(f"https://groups.roblox.com/v1/groups/{int(gid)}/bans/{int(user_id)}", {})

    def audit_log(self, gid, cursor=None, limit=50):
        params = {"limit": limit, "sortOrder": "Desc"}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"https://groups.roblox.com/v1/groups/{int(gid)}/audit-log", params)

    def set_group_description(self, gid, text):
        return self.patch(f"https://groups.roblox.com/v1/groups/{int(gid)}/description", {"newDescription": text})

    def set_group_status(self, gid, message):
        return self.patch(f"https://groups.roblox.com/v1/groups/{int(gid)}/status", {"message": message})

    # -- VIP (private) servers
    def private_servers(self, place_id):
        """Private servers of a game that this account can see (its own, and others it may join)."""
        return list(self.paged(f"https://games.roblox.com/v1/games/{int(place_id)}/private-servers", limit=100, max_pages=5))

    def vip_servers_listed(self, place_id, limit=100):
        """Private servers listed on the game page (the game's 'Private servers' tab)."""
        return list(self.paged(f"https://games.roblox.com/v1/games/{int(place_id)}/servers/VIP", limit=limit, max_pages=5))

    def vip_server(self, vip_id, retries=3):
        return self.get(f"https://games.roblox.com/v1/vip-servers/{int(vip_id)}", retries=retries)

    def my_private_servers(self, max_pages=10):
        """Every private server this account owns, across all games (Roblox's own 'my private servers' list)."""
        combos = [("vip-servers", "MyPrivateServers"), ("vip-servers", None), ("private-servers", "MyPrivateServers"), ("private-servers", None)]
        if getattr(self, "_mps_combo", None):
            combos.remove(self._mps_combo) if self._mps_combo in combos else None
            combos.insert(0, self._mps_combo)
        last = None
        for path, tab in combos:
            params = {"itemsPerPage": 25}
            if tab:
                params["privateServersTab"] = tab
            items, cursor = [], None
            try:
                for _ in range(max_pages):
                    q = dict(params)
                    if cursor:
                        q["cursor"] = cursor
                    d = self.get(f"https://games.roblox.com/v1/{path}/my-private-servers", q)
                    items += d.get("data", []) if isinstance(d, dict) else []
                    cursor = d.get("nextPageCursor") if isinstance(d, dict) else None
                    if not cursor:
                        break
            except RobloxError as e:
                last = e
                if e.status in (401, 403):
                    raise
                continue
            self._mps_combo = (path, tab)
            if items:
                log.info("my-private-servers: %d item(s), fields: %s", len(items), ",".join(sorted(items[0].keys())))
            return items
        raise last or RobloxError(0, "could not list your private servers")

    def place_names(self, place_ids):
        """{place id: game name} for places (a place's name is its game's name)."""
        ids = [int(p) for p in dict.fromkeys(place_ids) if p]
        out = {}
        for i in range(0, len(ids), 50):
            try:
                d = self.get("https://games.roblox.com/v1/games/multiget-place-details", {"placeIds": ids[i:i + 50]})
            except RobloxError:
                continue
            for p in d if isinstance(d, list) else d.get("data", []):
                out[int(p.get("placeId") or p.get("id"))] = p.get("name") or p.get("sourceName") or ""
        return out

    def can_invite(self, user_id):
        return self.get(f"https://games.roblox.com/v1/vip-server/can-invite/{int(user_id)}")

    def set_vip_permissions(self, vip_id, friends_allowed, users, current=None):
        """Change who may join a private server. Roblox does not document the request body, so the likely shapes are
        tried in order (each makes the same change); returns the name of the one Roblox accepted."""
        cur = current or {}
        base = {"clanAllowed": bool(cur.get("clanAllowed", False)), "enemyClanId": cur.get("enemyClanId"), "friendsAllowed": bool(friends_allowed)}
        full = [{"id": u["id"], "name": u.get("name", ""), "displayName": u.get("displayName", u.get("name", ""))} for u in users]
        variants = [("users as objects", {**base, "users": full}), ("users as ids", {**base, "users": [u["id"] for u in users]}),
                    ("minimal", {"friendsAllowed": bool(friends_allowed), "users": [u["id"] for u in users]})]
        remembered = getattr(self, "_perm_variant", None)
        if remembered:
            variants.sort(key=lambda v: v[0] != remembered)
        last = None
        for name, body in variants:
            try:
                self.patch(f"https://games.roblox.com/v1/vip-servers/{int(vip_id)}/permissions", body)
                self._perm_variant = name
                log.info("vip permissions accepted as '%s'", name)
                return name
            except RobloxError as e:
                if e.status not in (400, 422):
                    raise
                last = e
                log.info("vip permissions refused as '%s': %s", name, e)
        raise last

    def headshots(self, user_ids, size="48x48"):
        """{user id: image url} for avatar headshots (public)."""
        ids = [int(i) for i in dict.fromkeys(user_ids)]
        out = {}
        for i in range(0, len(ids), 100):
            try:
                d = self.get("https://thumbnails.roblox.com/v1/users/avatar-headshot",
                             {"userIds": ",".join(map(str, ids[i:i + 100])), "size": size, "format": "Png", "isCircular": "true"}, auth=False)
            except RobloxError:
                continue
            for t in d.get("data", []):
                if t.get("imageUrl"):
                    out[t["targetId"]] = t["imageUrl"]
        return out

    IMAGE_GAP = 0.25          # seconds between two image downloads: about 4 a second instead of a burst of dozens

    def _image_pace(self):
        with self._slow_lock:
            now = time.time()
            slot = max(now, getattr(self, "_image_next", 0.0))
            self._image_next = slot + self.IMAGE_GAP
        if slot > now:
            self._sleep(slot - now)

    def fetch_bytes(self, url):
        """Download a public image (the cookie is never sent: this is not a roblox.com address). Paced, and stoppable."""
        if not url.startswith("https://"):
            return b""
        self._image_pace()
        t0 = time.time()
        try:
            r = requests.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT})
            record_request(self._who(), "GET", url, None, r.status_code, int((time.time() - t0) * 1000), 0, False,
                           "image" + (", rate-limited: backing off" if r.status_code == 429 else ""))
            if r.status_code == 429:
                with self._slow_lock:
                    self._image_next = max(getattr(self, "_image_next", 0.0), time.time() + 10)
            return r.content if r.ok else b""
        except requests.RequestException as e:
            record_request(self._who(), "GET", url, None, None, int((time.time() - t0) * 1000), 0, False, "network error: " + e.__class__.__name__)
            return b""

    def update_vip_server(self, vip_id, **fields):
        return self.patch(f"https://games.roblox.com/v1/vip-servers/{int(vip_id)}", fields)

    def transaction_totals(self, time_frame="Month"):
        return self.get(f"https://economy.roblox.com/v2/users/{int(self.user['id'])}/transaction-totals",
                        {"timeFrame": time_frame, "transactionType": "summary"})

    def transactions(self, kind, max_pages=3, deadline=None):
        """Your newest transactions of one kind (Sale, Purchase, GroupPayout ...), newest first."""
        base = f"https://economy.roblox.com/v2/users/{int(self.user['id'])}/transactions"
        items, cursor = [], None
        for _ in range(max_pages):
            params = {"transactionType": kind, "limit": 100, "sortOrder": "Desc"}
            if cursor:
                params["cursor"] = cursor
            d = self.get(base, params, retries=1)
            items += d.get("data", [])
            cursor = d.get("nextPageCursor")
            if not cursor or (deadline and time.time() > deadline):
                break
        return items

    def email_status(self):
        d = self.get("https://accountsettings.roblox.com/v1/email")
        return {"address": d.get("emailAddress") or "", "verified": bool(d.get("verified"))}

    def probe_limits(self, progress=None):
        """Learn the rate limit of every read-only route the app uses, with one request each (Roblox reports a route's limit in its
        answers). Routes that are already known are skipped. Changing routes (unfriend, leave, switch on ...) cannot be probed without
        changing something: their limits are learned the first time they are used. Returns how many routes were learned."""
        uid = int(self.user["id"])
        routes = [
            ("GET", f"https://users.roblox.com/v1/users/{uid}", None, None),
            ("GET", "https://users.roblox.com/v1/users/search", {"keyword": "roblox", "limit": 10}, None),
            ("POST", "https://users.roblox.com/v1/users", None, {"userIds": [uid]}),
            ("POST", "https://presence.roblox.com/v1/presence/users", None, {"userIds": [uid]}),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/friends", None, None),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/friends/count", None, None),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/followers/count", None, None),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/followings/count", None, None),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/followers", {"limit": 10}, None),
            ("GET", f"https://friends.roblox.com/v1/users/{uid}/followings", {"limit": 10}, None),
            ("GET", "https://friends.roblox.com/v1/user/friend-requests/count", None, None),
            ("GET", "https://friends.roblox.com/v1/my/friends/requests", {"limit": 10}, None),
            ("GET", f"https://groups.roblox.com/v1/users/{uid}/groups/roles", None, None),
            ("GET", "https://games.roblox.com/v1/vip-servers/my-private-servers", {"itemsPerPage": 10, "privateServersTab": "MyPrivateServers"}, None),
            ("GET", "https://games.roblox.com/v1/games", {"universeIds": "383310974"}, None),
            ("GET", "https://games.roblox.com/v1/games/multiget-place-details", {"placeIds": 920587237}, None),
            ("GET", "https://thumbnails.roblox.com/v1/users/avatar-headshot", {"userIds": uid, "size": "48x48", "format": "Png", "isCircular": "true"}, None),
            ("GET", f"https://premiumfeatures.roblox.com/v1/users/{uid}/validate-membership", None, None),
            ("GET", "https://accountsettings.roblox.com/v1/email", None, None),
            ("GET", "https://economy.roblox.com/v1/user/currency", None, None),
            ("GET", f"https://economy.roblox.com/v2/users/{uid}/transaction-totals", {"timeFrame": "Month", "transactionType": "summary"}, None),
            ("GET", f"https://economy.roblox.com/v2/users/{uid}/transactions", {"transactionType": "Sale", "limit": 10}, None),
        ]
        learned = 0
        for n, (method, url, params, body) in enumerate(routes):
            if progress:
                progress(n, len(routes))
            if self.rates.known(self.rates.key(method, url)):
                continue
            try:
                self.request(method, url, params, body, retries=0)
            except Cancelled:
                raise
            except RobloxError:
                pass                       # an error answer still carries the limit headers
            learned += self.rates.known(self.rates.key(method, url))
        return learned

    def has_premium(self, user_id=None):
        """True if the account has a Roblox Plus (Premium) membership."""
        uid = user_id or self.user["id"]
        return bool(self.get(f"https://premiumfeatures.roblox.com/v1/users/{int(uid)}/validate-membership", retries=1))

    def renew_vip_server(self, vip_id, price):
        """Turn a VIP server's subscription on again. Roblox refuses if the real price differs from `price`."""
        return self.patch(f"https://games.roblox.com/v1/vip-servers/{int(vip_id)}/subscription", {"active": True, "price": int(price)})

    def create_vip_server(self, universe_id, name, expected_price):
        return self.post(f"https://games.roblox.com/v1/games/vip-servers/{int(universe_id)}",
                         {"name": name, "expectedPrice": int(expected_price)})


# ------------------------------------------------------------------ looking for friends' VIP servers
# ------------------------------------------------------------------ avatar cache (public pictures: no secrets in them)
AVATAR_DIR = STATE_DIR / "avatars"
AVATAR_MAX_AGE = 7 * 24 * 3600


def cached_avatar(uid):
    """The saved headshot of a user (bytes), if one is fresh enough, else b''."""
    f = AVATAR_DIR / f"{int(uid)}.png"
    try:
        if time.time() - f.stat().st_mtime < AVATAR_MAX_AGE:
            return f.read_bytes()
    except OSError:
        pass
    return b""


def save_avatar(uid, data):
    if not data:
        return
    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        (AVATAR_DIR / f"{int(uid)}.png").write_bytes(data)
    except OSError:
        pass


_CODE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _join_info(script):
    """The few values wanted from a join script (PascalCase as Roblox sends them, or camelCase)."""
    def pick(*names):
        for n in names:
            if n in script:
                return script[n]
        return None
    address = None
    for key in (("UdmuxEndpoints", "udmuxEndpoints"), ("ServerConnections", "serverConnections")):
        for e in pick(*key) or []:
            a = (e.get("Address") or e.get("address")) if isinstance(e, dict) else None
            if isinstance(a, str) and _public_ipv4(a):
                address = a.strip()
                break
        if address:
            break
    if not address:
        raise RobloxError(0, "Roblox did not give a public address for this server")

    def whole(v):
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None
    started = whole(pick("ServerClaimedTime", "serverClaimedTime"))
    if started and not 946684800000 < started < (time.time() + 86400) * 1000:           # (milliseconds since 1970, and not in the future)
        started = None
    return {"address": address, "started_ms": started, "dc": whole(pick("DataCenterId", "dataCenterId")), "place_version": whole(pick("PlaceVersion", "placeVersion"))}


def _public_ipv4(text):
    import ipaddress
    try:
        ip = ipaddress.ip_address(text.strip())
    except ValueError:
        return False
    return ip.version == 4 and ip.is_global


def safe_code(code):
    """A private server link code or a server id, only if it looks like one (letters, digits, - and _): it goes into a link that starts the launcher."""
    return code if isinstance(code, str) and _CODE.fullmatch(code) else None


def launcher_url(place_id, link_code=None, job_id=None):
    """The address that makes the Roblox launcher start and join: a game (placeId), a private/VIP server (placeId + linkCode) or one running server (gameInstanceId)."""
    url = f"roblox://experiences/start?placeId={int(place_id)}"
    if link_code:
        if not safe_code(link_code):
            raise ValueError("the join code does not look like a join code")
        url += f"&linkCode={link_code}"
    elif job_id:
        if not safe_code(job_id):
            raise ValueError("the server id does not look like a server id")
        url += f"&gameInstanceId={job_id}"
    return url


def link_code_of(url):
    """(place id or None, private server link code or None) from a roblox.com join link such as https://www.roblox.com/games/123?privateServerLinkCode=ABC."""
    from urllib.parse import parse_qs, urlparse
    try:
        u = urlparse(url or "")
        code = safe_code((parse_qs(u.query).get("privateServerLinkCode") or [None])[0])
        m = re.search(r"/games/(\d+)", u.path)
        return (int(m.group(1)) if m else None), code
    except ValueError:
        return None, None


def game_card(c):
    """One game as the home page and the search describe it (the fields differ a little), in one shape. Sponsored entries (ads) are not games: None."""
    if not isinstance(c, dict) or c.get("isSponsored") or not (c.get("universeId") or c.get("id")):
        return None
    return {"universeId": int(c.get("universeId") or c.get("id")), "placeId": c.get("rootPlaceId") or c.get("placeId"), "name": str(c.get("name") or ""),
            "playing": int(c.get("playerCount") or c.get("playing") or 0), "up": int(c.get("totalUpVotes") or 0), "down": int(c.get("totalDownVotes") or 0),
            "creator": c.get("creatorName") or "", "verified": bool(c.get("creatorHasVerifiedBadge")), "age": c.get("ageRecommendationDisplayName") or "",
            "genre": c.get("genreL1") or ""}


def join_link(place_id, link_code=None, job_id=None):
    if link_code:
        return f"https://www.roblox.com/games/{int(place_id)}?privateServerLinkCode={link_code}"
    if job_id:
        return f"https://www.roblox.com/games/start?placeId={int(place_id)}&gameInstanceId={job_id}"
    return f"https://www.roblox.com/games/{int(place_id)}"


def vip_scan(client, place_ids, friend_ids):
    """For each game, collect the private (VIP) servers this account can see and mark the ones owned by friends.
    Returns (rows, problems). Each row is a dict; problems maps place id -> readable message."""
    friend_ids = set(int(f) for f in friend_ids)
    rows, problems = [], {}
    for pid in place_ids:
        merged = {}
        for label, fn in (("private servers", client.private_servers), ("listed on the game page", client.vip_servers_listed)):
            try:
                items = fn(pid)
            except RobloxError as e:
                problems.setdefault(pid, []).append(f"{label}: {e}")
                continue
            for s in items:
                key = s.get("vipServerId") or s.get("id")
                if key is None:
                    continue
                cur = merged.setdefault(key, {})
                for k, v in s.items():
                    cur.setdefault(k, v)
        for key, s in merged.items():
            owner = s.get("owner") or {}
            oid = owner.get("id") or owner.get("userId")
            rows.append({"place_id": pid, "vip_id": key, "name": s.get("name") or "", "owner_id": oid,
                         "owner": owner.get("name") or owner.get("username") or "", "friend": oid in friend_ids if oid else False,
                         "playing": s.get("playing"), "max": s.get("maxPlayers"), "access_code": s.get("accessCode") or s.get("linkCode")})
    rows.sort(key=lambda r: (not r["friend"], r["place_id"], r["name"].lower()))
    return rows, problems


# ------------------------------------------------------------------ pending Robux
SOURCE_NAMES = {"gamepass": "Game pass", "asset": "Item sale", "developerproduct": "Developer product", "subscription": "Subscription",
                "privateserver": "VIP server", "badge": "Badge", "bundle": "Bundle", "assetownership": "Item sale", "plugin": "Plugin sale",
                "pass": "Game pass", "product": "Developer product", "game": "Game sale"}


def source_label(item):
    """What a pending transaction came from: a group, a game pass, an item, a developer product..."""
    agent = item.get("agent") or {}
    d = item.get("details") if isinstance(item.get("details"), dict) else {}
    if str(agent.get("type", "")).lower() == "group":
        return f"Group: {agent.get('name') or agent.get('id')}"
    kind = str(d.get("type") or d.get("itemType") or "").strip()
    if kind:
        return SOURCE_NAMES.get(kind.replace(" ", "").lower(), kind)
    t = str(item.get("transactionType") or "")
    return {"Sale": "Sale", "GroupPayout": "Group payout", "EngagementPayout": "Premium payout", "GroupEngagementPayout": "Group premium payout",
            "AdImpressionPayout": "Ad payout", "AffiliateSale": "Affiliate sale", "PremiumStipend": "Premium stipend"}.get(t, t or "Other")


def summarize_pending(items):
    """Total pending Robux and where it came from. Only Robux count (not tickets)."""
    total, by_source, by_game = 0, {}, {}
    for it in items:
        cur = it.get("currency") or {}
        if str(cur.get("type", "Robux")).lower() != "robux":
            continue
        amount = int(cur.get("amount") or 0)
        total += amount
        label = source_label(it)
        e = by_source.setdefault(label, {"amount": 0, "count": 0})
        e["amount"] += amount
        e["count"] += 1
        d = it.get("details") if isinstance(it.get("details"), dict) else {}
        place = d.get("place") if isinstance(d.get("place"), dict) else {}
        game = place.get("name") or d.get("gameName") or ""
        if game:
            by_game[game] = by_game.get(game, 0) + amount
    sources = sorted(by_source.items(), key=lambda kv: -kv[1]["amount"])
    return {"total": total, "sources": sources, "games": sorted(by_game.items(), key=lambda kv: -kv[1]), "count": len(items)}


def describe_sources(summary, limit=6):
    """'Game pass 300, Item sale 150, Group: Cool Club 50' for a summary."""
    parts = [f"{name} {v['amount']:,}" for name, v in summary["sources"][:limit]]
    more = len(summary["sources"]) - limit
    return ", ".join(parts) + (f", +{more} more" if more > 0 else "")


# Transaction types that can be pending. Roblox rejects the 'PendingRobux' type for some accounts, so pending sales are found
# by reading each type newest-first and keeping the ones flagged as pending.
PENDING_TYPES = ["Sale", "GroupPayout", "EngagementPayout", "GroupEngagementPayout", "AdImpressionPayout", "AffiliateSale", "PremiumStipend"]


def _load_bad_types(uid):
    """Transaction kinds Roblox said do not exist for this account (remembered between runs: the route allows only 10 a minute)."""
    try:
        return set(json.loads((STATE_DIR / "bad-transaction-types.json").read_text()).get(str(uid), []))
    except (OSError, ValueError):
        return set()

def _save_bad_types(uid, bad):
    try:
        f = STATE_DIR / "bad-transaction-types.json"
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            data = {}
        data[str(uid)] = sorted(bad)
        f.write_text(json.dumps(data))
    except OSError:
        pass


def _pending_methods():
    def pending_total(self, user_id=None):
        """Your pending Robux as one number: a single quick request."""
        uid = user_id or self.user["id"]
        d = self.get(f"https://economy.roblox.com/v2/users/{int(uid)}/transaction-totals",
                     {"timeFrame": "Month", "transactionType": "summary"}, retries=1)
        return int(d.get("pendingRobuxTotal") or 0)

    def pending_transactions(self, user_id=None, max_pages=4, deadline=None):
        """The pending sales behind that number (best effort: stops at the deadline or after a few pages per type)."""
        uid = user_id or self.user["id"]
        base = f"https://economy.roblox.com/v2/users/{int(uid)}/transactions"
        items, failures = [], 0
        bad = _load_bad_types(uid)
        if "PendingRobux" in bad:
            self._no_pending_type = True
        order = [t for t in (["PendingRobux"] if not getattr(self, "_no_pending_type", False) else []) + PENDING_TYPES if t not in bad]
        for t in order:
            if deadline and time.time() > deadline:
                break
            cursor = None
            try:
                for _ in range(max_pages):
                    if deadline and time.time() > deadline:
                        break
                    params = {"transactionType": t, "limit": 100, "sortOrder": "Desc"}
                    if cursor:
                        params["cursor"] = cursor
                    d = self.get(base, params, retries=1)
                    page = d.get("data", [])
                    pend = [x for x in page if t == "PendingRobux" or x.get("isPending")]
                    items += pend
                    cursor = d.get("nextPageCursor")
                    if not cursor or len(pend) < len(page):   # newest first: the first settled sale ends the pending ones
                        break
            except RobloxError as e:
                if e.status == 400:                  # Roblox says this kind does not exist for this account: never ask again
                    if t == "PendingRobux":
                        self._no_pending_type = True
                    bad = bad | {t}
                    _save_bad_types(uid, bad)
                    continue
                if e.status in (401, 403):
                    raise
                failures += 1
        if not items and failures >= len(order):
            raise RobloxError(0, "Roblox did not return your sales")
        return items

    def owned_groups_pending(self, groups, deadline=None, max_groups=8):
        """Pending Robux in groups you own. Each group is asked once; a rate limit or refusal just skips it."""
        out, notes = [], []
        for g in groups[:max_groups]:
            if deadline and time.time() > deadline:
                notes.append("Stopped checking groups to keep things quick.")
                break
            try:
                d = self.get(f"https://economy.roblox.com/v1/groups/{int(g['id'])}/revenue/summary/Month", retries=0)
                out.append({"id": g["id"], "name": g["name"], "pending": int(d.get("pendingRobux") or 0), "sources": None})
            except RobloxError as e:
                if e.status == 429:
                    notes.append("Roblox is rate-limiting; some groups were skipped.")
                    break
        return out, notes
    return pending_total, pending_transactions, owned_groups_pending


for _fn in _pending_methods():
    setattr(Client, _fn.__name__, _fn)
