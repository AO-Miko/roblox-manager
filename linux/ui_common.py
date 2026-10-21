"""Shared pieces for the Roblox Manager window: background requests, dialogs, small helpers."""
import csv
import re
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QStyle, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import rbx
import settings

PRESENCE = {0: "Offline", 1: "Online", 2: "In game", 3: "In Studio"}
PRESENCE_COLOUR = {0: "#7d808a", 1: "#5ab0ff", 2: "#3ba55d", 3: "#e0a030"}


class _Bridge(QObject):
    done = Signal(object, object, object, int)


class Async:
    """Run a function on a worker thread; the callbacks always run back in the window's thread."""

    def __init__(self, on_error):
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.bridge = _Bridge()
        self.bridge.done.connect(self._finish)
        self.on_error = on_error
        self.pending = 0
        self.generation = 0          # bumped when the account changes: answers to tasks started before that are thrown away

    def run(self, fn, ok=None, err=None):
        self.pending += 1
        gen = self.generation

        def work():
            try:
                res = fn()
                self.bridge.done.emit(ok, res, None, gen)
            except rbx.Cancelled as e:
                self.bridge.done.emit(err, None, e, gen)       # stopped on purpose: callbacks still run so they can tidy up
            except Exception as e:          # noqa: BLE001 - everything is reported to the user, never swallowed
                rbx.log.info("task failed: %s", rbx.redact(e))
                self.bridge.done.emit(err, None, e, gen)
        try:
            self.pool.submit(work)
        except RuntimeError:             # the window was closed: nothing new may start
            self.pending = max(0, self.pending - 1)

    def _finish(self, cb, res, error, gen=None):
        self.pending = max(0, self.pending - 1)
        if gen is not None and gen != self.generation:
            return                   # it belonged to the account that was in use before the switch: never show it for the new one
        if error is not None:
            (cb or self.on_error)(error)
        elif cb:
            cb(res)


class Context(QObject):
    """What every tab needs: the API client, background runner, and ways to talk to the user."""
    signed_in = Signal()
    signed_out = Signal()
    accounts_changed = Signal()       # an account was added, removed or switched
    counts = Signal(str, object)      # (what, how many or None): shown in the tab titles (friends, requests, followers, following, blocked, groups, vip)

    def __init__(self, client, window):
        super().__init__()
        self.client, self.window = client, window
        self.async_ = Async(self.error)
        self.client_factory = rbx.Client      # makes a client for another account's cookie (balances of the accounts you are not using)
        self.busy_checks = []                 # callables that say whether a long batch is running (accounts cannot be switched meanwhile)
        self.stoppers = []                    # callables that stop a running batch (called when the window closes)

    def busy(self):
        return any(check() for check in self.busy_checks)

    def set_count(self, what, n):
        self.counts.emit(what, n)

    def stop_everything(self):
        """The window is closing: stop every batch and every request that is waiting, for good."""
        for stop in self.stoppers:
            try:
                stop()
            except Exception:       # noqa: BLE001 - closing must always go through
                pass
        self.client.cancel_pending(permanent=True)

    @property
    def me(self):
        return self.client.user

    @property
    def logged_in(self):
        return self.client.user is not None

    def status(self, text, ms=6000):
        self.window.statusBar().showMessage(text, ms)

    def error(self, e):
        if isinstance(e, rbx.Cancelled):
            self.status("Stopped.")
            return
        msg = str(e) if isinstance(e, rbx.RobloxError) else f"{e.__class__.__name__}: {rbx.redact(e)}"
        if "cancelled private server" in msg:
            msg = ("This VIP server's subscription is cancelled, so Roblox won't let it be changed (switched on/off, renamed, "
                   "given a new link or have its people changed).\n\nRenew it on roblox.com to configure it again, or leave it: "
                   "it will simply expire.")
        if "more active free private servers" in msg:
            msg = ("Roblox only lets you have a limited number of free VIP servers switched on at once (with Roblox Plus, one free "
                   "server).\n\nSwitch another free server off first, then try again.")
        self.status("Error: " + msg, 15000)
        if isinstance(e, rbx.RobloxError) and e.status in (401, 403) and not self.logged_in:
            msg += "\n\nSign in first: Home tab, Sign in."

        QMessageBox.warning(self.window, "Roblox said no", msg)

    def confirm(self, title, text, danger=False):
        box = QMessageBox(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question, title, text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.window)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def need_login(self):
        if not self.logged_in:
            QMessageBox.information(self.window, "Not signed in", "This needs your account. Open the Home tab and sign in first.")
            return True
        return False


# ------------------------------------------------------------------ helpers
def parse_id(text):
    """A place/group/user id from a number or a roblox.com link."""
    m = re.search(r"(?:games|groups|communities|users)/(\d+)", text or "") or re.search(r"(\d{3,})", text or "")
    return int(m.group(1)) if m else None


def when(iso):
    """'2026-10-20T18:00:00Z' -> '2026-10-20 18:00' in local time."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso)[:16]


def day_in_range(iso, start, end):
    """True when an ISO time falls on a day from `start` to `end` (datetime.date, both included, local time). Unknown never matches."""
    if not iso:
        return False
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return start <= d.astimezone().date() <= end


def copy_text(text):
    QGuiApplication.clipboard().setText(text)


def open_url(url):
    webbrowser.open(url)


class Table(QTableWidget):
    """A table that says something friendly in its middle while it is empty."""

    def __init__(self, rows, cols):
        super().__init__(rows, cols)
        self.empty_text = ""

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.empty_text and self.rowCount() == 0:
            p = QPainter(self.viewport())
            p.setPen(QColor("#6f788a"))
            f = p.font()
            f.setPointSizeF(f.pointSizeF() + 1)
            p.setFont(f)
            p.drawText(self.viewport().rect().adjusted(20, 30, -20, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       self.empty_text)
            p.end()


def make_table(headers, widths=None, stretch_last=True, select_rows=True, empty=""):
    t = Table(0, len(headers))
    t.empty_text = empty
    t.setShowGrid(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    t.verticalHeader().setDefaultSectionSize(32)
    t.horizontalHeader().setMinimumSectionSize(40)
    t.setFrameShape(QTableWidget.Shape.NoFrame)
    t.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    t.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    if select_rows:
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setSortingEnabled(True)
    t.horizontalHeader().setStretchLastSection(stretch_last)
    for i, w in enumerate(widths or []):
        t.setColumnWidth(i, w)
    enable_table_menu(t)
    return t


# ------------------------------------------------------------------ copy and export for every table
def table_rows(table, selected_only=False):
    """[headers] + the visible rows as text, with the columns in the order they are shown on screen."""
    head = table.horizontalHeader()
    cols = sorted(range(table.columnCount()), key=head.visualIndex)
    heads = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else "" for c in cols]
    rows = sorted({i.row() for i in table.selectedIndexes()}) if selected_only else range(table.rowCount())
    return [heads] + [[(table.item(r, c).text() if table.item(r, c) else "") for c in cols] for r in rows if not table.isRowHidden(r)]


def export_csv(table, parent=None, selected_only=False, name="export"):
    """Ask where, then write the table as CSV. Returns the path (or None if cancelled)."""
    path, _ = QFileDialog.getSaveFileName(parent or table, "Export as CSV", f"{name}.csv", "CSV files (*.csv)")
    if not path:
        return None
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(table_rows(table, selected_only))
    return path


def enable_table_menu(table):
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(lambda pos, t=table: _table_menu(t, pos))
    sc = QShortcut(QKeySequence.StandardKey.Copy, table)
    sc.setContext(Qt.ShortcutContext.WidgetShortcut)
    sc.activated.connect(lambda t=table: copy_text("\n".join("\t".join(r) for r in table_rows(t, True)[1:])))


def _table_menu(table, pos):
    m = QMenu(table)
    item = table.itemAt(pos)
    sel = bool({i.row() for i in table.selectedIndexes()})
    if item is not None:
        m.addAction("Copy cell", lambda: copy_text(item.text()))
    if sel:
        m.addAction("Copy selected rows", lambda: copy_text("\n".join("\t".join(r) for r in table_rows(table, True)[1:])))
    m.addAction("Copy all rows", lambda: copy_text("\n".join("\t".join(r) for r in table_rows(table)[1:])))
    m.addSeparator()
    name = table.property("export_name") or "table"
    if sel:
        m.addAction("Export selected rows as CSV...", lambda: export_csv(table, selected_only=True, name=name))
    m.addAction("Export all rows as CSV...", lambda: export_csv(table, name=name))
    m.exec(table.viewport().mapToGlobal(pos))


def fill_table(table, rows, colours=None, keys=None, icons=None):
    """rows: list of lists (strings or numbers). Numbers sort as numbers. colours: {(row, col): '#hex'}.
    keys: one hidden value per row (kept on column 0, so it stays with its row when the user sorts).
    icons: {row: QIcon} shown in column 0."""
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            it = QTableWidgetItem()
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                it.setData(Qt.ItemDataRole.DisplayRole, val)
            else:
                it.setText("" if val is None else str(val))
            if colours and (r, c) in colours:
                it.setForeground(QColor(colours[(r, c)]))
            if c == 0:
                if keys is not None:
                    it.setData(Qt.ItemDataRole.UserRole, keys[r])
                if icons and r in icons:
                    it.setIcon(icons[r])
            table.setItem(r, c, it)
    table.setSortingEnabled(True)


def row_key(table, row):
    """The hidden key of a row (see fill_table)."""
    it = table.item(row, 0)
    return it.data(Qt.ItemDataRole.UserRole) if it else None


def selected_rows(table):
    return sorted({i.row() for i in table.selectedIndexes()})


def cell(table, row, col):
    it = table.item(row, col)
    return it.text() if it else ""


def button(text, callback=None, tip="", primary=False, danger=False):
    b = QPushButton(text)
    if callback:
        b.clicked.connect(lambda _=False: callback())
    if tip:
        b.setToolTip(tip)
    if primary:
        b.setProperty("primary", True)      # the main action of a screen (filled with the accent colour)
    if danger:
        b.setProperty("danger", True)       # something that deletes or cannot be undone (red)
    return b


def hint(text):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setProperty("role", "hint")
    return l


class WrapCheck(QCheckBox):
    """A check box whose text wraps onto more lines when the window is narrow, instead of being cut off at the edge. It is a normal
    QCheckBox otherwise (isChecked, setChecked, toggled ...); clicking the text toggles it."""

    def __init__(self, text=""):
        super().__init__()
        self._label = QLabel(text, self)
        self._label.setWordWrap(True)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setMinimumWidth(60)
        self._gap = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth) + self.style().pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing) + 2
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def setText(self, text):
        self._label.setText(text)
        self.updateGeometry()

    def text(self):
        return self._label.text()

    def changeEvent(self, e):
        super().changeEvent(e)
        self._label.setEnabled(self.isEnabled())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._label.setGeometry(self._gap, 0, max(self.width() - self._gap, 1), self.height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return max(self._label.heightForWidth(max(w - self._gap, 1)), super().sizeHint().height())

    def sizeHint(self):
        return QSize(self._gap + self._label.sizeHint().width(), self.heightForWidth(self._gap + self._label.sizeHint().width()))

    def minimumSizeHint(self):
        return QSize(self._gap + 80, super().sizeHint().height())


class BulkBar(QWidget):
    """Progress for a long batch of requests: 'done/left, time left', a Stop button and a note when Roblox rate-limits.
    start()/report() may be called from a worker thread; the display always updates in the window's thread."""
    _progress = Signal(str, int, int, float)
    _rate = Signal(str, float, bool, bool)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.stop_flag = False
        self.running = False
        self.rate_hits = 0          # this session
        self.run_rate_hits = 0      # during the current batch
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("role", "warn")
        self.note.hide()
        lay.addWidget(self.note)
        row = QHBoxLayout()
        self.bar = QProgressBar()
        row.addWidget(self.bar, 1)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setToolTip("Finish the one in progress, then stop")
        self.stop_btn.clicked.connect(self.stop)
        row.addWidget(self.stop_btn)
        self.box = QWidget()
        row.setContentsMargins(0, 0, 0, 0)
        self.box.setLayout(row)
        self.box.hide()
        lay.addWidget(self.box)
        self._progress.connect(self._show)
        self._rate.connect(self._on_rate)
        ctx.client.rate_hooks.append(lambda path, wait, gave_up, proactive=False: self._rate.emit(path, wait, gave_up, proactive))
        ctx.busy_checks.append(lambda: self.running)
        ctx.stoppers.append(self.stop)
        self._clear = QTimer(self)
        self._clear.setSingleShot(True)
        self._clear.timeout.connect(self.note.hide)

    def start(self, label, total):
        self.running, self.stop_flag, self.run_rate_hits = True, False, 0
        self.stop_btn.setEnabled(True)
        gap = self.ctx.client.SLOW_GAP
        if total > 3:
            self.ctx.status(f"Pacing requests (about one every {gap:.0f} s) to stay under Roblox's limit; this will take about "
                            f"{max(1, int(total * gap // 60))} min.", 12000)
        self._progress.emit(label, 0, total, 0.0)

    def report(self, label, done, total, t0):
        self._progress.emit(label, done, total, time.time() - t0)

    def finish(self):
        self.running = False
        self.box.hide()
        self.ctx.client.clear_cancel()

    def stop(self):
        """Stop the batch now: nothing more is sent, and a request that is waiting (pacing, a rate-limit wait) is dropped."""
        self.stop_flag = True
        self.stop_btn.setEnabled(False)
        if self.running:
            self.ctx.client.cancel_pending()
        self.ctx.status("Stopping...")

    def _show(self, label, done, total, secs):
        if total <= 0:
            return
        left = ""
        if 0 < done < total:
            eta = secs / done * (total - done)
            left = f", about {int(eta // 60)}m {int(eta % 60):02d}s left" if eta >= 60 else f", about {int(eta)}s left"
        text = f"{label}: {done}/{total} done, {total - done} left{left}"
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.bar.setFormat(text)
        self.box.show()
        self.ctx.status(text, 4000)

    def _on_rate(self, path, wait, gave_up, proactive=False):
        if proactive:
            self.note.setText(f"Staying within Roblox's limit: waiting {wait:.0f} s on {path} (Roblox allows only so many of these per minute; nothing was refused).")
            if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
                self.note.show()
            self._clear.start(20000)
            return
        self.rate_hits += 1
        self.run_rate_hits += 1
        self.note.setText("Roblox is rate-limiting requests (too many in a short time). "
                          + (f"Gave up on one request to {path}." if gave_up else f"Waiting {wait:.0f} s before retrying {path}.")
                          + f" Times this session: {self.rate_hits}.")
        if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
            self.note.show()
        self._clear.start(20000)
