"""Checks OpenSSH file signatures (`ssh-keygen -Y sign`) in plain Python, so Windows (which has no git or ssh-keygen to rely on) can still
verify that an update was signed by a key it trusts. Only Ed25519 keys are supported. Nothing here signs anything.

  verify(message_bytes, armored_signature, allowed_signers_text, namespace) -> the signer's name, or None
"""
import base64
import hashlib
import shlex
import struct

# ------------------------------------------------------------------ Ed25519 (RFC 8032), signature verification only
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * _inv(5) % _P
_G = (_recover_x(_GY, 0), _GY, 1, _recover_x(_GY, 0) * _GY % _P)


def ed25519_verify(public, message, signature):
    """True if `signature` (64 bytes) is a valid Ed25519 signature of `message` by `public` (32 bytes)."""
    if len(public) != 32 or len(signature) != 64:
        return False
    a, r = _decompress(public), _decompress(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _Q
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


# ------------------------------------------------------------------ the OpenSSH formats
class _Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def take(self, n):
        if n < 0 or self.i + n > len(self.d):
            raise ValueError("truncated")
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def u32(self):
        return struct.unpack(">I", self.take(4))[0]

    def string(self):
        return self.take(self.u32())


def _string(b):
    return struct.pack(">I", len(b)) + b


def parse_allowed_signers(text):
    """[(principals, namespaces or None, 32 byte key)] for the Ed25519 lines of an allowed_signers file."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        k = next((i for i, p in enumerate(parts) if p == "ssh-ed25519"), None)
        if k is None or k < 1 or k + 1 >= len(parts):
            continue
        try:
            r = _Reader(base64.b64decode(parts[k + 1]))
            if r.string() != b"ssh-ed25519":
                continue
            key = r.string()
        except (ValueError, TypeError):
            continue
        namespaces = None
        for opt in parts[1:k]:                                  # options such as: namespaces="git,roblox-manager-release"
            i = opt.find("namespaces=")
            if i >= 0:
                namespaces = [n.strip() for n in opt[i + len("namespaces="):].strip('"').split(",") if n.strip()]
        out.append((parts[0], namespaces, key))
    return out


def verify(message, armored, allowed_text, namespace):
    """The principal (name) of the trusted key that signed `message` in `namespace`, or None if the signature is wrong, for another
    namespace, or made by a key that is not in `allowed_text`."""
    try:
        lines = [l.strip() for l in armored.strip().splitlines()]
        if lines[0] != "-----BEGIN SSH SIGNATURE-----" or lines[-1] != "-----END SSH SIGNATURE-----":
            return None
        blob = base64.b64decode("".join(lines[1:-1]))
        r = _Reader(blob)
        if r.take(6) != b"SSHSIG" or r.u32() != 1:
            return None
        pub, ns, _reserved, hash_alg, sig = r.string(), r.string(), r.string(), r.string(), r.string()
        if ns.decode() != namespace:
            return None
        hasher = {b"sha512": hashlib.sha512, b"sha256": hashlib.sha256}.get(hash_alg)
        if hasher is None:
            return None
        pr = _Reader(pub)
        if pr.string() != b"ssh-ed25519":
            return None
        key = pr.string()
        sr = _Reader(sig)
        if sr.string() != b"ssh-ed25519":
            return None
        raw = sr.string()
        signed = b"SSHSIG" + _string(namespace.encode()) + _string(b"") + _string(hash_alg) + _string(hasher(message).digest())
        if not ed25519_verify(key, signed, raw):
            return None
    except (ValueError, TypeError, IndexError, struct.error):
        return None
    for principal, namespaces, trusted in parse_allowed_signers(allowed_text):
        if trusted == key and (namespaces is None or namespace in namespaces):
            return principal
    return None
