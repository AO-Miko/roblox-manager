"""Settings tab: clear what the app saves on this PC (logs, records, saved pictures and names) and the app's few choices."""
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import accounts
import cleanup
import rbx
import settings
from ui_common import button, hint, make_table


class SettingsTab(QWidget):
    def __init__(self, ctx, on_cleared=None):
        super().__init__()
        self.ctx = ctx
        self.on_cleared = on_cleared or (lambda category: None)      # the window uses this to empty the Requests tab's list too
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.addWidget(self._data_box())
        lay.addWidget(self._rate_box())
        lay.addWidget(self._log_box())
        lay.addWidget(self._cache_box())
        lay.addWidget(self._update_box())
        lay.addWidget(self._ui_box())
        lay.addWidget(self._about_box())
        lay.addStretch()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(4000)
        settings.on_change(lambda k, v: self.load_values())

    # ------------------------------------------------------------ what the app saves, and clearing it
    def _data_box(self):
        box = QGroupBox("What the app saves on this PC")
        lay = QVBoxLayout(box)
        lay.addWidget(hint("Clearing is permanent. Your sign-ins (kept encrypted in the wallet), the list of accounts and these settings are never touched here."))
        self.table = make_table(["What", "Files", "Size", ""], [210, 60, 90, 130], stretch_last=False)
        self.table.setSortingEnabled(False)
        self.table.setSelectionMode(self.table.SelectionMode.NoSelection)
        self.table.setMaximumHeight(150)
        self.table.setRowCount(len(cleanup.CATEGORIES))
        self.clear_buttons = {}
        for r, (key, info) in enumerate(cleanup.CATEGORIES.items()):
            it = QTableWidgetItem(info["title"])
            it.setToolTip(info["what"])
            self.table.setItem(r, 0, it)
            for c in (1, 2):
                self.table.setItem(r, c, QTableWidgetItem(""))
            b = QPushButton("Clear...")
            b.setProperty("danger", True)
            b.setToolTip(info["what"])
            b.clicked.connect(lambda _=False, k=key: self.clear(k))
            self.table.setCellWidget(r, 3, b)
            self.clear_buttons[key] = b
        lay.addWidget(self.table)
        row = QHBoxLayout()
        self.b_all_logs = button("Clear all logs...", lambda: self.clear("logs"), "manager.log, requests.log and their older copies", danger=True)
        row.addWidget(self.b_all_logs)
        row.addWidget(button("Clear everything listed...", self.clear_all, "Logs, activity records, and saved pictures and names", danger=True))
        row.addStretch()
        row.addWidget(button("Open the folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.STATE_DIR)))))
        lay.addLayout(row)
        self.data_note = hint("")
        lay.addWidget(self.data_note)
        return box

    def refresh(self):
        total = 0
        for r, key in enumerate(cleanup.CATEGORIES):
            n, size = cleanup.summary()[key]
            self.table.item(r, 1).setText(str(n))
            self.table.item(r, 2).setText(cleanup.human(size))
            self.clear_buttons[key].setEnabled(n > 0)
            total += n
        self.b_all_logs.setEnabled(self.clear_buttons["logs"].isEnabled())

    def _tick(self):
        if self.isVisible():
            self.refresh()

    def _confirm(self, categories):
        parts = []
        for k in categories:
            info = cleanup.CATEGORIES[k]
            parts.append(f"{info['title']}:\n{cleanup.describe(k)}\n{info['what']}")
        total = cleanup.size([p for k in categories for p in cleanup.files(k)])
        box = QMessageBox(QMessageBox.Icon.Warning, "Clear", "This will permanently delete:\n\n" + "\n\n".join(parts)
                          + f"\n\nIn total {cleanup.human(total)}. This cannot be undone.",
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def clear(self, key):
        self._clear([key])

    def clear_all(self):
        self._clear(list(cleanup.CATEGORIES))

    def _clear(self, keys):
        keys = [k for k in keys if cleanup.files(k)]
        if not keys:
            self.ctx.status("Nothing to clear.")
            return
        if not self._confirm(keys):
            return
        done, freed, problems = 0, 0, []
        for k in keys:
            n, b, p = cleanup.clear(k)
            done, freed, problems = done + n, freed + b, problems + p
            self.on_cleared(k)
        self.refresh()
        msg = f"Cleared {done} file(s), {cleanup.human(freed)} freed."
        self.data_note.setText(msg + (" Problems: " + "; ".join(problems) if problems else ""))
        self.ctx.status(msg, 8000)
        if problems:
            QMessageBox.warning(self, "Clear", msg + "\n\nThese could not be cleared:\n" + "\n".join(problems))

    # ------------------------------------------------------------ the choices
    def _spin(self, key, suffix="", step=1):
        sp = QSpinBox()
        _, lo, hi = settings.DEFAULTS[key]
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setSuffix(suffix)
        sp.setMaximumWidth(380)
        sp.setValue(settings.get(key))
        sp.valueChanged.connect(lambda v, k=key: settings.set(k, v))
        self.widgets[key] = sp
        return sp

    def _check(self, key, text):
        cb = QCheckBox(text)
        cb.setChecked(settings.get(key))
        cb.toggled.connect(lambda v, k=key: settings.set(k, v))
        self.widgets[key] = cb
        return cb

    @property
    def widgets(self):
        if not hasattr(self, "_widgets"):
            self._widgets = {}
        return self._widgets

    def load_values(self):
        for key, w in self.widgets.items():
            w.blockSignals(True)
            if isinstance(w, QCheckBox):
                w.setChecked(settings.get(key))
            else:
                w.setValue(settings.get(key))
            w.blockSignals(False)

    def _rate_box(self):
        box = QGroupBox("Rate limits")
        form = QFormLayout(box)
        form.addRow("A read may use", self._spin("rate.read_burst", " % of a route's limit at once"))
        form.addRow(hint("Roblox limits how many requests each route allows per minute. Changes (unfriend, leave, switch on ...) are always "
                         "spread evenly over the time. For reads, a higher number loads screens faster; 0 spreads them evenly too."))
        form.addRow(self._check("ui.rate_notes", "Show the orange note when the app waits to stay within Roblox's limit"))
        return box

    def _log_box(self):
        box = QGroupBox("Request log")
        form = QFormLayout(box)
        form.addRow(self._check("log.requests", "Write every request to requests.log"))
        form.addRow("Rows kept in the Request log tab", self._spin("log.keep_rows", " rows", 100))
        return box

    def _cache_box(self):
        box = QGroupBox("Saved pictures and names")
        form = QFormLayout(box)
        form.addRow("Reuse a saved picture for", self._spin("cache.avatar_days", " days"))
        form.addRow("Reuse a saved name for", self._spin("cache.names_days", " days"))
        return box

    def _ui_box(self):
        box = QGroupBox("Window and confirmations")
        form = QFormLayout(box)
        form.addRow(self._check("ui.remember_window", "Remember the window size and the tab you were on"))
        form.addRow("Ask me to type the number when I change", self._spin("confirm.typed_from", " people or groups or more at once"))
        row = QHBoxLayout()
        row.addWidget(button("Reset all settings", self.reset))
        row.addStretch()
        form.addRow(row)
        return box

    def reset(self):
        if self.ctx.confirm("Reset settings", "Put every setting back to its default?"):
            settings.reset()
            self.load_values()

    # ------------------------------------------------------------ about
    # ------------------------------------------------------------ updates from the git repository
    def _update_box(self):
        import updater
        self.updater = updater
        box = QGroupBox("Updates")
        lay = QVBoxLayout(box)
        self.upd_version = QLabel("")
        self.upd_version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.upd_version)
        form = QFormLayout()
        self.upd_repo = QLineEdit()
        self.upd_repo.setPlaceholderText("Address of the update repository, for example https://github.com/you/roblox-manager.git")
        self.upd_branch = QLineEdit()
        self.upd_branch.setMaximumWidth(200)
        self.upd_auto = QCheckBox("Look for updates and install them every time the app starts")
        self.upd_sig = QCheckBox("Only install updates signed with a key I trust (strongly recommended)")
        form.addRow("Update server", self.upd_repo)
        form.addRow("Branch", self.upd_branch)
        form.addRow(self.upd_auto)
        form.addRow(self.upd_sig)
        lay.addLayout(form)
        for w in (self.upd_repo, self.upd_branch):
            w.editingFinished.connect(self.save_update_settings)
        for w in (self.upd_auto, self.upd_sig):
            w.toggled.connect(lambda _=False: self.save_update_settings())
        row = QHBoxLayout()
        self.b_upd_check = button("Check now", self.check_updates)
        self.b_upd_apply = button("Update now", self.apply_update, "Download and install the newest version", primary=True)
        self.b_upd_back = button("Go back to the previous version", self.roll_back, "Puts back the version that was installed before the last update")
        self.b_upd_restart = button("Restart now", self.restart_app, "Close and open the app again, on the new version")
        self.b_upd_apply.setEnabled(False)
        self.b_upd_restart.hide()
        for b in (self.b_upd_check, self.b_upd_apply, self.b_upd_back, self.b_upd_restart):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.upd_status = hint("")
        lay.addWidget(self.upd_status)
        self.load_update_settings()
        return box

    def load_update_settings(self):
        u = self.updater
        cfg = u.load_config()
        for w, v in ((self.upd_repo, cfg["repo"]), (self.upd_branch, cfg["branch"])):
            w.blockSignals(True)
            w.setText(v)
            w.blockSignals(False)
        for w, v in ((self.upd_auto, cfg["auto"]), (self.upd_sig, cfg["require_signature"])):
            w.blockSignals(True)
            w.setChecked(bool(v))
            w.blockSignals(False)
        inst = u.installed()
        since = f", installed {inst['installed_at']}" if inst.get("installed_at") else ""
        self.upd_version.setText(f"Roblox Manager <b>{u.version()}</b>" + (f"  (commit {inst['commit'][:10]}{since})" if inst.get("commit") else ""))
        self.upd_version.setTextFormat(Qt.TextFormat.RichText)

    def save_update_settings(self):
        cfg = self.updater.load_config()
        cfg.update(repo=self.upd_repo.text().strip(), branch=self.upd_branch.text().strip() or "release", auto=self.upd_auto.isChecked(),
                   require_signature=self.upd_sig.isChecked())
        if not cfg["require_signature"] and not self.ctx.confirm(
                "Updates without a signature", "Without the signature check, anyone who can write to the update repository can run programs "
                "on this PC through an update.\n\nTurn the check off anyway?", danger=True):
            self.upd_sig.blockSignals(True)
            self.upd_sig.setChecked(True)
            self.upd_sig.blockSignals(False)
            cfg["require_signature"] = True
        self.updater.save_config(cfg)

    def _say_update(self, text, bad=False):
        self.upd_status.setText(text)
        self.upd_status.setProperty("role", "warn" if bad else "hint")
        self.upd_status.style().unpolish(self.upd_status)
        self.upd_status.style().polish(self.upd_status)

    def check_updates(self):
        self.save_update_settings()
        self._say_update("Asking the update server...")
        self.b_upd_check.setEnabled(False)

        def done(r):
            self.b_upd_check.setEnabled(True)
            self.b_upd_apply.setEnabled(r["status"] == "available")
            self._say_update(r["message"], bad=r["status"] == "error")
        self.ctx.async_.run(self.updater.check, done, lambda e: (self.b_upd_check.setEnabled(True), self._say_update(str(e), bad=True)))

    def apply_update(self):
        self.save_update_settings()
        self._say_update("Downloading and checking the update...")
        self.b_upd_apply.setEnabled(False)

        def done(r):
            self._say_update(r["message"], bad=r["status"] in ("error", "refused"))
            self.b_upd_restart.setVisible(r["status"] == "updated")
            self.load_update_settings()
        self.ctx.async_.run(self.updater.apply, done, lambda e: self._say_update(str(e), bad=True))

    def roll_back(self):
        if not self.ctx.confirm("Go back", "Go back to the version that was installed before the last update?"):
            return
        r = self.updater.rollback()
        self._say_update(r["message"], bad=r["status"] == "error")
        self.b_upd_restart.setVisible(r["status"] == "rolled-back")
        self.load_update_settings()

    def restart_app(self):
        import subprocess
        from pathlib import Path
        launcher = Path.home() / ".local/bin/roblox-manager"
        if launcher.exists():
            subprocess.Popen(["sh", "-c", f'sleep 1.5; exec "{launcher}"'], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _about_box(self):
        box = QGroupBox("Where things are")
        lay = QVBoxLayout(box)
        self.about = QLabel("")
        self.about.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.about.setWordWrap(True)
        lay.addWidget(self.about)
        row = QHBoxLayout()
        row.addWidget(button("Open the settings folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.CONFIG_DIR)))))
        row.addStretch()
        lay.addLayout(row)
        self.update_about()
        return box

    def update_about(self):
        kind, plain = accounts.storage_status()
        where = {"encrypted": "encrypted in the system wallet (KDE Wallet)", "plain": f"in {plain} plain private file(s): NOT encrypted (the wallet was not available)",
                 "none": "not saved (no account is signed in)"}[kind]
        self.about.setText(f"Sign-ins: {where}.<br>Settings, accounts list: <code>{rbx.CONFIG_DIR}</code><br>Logs, records, saved pictures and names: "
                           f"<code>{rbx.STATE_DIR}</code>")
        self.about.setTextFormat(Qt.TextFormat.RichText)

    def showEvent(self, ev):
        self.refresh()
        self.update_about()
        super().showEvent(ev)
