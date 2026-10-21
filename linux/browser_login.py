"""Sign in on the real roblox.com login page inside a window of this app.

This is the way in that always works: Roblox shows its own page, so CAPTCHAs, passkeys, security keys and any new kind of check
are handled by Roblox itself. The window uses a private, throw-away browser profile (nothing is remembered once it closes), only
lets the page itself navigate within roblox.com, and the app takes just the .ROBLOSECURITY cookie that Roblox sets when you are in.
"""
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    AVAILABLE = True
except ImportError:                       # pragma: no cover - depends on how Qt was installed
    AVAILABLE = False

LOGIN_URL = "https://www.roblox.com/login"


def is_roblox_host(host):
    host = (host or "").lower()
    return host == "roblox.com" or host.endswith(".roblox.com")


if AVAILABLE:
    class _Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            # embedded parts (the CAPTCHA, for example) may come from elsewhere; the page itself may only go to roblox.com
            if is_main_frame and url.scheme() in ("http", "https") and not is_roblox_host(url.host()):
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BrowserLoginDialog(QDialog):
    """exec() returns Accepted when the cookie was captured; read it with .cookie."""

    def __init__(self, parent=None, url=LOGIN_URL):
        super().__init__(parent)
        self.setWindowTitle("Sign in to Roblox")
        self.resize(560, 720)
        self.cookie = ""
        lay = QVBoxLayout(self)
        note = QLabel("Sign in below exactly as you would on roblox.com (password, 2-step code, CAPTCHA, passkey ...). "
                      "This window closes by itself when you are in. Your password goes to Roblox in this window; the app only keeps "
                      "the sign-in cookie.")
        note.setWordWrap(True)
        note.setProperty("role", "hint")
        lay.addWidget(note)
        self.view = None
        self.profile = None
        if AVAILABLE:
            self.profile = QWebEngineProfile(self)        # no storage name: private, nothing is kept on disk
            self.page = _Page(self.profile, self)
            self.view = QWebEngineView(self)
            self.view.setPage(self.page)
            lay.addWidget(self.view, 1)
            store = self.profile.cookieStore()
            store.cookieAdded.connect(self._cookie_added)
            self.page.load(QUrl(url))
        else:
            lay.addWidget(QLabel("The built-in browser is not installed (python3-pyside6 WebEngine)."), 1)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _cookie_added(self, cookie):
        if bytes(cookie.name()).decode(errors="ignore") != ".ROBLOSECURITY" or not is_roblox_host(cookie.domain().lstrip(".")):
            return
        value = bytes(cookie.value()).decode(errors="ignore")
        if len(value) > 100 and not self.cookie:
            self.cookie = value
            QTimer.singleShot(400, self.accept)

    def done(self, result):
        # throw the page and its private profile away before the window goes
        if self.view is not None:
            self.view.setPage(None)
            self.page.deleteLater()
            self.profile.deleteLater()
            self.view = None
        super().done(result)
