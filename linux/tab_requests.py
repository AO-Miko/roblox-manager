"""Requests tab: a live list of every request this app sends to Roblox and how Roblox answered.

The same lines are written to requests.log in the state folder (rotated, about 8 MB at most). Nothing secret is ever recorded: no cookie,
no password or code, no request body, no headers; the value of anything in an address that looks like a secret is hidden.
"""
import time
from collections import deque
from datetime import datetime

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget

import rbx
import settings
from ui_common import button, export_csv, hint, make_table

KEEP = 5000
WINDOW = 30            # seconds the 'recent' counters look back (Roblox's limit for changes is measured in about this window)
# Routes that change something. Their limit cannot be asked without changing something, so Roblox reports it the first time one is used.
CHANGING_ROUTES = [
    "POST friends.roblox.com/v1/users/{n}/unfriend", "POST friends.roblox.com/v1/users/{n}/accept-friend-request",
    "POST friends.roblox.com/v1/users/{n}/decline-friend-request", "POST friends.roblox.com/v1/users/{n}/request-friendship",
    "POST friends.roblox.com/v1/users/{n}/follow", "POST friends.roblox.com/v1/users/{n}/unfollow",
    "DELETE groups.roblox.com/v1/groups/{n}/users/{n}", "PATCH games.roblox.com/v1/vip-servers/{n}",
    "PATCH games.roblox.com/v1/vip-servers/{n}/subscription", "POST apis.roblox.com/user-blocking-api/v1/users/{n}/block-user",
    "POST apis.roblox.com/user-blocking-api/v1/users/{n}/unblock-user",
]
HEADERS = ["Time", "Account", "Method", "Request", "Status", "ms", "Notes", "Rate limit (from Roblox)"]


def status_colour(e):
    s = e["status"]
    if s is None:
        return "#7d808a" if "cancelled" in e["note"] or "cool-down" in e["note"] else "#e5534b"
    if s == 429 or s >= 500:
        return "#e5534b"
    if s >= 400:
        return "#e0a030"
    return "#3ba55d"


def is_problem(e):
    return e["status"] is None or e["status"] >= 400


def entry_cells(e):
    t = datetime.fromtimestamp(e["time"])
    return [t.strftime("%H:%M:%S.") + f"{t.microsecond // 1000:03d}", e["account"], e["method"],
            e["host"] + e["path"] + (f"?{e['query']}" if e["query"] else ""),
            "-" if e["status"] is None else str(e["status"]), "" if e["ms"] is None else str(e["ms"]),
            (e["note"] + (" " if e["note"] and (e["paced"] or e["attempt"]) else "") + ("[paced] " if e["paced"] else "")
             + (f"[retry {e['attempt']}]" if e["attempt"] else "")).strip(), e.get("rate", "")]


def summary(entries, now=None, window=WINDOW):
    """(requests, changes, 429s, problems) in the last `window` seconds."""
    now = now or time.time()
    recent = [e for e in entries if e["time"] >= now - window and e["status"] is not None]
    return (len(recent), sum(1 for e in recent if e["method"] != "GET"), sum(1 for e in recent if e["status"] == 429),
            sum(1 for e in recent if e["status"] >= 400))


class RequestsTab(QWidget):
    _entry = Signal(object)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.entries = deque(maxlen=KEEP)
        self.queue = []
        self.total = 0
        self.btn_probe_running = False
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter lines...")
        self.filter.setToolTip("Any word in the line: account, method, address, status, note")
        self.filter.setMinimumWidth(140)
        self.filter.textChanged.connect(lambda _=None: self.rebuild())
        top.addWidget(self.filter, 1)
        self.only_problems = QCheckBox("Only problems")
        self.only_problems.setToolTip("Errors (4xx, 5xx), rate limits (429), network errors and stops")
        self.only_problems.toggled.connect(lambda _=False: self.rebuild())
        self.pause = QCheckBox("Pause")
        self.pause.setToolTip("Stop adding rows to the list (requests are still logged and counted)")
        self.follow = QCheckBox("Follow newest")
        self.follow.setChecked(True)
        for w in (self.only_problems, self.pause, self.follow):
            top.addWidget(w)
        top.addWidget(button("Clear list", self.clear, "Empties this list (the log file is kept)"))
        top.addWidget(button("Export CSV...", lambda: export_csv(self.table, self, name="roblox-manager-requests")))
        top.addWidget(button("Open log folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.STATE_DIR))),
                             "Where requests.log is kept"))
        lay.addLayout(top)
        self.stats = QLabel("")
        self.stats.setStyleSheet("font-size: 14px;")
        lay.addWidget(self.stats)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = make_table(HEADERS, [100, 90, 72, 430, 62, 56, 170, 270], empty="No requests yet.\nEverything the app asks Roblox appears here as it happens.")
        self.table.setSortingEnabled(False)          # newest at the bottom, in the order they happened
        self.table.setProperty("export_name", "roblox-manager-requests")
        split.addWidget(self.table)
        lim = QWidget()
        ll = QVBoxLayout(lim)
        ll.setContentsMargins(0, 4, 0, 0)
        lrow = QHBoxLayout()
        title = QLabel("Limits Roblox has reported (per route, for the account in use)")
        title.setStyleSheet("font-weight: bold;")
        lrow.addWidget(title)
        lrow.addStretch()
        self.btn_probe = button("Check limits now", self.probe, "Sends one harmless read request to each route the app reads from (about 20 requests) "
                                "so Roblox reports its limit. Routes that change something are learned the first time they are used.")
        lrow.addWidget(self.btn_probe)
        ll.addLayout(lrow)
        self.limits = make_table(["Route", "Limit", "Window", "Left now", "Resets in"], [520, 70, 80, 90, 90], empty="Nothing learned yet. Press \"Check limits now\".")
        self.limits.setSortingEnabled(False)
        self.limits.setProperty("export_name", "roblox-rate-limits")
        ll.addWidget(self.limits, 1)
        split.addWidget(lim)
        split.setSizes([420, 230])
        lay.addWidget(split, 1)
        lay.addWidget(hint(f"Every request is also written to {rbx.STATE_DIR / 'requests.log'}. Cookies, passwords, codes, request bodies and headers are never "
                           "recorded. Roblox allows roughly 12 changes (anything that is not a plain read) per 30 seconds."))
        self._entry.connect(self._add)
        rbx.LISTENERS.append(lambda e: self._entry.emit(e))
        self.flush_timer = QTimer(self)
        self.flush_timer.timeout.connect(self.flush)
        self.flush_timer.start(400)
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(1000)
        self.update_stats()

    # ---------------------------------------------------------------- data
    def _add(self, e):
        self.entries.append(e)
        self.total += 1
        self.queue.append(e)

    def matches(self, e):
        if self.only_problems.isChecked() and not is_problem(e):
            return False
        q = self.filter.text().strip().lower()
        return not q or all(w in " ".join(entry_cells(e)).lower() for w in q.split())

    def _row(self, e):
        r = self.table.rowCount()
        self.table.insertRow(r)
        colour = QColor(status_colour(e))
        for c, text in enumerate(entry_cells(e)):
            it = QTableWidgetItem(text)
            if c == 4:
                it.setForeground(colour)
            self.table.setItem(r, c, it)

    def flush(self):
        """Add the requests that arrived since the last tick (a batch at a time, so a busy moment never freezes the window)."""
        if not self.queue:
            return
        batch, self.queue = self.queue, []
        if self.pause.isChecked():
            return
        for e in batch:
            if self.matches(e):
                self._row(e)
        extra = self.table.rowCount() - settings.get("log.keep_rows")
        if extra > 0:
            for _ in range(extra):
                self.table.removeRow(0)
        if self.follow.isChecked():
            self.table.scrollToBottom()

    def rebuild(self):
        self.table.setRowCount(0)
        for e in list(self.entries)[-settings.get("log.keep_rows") * 3:]:
            if self.matches(e):
                self._row(e)
        extra = self.table.rowCount() - settings.get("log.keep_rows")
        for _ in range(max(0, extra)):
            self.table.removeRow(0)
        if self.follow.isChecked():
            self.table.scrollToBottom()

    def clear(self):
        self.table.setRowCount(0)
        self.entries.clear()
        self.queue = []

    def update_limits(self):
        """Show every route Roblox has reported a limit for (live), plus the changing routes whose limit is not known yet."""
        rows = self.ctx.client.rates.snapshot() if self.ctx.client else []
        known = {r["route"] for r in rows}
        data = [[r["route"], "" if r["limit"] is None else r["limit"], f"{r['window']} s" if r["window"] else "",
                 "" if r["left"] is None else r["left"], f"{r['reset_in']:.0f} s" if r["reset_in"] else ""] for r in rows]
        data += [[k, "unknown until first use", "", "", ""] for k in CHANGING_ROUTES if k not in known]
        t = self.limits
        t.setRowCount(len(data))
        for i, row in enumerate(data):
            for c, v in enumerate(row):
                it = t.item(i, c)
                if it is None:
                    it = QTableWidgetItem()
                    t.setItem(i, c, it)
                it.setData(Qt.ItemDataRole.DisplayRole, v)
                if row[1] == "unknown until first use":
                    it.setForeground(QColor("#7d808a"))
                elif c == 3 and isinstance(v, int) and isinstance(row[1], int) and row[1] and v <= max(1, row[1] // 10):
                    it.setForeground(QColor("#e0a030"))            # nearly used up

    def probe(self):
        c = self.ctx
        if c.need_login() or self.btn_probe_running:
            return
        self.btn_probe_running = True
        self.btn_probe.setEnabled(False)
        c.status("Checking limits: one read request per route...", 10000)

        def done(n):
            self.btn_probe_running = False
            self.btn_probe.setEnabled(True)
            self.update_limits()
            c.status(f"Learned the limits of {n} more route(s).", 8000)

        def failed(e):
            self.btn_probe_running = False
            self.btn_probe.setEnabled(True)
            c.error(e)
        c.async_.run(lambda: c.client.probe_limits(), done, failed)

    def update_stats(self):
        self.update_limits()
        n, changes, limited, problems = summary(self.entries)
        text = f"Last {WINDOW} s: <b>{n}</b> requests, <b>{changes}</b> changes, "
        text += f"<b style='color:#e5534b'>{limited} rate-limited (429)</b>" if limited else "no rate limits"
        text += f", {problems} problem(s).   Since the app started: {self.total:,} requests."
        self.stats.setText(text)
