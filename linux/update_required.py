"""The 'Update required' page (see policy.py): the app is too far behind, so it covers the whole window and nothing else can be used until it is updated.
It says what is wrong and has one button: Update now downloads, checks and installs the newest version and restarts the app by itself. The download page
(GitHub) is only offered if the automatic update did not work."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import policy
import updater
from ui_common import button, hint, open_url


class UpdateRequiredPage(QWidget):
    RESTART_DELAY = 1500              # ms the person can read "Updated ... Restarting" before the app restarts

    def __init__(self, ctx, restart=None):
        super().__init__()
        self.ctx = ctx
        self.restart = restart            # called to restart the app after the update
        self.updated = False
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        card = QFrame()
        card.setProperty("card", True)
        card.setMinimumWidth(440)
        card.setMaximumWidth(560)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 22, 24, 20)
        self.title = QLabel("Please update Roblox Manager")
        self.title.setProperty("role", "title")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.text)
        self.status = hint("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.b_page = button("Open the download page", lambda: open_url(policy.releases_url()), "The update did not work: download the newest version yourself")
        self.b_page.hide()                                # (only after the automatic update failed)
        self.b_update = button("Update now", self.update_now, "Download, check and install the newest version, then restart", primary=True)
        self.b_restart = button("Restart now", self.restart_now, "Restart at once (it also happens by itself)", primary=True)
        self.b_restart.hide()
        for b in (self.b_page, self.b_update, self.b_restart):
            buttons.addWidget(b)
        lay.addLayout(buttons)
        row.addWidget(card, 3)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

    def show_status(self, st):
        n = st["behind"]
        self.text.setText(f"This is version <b>{st['installed']}</b> and it is {n} update{'' if n == 1 else 's'} behind (the newest is <b>{st['latest']}</b>). "
                          "Roblox Manager cannot be used until it is updated.<br><br>Nothing is lost: your saved accounts and settings stay on this device.")

    def update_now(self):
        self.b_update.setEnabled(False)
        self.status.setText("Downloading and checking the update...")

        def done(r):
            if r["status"] == "updated":
                self.updated = True
                self.status.setText(r["message"].replace(" Restart the app to use it.", "") + " Restarting...")
                self.b_update.hide()
                self.b_page.hide()
                self.b_restart.show()
                QTimer.singleShot(self.RESTART_DELAY, self.restart_now)         # (no second press: the new version starts by itself)
            else:
                self.b_update.setEnabled(True)
                self.b_page.show()
                self.status.setText(r["message"] if r["status"] != "up-to-date" else "No newer version was found on your update channel. Use the download page.")

        def failed(e):
            self.b_update.setEnabled(True)
            self.b_page.show()
            self.status.setText(f"The update did not work: {e}")
        self.ctx.async_.run(updater.apply, done, failed)

    def restart_now(self):
        if not self.updated:
            return
        self.updated = False
        if self.restart:
            self.restart()
        else:
            QApplication.quit()
