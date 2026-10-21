"""Keeps sign-in cookies encrypted.

Linux: in the system wallet (KDE Wallet / any Secret Service) through the `secret-tool` program. The cookie is passed to secret-tool on its
standard input, never on the command line, so it does not show up in the process list.
Windows: encrypted with DPAPI (CryptProtectData), which only the same Windows user can decrypt; the encrypted blobs are files in the settings
folder (useless on their own, and not readable by another Windows account or another PC).
If neither can be used, the cookie falls back to a private file (owner-only permissions) and `plaintext_in_use()` says so, so the app can warn.
A cookie already sitting in a plain file is moved into the safe store the first time it is read, and the file is overwritten and deleted.
"""
import hashlib
import os
import shutil
import subprocess

import plat

TOOL = shutil.which("secret-tool")
_DPAPI_ENTROPY = b"roblox-manager"


def _dpapi(data, protect):
    """Windows DPAPI: bytes in, bytes out (None if it does not work). Only the current Windows user can undo what it does."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    try:
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        src, keep1 = blob(data)
        ent, keep2 = blob(_DPAPI_ENTROPY)
        out = Blob()
        ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))      # 0x01: never show a dialog
        if not ok:
            return None
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)
    except (OSError, AttributeError):
        return None


def _win_file(key):
    return plat.config_dir() / "vault" / (hashlib.sha256(f"{_app()}\0{key}".encode()).hexdigest()[:40] + ".bin")
TIMEOUT = 30            # a locked wallet shows a password prompt; give the person time, but never hang for ever

_state = {"ok": None}


def _app():
    # an isolated namespace when a different config directory is used (tests), so they never touch the real entries
    cfg = os.environ.get("ROBLOX_MANAGER_CONFIG")
    return "roblox-manager" + (":" + cfg if cfg else "")


def _run(args, value=None):
    try:
        return subprocess.run([TOOL, *args], input=value, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None


def available(refresh=False):
    """True if a safe store answers. (Linux: a missing entry is an ordinary 'not found'; an unreachable service prints an error.)"""
    if os.environ.get("ROBLOX_MANAGER_VAULT") == "off":
        return False
    if plat.IS_WIN:
        if _state["ok"] is None or refresh:
            sealed = _dpapi(b"probe", True)
            _state["ok"] = bool(sealed) and _dpapi(sealed, False) == b"probe"
        return _state["ok"]
    if not TOOL:
        return False
    if _state["ok"] is None or refresh:
        r = _run(["lookup", "application", _app(), "account", "__probe__"])
        _state["ok"] = bool(r is not None and r.returncode in (0, 1) and not (r.stderr or "").strip())
    return _state["ok"]


def get(key):
    if not available():
        return ""
    if plat.IS_WIN:
        try:
            plain = _dpapi(_win_file(key).read_bytes(), False)
        except OSError:
            return ""
        return plain.decode("utf-8", "replace") if plain else ""
    r = _run(["lookup", "application", _app(), "account", key])
    return r.stdout.strip() if r is not None and r.returncode == 0 else ""


def put(key, value, label="Roblox Manager sign-in"):
    if not available():
        return False
    if plat.IS_WIN:
        sealed = _dpapi(value.encode("utf-8"), True)
        if not sealed:
            return False
        f = _win_file(key)
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_bytes(sealed)
            tmp.replace(f)
            return True
        except OSError:
            return False
    r = _run(["store", "--label", label, "application", _app(), "account", key], value)
    ok = r is not None and r.returncode == 0
    if not ok:
        _state["ok"] = None             # check again next time (the wallet may have been locked)
    return ok


def delete(key):
    if plat.IS_WIN:
        _win_file(key).unlink(missing_ok=True)
        return
    if available():
        _run(["clear", "application", _app(), "account", key])


def wipe(path):
    """Overwrite a file with zeros, then delete it (best effort: an SSD may still keep old blocks)."""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(b"\0" * size)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(path, 0o600)


def read(key, path):
    """The secret `key`: from the wallet, or (and migrated into it) from the old plain file."""
    v = get(key)
    if v:
        return v
    try:
        v = path.read_text().strip()
    except OSError:
        return ""
    if v and put(key, v):
        wipe(path)                      # moved into the wallet; the plain copy is destroyed
    return v


def write(key, path, value):
    """Store a secret encrypted if possible. Returns True if it is now encrypted, False if it had to go in a plain private file."""
    if put(key, value):
        if path.exists():
            wipe(path)
        return True
    _write_file(path, value)
    return False


def remove(key, path):
    delete(key)
    if path.exists():
        wipe(path)


def plaintext_in_use(paths):
    """True if any of these files still holds a secret in plain text."""
    return any(p.exists() and p.stat().st_size > 0 for p in paths)
