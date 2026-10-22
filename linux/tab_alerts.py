"""Friend alerts (People > Alerts): pick friends to watch and get a notification when they come online or join a game."""
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QTableWidgetItem, QVBoxLayout, QWidget

import alerts
from ui_common import PRESENCE, button, hint, make_table


class AlertsTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.data = alerts.load()
        self.friends = []            # [{id, name, displayName}] of the signed-in account
        self.snap = {}               # the last look at the watched friends
        self._loading = self._polling = self._filling = False
        self._gen = 0
        self.timer = QTimer(self)
        self.timer.setInterval(alerts.INTERVAL_S * 1000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

        lay = QVBoxLayout(self)
        lay.addWidget(hint("Tick the friends you want news about. While the app is open, it looks at them every "
                           f"{alerts.INTERVAL_S} seconds and shows a notification when one comes online or joins a game. Nothing is sent to anyone but Roblox."))
        row = QHBoxLayout()
        self.on = QCheckBox("Alerts on")
        self.on.setToolTip("Switches all alerts on or off")
        self.on.setChecked(self.data["enabled"])
        self.on.toggled.connect(lambda v: self._option("enabled", v))
        self.c_online = QCheckBox("when a friend comes online")
        self.c_online.setChecked(self.data["online"])
        self.c_online.toggled.connect(lambda v: self._option("online", v))
        self.c_game = QCheckBox("when a friend joins a game")
        self.c_game.setChecked(self.data["ingame"])
        self.c_game.toggled.connect(lambda v: self._option("ingame", v))
        for w in (self.on, self.c_online, self.c_game):
            row.addWidget(w)
        row.addStretch()
        lay.addLayout(row)

        row = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter friends...")
        self.filter.textChanged.connect(lambda _=None: self.show_friends())
        row.addWidget(self.filter, 1)
        row.addWidget(button("Watch all shown", lambda: self._watch_shown(True), f"Ticks every friend in the list below (up to {alerts.MAX_WATCHED})"))
        row.addWidget(button("Watch none", lambda: self._watch_shown(False), "Unticks every friend in the list below"))
        row.addWidget(button("Refresh", lambda: self.load(True)))
        row.addWidget(button("Test", self.test, "Shows a test notification"))
        lay.addLayout(row)
        self.table = make_table(["Watch", "Friend", "Username", "Now"], [60, 200, 160, 110], empty="No friends to show.")
        self.table.setSelectionMode(self.table.SelectionMode.NoSelection)
        self.table.setSortingEnabled(False)
        self.table.itemChanged.connect(self._ticked)
        lay.addWidget(self.table, 1)
        self.count = QLabel("")
        lay.addWidget(self.count)
        lay.addWidget(QLabel("Latest news:"))
        self.news = QListWidget()
        self.news.setMaximumHeight(110)
        lay.addWidget(self.news)

        ctx.signed_in.connect(self._signed_in)
        ctx.signed_out.connect(self._signed_out)
        ctx.data_restored.connect(self._restored)

    # ---------------------------------------------------------------- what is watched
    def _me(self):
        return str(self.ctx.me["id"]) if self.ctx.logged_in else None

    def watched(self):
        me = self._me()
        return self.data["watch"].setdefault(me, {}) if me else {}

    def _option(self, key, value):
        self.data[key] = bool(value)
        alerts.save(self.data)
        if key == "enabled" and value:
            self.snap = {}
            self.poll()

    def _ticked(self, item):
        if self._filling or item.column() != 0:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        w = self.watched()
        if item.checkState() == Qt.CheckState.Checked:
            if len(w) >= alerts.MAX_WATCHED and str(fid) not in w:
                self.ctx.status(f"At most {alerts.MAX_WATCHED} friends can be watched.")
                self._filling = True
                item.setCheckState(Qt.CheckState.Unchecked)
                self._filling = False
                return
            w[str(fid)] = next((f.get("displayName") or f.get("name") or "" for f in self.friends if f["id"] == fid), "")
        else:
            w.pop(str(fid), None)
            self.snap.pop(fid, None)
        alerts.save(self.data)
        self._count()

    def _watch_shown(self, on):
        if not self.ctx.logged_in:
            return
        w = self.watched()
        for f in self._shown_friends():
            if on and len(w) < alerts.MAX_WATCHED:
                w[str(f["id"])] = f.get("displayName") or f.get("name") or ""
            elif not on:
                w.pop(str(f["id"]), None)
                self.snap.pop(f["id"], None)
        alerts.save(self.data)
        self.show_friends()

    def _count(self):
        n = len(self.watched())
        self.count.setText(f"{n} friend(s) watched" + ("" if self.data["enabled"] else "  (alerts are off)"))

    # ---------------------------------------------------------------- the friends list
    def ensure_loaded(self):
        if self.ctx.logged_in and not self.friends:
            self.load()

    def load(self, force=False):
        c = self.ctx
        if c.need_login() or self._loading:
            return
        self._loading = True
        gen = self._gen
        c.async_.run(c.client.friends, lambda d: self._loaded(gen, d), lambda e: (setattr(self, "_loading", False), c.error(e)))

    def _loaded(self, gen, friends):
        self._loading = False
        if gen != self._gen:
            return
        self.friends = sorted(friends, key=lambda f: (f.get("displayName") or f.get("name") or "").lower())
        w = self.watched()
        for f in self.friends:                       # keep the saved names current
            if str(f["id"]) in w:
                w[str(f["id"])] = f.get("displayName") or f.get("name") or w[str(f["id"])]
        self.show_friends()
        if self.data["enabled"]:
            self.poll()

    def _shown_friends(self):
        q = self.filter.text().strip().lower()
        return [f for f in self.friends if not q or q in (f.get("name") or "").lower() or q in (f.get("displayName") or "").lower()]

    def show_friends(self):
        w = self.watched()
        rows = self._shown_friends()
        self._filling = True
        t = self.table
        t.setRowCount(len(rows))
        for r, f in enumerate(rows):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            box.setCheckState(Qt.CheckState.Checked if str(f["id"]) in w else Qt.CheckState.Unchecked)
            box.setData(Qt.ItemDataRole.UserRole, f["id"])
            t.setItem(r, 0, box)
            for col, text in ((1, f.get("displayName") or f.get("name") or ""), (2, f.get("name") or ""), (3, self._now(f["id"]))):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                t.setItem(r, col, it)
        self._filling = False
        self._count()

    def _now(self, fid):
        s = self.snap.get(fid)
        return PRESENCE.get(s[0], "") if s else ""

    # ---------------------------------------------------------------- looking at the watched friends
    def poll(self):
        c = self.ctx
        ids = [int(i) for i in self.watched()]
        if not (self.data["enabled"] and c.logged_in and ids) or self._polling or c.busy():
            return
        self._polling = True
        gen = self._gen
        c.async_.run(lambda: c.client.presence(ids), lambda p: self._polled(gen, p), lambda e: setattr(self, "_polling", False))

    def _polled(self, gen, presences):
        self._polling = False
        if gen != self._gen:
            return
        now = alerts.snapshot(presences)
        names = {int(i): n for i, n in self.watched().items()}
        found = alerts.news(self.snap, now, names, self.data["online"], self.data["ingame"])
        self.snap = now
        for _, _, text in found[:5]:
            self.notify(text)
        if len(found) > 5:
            self.notify(f"...and {len(found) - 5} more friends")
        self.show_friends()

    def notify(self, text):
        self.news.insertItem(0, f"{datetime.now():%H:%M}  {text}")
        while self.news.count() > alerts.KEEP_NEWS:
            self.news.takeItem(self.news.count() - 1)
        self.ctx.notify("Roblox Manager", text)

    def test(self):
        self.notify("This is how a friend alert looks.")

    # ---------------------------------------------------------------- accounts
    def _signed_in(self):
        self._gen += 1
        self.snap, self.friends, self._loading, self._polling = {}, [], False, False
        self.data = alerts.load()
        for box, key in ((self.on, "enabled"), (self.c_online, "online"), (self.c_game, "ingame")):
            box.blockSignals(True)
            box.setChecked(self.data[key])
            box.blockSignals(False)
        self.show_friends()

    def _restored(self):
        self._signed_in()
        if self.ctx.logged_in:
            self.load()

    def _signed_out(self):
        self._gen += 1
        self.snap, self.friends, self._loading, self._polling = {}, [], False, False
        self.show_friends()
