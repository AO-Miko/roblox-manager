"""App debug: everything that happens in the app, with the output (a view inside the Request log tab).

The events come from debuglog.py: requests with what was sent and what came back, background tasks and their results, button presses, pages and dialogs
that were opened, messages shown to you, settings changed, sign-ins, warnings and errors (with the full trace), and what the program prints. Everything
private is hidden before an event is even kept (see debuglog.scrub), so the list can be copied or saved and shown to somebody.
"""
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QTabWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import debuglog
import rbx
from ui_common import button, hint, make_table
from theme import Live, T

LEVEL_COLOUR = Live({"debug": "faint", "info": "muted", "warning": "warn", "error": "danger"})
LEVEL_CHOICES = [("Everything", "debug"), ("Info and more serious", "info"), ("Warnings and errors", "warning"), ("Errors only", "error")]
ROWS = 3000


class DebugView(QWidget):
    _event = Signal(object)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.rows = []              # the events shown, one per table row
        self.queue = []
        self.areas = set()
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter events...")
        self.filter.setToolTip("Any word of the line or of its output")
        self.filter.setMinimumWidth(140)
        self.filter.textChanged.connect(lambda _=None: self.rebuild())
        top.addWidget(self.filter, 1)
        self.level = QComboBox()
        for label, key in LEVEL_CHOICES:
            self.level.addItem(label, key)
        self.level.setToolTip("Hide the less important events")
        self.level.currentIndexChanged.connect(lambda _=0: self.rebuild())
        top.addWidget(self.level)
        self.area = QComboBox()
        self.area.addItem("All areas", "")
        self.area.setToolTip("Only one kind of event: http, task, click, page, dialog, settings, account, output, crash ...")
        self.area.currentIndexChanged.connect(lambda _=0: self.rebuild())
        top.addWidget(self.area)
        self.pause = QCheckBox("Pause")
        self.pause.setToolTip("Stop adding rows to the list (events are still kept)")
        self.follow = QCheckBox("Follow newest")
        self.follow.setChecked(True)
        top.addWidget(self.pause)
        top.addWidget(self.follow)
        lay.addLayout(top)
        row2 = QHBoxLayout()
        self.count = QLabel("")
        row2.addWidget(self.count, 1)
        row2.addWidget(button("Copy", self.copy, "Copy the events shown (with their output) as text"))
        row2.addWidget(button("Save as text...", self.save, "Save the events shown (with their output) to a text file"))
        row2.addWidget(button("Clear list", self.clear, "Empties this list (debug.log is kept)"))
        row2.addWidget(button("Open log folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rbx.STATE_DIR))), "Where debug.log is kept"))
        lay.addLayout(row2)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = make_table(["Time", "Level", "Area", "What happened"], [110, 72, 80, 760], empty="Nothing yet.\nEverything that happens in the app appears here as it happens.")
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self.show_detail)
        split.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Select an event to see its output.")
        self.detail.setMinimumHeight(70)
        split.addWidget(self.detail)
        split.setSizes([420, 200])
        lay.addWidget(split, 1)
        note = hint(f"Also written to {rbx.STATE_DIR / 'debug.log'} (switch off in Settings). Cookies, tokens, passwords, codes, e-mail addresses, phone numbers, IP addresses, names of accounts "
                    "and of people in Roblox's answers, and your folder names are hidden before anything is kept. Answers are shortened.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self._event.connect(self._add)
        debuglog.LISTENERS.append(lambda e: self._event.emit(e))
        for e in list(debuglog.EVENTS)[-ROWS:]:
            self.queue.append(e)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.flush)
        self.timer.start(400)
        self.flush()

    # ---------------------------------------------------------------- data
    def _add(self, e):
        self.queue.append(e)

    def matches(self, e):
        floor = debuglog.LEVELS.index(self.level.currentData())
        if debuglog.LEVELS.index(e["level"]) < floor:
            return False
        area = self.area.currentData()
        if area and e["area"] != area:
            return False
        words = self.filter.text().lower().split()
        if words:
            hay = f"{e['area']} {e['level']} {e['message']} {e['detail']}".lower()
            return all(w in hay for w in words)
        return True

    def _row(self, e):
        r = self.table.rowCount()
        self.table.insertRow(r)
        t = time.localtime(e["time"])
        cells = [f"{time.strftime('%H:%M:%S', t)}.{int(e['time'] * 1000) % 1000:03d}", e["level"], e["area"], e["message"] + ("   [+ output]" if e["detail"] else "")]
        for c, text in enumerate(cells):
            it = QTableWidgetItem(text)
            if c == 1:
                it.setForeground(QColor(LEVEL_COLOUR[e["level"]]))
            self.table.setItem(r, c, it)
        self.rows.append(e)

    def _note_area(self, e):
        if e["area"] not in self.areas:
            self.areas.add(e["area"])
            keep = self.area.currentData()
            self.area.blockSignals(True)
            self.area.clear()
            self.area.addItem("All areas", "")
            for a in sorted(self.areas):
                self.area.addItem(a, a)
            i = self.area.findData(keep)
            self.area.setCurrentIndex(max(0, i))
            self.area.blockSignals(False)

    def _trim(self):
        extra = self.table.rowCount() - ROWS
        for _ in range(max(0, extra)):
            self.table.removeRow(0)
            self.rows.pop(0)

    def flush(self):
        if not self.queue:
            return
        batch, self.queue = self.queue, []
        for e in batch:
            self._note_area(e)
        if self.pause.isChecked():
            return
        for e in batch:
            if self.matches(e):
                self._row(e)
        self._trim()
        self.count.setText(f"{self.table.rowCount()} shown, {debuglog.total:,} events since the app started.")
        if self.follow.isChecked():
            self.table.scrollToBottom()

    def rebuild(self):
        self.table.setRowCount(0)
        self.rows = []
        for e in list(debuglog.EVENTS)[-ROWS * 3:]:
            if self.matches(e):
                self._row(e)
        self._trim()
        self.detail.setPlainText("")
        self.count.setText(f"{self.table.rowCount()} shown, {debuglog.total:,} events since the app started.")
        if self.follow.isChecked():
            self.table.scrollToBottom()

    def show_detail(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel or sel[0].row() >= len(self.rows):
            self.detail.setPlainText("")
            return
        e = self.rows[sel[0].row()]
        self.detail.setPlainText(debuglog.format_event(e))

    def shown_events(self):
        return list(self.rows)

    def clear(self):
        self.table.setRowCount(0)
        self.rows = []
        self.queue = []
        debuglog.clear()
        self.detail.setPlainText("")
        self.count.setText("")

    def copy(self):
        QGuiApplication.clipboard().setText(debuglog.export_text(self.shown_events()))
        self.ctx.status(f"Copied {len(self.rows)} event(s).")

    def save(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save the debug log", "roblox-manager-debug.txt", "Text (*.txt)")
        if not name:
            return
        try:
            with open(name, "w", encoding="utf-8") as f:
                f.write(debuglog.export_text(self.shown_events()))
        except OSError as e:
            self.ctx.error(e)
            return
        self.ctx.status(f"Saved {len(self.rows)} event(s) to {name}.")


# ------------------------------------------------------------------ what happens in the window
class UiWatcher(QObject):
    """Button presses, dialogs that open, pages that are opened: told to the debug log (the text of buttons and titles only, hidden like everything else)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def page(self):
        try:
            return self.window.tabs.tabText(self.window.tabs.currentIndex())
        except Exception:       # noqa: BLE001
            return "?"

    def eventFilter(self, obj, ev):
        try:
            t = ev.type()
            if t == QEvent.Type.MouseButtonRelease and isinstance(obj, QAbstractButton) and obj.isEnabled() and obj.rect().contains(ev.position().toPoint()):
                label = (obj.text() or obj.toolTip() or obj.objectName() or obj.metaObject().className()).replace("&", "")
                extra = ""
                if obj.isCheckable():
                    extra = " (will be " + ("off" if obj.isChecked() else "on") + ")"        # (the press has not changed it yet)
                debuglog.event("click", f"pressed '{label}' on {self.page()}{extra}", "info")
            elif t == QEvent.Type.Show and isinstance(obj, QDialog):
                text = obj.text() if isinstance(obj, QMessageBox) else ""
                debuglog.event("dialog", f"opened '{obj.windowTitle()}'", "info", text)
            elif t == QEvent.Type.Hide and isinstance(obj, QDialog) and not obj.isVisible():
                debuglog.event("dialog", f"closed '{obj.windowTitle()}'", "debug")
        except Exception:       # noqa: BLE001 - watching must never disturb the window
            pass
        return False


def watch(window, app):
    """Tell the debug log what happens in this window: pages, buttons, dialogs, sign-ins, account changes."""
    ctx = window.ctx
    watcher = UiWatcher(window)
    app.installEventFilter(watcher)
    window._ui_watcher = watcher

    def names():
        try:
            import accounts
            debuglog.set_identity(*[a for a in accounts.list_accounts()])
        except Exception:       # noqa: BLE001
            pass

    def signed_in():
        names()
        debuglog.set_identity(ctx.me or {})
        debuglog.event("account", "signed in")

    def page(i):
        debuglog.event("page", f"opened page '{window.tabs.tabText(i)}'", "info")
    window.tabs.currentChanged.connect(page)
    for tabs in window.findChildren(QTabWidget):
        if tabs is window.tabs:
            continue
        tabs.currentChanged.connect(lambda i, tw=tabs: debuglog.event("page", f"opened '{tw.tabText(i)}' ({window.tabs.tabText(window.tabs.currentIndex())})", "info"))
    ctx.signed_in.connect(signed_in)
    ctx.signed_out.connect(lambda: debuglog.event("account", "signed out"))
    ctx.accounts_changed.connect(lambda: (names(), debuglog.event("account", "the list of accounts changed")))
    ctx.alerts_changed.connect(lambda: debuglog.event("alerts", "friend alerts switched on or off"))
    ctx.data_restored.connect(lambda: debuglog.event("backup", "a backup was restored"))
    names()
    debuglog.event("app", "window opened")
