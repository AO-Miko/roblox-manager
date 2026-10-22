"""Finding your way around: the side bar (grouped pages, counts, account switch) and the search that jumps to any page, setting or loaded item (Ctrl+K)."""
import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from theme import T

# page title -> (group, one line that says what the page is for)
PAGES = {
    "Home": ("", "Your account at a glance, and Discover: find games, see their stats and play them."),
    "People": ("Social", "Friends, requests, followers, following, blocked users and a search for any user."),
    "Groups": ("Social", "Your groups: members and ranks, join requests, roles, audit log, bans and the shout."),
    "VIP servers": ("Roblox", "Every private server you have: switch on or off, renew, duplicates and bulk actions."),
    "Money": ("Roblox", "Robux balance, pending, totals per period and the transaction history."),
    "Request log": ("Tools", "Every request the app sends to Roblox and how Roblox answered."),
    "API Explorer": ("Tools", "Send any Roblox web API request and read the answer."),
    "Staff List": ("Staff", "Who is on the staff, from the owner down, with their Roblox profiles."),
    "Admin": ("Staff", "Ban and unban Roblox user ids. Only accounts with the admin role or higher see this page."),
    "Info": ("", "Settings, updates and what changed in each version."),
}
KEYWORDS = {                      # extra words the search also understands, so "robux" finds Money and "private server" finds VIP servers
    "Home": "account login sign in cookie profile avatar switch discover games search play browse trending",
    "People": "friends friend requests followers following blocked block unfriend find user",
    "Groups": "group members ranks roles audit log join requests shout leave",
    "VIP servers": "vip private servers renew expire duplicates link",
    "Money": "robux balance pending transactions history csv export revenue",
    "Request log": "log requests http rate limit errors",
    "API Explorer": "api endpoint http get post developer",
    "Info": "settings updates update log version changes about preferences theme confirm cache",
    "Admin": "ban unban banned reason roles moderator",
    "Staff List": "staff team owner co-owner senior admin trusted friends roles hierarchy members profile",
}


def base_title(text):
    """'Groups (7)' -> ('Groups', '7');  'People (3 requests)' -> ('People', '3')."""
    m = re.match(r"^(.*?)\s*\((\d[\d,+]*)(?:\s+\w+)?\)$", text)
    return (m.group(1), m.group(2)) if m else (text, "")


def icon_path(name):
    """A simple line drawing for each page, in a 24 x 24 box."""
    p = QPainterPath()
    if name == "Home":
        p.moveTo(4, 12); p.lineTo(12, 4.5); p.lineTo(20, 12); p.moveTo(6.5, 10.5); p.lineTo(6.5, 19.5); p.lineTo(17.5, 19.5); p.lineTo(17.5, 10.5)
        p.moveTo(10, 19.5); p.lineTo(10, 14.5); p.lineTo(14, 14.5); p.lineTo(14, 19.5)
    elif name == "People":
        p.addEllipse(QPointF(9, 8.5), 3.2, 3.2); p.moveTo(3.5, 19.5); p.cubicTo(3.5, 13.5, 14.5, 13.5, 14.5, 19.5)
        p.addEllipse(QPointF(17, 9.5), 2.5, 2.5); p.moveTo(16.5, 14.2); p.cubicTo(19.5, 13.6, 21, 16, 20.8, 19)
    elif name == "Groups":
        p.addEllipse(QPointF(12, 7.5), 3, 3); p.addEllipse(QPointF(5.8, 10.5), 2.3, 2.3); p.addEllipse(QPointF(18.2, 10.5), 2.3, 2.3)
        p.moveTo(7, 19.5); p.cubicTo(7, 13.2, 17, 13.2, 17, 19.5); p.moveTo(2.5, 17.5); p.cubicTo(2.5, 14.5, 4.5, 14, 6, 14.3)
        p.moveTo(21.5, 17.5); p.cubicTo(21.5, 14.5, 19.5, 14, 18, 14.3)
    elif name == "VIP servers":
        p.addRoundedRect(QRectF(4, 4.5, 16, 6), 1.8, 1.8); p.addRoundedRect(QRectF(4, 13.5, 16, 6), 1.8, 1.8)
        p.moveTo(7.5, 7.5); p.lineTo(7.6, 7.5); p.moveTo(7.5, 16.5); p.lineTo(7.6, 16.5); p.moveTo(11, 7.5); p.lineTo(16.5, 7.5); p.moveTo(11, 16.5); p.lineTo(16.5, 16.5)
    elif name == "Money":
        p.addEllipse(QPointF(12, 12), 8, 8); p.moveTo(14.8, 9.3); p.cubicTo(13.2, 7.8, 9.2, 8.3, 9.4, 10.4); p.cubicTo(9.6, 12.4, 14.6, 11.6, 14.8, 13.8)
        p.cubicTo(15, 16.2, 10.6, 16.4, 9.2, 14.7); p.moveTo(12, 6.8); p.lineTo(12, 8.4); p.moveTo(12, 15.8); p.lineTo(12, 17.4)
    elif name == "Request log":
        p.addRoundedRect(QRectF(4.5, 3.5, 15, 17), 2.2, 2.2)
        for y in (8.5, 12, 15.5):
            p.moveTo(8, y); p.lineTo(16, y)
    elif name == "API Explorer":
        p.moveTo(9, 7); p.lineTo(4, 12); p.lineTo(9, 17); p.moveTo(15, 7); p.lineTo(20, 12); p.lineTo(15, 17); p.moveTo(13.4, 5.5); p.lineTo(10.6, 18.5)
    elif name == "Staff List":
        p.moveTo(3.5, 17.5); p.lineTo(3.5, 8); p.lineTo(8, 12); p.lineTo(12, 5.5); p.lineTo(16, 12); p.lineTo(20.5, 8); p.lineTo(20.5, 17.5); p.closeSubpath()
        p.moveTo(3.5, 20.5); p.lineTo(20.5, 20.5)
    elif name == "Admin":
        p.moveTo(12, 3.5); p.lineTo(19.5, 6.5); p.lineTo(19.5, 12); p.cubicTo(19.5, 16.5, 16, 19.5, 12, 20.8); p.cubicTo(8, 19.5, 4.5, 16.5, 4.5, 12)
        p.lineTo(4.5, 6.5); p.closeSubpath(); p.moveTo(9, 12); p.lineTo(11.2, 14.2); p.lineTo(15.2, 9.8)
    elif name == "Info":
        p.moveTo(4, 7); p.lineTo(20, 7); p.moveTo(4, 17); p.lineTo(20, 17); p.addEllipse(QPointF(9, 7), 2.2, 2.2); p.addEllipse(QPointF(15, 17), 2.2, 2.2)
    elif name == "chevron_down":
        p.moveTo(6, 9.5); p.lineTo(12, 15.5); p.lineTo(18, 9.5)
    elif name == "chevron_right":
        p.moveTo(9.5, 6); p.lineTo(15.5, 12); p.lineTo(9.5, 18)
    elif name == "menu_close":             # the side bar is open: arrows pointing in
        p.moveTo(11, 7); p.lineTo(6, 12); p.lineTo(11, 17); p.moveTo(18, 7); p.lineTo(13, 12); p.lineTo(18, 17)
    elif name == "menu_open":              # the side bar is closed: arrows pointing out
        p.moveTo(6, 7); p.lineTo(11, 12); p.lineTo(6, 17); p.moveTo(13, 7); p.lineTo(18, 12); p.lineTo(13, 17)
    elif name == "reload":
        p.moveTo(19, 12); p.cubicTo(19, 16, 15.5, 19, 12, 19); p.cubicTo(8, 19, 5, 16, 5, 12); p.cubicTo(5, 8, 8, 5, 12, 5); p.cubicTo(14.5, 5, 16.8, 6.3, 18, 8.2)
        p.moveTo(18.5, 4.5); p.lineTo(18.5, 8.5); p.lineTo(14.5, 8.5)
    elif name == "search":
        p.addEllipse(QPointF(10.5, 10.5), 5.8, 5.8); p.moveTo(15, 15); p.lineTo(20, 20)
    return p


def draw_icon(painter, name, rect, colour, width=1.7):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.x(), rect.y())
    s = rect.width() / 24.0
    painter.scale(s, s)
    painter.setPen(QPen(QColor(colour), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(icon_path(name))
    painter.restore()


class PageHolder(QScrollArea):
    """Holds one page. A page that is wider or taller than the window gets scroll bars instead of forcing the window to be big,
    so the window can be as small as a laptop screen needs."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(page)
        self.setProperty("holder", True)

    def ensure_loaded(self):
        fn = getattr(self.page, "ensure_loaded", None)
        if fn:
            fn()


class NavItem(QAbstractButton):
    """One page in the side bar: line icon, title, and a count badge on the right."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.badge = ""
        self.compact = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)
        self._hover = False

    def set_title(self, text):
        self.title, self.badge = base_title(text)
        self.setToolTip(f"{self.title}" + (f" ({self.badge})" if self.badge else "") + ("" if not self.compact else ""))
        self.update()

    def sizeHint(self):
        return QSize(190, 38)

    def minimumSizeHint(self):
        return QSize(44, 38)

    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        on = self.isChecked()
        if on or self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T["accent_dim"] if on else T["surface2"]))
            p.drawRoundedRect(r, 8, 8)
        if on:
            p.setBrush(QColor(T["accent"]))
            p.drawRoundedRect(QRectF(r.x(), r.center().y() - 9, 3, 18), 1.5, 1.5)
        colour = T["text"] if on else (T["text"] if self._hover else T["muted"])
        x = r.x() + (r.width() - 20) / 2 if self.compact else r.x() + 14
        draw_icon(p, self.title, QRectF(x, r.center().y() - 10, 20, 20), T["accent_hover"] if on else colour)
        if self.compact:
            if self.badge:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T["accent"]))
                p.drawEllipse(QPointF(r.right() - 9, r.y() + 9), 4, 4)
            return
        f = self.font(); f.setPixelSize(13); f.setWeight(f.Weight.DemiBold if on else f.Weight.Medium)
        p.setFont(f)
        fm = QFontMetrics(f)
        badge_w = 0
        if self.badge:
            bf = self.font(); bf.setPixelSize(11); bf.setWeight(bf.Weight.DemiBold)
            bfm = QFontMetrics(bf)
            badge_w = max(22, bfm.horizontalAdvance(self.badge) + 14)
            br = QRectF(r.right() - badge_w - 8, r.center().y() - 9, badge_w, 18)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T["accent"] if on else T["surface3"]))
            p.drawRoundedRect(br, 9, 9)
            p.setFont(bf); p.setPen(QColor("white" if on else T["text"]))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self.badge)
            p.setFont(f)
            badge_w += 8
        p.setPen(QColor(T["text"] if (on or self._hover) else T["muted"]))
        text_rect = QRectF(r.x() + 42, r.y(), r.width() - 42 - badge_w - 6, r.height())
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(text_rect.width())))


class IconButton(QAbstractButton):
    """A small round-cornered button with a line icon (collapse the menu, reload)."""

    def __init__(self, icon, tip="", size=30, parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.setToolTip(tip)
        self.setAccessibleName(tip or icon)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def set_icon(self, name, tip=None):
        self.icon_name = name
        if tip is not None:
            self.setToolTip(tip)
            self.setAccessibleName(tip)
        self.update()

    def enterEvent(self, ev):
        self._hover = True; self.update()

    def leaveEvent(self, ev):
        self._hover = False; self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover or self.isDown():
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T["surface2"]))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        s = min(self.width(), self.height()) - 12
        draw_icon(p, self.icon_name, QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s), T["text"] if self._hover else T["muted"], 1.8)


class GroupHeader(QAbstractButton):
    """The name of a group of pages (SOCIAL, ROBLOX ...) with an arrow: press it to hide or show the pages of the group."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.collapsed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(text)
        self._hover = False
        self._tip()

    def _tip(self):
        self.setToolTip(f"Show {self.text().title()}" if self.collapsed else f"Hide {self.text().title()}")

    def set_collapsed(self, v):
        self.collapsed = bool(v)
        self._tip()
        self.update()

    def sizeHint(self):
        return QSize(190, 26)

    def minimumSizeHint(self):
        return QSize(60, 26)

    def enterEvent(self, ev):
        self._hover = True; self.update()

    def leaveEvent(self, ev):
        self._hover = False; self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T["surface"])); p.drawRoundedRect(r, 6, 6)
        f = self.font(); f.setPixelSize(10); f.setWeight(f.Weight.Bold); f.setLetterSpacing(f.SpacingType.PercentageSpacing, 104)
        p.setFont(f)
        p.setPen(QColor(T["text"] if self._hover else T["muted"]))
        p.drawText(QRectF(r.x() + 8, r.y(), r.width() - 34, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        draw_icon(p, "chevron_right" if self.collapsed else "chevron_down", QRectF(r.right() - 22, r.center().y() - 8, 16, 16), T["muted"], 2.0)


class SearchButton(QAbstractButton):
    """The 'Search ... Ctrl+K' box at the top of the side bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.compact = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Search pages, settings, friends, groups and servers (Ctrl+K)")
        self.setAccessibleName("Search")
        self.setFixedHeight(36)
        self._hover = False

    def enterEvent(self, ev):
        self._hover = True; self.update()

    def leaveEvent(self, ev):
        self._hover = False; self.update()

    def minimumSizeHint(self):
        return QSize(44, 36)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        p.setPen(QPen(QColor(T["border2"] if self._hover else T["border"]), 1)); p.setBrush(QColor(T["surface"]))
        p.drawRoundedRect(r, 9, 9)
        draw_icon(p, "search", QRectF(r.x() + (r.width() - 18) / 2 if self.compact else r.x() + 11, r.center().y() - 9, 18, 18), T["muted"], 1.9)
        if self.compact:
            return
        f = self.font(); f.setPixelSize(13); p.setFont(f); p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(r.x() + 38, r.y(), r.width() - 100, r.height()), Qt.AlignmentFlag.AlignVCenter, "Search")
        kf = self.font(); kf.setPixelSize(10); kf.setWeight(kf.Weight.DemiBold); p.setFont(kf)
        kr = QRectF(r.right() - 52, r.center().y() - 9, 44, 18)
        p.setPen(QPen(QColor(T["border2"]), 1)); p.setBrush(QColor(T["surface2"])); p.drawRoundedRect(kr, 5, 5)
        p.setPen(QColor(T["muted"])); p.drawText(kr, Qt.AlignmentFlag.AlignCenter, "Ctrl+K")


class Sidebar(QFrame):
    """The side bar: the account in use, a search box, the pages in groups, and the version at the bottom.
    It can be made narrow (icons only) with the button at the top or by a narrow window, and every group can be folded with its arrow."""
    picked = Signal(int)
    search_requested = Signal()
    layout_changed = Signal()            # the person folded a group or collapsed the menu (the window remembers it)
    FULL, COMPACT = 224, 62

    def __init__(self, tabs, account_combo, version=""):
        super().__init__()
        self.tabs = tabs
        self.setProperty("sidebar", True)
        self.setFixedWidth(self.FULL)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.brand = QLabel("Roblox Manager")
        self.brand.setProperty("role", "brand")
        self.toggle = IconButton("menu_close", "Collapse the menu")
        self.toggle.clicked.connect(self.toggle_menu)
        top.addWidget(self.brand, 1)
        top.addWidget(self.toggle)
        lay.addLayout(top)
        lay.addSpacing(6)
        self.account = account_combo
        lay.addWidget(self.account)
        lay.addSpacing(6)
        self.search = SearchButton()
        self.search.clicked.connect(self.search_requested)
        lay.addWidget(self.search)
        lay.addSpacing(8)
        self.items = []
        self.group_labels = []           # the GroupHeader buttons
        self.compact = False
        self.manual_compact = False      # chosen with the button
        self.auto_compact = False        # forced by a narrow window
        self.collapsed = set()           # names of the folded groups, upper case
        last, label = None, None
        for i in range(tabs.count()):
            title = base_title(tabs.tabText(i))[0]
            group = PAGES.get(title, ("", ""))[0]
            if i == tabs.count() - 1 and title == "Info":
                lay.addStretch(1)
                group = ""
            if group != last:
                label = None
                if group:
                    label = GroupHeader(group.upper())
                    label.clicked.connect(lambda _=False, lab=label: self.toggle_group(lab.text()))
                    lay.addSpacing(6)
                    lay.addWidget(label)
                    self.group_labels.append(label)
                last = group
            it = NavItem(title)
            it.group_label = label
            it.allowed = True            # False: the page is not for this account (Admin)
            it.set_title(tabs.tabText(i))
            it.clicked.connect(lambda _=False, n=i: self.picked.emit(n))
            lay.addWidget(it)
            self.items.append(it)
        self.version = QLabel(version)
        self.version.setProperty("role", "hint")
        self.version.setContentsMargins(8, 6, 0, 0)
        lay.addWidget(self.version)
        tabs.currentChanged.connect(self.sync)
        self.sync()

    # ---- what is shown
    def sync(self, *_):
        cur = self.tabs.currentIndex()
        for i, it in enumerate(self.items):
            it.set_title(self.tabs.tabText(i))
            it.setChecked(i == cur)
        self._apply()

    def _apply(self):
        """Show what should be shown: a page that is not for this account is hidden; the pages of a folded group are hidden (except the one in view)."""
        for it in self.items:
            folded = it.group_label is not None and it.group_label.text() in self.collapsed and not self.compact and not it.isChecked()
            it.setVisible(it.allowed and not folded)
        for lab in self.group_labels:
            lab.setVisible(not self.compact and any(it.group_label is lab and it.allowed for it in self.items))
            lab.set_collapsed(lab.text() in self.collapsed)

    def set_page_visible(self, title, visible):
        """Show or hide the entry of a page (the Admin page only exists for admins); a group name goes when all its pages are hidden."""
        for it in self.items:
            if it.title == title:
                it.allowed = visible
        self._apply()

    # ---- fold a group
    def toggle_group(self, name):
        self.collapsed ^= {name}
        self._apply()
        self.layout_changed.emit()

    # ---- narrow / wide
    def toggle_menu(self):
        self.manual_compact = not self.manual_compact
        self._update_compact()
        self.layout_changed.emit()

    def set_auto_compact(self, narrow):
        self.auto_compact = narrow
        self._update_compact()

    def set_compact(self, compact):
        """(kept for callers that set it directly) icons only or the full menu."""
        self.auto_compact = compact
        self._update_compact()

    def _update_compact(self):
        compact = self.manual_compact or self.auto_compact
        self.compact = compact
        self.setFixedWidth(self.COMPACT if compact else self.FULL)
        for w in [*self.items, self.search]:
            w.compact = compact
            w.update()
        for w in [self.brand, self.account, self.version]:
            w.setVisible(not compact)
        self.toggle.set_icon("menu_open" if compact else "menu_close", "Expand the menu" if compact else "Collapse the menu")
        self._apply()
        for it in self.items:
            it.setToolTip(it.title + (f" ({it.badge})" if it.badge else ""))

    # ---- remembered between runs
    def state(self):
        return {"menu_collapsed": self.manual_compact, "groups_collapsed": sorted(self.collapsed)}

    def restore(self, st):
        self.manual_compact = bool(st.get("menu_collapsed", False))
        self.collapsed = {g for g in st.get("groups_collapsed", []) if isinstance(g, str)}
        self._update_compact()


class PageHeader(QWidget):
    """Title and one line of help for the page in view, and a reload button for the pages that can be reloaded."""
    reload_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setProperty("header", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 12, 10, 8)
        row.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel()
        self.title.setProperty("role", "title")
        self.sub = QLabel()
        self.sub.setProperty("role", "hint")
        self.sub.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        row.addLayout(col, 1)
        self.reload = IconButton("reload", "Reload this page (F5)", 34)
        self.reload.clicked.connect(self.reload_requested)
        self.reload.hide()
        row.addWidget(self.reload, 0, Qt.AlignmentFlag.AlignTop)

    def set_reloadable(self, on):
        self.reload.setVisible(bool(on))

    def show_page(self, name):
        base = base_title(name)[0]
        self.title.setText(base)
        self.sub.setText(PAGES.get(base, ("", ""))[1])


def _matches(query, text):
    """Every word of the query appears at the start of a word, or anywhere in the text; 'vip ren' finds 'VIP servers: renew'."""
    t = text.lower()
    return all(w in t for w in query.lower().split())


def _score(query, title, hay):
    q = query.lower().strip()
    t = title.lower()
    if t == q: return 0
    if t.startswith(q): return 1
    if any(w.startswith(q) for w in re.split(r"[\s:>]+", t)): return 2
    if q in t: return 3
    return 4


class Palette(QDialog):
    """Ctrl+K: type a few letters, press Enter, you are there. Entries: (title, where, haystack, callback)."""

    def __init__(self, parent, entries_fn):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setProperty("palette", True)
        self.entries_fn = entries_fn
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search pages, settings, friends, groups, servers...")
        self.edit.textChanged.connect(self.fill)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setProperty("palette_list", True)
        self.list.itemActivated.connect(self.go)
        self.list.itemClicked.connect(self.go)
        lay.addWidget(self.list)
        self.hint = QLabel("Up and down to choose, Enter to open, Esc to close")
        self.hint.setProperty("role", "hint")
        lay.addWidget(self.hint)
        self.entries = []

    def open(self):
        self.entries = self.entries_fn()
        self.edit.clear()
        self.fill()
        w = max(520, min(680, self.parent().width() - 80))
        self.resize(w, 420)
        pg = self.parent().mapToGlobal(self.parent().rect().topLeft())
        self.move(pg.x() + (self.parent().width() - w) // 2, pg.y() + 70)
        self.show()
        self.edit.setFocus()

    def fill(self, *_):
        q = self.edit.text().strip()
        self.list.clear()
        rows = [e for e in self.entries if not q or _matches(q, e[0] + " " + e[1] + " " + e[2])]
        if q:
            rows.sort(key=lambda e: _score(q, e[0], e[2]))
        for title, where, _hay, cb in rows[:60]:
            it = QListWidgetItem(f"{title}    -    {where}" if where else title)
            it.setData(Qt.ItemDataRole.UserRole, cb)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            it = QListWidgetItem("Nothing found. Friends, groups and servers are searched once they are loaded.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(it)

    def go(self, item):
        cb = item.data(Qt.ItemDataRole.UserRole)
        if cb:
            self.close()
            cb()

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                n = self.list.count()
                if n:
                    self.list.setCurrentRow((self.list.currentRow() + (1 if k == Qt.Key.Key_Down else -1)) % n)
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.currentItem():
                    self.go(self.list.currentItem())
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)


def install_shortcuts(win):
    """Ctrl+K opens the search, Ctrl+1 ... Ctrl+8 open the pages, F5 reloads the page in view."""
    out = [QShortcut(QKeySequence("Ctrl+K"), win, activated=win.open_search)]
    for n in range(9):
        out.append(QShortcut(QKeySequence(f"Ctrl+{n + 1}"), win, activated=lambda n=n: win.open_nth_page(n)))
    out.append(QShortcut(QKeySequence("F5"), win, activated=win.reload_page))
    return out
