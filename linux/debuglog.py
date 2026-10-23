"""The app's debug log: what happens in the app, with the output, shown in the Request log tab (App debug) and written to debug.log.

Everything goes through scrub() before it is kept or written: cookies, tokens, passwords, codes, e-mail addresses, phone numbers, IP addresses, long
opaque strings, the names and id of the accounts in use, and names and descriptions of people in answers from Roblox are replaced by a mark, and your
home folder becomes ~. Nothing here is ever sent anywhere: it stays in memory and in debug.log in the private state folder.
"""
import getpass
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import rbx

LEVELS = ["debug", "info", "warning", "error"]
KEEP = 8000                    # events kept in memory
DETAIL_MAX = 6000              # characters of one event's output that are kept
PREVIEW_MAX = 2400             # characters of an answer from Roblox that are kept
FILE = rbx.STATE_DIR / "debug.log"

ENABLED = True                 # settings: write debug.log (the list in the app is always kept)
EVENTS = deque(maxlen=KEEP)
LISTENERS = []                 # callables(event dict), called from whatever thread made the event
total = 0

# ------------------------------------------------------------------ hiding personal things
_COOKIE = re.compile(r"(_\|WARNING:[^;\s\"']+|\.ROBLOSECURITY=[^;\s\"']+)")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])")
_IPV6 = re.compile(r"(?i)(?<![\w:])(?:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?|(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4})(?![\w:])")
_PHONE = re.compile(r"(?<!\w)\+\d[\d ()-]{7,}\d")
_OPAQUE = re.compile(r"(?<![\w-])[A-Za-z0-9_+=-]{40,}(?![\w-])")
SENSITIVE = r"cookie|token|ticket|passw|secret|authoriz|session|csrf|e-?mail|phone|birth|signature|credential|api[-_]?key|private"
_KEYVALUE = re.compile(r"""(?ix)
    (?P<k>["']?[\w.-]*(?:%s)[\w.-]*["']?)       # a key that names something secret
    (?P<sep>\s*[:=]\s*)
    (?P<v>\[[a-z ]*\]|"(?:[^"\\]|\\.)*"|'[^']*'|[^\s,;&}\]"']+)""" % SENSITIVE)
_EXACT = re.compile(r"""(?ix)
    (?P<k>["']?\b(?:code|pin|otp|auth|key|dob)["']?)(?P<sep>\s*[:=]\s*)(?P<v>"(?:[^"\\]|\\.)*"|'[^']*'|\d{5,})""")
# keys whose text in an answer from Roblox is about a person: shown as ***, whatever the value
PERSONAL_KEYS = re.compile(r"(?i)^(name|displayname|username|user_?name|requested_?(user)?name|description|about|bio|body|content|text|location|ip|address|"
                           r"cookie|.*token.*|.*ticket.*|.*password.*|.*secret.*|authorization|.*session.*|.*csrf.*|.*email.*|.*phone.*|.*birth.*|.*signature.*|.*credential.*)$")
_ME = {"names": set(), "ids": set()}
_HOME = str(Path.home())
try:
    _OSUSER = getpass.getuser()
except Exception:       # noqa: BLE001
    _OSUSER = ""


def set_identity(*people, replace=False):
    """Accounts in use: their names (and ids) are hidden wherever they appear. Pass user dicts ({'id', 'name', 'displayName'}) or plain names."""
    if replace:
        _ME["names"].clear()
        _ME["ids"].clear()
    for p in people:
        if isinstance(p, dict):
            for k in ("name", "displayName"):
                if p.get(k) and len(str(p[k])) >= 3:
                    _ME["names"].add(str(p[k]))
            if p.get("id"):
                _ME["ids"].add(str(p["id"]))
        elif p and len(str(p)) >= 3:
            _ME["names"].add(str(p))


def scrub(text, limit=None):
    """The text with everything private replaced by a mark. Never raises."""
    try:
        t = str(text)
        t = _COOKIE.sub("[cookie]", t)
        if _HOME and len(_HOME) > 1:
            t = t.replace(_HOME, "~")
        t = _JWT.sub("[token]", t)
        t = _BEARER.sub(lambda m: m.group(1) + " ***", t)
        t = _KEYVALUE.sub(lambda m: m.group("k") + m.group("sep") + ('"***"' if m.group("v")[:1] in "\"'" else "***"), t)
        t = _EXACT.sub(lambda m: m.group("k") + m.group("sep") + ('"***"' if m.group("v")[:1] in "\"'" else "***"), t)
        t = _EMAIL.sub("[email]", t)
        t = _IPV4.sub("[ip]", t)
        t = _IPV6.sub("[ip]", t)
        t = _PHONE.sub("[phone]", t)
        t = _OPAQUE.sub("[token]", t)
        if _OSUSER and len(_OSUSER) >= 3:
            t = re.sub(r"(?<=/home/)" + re.escape(_OSUSER) + r"\b|(?<=\\Users\\)" + re.escape(_OSUSER) + r"\b", "user", t)
        for n in sorted(_ME["names"], key=len, reverse=True):
            t = re.sub(r"(?<![\w])" + re.escape(n) + r"(?![\w])", "<me>", t, flags=re.I)
        for i in _ME["ids"]:
            t = re.sub(r"(?<!\d)" + re.escape(i) + r"(?!\d)", "<my id>", t)
        if limit and len(t) > limit:
            t = t[:limit] + f"... [{len(t) - limit} more characters]"
        return t
    except Exception:           # noqa: BLE001 - the log must never break the app; when in doubt, show nothing
        return "[could not be hidden safely: not shown]"


def _walk(o, depth=0):
    if depth > 6:
        return "..."
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            key = str(k)
            if PERSONAL_KEYS.match(key):
                out[key] = v if v is None or isinstance(v, bool) else "***"
            else:
                out[key] = _walk(v, depth + 1)
        return out
    if isinstance(o, (list, tuple)):
        items = [_walk(x, depth + 1) for x in o[:6]]
        if len(o) > 6:
            items.append(f"... {len(o) - 6} more")
        return items
    if isinstance(o, str):
        return o if len(o) <= 120 else o[:117] + "..."
    if isinstance(o, (bool, int, float)) or o is None:
        return o
    return f"<{o.__class__.__name__}>"


_PERSONAL_TEXT = re.compile(r"""(?ix)(?P<k>"(?:name|display_?name|user_?name|requested_?(?:user)?name|description|about|bio|body|content|text|location|ip|address)"\s*:\s*)(?P<v>"(?:[^"\\]|\\.)*"?)""")


def preview(data, limit=PREVIEW_MAX):
    """A short, hidden version of something that came back (a decoded answer, or text): the output of a request or task."""
    try:
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data[:limit * 2]).decode("utf-8", "replace")
        if isinstance(data, str):
            s = data.strip()
            if s[:1] in "{[":
                try:
                    data = json.loads(s)
                except ValueError:                  # (cut off or not json: the names in it are still hidden)
                    return scrub(_PERSONAL_TEXT.sub(lambda m: m.group("k") + '"***"', s[:limit * 2]), limit)
            else:
                return scrub(s[:limit * 2], limit)
        if isinstance(data, (dict, list, tuple)):
            return scrub(json.dumps(_walk(data), ensure_ascii=False, separators=(", ", ": ")), limit)
        return scrub(repr(data), limit)
    except Exception:           # noqa: BLE001
        return "[output not shown]"


# ------------------------------------------------------------------ the events
_file = None
_lock = threading.Lock()


class _PrivateFile(RotatingFileHandler):
    """The log file (and each file it rotates into) can be read by this user only."""

    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


def _open_file():
    global _file
    if _file is None:
        _file = logging.getLogger("roblox-manager.debug")
        _file.setLevel(logging.DEBUG)
        _file.propagate = False
        if not _file.handlers:
            try:
                h = _PrivateFile(FILE, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(message)s"))
                _file.addHandler(h)
            except OSError:
                pass
    return _file


def event(area, message, level="info", detail=""):
    """Record one thing that happened. `message` is one line; `detail` is the output (many lines). Both are hidden before they are kept."""
    global total
    try:
        e = {"time": time.time(), "level": level if level in LEVELS else "info", "area": str(area), "message": scrub(message, 600).replace("\n", " "),
             "detail": scrub(detail, DETAIL_MAX) if detail else "", "thread": threading.current_thread().name}
        with _lock:
            EVENTS.append(e)
            total += 1
        if ENABLED:
            line = f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e['time']))}.{int(e['time'] * 1000) % 1000:03d} {e['level'].upper():7} [{e['area']}] {e['message']}"
            if e["detail"]:
                line += "\n    " + e["detail"].replace("\n", "\n    ")
            _open_file().info(line)
        for fn in list(LISTENERS):
            try:
                fn(e)
            except Exception:       # noqa: BLE001
                pass
        return e
    except Exception:           # noqa: BLE001
        return None


def http(entry, sent=None, got=None):
    """A request that was made: one line (like the Requests list) and, as output, what was sent and what came back."""
    st = entry["status"]
    level = "error" if st is None or st >= 500 else "warning" if st >= 400 else "info"
    msg = f"{entry['method']} {entry['host']}{entry['path']}" + (f"?{entry['query']}" if entry["query"] else "") + f" -> {'no answer' if st is None else st}"
    if entry.get("ms") is not None:
        msg += f" ({entry['ms']} ms)"
    if entry.get("note"):
        msg += f" {entry['note']}"
    parts = []
    if sent is not None:
        parts.append("sent: " + preview(sent, 1200))
    if got is not None:
        try:
            ctype = got.headers.get("content-type", "")
            size = len(got.content or b"")
            body = got.content[:PREVIEW_MAX * 2] if size and ("json" in ctype or "text" in ctype or not ctype) else b""
            parts.append(f"answer: HTTP {got.status_code}, {size} bytes" + (f", {ctype.split(';')[0]}" if ctype else "") + (("\n" + preview(body)) if body else ""))
        except Exception:       # noqa: BLE001
            parts.append("answer: (not readable)")
    event("http", msg, level, "\n".join(parts))


def net(method, url, status=None, size=0, error=""):
    """A request to somewhere that is not Roblox (the update server, RoSeal's list, ipwho.is, the ban and policy lists): the host and path only, never what is in the query."""
    from urllib.parse import urlparse
    u = urlparse(url)
    msg = f"{method} {u.hostname or ''}{u.path}" + (f" -> {status}" if status is not None else " -> no answer") + (f", {size} bytes" if size else "") + (f" ({error})" if error else "")
    event("net", msg, "info" if status is not None and status < 400 else "warning")


def snapshot(level="debug", area="", text=""):
    """The kept events that pass the filters (level at least `level`, area equal to `area` if given, `text` words all in the line)."""
    floor = LEVELS.index(level) if level in LEVELS else 0
    words = text.lower().split()
    out = []
    for e in list(EVENTS):
        if LEVELS.index(e["level"]) < floor or (area and e["area"] != area):
            continue
        if words:
            hay = f"{e['area']} {e['level']} {e['message']} {e['detail']}".lower()
            if not all(w in hay for w in words):
                continue
        out.append(e)
    return out


def format_event(e, with_detail=True):
    t = time.localtime(e["time"])
    line = f"{time.strftime('%H:%M:%S', t)}.{int(e['time'] * 1000) % 1000:03d} {e['level'].upper():7} [{e['area']}] {e['message']}"
    if with_detail and e["detail"]:
        line += "\n    " + e["detail"].replace("\n", "\n    ")
    return line


def _version():
    try:
        return (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"


def export_text(events=None):
    """The events as text to save or copy, with a header (version, system) and nothing private."""
    head = [f"Roblox Manager debug log, exported {time.strftime('%Y-%m-%d %H:%M:%S')}", f"app {_version()}, python {sys.version.split()[0]}, {sys.platform}",
            "Cookies, tokens, passwords, codes, e-mails, phone numbers, IP addresses, names of accounts and people, and names of folders are hidden.", ""]
    return "\n".join(head + [format_event(e) for e in (events if events is not None else list(EVENTS))]) + "\n"


def clear():
    with _lock:
        EVENTS.clear()


# ------------------------------------------------------------------ catching everything
class _Handler(logging.Handler):
    """Every record of the standard logging (the app's own and the libraries') becomes an event."""

    def emit(self, record):
        try:
            name = record.name.replace("roblox-manager", "app").strip(".") or "app"
            if name.startswith("app.requests") or name.startswith("app.debug"):
                return
            level = "error" if record.levelno >= logging.ERROR else "warning" if record.levelno >= logging.WARNING else "info" if record.levelno >= logging.INFO else "debug"
            detail = ""
            if record.exc_info:
                detail = "".join(traceback.format_exception(*record.exc_info))
            event(name.split(".")[0] if name.startswith("app") else "log:" + name, record.getMessage(), level, detail)
        except Exception:       # noqa: BLE001
            pass


class _Tee:
    """Wraps stdout/stderr: the text still goes where it went, and each line is also an event."""

    def __init__(self, inner, level):
        self.inner, self.level, self.buf = inner, level, ""

    def write(self, s):
        try:
            if self.inner is not None:
                self.inner.write(s)
        except Exception:       # noqa: BLE001
            pass
        try:
            self.buf += s
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                if line.strip():
                    event("output", line, self.level)
            if len(self.buf) > 4000:
                event("output", self.buf, self.level)
                self.buf = ""
        except Exception:       # noqa: BLE001
            pass
        return len(s)

    def flush(self):
        try:
            if self.inner is not None:
                self.inner.flush()
        except Exception:       # noqa: BLE001
            pass

    def __getattr__(self, name):
        return getattr(self.inner, name)


_installed = False


def install():
    """Start catching: the logging records, uncaught errors (any thread), what the program prints, and Qt's own messages. Safe to call twice."""
    global _installed
    if _installed:
        return
    _installed = True
    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    root.addHandler(_Handler())
    old_hook = sys.excepthook

    def hook(kind, value, tb):
        event("crash", f"uncaught {kind.__name__}: {value}", "error", "".join(traceback.format_exception(kind, value, tb)))
        old_hook(kind, value, tb)
    sys.excepthook = hook
    old_thread_hook = threading.excepthook

    def thread_hook(args):
        event("crash", f"uncaught {args.exc_type.__name__} in thread {getattr(args.thread, 'name', '?')}: {args.exc_value}", "error",
              "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        old_thread_hook(args)
    threading.excepthook = thread_hook
    sys.stdout = _Tee(sys.stdout, "info")
    sys.stderr = _Tee(sys.stderr, "warning")
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def qt_message(kind, context, message):
            level = {QtMsgType.QtDebugMsg: "debug", QtMsgType.QtInfoMsg: "info", QtMsgType.QtWarningMsg: "warning"}.get(kind, "error")
            event("qt", message, level)
        qInstallMessageHandler(qt_message)
    except Exception:       # noqa: BLE001
        pass
    event("app", f"debug log started (python {sys.version.split()[0]}, {sys.platform})", "info")
