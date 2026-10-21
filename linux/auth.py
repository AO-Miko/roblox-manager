"""Signing in to Roblox with a username and password, including 2-step verification.

What is sent where: the password and the codes go only to auth.roblox.com, twostepverification.roblox.com and apis.roblox.com
over https. Nothing is logged or written to disk by this module; the caller gets the .ROBLOSECURITY cookie back and stores it
the same way a pasted cookie is stored.

Roblox decides what it wants from you at sign-in. This module handles a normal login and the 2-step check (authenticator app,
email, text message, recovery code). Anything it cannot do itself (a CAPTCHA, a passkey or security key, an unknown check) raises
NeedBrowser, and the app then offers the browser sign-in, which handles every kind of check.
"""
import base64
import json
import time
from urllib.parse import urlparse

import requests

import rbx

ALLOWED_HOSTS = ("auth.roblox.com", "twostepverification.roblox.com", "apis.roblox.com")

# The 2-step methods this module can complete, as Roblox names them, with the name used in its addresses.
METHODS = {"Authenticator": "authenticator", "Email": "email", "SMS": "sms", "RecoveryCode": "recoverycode"}
SENDS_A_CODE = ("Email", "SMS")
METHOD_TEXT = {"Authenticator": "Authenticator app", "Email": "Email", "SMS": "Text message", "RecoveryCode": "Recovery code"}


class LoginError(Exception):
    """Roblox refused the sign-in (wrong password, locked account, too many tries ...). str() is safe to show."""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code, self.status = code, status


class NeedBrowser(Exception):
    """Roblox asked for a check that cannot be done here (CAPTCHA, passkey ...). str() says what it asked for."""


class Done:
    def __init__(self, cookie, user=None):
        self.cookie, self.user = cookie, user


class TwoStep:
    """Roblox wants a code. `methods` are the ones this app can handle, `unsupported` the ones that need the browser."""

    def __init__(self, user_id, challenge_id, action, methods, unsupported, primary):
        self.user_id, self.challenge_id, self.action = user_id, challenge_id, action
        self.methods, self.unsupported, self.primary = methods, unsupported, primary


def _b64_json(text):
    try:
        pad = "=" * (-len(text) % 4)
        return json.loads(base64.b64decode(text + pad).decode())
    except (ValueError, TypeError):
        return {}


class PasswordLogin:
    def __init__(self, session=None):
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": rbx.USER_AGENT, "Accept": "application/json"})
        self.csrf = ""
        self.rates = rbx.RateTable()
        self._login_body = None      # kept only while a sign-in is in progress; dropped by forget()
        self._login_challenge = None
        self.step = None

    # ------------------------------------------------------------ plumbing
    def _call(self, method, url, body=None, headers=None):
        u = urlparse(url)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
            raise ValueError("Refusing to send sign-in details to " + str(u.hostname))
        hdrs = dict(headers or {})
        key = self.rates.key(method, url)
        for attempt in range(2):
            try:
                self.rates.gate(key, time.sleep, max_wait=30)       # follow the limit Roblox reported for this route
            except rbx.LocalLimit as e:
                raise LoginError(str(e) + ". Wait a moment and try again.") from None
            t0 = time.time()
            r = self.s.request(method, url, json=body, headers={**hdrs, "x-csrf-token": self.csrf} if self.csrf else hdrs,
                               timeout=20, allow_redirects=False)
            # logged without its address' query and without any body: sign-in details never reach the log
            rate = self.rates.learn(key, r.headers, r.status_code, attempt, 10)
            rbx.record_request("signing in", method, url.split("?")[0], None, r.status_code, int((time.time() - t0) * 1000), attempt, False,
                               "challenge" if r.headers.get("rblx-challenge-id") else "", rate)
            tok = r.headers.get("x-csrf-token")
            if tok:
                self.csrf = tok
            # the first write is always answered with a fresh token and a refusal: send it again with the token
            if r.status_code == 403 and tok and attempt == 0 and not r.headers.get("rblx-challenge-id"):
                continue
            return r
        return r

    @staticmethod
    def _errors(r):
        try:
            data = r.json()
        except ValueError:
            data = {}
        errs = (data or {}).get("errors") or []
        e0 = errs[0] if errs else {}
        return (e0.get("userFacingMessage") or e0.get("message") or r.reason or "Roblox refused the request"), e0.get("code")

    def _cookie(self):
        for c in self.s.cookies:
            if c.name == ".ROBLOSECURITY" and c.value:
                return c.value
        return ""

    def forget(self):
        """Drop everything kept in memory about this sign-in attempt (the password included)."""
        self._login_body = None
        self._login_challenge = None
        self.step = None

    # ------------------------------------------------------------ step 1: username and password
    def start(self, username, password):
        """Returns Done, or TwoStep (a code is needed). Raises LoginError or NeedBrowser."""
        username = (username or "").strip()
        if not username or not password:
            raise LoginError("Enter your username and password.")
        self._login_body = {"ctype": "Email" if "@" in username else "Username", "cvalue": username, "password": password}
        try:
            r = self._call("POST", "https://auth.roblox.com/v2/login", self._login_body)
            return self._after_login(r)
        except (LoginError, NeedBrowser):
            self.forget()
            raise

    def _after_login(self, r):
        if r.status_code == 200:
            cookie = self._cookie()
            if cookie:
                user = {}
                try:
                    user = (r.json() or {}).get("user") or {}
                except ValueError:
                    pass
                self.forget()
                return Done(cookie, user)
            raise NeedBrowser("Roblox asked for an extra check that this app does not handle (older two-step flow).")
        ctype, cid = r.headers.get("rblx-challenge-type"), r.headers.get("rblx-challenge-id")
        if ctype and cid:
            meta = _b64_json(r.headers.get("rblx-challenge-metadata", ""))
            if ctype.lower() == "twostepverification" and meta.get("userId") and meta.get("challengeId"):
                self._login_challenge = {"id": cid, "type": ctype, "outer": meta}
                self.step = self._two_step(meta)
                return self.step
            raise NeedBrowser(f"Roblox asked for a '{ctype}' check (for example a CAPTCHA), which has to be done in a browser.")
        msg, code = self._errors(r)
        if r.status_code == 429:
            msg = "Roblox says too many sign-in attempts. Wait a few minutes before trying again."
        raise LoginError(msg, code, r.status_code)

    def _two_step(self, meta):
        uid, chid, action = meta["userId"], meta["challengeId"], meta.get("actionType", "Login")
        r = self._call("GET", f"https://twostepverification.roblox.com/v1/users/{uid}/configuration?challengeId={chid}&actionType={action}")
        if r.status_code != 200:
            raise NeedBrowser("Roblox wants a 2-step check but would not say which methods you have.")
        data = r.json() or {}
        enabled = [m.get("mediaType") for m in data.get("methods", []) if m.get("enabled", True)]
        ok = [m for m in enabled if m in METHODS]
        bad = [m for m in enabled if m not in METHODS]
        if not ok:
            raise NeedBrowser("Your account uses " + (", ".join(bad) or "a verification method") + ", which has to be done in a browser.")
        primary = data.get("primaryMediaType")
        return TwoStep(uid, chid, action, ok, bad, primary if primary in ok else ok[0])

    # ------------------------------------------------------------ step 2: the code
    def send_code(self, method):
        """Ask Roblox to send the code by email or text message (authenticator and recovery codes need no sending)."""
        t = self.step
        if not t or method not in SENDS_A_CODE:
            return
        r = self._call("POST", f"https://twostepverification.roblox.com/v1/users/{t.user_id}/challenges/{METHODS[method]}/send-code",
                       {"challengeId": t.challenge_id, "actionType": t.action})
        if r.status_code != 200:
            msg, code = self._errors(r)
            raise LoginError(msg, code, r.status_code)

    def verify(self, method, code, remember=False):
        """Check the code and finish signing in. Returns Done. Raises LoginError (wrong code: you can try again) or NeedBrowser."""
        t, lc = self.step, self._login_challenge
        if not t or not lc or method not in METHODS:
            raise LoginError("Start the sign-in first.")
        code = (code or "").strip().replace(" ", "")
        if not code:
            raise LoginError("Enter the code.")
        r = self._call("POST", f"https://twostepverification.roblox.com/v1/users/{t.user_id}/challenges/{METHODS[method]}/verify",
                       {"challengeId": t.challenge_id, "actionType": t.action, "code": code})
        if r.status_code != 200:
            msg, ecode = self._errors(r)
            if r.status_code == 429:
                msg = "Too many wrong codes. Wait a few minutes before trying again."
            raise LoginError(msg, ecode, r.status_code)
        token = (r.json() or {}).get("verificationToken")
        if not token:
            raise NeedBrowser("Roblox accepted the code but did not finish the check here.")
        meta = {"rememberDevice": bool(remember), "actionType": t.action, "verificationToken": token, "challengeId": t.challenge_id}
        cont = self._call("POST", "https://apis.roblox.com/challenge/v1/continue",
                          {"challengeId": lc["id"], "challengeType": lc["type"], "challengeMetadata": json.dumps(meta)})
        if cont.status_code != 200:
            msg, ecode = self._errors(cont)
            raise LoginError(msg, ecode, cont.status_code)
        headers = {"rblx-challenge-id": lc["id"], "rblx-challenge-type": lc["type"],
                   "rblx-challenge-metadata": base64.b64encode(json.dumps(meta).encode()).decode()}
        r = self._call("POST", "https://auth.roblox.com/v2/login", self._login_body, headers)
        res = self._after_login(r)
        if isinstance(res, TwoStep):
            raise NeedBrowser("Roblox asked for a second check after the code.")
        return res
