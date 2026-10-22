"""The 'Update required' page (see policy.py): the app is too far behind, so it covers the whole window and nothing else can be used until it is updated.
It says what is wrong and has a button that updates the app (and one that opens the download page, in case the update does not work)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import policy
import updater
from ui_common import button, hint, open_url


class UpdateRequiredPage(QWidget):
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
        self.b_page = button("Open the download page", lambda: open_url(policy.releases_url()), "In case the update does not work: download the newest version yourself")
        self.b_update = button("Update now", self.update_now, "Download and install the newest version", primary=True)
        self.b_restart = button("Restart now", self.restart_now, primary=True)
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
                self.status.setText(r["message"])
                self.b_update.hide()
                self.b_restart.show()
            else:
                self.b_update.setEnabled(True)
                self.status.setText(r["message"] if r["status"] != "up-to-date" else "No newer version was found on your update channel. Use the download page.")
        self.ctx.async_.run(updater.apply, done, lambda e: (self.b_update.setEnabled(True), self.status.setText(f"The update did not work: {e}")))

    def restart_now(self):
        if self.restart:
            self.restart()
        else:
            QApplication.quit()
