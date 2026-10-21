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
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

import accounts
import bans
import nav
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
        self.setMinimumSize(560, 420)
        theme.apply(QApplication.instance(), rbx.STATE_DIR / "ui-assets")
        self.ctx = Context(client or rbx.Client(), self)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()               # the side bar is the way around now (the tab widget still holds the pages, their titles and the counts)
        self.tabs.setDocumentMode(True)
        self.account = AccountTab(self.ctx)
        self.people = PeopleTab(self.ctx)
        self.friends = self.people.friends
        self.groups = GroupsTab(self.ctx)
        self.vip = VipTab(self.ctx)
        self.money = MoneyTab(self.ctx, show_pending=self.account.pending_details)
        self.requests = RequestsTab(self.ctx)
        self.explorer = ExplorerTab(self.ctx)
        self.info_tab = InfoTab(self.ctx, on_cleared=self._cleared)
        self.holders = {}
        self.settings_tab = self.info_tab.settings_tab
        for w, name in ((self.account, "Home"), (self.people, "People"), (self.groups, "Groups"), (self.vip, "VIP servers"),
                        (self.money, "Money"), (self.requests, "Request log"), (self.explorer, "API Explorer"),
                        (self.info_tab, "Info")):
            holder = nav.PageHolder(w)
            self.holders[w] = holder
            self.tabs.addTab(holder, name)
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i).ensure_loaded())
        # quick account switch, visible on every tab
        self.acct_combo = QComboBox()
        self.acct_combo.setMinimumWidth(190)
        self.acct_combo.setToolTip("The account in use. Pick another to switch to it, or add one.")
        self.acct_combo.activated.connect(self._account_picked)
        import updater
        self.sidebar = nav.Sidebar(self.tabs, self.acct_combo, f"Version {updater.version()}")
        self.sidebar.picked.connect(self.tabs.setCurrentIndex)
        self.sidebar.search_requested.connect(self.open_search)
        self.header = nav.PageHeader()
        self.tabs.currentChanged.connect(lambda i: self.header.show_page(self.tabs.tabText(i)))
        self.tabs.currentChanged.connect(lambda i: self.setWindowTitle(f"{nav.base_title(self.tabs.tabText(i))[0]} - Roblox Manager"))
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.header)
        rl.addWidget(self.tabs, 1)
        shell = QWidget()
        sl = QHBoxLayout(shell)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(self.sidebar)
        sl.addWidget(right, 1)
        self.setCentralWidget(shell)
        self.palette_box = nav.Palette(self, self._search_entries)
        self._shortcuts = nav.install_shortcuts(self)
        self.header.show_page(self.tabs.tabText(0))
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
        if auto_login:                                   # the ban list: now, and every ten minutes while the app is open
            self._ban_timer = QTimer(self)
            self._ban_timer.timeout.connect(self._check_bans)
            self._ban_timer.start(bans.REFRESH_SECONDS * 1000)
            QTimer.singleShot(1500, self._check_bans)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        compact = self.width() < 1000            # a narrow window keeps only the icons, so the pages get the room
        if compact != (self.sidebar.width() == self.sidebar.COMPACT):
            self.sidebar.set_compact(compact)

    # ---- search (Ctrl+K) and reload (F5)
    def current_page(self):
        return self.tabs.currentWidget().page

    def open_search(self):
        self.palette_box.open()

    def _go(self, page, sub=None, row=None, table=None):
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.holders[page]))
        if sub is not None and hasattr(page, "tabs"):
            page.tabs.setCurrentIndex(sub)
        if table is not None and row is not None and row < table.rowCount():
            table.selectRow(row)
            table.scrollToItem(table.item(row, 0))

    def _search_entries(self):
        """Everything the search can jump to: pages, their sub pages, accounts, and the friends, groups and servers that are loaded."""
        out = []
        for i in range(self.tabs.count()):
            name = nav.base_title(self.tabs.tabText(i))[0]
            page = self.tabs.widget(i).page
            out.append((name, "page", nav.KEYWORDS.get(name, ""), lambda page=page: self._go(page)))
            if page is self.people:
                for j in range(page.tabs.count()):
                    sub = nav.base_title(page.tabs.tabText(j))[0]
                    out.append((sub, "People", "", lambda page=page, j=j: self._go(page, j)))
            if page is self.info_tab:
                for j in range(page.count()):
                    sub = page.tabText(j)
                    out.append((sub, "Info", "update version changes" if sub == "Updates" else "preferences options", lambda page=page, j=j: (self._go(page), page.setCurrentIndex(j))))
        for a in accounts.list_accounts():
            if a["id"] != accounts.active_id():
                out.append((f"Switch to {a['displayName'] or a['name']}", "account", f"@{a['name']} account", lambda a=a: self.account.switch_to(a["id"])))
        out.append(("Add another account", "account", "sign in login cookie", lambda: self.account.set_cookie()))
        loaded = ((self.friends.table, self.people, 0, "friend", 2), (self.groups.glist, self.groups, None, "group", 1), (self.vip.mtable, self.vip, None, "VIP server", 2))
        for table, page, sub, kind, ncols in loaded:
            for r in range(min(table.rowCount(), 2000)):
                label = " - ".join(x for x in (table.item(r, c).text() if table.item(r, c) else "" for c in range(ncols)) if x)
                if label:
                    out.append((label, kind, "", lambda page=page, sub=sub, r=r, table=table: self._go(page, sub, r, table)))
        return out

    def reload_page(self):
        page = self.current_page()
        inner = page.tabs.currentWidget() if page is self.people else page
        for name in ("load", "load_groups", "load_mine"):
            fn = getattr(inner, name, None)
            if callable(fn) and self.ctx.client.has_cookie:
                fn()
                self.statusBar().showMessage("Reloading...", 2000)
                return

    def _check_bans(self):
        self.ctx.async_.run(bans.refresh, lambda _: self.account.enforce_bans())

    def _cleared(self, category):
        if category == "logs":
            self.requests.clear()            # the list on screen goes too: it is the same history

    def _on_count(self, what, n):
        """Show how many there are in the tab titles: Groups (7), VIP servers (250), People (3 requests) ..."""
        self.counts[what] = n
        for widget, base, what_ in ((self.groups, "Groups", "groups"), (self.vip, "VIP servers", "vip")):
            if what == what_:
                self.tabs.setTabText(self.tabs.indexOf(self.holders[widget]), f"{base} ({format(n, ',')})" if n else base)
                self.sidebar.sync()
        if what == "requests":
            shown = n if isinstance(n, str) or n is None else format(n, ",")
            self.tabs.setTabText(self.tabs.indexOf(self.holders[self.people]), f"People ({shown} request{'' if n == 1 else 's'})" if n else "People")
            self.sidebar.sync()

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
