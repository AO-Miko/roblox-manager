"""The question an account is asked at its first sign-in (and when the texts change): accept the Terms of use and the Privacy policy, or be signed out."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout

import legal
from ui_common import button


class LegalDialog(QDialog):
    def __init__(self, user_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Roblox Manager: before you start")
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        title = QLabel("Before you start" + (f", @{user_name}" if user_name else ""))
        title.setProperty("role", "display")
        lay.addWidget(title)
        intro = QLabel(
            "To use Roblox Manager with this account you need to accept its Terms of use and its Privacy policy. You are asked once for each account, and again if the texts change.\n\n"
            "In short: it is an unofficial hobby project, not made by Roblox. Everything it keeps stays on your device, nothing is sent to its maker, "
            "and it only talks to Roblox and GitHub (and two optional services if you turn them on). You use it at your own risk, "
            "and abusing it or the project gets your Roblox account banned from it.\n\n"
            "If you do not accept, this account is signed out (its saved sign-in is kept, and you are asked again next time).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        links = QHBoxLayout()
        self.b_terms = button("Read the Terms of use", lambda: QDesktopServices.openUrl(QUrl(legal.TERMS_URL)), "Opens the terms on GitHub")
        self.b_privacy = button("Read the Privacy policy", lambda: QDesktopServices.openUrl(QUrl(legal.PRIVACY_URL)), "Opens the policy on GitHub")
        links.addWidget(self.b_terms)
        links.addWidget(self.b_privacy)
        links.addStretch()
        lay.addLayout(links)
        self.check = QCheckBox("I have read and I accept the Terms of use and the Privacy policy")
        self.check.toggled.connect(lambda on: self.b_accept.setEnabled(on))
        lay.addWidget(self.check)
        row = QHBoxLayout()
        row.addStretch()
        self.b_decline = button("Decline and sign out", self.reject, "This account is signed out; you are asked again next time")
        self.b_accept = button("Accept and continue", self.accept, primary=True)
        self.b_accept.setEnabled(False)
        self.b_accept.setDefault(False)
        row.addWidget(self.b_decline)
        row.addWidget(self.b_accept)
        lay.addLayout(row)
        self.b_decline.setDefault(True)           # (Enter never accepts by accident)

    def showEvent(self, event):
        super().showEvent(event)
        need = self.layout().totalHeightForWidth(self.width())          # (wrapped text is taller than the first guess, most of all with a wide font)
        if need > self.height():
            self.resize(self.width(), need)


def ask(user, parent=None):
    """Shows the question for this account ({'id', 'name'}); True once accepted (and remembered). Declining, or closing the window, is False."""
    if legal.accepted(user["id"]):
        return True
    dlg = LegalDialog(user.get("name", ""), parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        legal.accept(user["id"])
        return True
    return False
