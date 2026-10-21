"""The sign-in window: password (with 2-step verification), the browser, or a pasted cookie."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

import auth
import browser_login
from ui_common import hint

WARN_STYLE = "background: #3a2a1e; border: 1px solid #8a5a2a; border-radius: 8px; padding: 10px;"


class SignInDialog(QDialog):
    """exec() returns Accepted once a cookie is available in .cookie (it is checked and saved by the caller)."""

    def __init__(self, parent, ctx, login_factory=auth.PasswordLogin):
        super().__init__(parent)
        self.ctx = ctx
        self.login_factory = login_factory
        self.login = None
        self.step = None
        self.cookie = ""
        self.setWindowTitle("Sign in to Roblox")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.tabs.addTab(self._password_page(), "Password")
        self.tabs.addTab(self._browser_page(), "Browser")
        self.tabs.addTab(self._cookie_page(), "Cookie")
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def done(self, result):
        if self.login:
            self.login.forget()          # whatever way the window closes, the password is not kept
        super().done(result)

    # ------------------------------------------------------------ password
    def _password_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(hint("Your password goes only to Roblox (auth.roblox.com) and is never saved or logged. If Roblox asks for a "
                           "2-step code, you are asked for it here. If it asks for a CAPTCHA or a passkey, use the Browser tab."))
        self.user = QLineEdit()
        self.user.setPlaceholderText("Username or email")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("Password")
        self.pw.returnPressed.connect(self.start)
        self.user.returnPressed.connect(self.pw.setFocus)
        lay.addWidget(self.user)
        lay.addWidget(self.pw)
        self.go = QPushButton("Sign in")
        self.go.setProperty("primary", True)
        self.go.setDefault(True)
        self.go.clicked.connect(self.start)
        lay.addWidget(self.go)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        # the 2-step part, shown only when Roblox asks
        self.two = QWidget()
        tl = QVBoxLayout(self.two)
        tl.setContentsMargins(0, 8, 0, 0)
        self.two_text = QLabel("Roblox wants a verification code.")
        self.two_text.setWordWrap(True)
        tl.addWidget(self.two_text)
        mrow = QHBoxLayout()
        self.method = QComboBox()
        self.method.currentIndexChanged.connect(self._method_changed)
        mrow.addWidget(self.method, 1)
        self.send = QPushButton("Send code")
        self.send.clicked.connect(self.send_code)
        mrow.addWidget(self.send)
        tl.addLayout(mrow)
        crow = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("Code")
        self.code.returnPressed.connect(self.verify)
        crow.addWidget(self.code, 1)
        self.verify_btn = QPushButton("Verify")
        self.verify_btn.setProperty("primary", True)
        self.verify_btn.clicked.connect(self.verify)
        crow.addWidget(self.verify_btn)
        tl.addLayout(crow)
        self.two.hide()
        lay.addWidget(self.two)
        self.to_browser = QPushButton("Use the browser sign-in instead")
        self.to_browser.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.to_browser.hide()
        lay.addWidget(self.to_browser)
        lay.addStretch()
        return w

    def _fit(self):
        """The window grows (or shrinks) to the content when a panel appears or goes: nothing is squeezed."""
        QTimer.singleShot(0, lambda: (self.layout().activate(), self.resize(self.width(), self.sizeHint().height())))

    def _say(self, text, bad=True):
        self.msg.setStyleSheet("color: #e5534b;" if bad else "color: #3ba55d;")
        self.msg.setText(text)

    def _busy(self, on):
        for b in (self.go, self.send, self.verify_btn):
            b.setEnabled(not on)

    def start(self):
        if not self.go.isEnabled():
            return
        user, pw = self.user.text(), self.pw.text()
        self.login = self.login_factory()
        self.two.hide()
        self.to_browser.hide()
        self._say("Signing in...", bad=False)
        self._busy(True)
        login = self.login
        self.ctx.async_.run(lambda: login.start(user, pw), self._login_result, self._login_failed)

    def _login_result(self, res):
        self._busy(False)
        if isinstance(res, auth.Done):
            return self._finish(res.cookie)
        self.step = res                                   # a code is needed
        self.pw.clear()
        self.method.blockSignals(True)
        self.method.clear()
        for m in res.methods:
            self.method.addItem(auth.METHOD_TEXT.get(m, m), m)
        self.method.setCurrentIndex(max(0, res.methods.index(res.primary)))
        self.method.blockSignals(False)
        self.two.show()
        extra = f" (Your account also has {', '.join(res.unsupported)}, which only works in the browser.)" if res.unsupported else ""
        self.two_text.setText("Roblox wants a verification code. Choose how to get it, then enter it." + extra)
        self._method_changed()
        self._say("Password accepted. Now the code.", bad=False)
        self.code.setFocus()
        self._fit()

    def _method_changed(self):
        m = self.method.currentData()
        self.send.setVisible(m in auth.SENDS_A_CODE)
        hints = {"Authenticator": "Open your authenticator app and type the 6-digit code.", "RecoveryCode": "Type one of your recovery codes.",
                 "Email": "Press Send code, then type the code from your email.", "SMS": "Press Send code, then type the code from the text message."}
        self.code.setPlaceholderText(hints.get(m, "Code"))

    def _login_failed(self, e):
        self._busy(False)
        if isinstance(e, auth.NeedBrowser):
            self._say(str(e) + " Use the Browser tab.")
            self.to_browser.show()
            self._fit()
        elif isinstance(e, auth.LoginError):
            self._say(str(e))
        else:
            self._say(f"Could not reach Roblox ({e.__class__.__name__}). Check your connection and try again.")

    def send_code(self):
        m, login = self.method.currentData(), self.login
        self._busy(True)
        self.ctx.async_.run(lambda: login.send_code(m), lambda _: (self._busy(False), self._say("Code sent. Check and type it below.", bad=False)),
                            self._login_failed)

    def verify(self):
        if not self.verify_btn.isEnabled() or not self.login:
            return
        m, code, login = self.method.currentData(), self.code.text(), self.login
        self._busy(True)
        self._say("Checking the code...", bad=False)

        def failed(e):
            self.code.selectAll()
            self._login_failed(e)
        self.ctx.async_.run(lambda: login.verify(m, code), lambda res: self._finish(res.cookie), failed)

    def _finish(self, cookie):
        self.pw.clear()
        self.code.clear()
        self.cookie_edit.clear()
        if self.login:
            self.login.forget()
        self.cookie = cookie
        self.accept()

    # ------------------------------------------------------------ browser
    def _browser_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(hint("The most reliable way: Roblox's own login page opens in a window here, so passkeys, security keys, CAPTCHAs and "
                           "every kind of check work exactly as on roblox.com. Nothing is remembered by that window; this app only "
                           "keeps the sign-in cookie."))
        b = QPushButton("Open the Roblox login page...")
        b.setProperty("primary", True)
        b.clicked.connect(self.open_browser)
        b.setEnabled(browser_login.AVAILABLE)
        lay.addWidget(b)
        if not browser_login.AVAILABLE:
            lay.addWidget(QLabel("The built-in browser is not installed on this PC."))
        lay.addStretch()
        return w

    def open_browser(self):
        d = browser_login.BrowserLoginDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted and d.cookie:
            self._finish(d.cookie)

    # ------------------------------------------------------------ cookie
    def _cookie_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        warn = QLabel("<b>Your cookie is the key to your account.</b> Anyone who has it can log in as you, <b>skipping your password and "
                      "2-step verification</b>, and take your Robux and items. Roblox staff never ask for it. This app keeps it in a file "
                      "only you can read (<code>~/.config/roblox-manager/cookie</code>), sends it <b>only to roblox.com</b>, and never "
                      "shows it or writes it to its log.")
        warn.setWordWrap(True)
        warn.setProperty("role", "notice")
        lay.addWidget(warn)
        lay.addWidget(QLabel("Paste the .ROBLOSECURITY value (it starts with  _|WARNING:-DO-NOT-SHARE-THIS...):"))
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.cookie_edit.setPlaceholderText("paste it here; the text stays hidden")
        lay.addWidget(self.cookie_edit)
        lay.addWidget(hint("Where to find it: in your browser, open roblox.com while logged in, press F12, go to Application (Chrome/Brave) or "
                           "Storage (Firefox), then Cookies, then roblox.com, and copy the value of .ROBLOSECURITY."))
        b = QPushButton("Use this cookie")
        b.setProperty("primary", True)
        b.clicked.connect(lambda: self._finish(self.cookie_edit.text()) if self.cookie_edit.text().strip() else None)
        lay.addWidget(b)
        lay.addStretch()
        return w
