"""Settings tab: clear what the app saves on this PC (logs, records, saved pictures and names) and the app's few choices."""
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import accounts
import alerts
import backup
import cleanup
import plat
import rbx
import settings
from ui_common import esc, FlowLayout, WrapCheck, button, hint, make_table


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
        lay.addWidget(self._backup_box())
        lay.addWidget(self._rate_box())
        lay.addWidget(self._log_box())
        lay.addWidget(self._cache_box())
        self.update_box = self._update_box()       # shown on the Info tab's Updates page, next to the update log
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
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)           # the name takes what is left, so the buttons are never cut off
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        row = FlowLayout()
        self.b_all_logs = button("Clear all logs...", lambda: self.clear("logs"), "manager.log, requests.log and their older copies", danger=True)
        row.addWidget(self.b_all_logs)
        row.addWidget(button("Clear everything listed...", self.clear_all, "Logs, activity records, and saved pictures and names", danger=True))
        row.addStretch()
        row.addWidget(button("Open the folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.STATE_DIR)))))
        lay.addLayout(row)
        self.data_note = hint("")
        lay.addWidget(self.data_note)
        return box

    # ------------------------------------------------------------ backup
    def _backup_box(self):
        box = QGroupBox("Backup")
        lay = QVBoxLayout(box)
        lay.addWidget(hint("Save your settings, friend alerts and recently viewed games to a file, and bring them back later or on another computer. "
                           "Your sign-ins are never in the file."))
        self.c_lists = WrapCheck("Also keep a copy of my friends, followers, following and groups (needs sign-in)")
        self.c_lists.setChecked(True)
        lay.addWidget(self.c_lists)
        row = FlowLayout()
        self.b_backup = button("Save a backup...", self.save_backup, "Writes the backup file")
        row.addWidget(self.b_backup)
        row.addWidget(button("Restore from a backup...", self.restore_backup, "Brings back the settings, friend alerts and recently viewed games from a backup file"))
        row.addStretch()
        lay.addLayout(row)
        self.backup_note = hint("")
        lay.addWidget(self.backup_note)
        return box

    def save_backup(self, path=None):
        """Collect what is to be saved (the lists need requests to Roblox, so they are fetched in the background), then write the file."""
        c = self.ctx
        if path is None:
            from datetime import date
            path, _ = QFileDialog.getSaveFileName(self, "Save a backup", f"roblox-manager-backup-{date.today():%Y-%m-%d}.json", "Backup (*.json)")
            if not path:
                return
        import updater
        version = updater.version()
        want_lists = self.c_lists.isChecked() and c.logged_in
        client = c.client
        self.b_backup.setEnabled(False)
        self.backup_note.setText("Collecting..." if want_lists else "Saving...")

        def work():
            lists = {}
            if want_lists:
                lists = {"account": dict(client.user), "friends": client.friends(), "followers": client.followers(), "following": client.followings(),
                         "groups": client.my_groups()}
            return backup.save(path, backup.build(version, **lists))

        def done(size):
            self.b_backup.setEnabled(True)
            self.backup_note.setText(f"Saved {path} ({size // 1024 + 1} KB).")
            c.status("Backup saved.")

        def failed(e):
            self.b_backup.setEnabled(True)
            self.backup_note.setText(f"The backup was not saved: {e}")
            c.error(e) if isinstance(e, rbx.RobloxError) else None

        c.async_.run(work, done, failed)

    def restore_backup(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Restore from a backup", "", "Backup (*.json)")
            if not path:
                return
        try:
            data = backup.read(path)
        except backup.BackupError as e:
            self.backup_note.setText(str(e))
            QMessageBox.warning(self, "Backup", str(e))
            return
        if not self.ctx.confirm("Restore backup", "Replace your settings, friend alerts and recently viewed games with those in this backup?\n"
                                "Nothing on Roblox is changed and your sign-ins stay as they are."):
            return
        done = backup.restore(data)
        self.backup_note.setText(f"Restored {done['settings']} setting(s), {done['alerts']} watched friend(s) and {done['games']} recent game(s).")
        self.load_values()
        self.ctx.data_restored.emit()

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

    @staticmethod
    def _lab(text):
        """A form label that wraps when the window is narrow."""
        l = QLabel(text)
        l.setWordWrap(True)
        return l

    @staticmethod
    def _breakable(path):
        """A folder name for a label: lets a long path break after each separator instead of forcing the window wider."""
        return str(path).replace("\\", "\\\u200b").replace("/", "/\u200b")

    @staticmethod
    def _form(box):
        """A form whose long labels move above their field when the window is narrow, instead of running off the edge."""
        form = QFormLayout(box)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    def _check(self, key, text):
        cb = WrapCheck(text)
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
        form = self._form(box)
        form.addRow(self._lab("A read may use"), self._spin("rate.read_burst", " % of a route's limit at once"))
        form.addRow(hint("Roblox limits how many requests each route allows per minute. Changes (unfriend, leave, switch on ...) are always "
                         "spread evenly over the time. For reads, a higher number loads screens faster; 0 spreads them evenly too."))
        form.addRow(self._check("ui.rate_notes", "Show the orange note when the app waits to stay within Roblox's limit"))
        return box

    def _log_box(self):
        box = QGroupBox("Request log")
        form = self._form(box)
        form.addRow(self._check("log.requests", "Write every request to requests.log"))
        form.addRow(self._lab("Rows kept in the Request log tab"), self._spin("log.keep_rows", " rows", 100))
        return box

    def _cache_box(self):
        box = QGroupBox("Saved pictures and names")
        form = self._form(box)
        form.addRow(self._lab("Reuse a saved picture for"), self._spin("cache.avatar_days", " days"))
        form.addRow(self._lab("Reuse a saved name for"), self._spin("cache.names_days", " days"))
        return box

    def _ui_box(self):
        box = QGroupBox("Window and confirmations")
        form = self._form(box)
        self.c_alerts = WrapCheck("Friend alerts: a notification when friends I picked (People > Alerts) come online or join a game")
        self.c_alerts.setChecked(alerts.load()["enabled"])
        self.c_alerts.toggled.connect(self._alerts_toggled)
        form.addRow(self.c_alerts)
        self.ctx.alerts_changed.connect(self._alerts_synced)
        self.ctx.data_restored.connect(self._alerts_synced)
        form.addRow(self._check("ui.remember_window", "Remember the window size and the tab you were on"))
        form.addRow(self._lab("Ask me to type the number when I change"), self._spin("confirm.typed_from", " people or groups or more at once"))
        row = FlowLayout()
        row.addWidget(button("Reset all settings", self.reset))
        row.addStretch()
        form.addRow(row)
        return box

    def _alerts_toggled(self, on):
        data = alerts.load()
        data["enabled"] = bool(on)
        alerts.save(data)
        self.ctx.alerts_changed.emit()

    def _alerts_synced(self):
        self.c_alerts.blockSignals(True)
        self.c_alerts.setChecked(alerts.load()["enabled"])
        self.c_alerts.blockSignals(False)

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
        lic = QLabel('Free software under the <a href="https://www.gnu.org/licenses/gpl-3.0.html">GNU GPL v3</a>. Copyright (C) 2026 Miko. No warranty.')
        lic.setOpenExternalLinks(True)
        lic.setWordWrap(True)
        lay.addWidget(lic)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.upd_repo = QLineEdit()
        self.upd_repo.setPlaceholderText("Update repository address")
        self.upd_branch = QLineEdit()
        self.upd_branch.setMaximumWidth(200)
        self.upd_channel = QComboBox()
        self.upd_channel.addItem("Stable", "stable")
        self.upd_channel.addItem("Beta (early access)", "beta")
        self.upd_channel.setToolTip("Beta gets every update before it goes to Stable. You can go back to Stable at any time; you then keep the version you have until Stable catches up.")
        self.upd_channel_note = hint("")
        self.upd_channel_note.setWordWrap(True)
        self.upd_auto = WrapCheck("Look for updates and install them every time the app starts")
        self.upd_sig = WrapCheck("Only install updates signed with a key I trust (strongly recommended)")
        form.addRow(self._lab("Update server"), self.upd_repo)
        form.addRow(self._lab("Channel"), self.upd_channel)
        form.addRow(self.upd_channel_note)
        form.addRow(self._lab("Branch (stable)"), self.upd_branch)
        form.addRow(self.upd_auto)
        form.addRow(self.upd_sig)
        lay.addLayout(form)
        for w in (self.upd_repo, self.upd_branch):
            w.editingFinished.connect(self.save_update_settings)
        self.upd_channel.activated.connect(lambda _=0: self.channel_changed())
        for w in (self.upd_auto, self.upd_sig):
            w.toggled.connect(lambda _=False: self.save_update_settings())
        row = FlowLayout()
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
        self.upd_channel.blockSignals(True)
        self.upd_channel.setCurrentIndex(max(0, self.upd_channel.findData(cfg["channel"])))
        self.upd_channel.blockSignals(False)
        self._channel_note(cfg["channel"])
        for w, v in ((self.upd_auto, cfg["auto"]), (self.upd_sig, cfg["require_signature"])):
            w.blockSignals(True)
            w.setChecked(bool(v))
            w.blockSignals(False)
        inst = u.installed()
        since = f", installed {inst['installed_at']}" if inst.get("installed_at") else ""
        self.upd_version.setText(f"Roblox Manager <b>{u.version()}</b>" + (f"  (commit {inst['commit'][:10]}{since})" if inst.get("commit") else ""))
        self.upd_version.setTextFormat(Qt.TextFormat.RichText)

    def _channel_note(self, channel):
        self.upd_channel_note.setText("You get every new version first, before it goes to Stable. Beta versions are less tested." if channel == "beta"
                                      else "You get versions once they are released to everybody.")

    def channel_changed(self):
        """Switching to Beta asks first; switching back to Stable never installs an older version (the numbers never go down)."""
        want = self.upd_channel.currentData()
        before = self.updater.load_config()["channel"]
        if want == before:
            return
        if want == "beta" and not self.ctx.confirm(
                "Beta versions", "Beta versions get every update before it goes to everybody else. They are less tested and may have bugs.\n\n"
                "You can go back to Stable at any time: you then keep the version you have until Stable catches up.\n\nJoin the beta?"):
            self.upd_channel.blockSignals(True)
            self.upd_channel.setCurrentIndex(self.upd_channel.findData(before))
            self.upd_channel.blockSignals(False)
            return
        self.save_update_settings()
        self._channel_note(want)
        self.upd_status.setText("Channel changed. Press Check now to look for versions on it.")

    def save_update_settings(self):
        cfg = self.updater.load_config()
        cfg.update(repo=self.upd_repo.text().strip(), branch=self.upd_branch.text().strip() or "release", auto=self.upd_auto.isChecked(),
                   require_signature=self.upd_sig.isChecked(), channel=self.upd_channel.currentData() or "stable")
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
        if plat.IS_WIN:
            # the same program that runs the app, started again after a moment (the launcher checks for updates first)
            import sys
            script = Path(__file__).resolve().parent / "launcher.py"
            wait = "import subprocess, sys, time; time.sleep(1.5); subprocess.Popen(sys.argv[1:], close_fds=True)"
            subprocess.Popen([sys.executable, "-c", wait, sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x00000008 | 0x00000200)           # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            launcher = Path.home() / ".local/bin/roblox-manager"
            if launcher.exists():
                subprocess.Popen(["sh", "-c", 'sleep 1.5; exec "$0"', str(launcher)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)      # (the path is an argument, never part of the shell text)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _about_box(self):
        box = QGroupBox("Where things are")
        lay = QVBoxLayout(box)
        self.about = QLabel("")
        self.about.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.about.setWordWrap(True)
        lay.addWidget(self.about)
        row = FlowLayout()
        row.addWidget(button("Open the settings folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.CONFIG_DIR)))))
        row.addStretch()
        lay.addLayout(row)
        self.update_about()
        return box

    def update_about(self):
        kind, plain = accounts.storage_status()
        where = {"encrypted": f"encrypted ({plat.WALLET})", "plain": f"in {plain} plain private file(s): NOT encrypted (the wallet was not available)",
                 "none": "not saved (no account is signed in)"}[kind]
        self.about.setText(f"Sign-ins: {where}.<br>Settings, accounts list: <code>{esc(self._breakable(rbx.CONFIG_DIR))}</code><br>Logs, records, saved pictures and names: "
                           f"<code>{esc(self._breakable(rbx.STATE_DIR))}</code>")
        self.about.setTextFormat(Qt.TextFormat.RichText)

    def showEvent(self, ev):
        self.refresh()
        self.update_about()
        super().showEvent(ev)
