#!/usr/bin/env python3
"""Roblox Manager: your Roblox account from one window.

  Home           sign in (password + 2-step, browser, or cookie), your account at a glance
  People         friends, friend requests, followers, following, blocked users, find a user (all with bulk actions)
  Groups         your groups: members and ranks, join requests, roles, audit log, bans, shout; leave several at once
  VIP servers    every private server you have: switch on/off, renew, bulk actions, duplicates
  Money          Robux balance, pending, totals per period, transaction history, CSV export
  Request log    every request the app sends to Roblox and how Roblox answered (also written to requests.log)
  API Explorer   any Roblox web API endpoint: fill it in, send it, read the answer
  Settings       clear logs and saved data (with confirmation), rate-limit, log, cache and confirmation choices

  app.py              open the manager
  app.py --shot FILE  render the window to a PNG and exit (testing)
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtCore import QByteArray, QLockFile, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMainWindow, QMessageBox, QTabWidget

import accounts
import plat
import rbx
import settings
import theme
from tab_account import AccountTab
from tab_explorer import ExplorerTab
from tab_groups import GroupsTab
from tab_money import MoneyTab
from tab_people import PeopleTab
from tab_requests import RequestsTab
from tab_info import InfoTab
from tab_vip import VipTab
from ui_common import Context



class MainWindow(QMainWindow):
    def __init__(self, client=None, auto_login=True):
        super().__init__()
        self.setWindowTitle("Roblox Manager")
        self.resize(1180, 760)
        theme.apply(QApplication.instance(), rbx.STATE_DIR / "ui-assets")
        self.ctx = Context(client or rbx.Client(), self)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.account = AccountTab(self.ctx)
        self.people = PeopleTab(self.ctx)
        self.friends = self.people.friends
        self.groups = GroupsTab(self.ctx)
        self.vip = VipTab(self.ctx)
        self.money = MoneyTab(self.ctx, show_pending=self.account.pending_details)
        self.requests = RequestsTab(self.ctx)
        self.explorer = ExplorerTab(self.ctx)
        self.info_tab = InfoTab(self.ctx, on_cleared=self._cleared)
        self.settings_tab = self.info_tab.settings_tab
        for w, name in ((self.account, "Home"), (self.people, "People"), (self.groups, "Groups"), (self.vip, "VIP servers"),
                        (self.money, "Money"), (self.requests, "Request log"), (self.explorer, "API Explorer"),
                        (self.info_tab, "Info")):
            self.tabs.addTab(w, name)
        self.tabs.currentChanged.connect(lambda i: getattr(self.tabs.widget(i), "ensure_loaded", lambda: None)())
        # quick account switch, visible on every tab
        self.acct_combo = QComboBox()
        self.acct_combo.setMinimumWidth(190)
        self.acct_combo.setToolTip("The account in use. Pick another to switch to it, or add one.")
        self.acct_combo.activated.connect(self._account_picked)
        self.tabs.setCornerWidget(self.acct_combo, Qt.Corner.TopRightCorner)
        self.ctx.accounts_changed.connect(self._fill_accounts)
        self._fill_accounts()
        self.counts = {}
        self.ctx.counts.connect(self._on_count)
        self.ctx.signed_out.connect(lambda: [self.ctx.counts.emit(k, None) for k in ("friends", "requests", "followers", "following", "blocked", "groups", "vip")])
        self._restore_state(auto_login)
        self.who = QLabel("Not signed in")
        self.who.setContentsMargins(0, 0, 10, 0)
        self.statusBar().addPermanentWidget(self.who)
        self.ctx.signed_in.connect(lambda: self.who.setText(f"Signed in as {self.ctx.me['name']}"))
        self.ctx.signed_out.connect(lambda: self.who.setText("Not signed in"))
        self.statusBar().showMessage("Sign in on the Home tab to unlock friends, groups and VIP servers. The API Explorer works without one.")
        if auto_login and self.ctx.client.has_cookie:
            QTimer.singleShot(200, self.account.sign_in)

    def _cleared(self, category):
        if category == "logs":
            self.requests.clear()            # the list on screen goes too: it is the same history

    def _on_count(self, what, n):
        """Show how many there are in the tab titles: Groups (7), VIP servers (250), People (3 requests) ..."""
        self.counts[what] = n
        for widget, base, what_ in ((self.groups, "Groups", "groups"), (self.vip, "VIP servers", "vip")):
            if what == what_:
                self.tabs.setTabText(self.tabs.indexOf(widget), f"{base} ({format(n, ',')})" if n else base)
        if what == "requests":
            shown = n if isinstance(n, str) or n is None else format(n, ",")
            self.tabs.setTabText(self.tabs.indexOf(self.people), f"People ({shown} request{'' if n == 1 else 's'})" if n else "People")

    def _fill_accounts(self):
        active = accounts.active_id()
        self.acct_combo.blockSignals(True)
        self.acct_combo.clear()
        for a in accounts.list_accounts():
            self.acct_combo.addItem(f"{a['displayName'] or a['name']} (@{a['name']})", a["id"])
        self.acct_combo.addItem("Add another account..." if accounts.list_accounts() else "Sign in...", "add")
        idx = self.acct_combo.findData(active) if active is not None else -1
        self.acct_combo.setCurrentIndex(idx if idx >= 0 else self.acct_combo.count() - 1)
        self.acct_combo.blockSignals(False)

    def _account_picked(self, i):
        data = self.acct_combo.itemData(i)
        if data == "add":
            self.account.set_cookie()
        elif data != accounts.active_id():
            self.account.switch_to(data)
        self._fill_accounts()

    # ---- remembers the window size, the open tabs and the VIP list's hide switches between runs
    STATE_FILE = rbx.CONFIG_DIR / "ui.json"
    COLUMNS_VERSION = 3

    def _restore_state(self, enabled):
        self._state_on = enabled
        if not enabled or not settings.get("ui.remember_window"):
            return
        try:
            st = json.loads(self.STATE_FILE.read_text())
            if st.get("geometry"):
                self.restoreGeometry(QByteArray.fromBase64(st["geometry"].encode()))
            self.tabs.setCurrentIndex(min(int(st.get("tab", 0)), self.tabs.count() - 1))
            self.people.tabs.setCurrentIndex(min(int(st.get("people_tab", 0)), self.people.tabs.count() - 1))
            for k, cb in self.vip.hide.items():
                cb.setChecked(bool(st.get("vip_hide", {}).get(k, True)))
            if st.get("vip_columns") and st.get("vip_columns_version") == self.COLUMNS_VERSION:         # (an older layout is not restored: the columns got new widths)
                self.vip.mtable.horizontalHeader().restoreState(QByteArray.fromBase64(st["vip_columns"].encode()))
        except (OSError, ValueError, TypeError):
            pass

    def _save_state(self):
        if not getattr(self, "_state_on", False) or not settings.get("ui.remember_window"):
            return
        st = {"geometry": bytes(self.saveGeometry().toBase64()).decode(), "tab": self.tabs.currentIndex(),
              "people_tab": self.people.tabs.currentIndex(), "vip_hide": {k: cb.isChecked() for k, cb in self.vip.hide.items()},
              "vip_columns": bytes(self.vip.mtable.horizontalHeader().saveState().toBase64()).decode(), "vip_columns_version": self.COLUMNS_VERSION}
        try:
            self.STATE_FILE.write_text(json.dumps(st))
        except OSError:
            pass

    def closeEvent(self, ev):
        self._save_state()
        self.ctx.stop_everything()          # batches stop and waiting requests are dropped: nothing keeps running after the window is gone
        self.ctx.async_.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(ev)


SERVER_NAME = "roblox-manager"


def already_running():
    """True if another Roblox Manager holds the lock; in that case ask it to come to the front."""
    lock = QLockFile(str(rbx.STATE_DIR / "instance.lock"))
    lock.setStaleLockTime(0)        # a lock left behind by a crashed run is reclaimed
    if lock.tryLock(0):
        return None, lock
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(1500):
        sock.write(b"show")
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
    else:
        QMessageBox.information(None, "Roblox Manager", "Roblox Manager is already open.")
    return True, lock


ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Roblox Manager")
    QGuiApplication.setDesktopFileName("roblox-manager")        # ties the window to its launcher, so the taskbar shows the right icon
    if os.path.exists(ICON):
        app.setWindowIcon(QIcon(ICON))
    lock = None
    if "--shot" not in sys.argv:
        running, lock = already_running()
        if running:
            rbx.log.info("Another Roblox Manager is already open; showing it and exiting")
            sys.exit(0)
    if "--shot" not in sys.argv:
        accounts.migrate()          # sign-ins still in plain files move into the encrypted wallet
    w = MainWindow(auto_login="--shot" not in sys.argv)
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def raise_window():
        server.nextPendingConnection()
        w.showNormal()
        w.raise_()
        w.activateWindow()
    server.newConnection.connect(raise_window)
    w.show()
    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        tab = int(sys.argv[sys.argv.index("--tab") + 1]) if "--tab" in sys.argv else 0
        w.tabs.setCurrentIndex(tab)
        QTimer.singleShot(1500, lambda: (w.grab().save(out), app.quit()))
    code = app.exec()
    # leave at once: a request that was already on its way cannot be recalled, but nothing else is sent and no thread keeps the app alive
    if lock is not None:
        lock.unlock()
    logging.shutdown()
    plat.hard_exit(code)


if __name__ == "__main__":
    main()
