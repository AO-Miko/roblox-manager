"""Notifications page: messages from the developer (see notices.py). Unread ones have a red dot, and the side bar shows how many there are."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

import notices
from nav import IconButton
from ui_common import button, hint, open_url


def channel():
    """'beta' when this app follows the Beta update channel, otherwise 'stable' (a notification can be for one of them)."""
    import updater
    return "beta" if updater.load_config().get("channel") == "beta" else "stable"


class NoticesTab(QWidget):
    LEVEL_NAMES = {"important": "Important", "warning": "Warning"}

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.loaded = False
        self.show_read = False                 # the check icon: also show the messages that were read
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setProperty("role", "title")
        top.addWidget(self.summary, 1)
        self.b_read = IconButton("check", "Show the messages I have read", 34)
        self.b_read.setCheckable(True)
        self.b_read.toggled.connect(self._toggle_read)
        top.addWidget(self.b_read)
        self.b_all = button("Mark all as read", self.read_all, "Every notification counts as read")
        self.b_check = button("Check now", self.check_now, "Look for new notifications (the app does this by itself every ten minutes)")
        top.addWidget(self.b_all)
        top.addWidget(self.b_check)
        lay.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.box = QWidget()
        self.col = QVBoxLayout(self.box)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(10)
        self.scroll.setWidget(self.box)
        lay.addWidget(self.scroll, 1)
        self.cards = {}

    def ensure_loaded(self):
        if not self.loaded:
            self.reload()

    def reload(self, announce=False):
        """Show the notifications from the saved list; with `announce`, pop up the ones that are new."""
        self.loaded = True
        ch = channel()
        items = notices.current(ch)
        read = notices.read_ids()
        while self.col.count():
            w = self.col.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.cards = {}
        shown = items if self.show_read else [e for e in items if e["id"] not in read]
        if not items:
            self.col.addWidget(hint("No notifications."))
        elif not shown:
            self.col.addWidget(hint("You are all caught up. Press the check mark above to see the messages you have read."))
        for e in shown:
            card = self._card(e, e["id"] not in read)
            self.cards[e["id"]] = card
            self.col.addWidget(card)
        self.col.addStretch()
        self._count(items)
        if announce:
            for e in notices.fresh(ch)[:3]:
                self.ctx.notify("Roblox Manager", e["title"])

    def _card(self, e, unread):
        card = QFrame()
        card.setProperty("card", True)
        card.setProperty("unread", unread)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(6)
        head = QHBoxLayout()
        if unread:
            dot = QLabel("●")
            dot.setProperty("role", "unread-dot")
            dot.setAccessibleName("unread")
            head.addWidget(dot)
        else:
            tick = QLabel("✓")
            tick.setProperty("role", "read-check")
            tick.setAccessibleName("read")
            head.addWidget(tick)
        title = QLabel(e["title"])
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setProperty("role", "card-title")
        head.addWidget(title, 1)
        if e["date"]:
            head.addWidget(hint(e["date"]))
        v.addLayout(head)
        if e["body"]:
            body = QLabel(e["body"])
            body.setTextFormat(Qt.TextFormat.PlainText)       # text from the internet is never read as HTML
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(body)
        row = QHBoxLayout()
        if e["level"] in self.LEVEL_NAMES:
            tag = QLabel(self.LEVEL_NAMES[e["level"]])
            tag.setProperty("level", e["level"])
            tag.setProperty("role", "level")
            row.addWidget(tag)
        row.addStretch()
        if e["link"]:
            row.addWidget(button("Open link", lambda link=e["link"]: open_url(link), e["link"]))
        if unread:
            row.addWidget(button("Mark as read", lambda nid=e["id"]: self.read_one(nid)))
        if row.count() > 1 or e["level"] in self.LEVEL_NAMES:
            v.addLayout(row)
        return card

    def _count(self, items=None):
        items = notices.current(channel()) if items is None else items
        n = len(notices.unread(channel()))
        r = len(items) - n
        self.summary.setText(f"{n} unread" if items else "Notifications")
        self.b_all.setEnabled(n > 0)
        self.b_read.setEnabled(r > 0 or self.show_read)
        tip = ("Hide" if self.show_read else "Show") + f" the messages I have read ({r})"
        self.b_read.setToolTip(tip)
        self.b_read.setAccessibleName(tip)
        self.ctx.set_count("notices", n)

    def _toggle_read(self, on):
        self.show_read = bool(on)
        self.reload()

    def read_one(self, nid):
        notices.mark_read(nid)
        self.reload()

    def read_all(self):
        notices.mark_all_read(channel())
        self.reload()

    def check_now(self):
        self.b_check.setEnabled(False)

        def done(changed):
            self.b_check.setEnabled(True)
            self.reload(announce=True)
            self.ctx.status("Notifications are up to date." if changed is not None else "Could not reach the notification list.")
        self.ctx.async_.run(notices.refresh, done, lambda e: done(None))
