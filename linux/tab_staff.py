"""Staff List: everybody who has a role in the signed role list (see roles.py), shown as the hierarchy it is: owner, co-owner, senior admin, admin,
trusted friend. Pick someone to see their Roblox profile (name, display name, joined, followers, following, friends, description) and to open it."""
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout, QWidget

import rbx
import roles
from ui_common import button, copy_text, hint, open_url, when

ROLE_COLOURS = {"owner": "#f0a73a", "co-owner": "#ef8a5b", "senior-admin": "#b07cff", "admin": "#2f8cff", "trusted-friend": "#35c27a"}


def round_icon(data, size=64):
    """A round picture from PNG bytes (a plain circle when there is none)."""
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    pm = QPixmap()
    if data and pm.loadFromData(data):
        p.setClipPath(path)
        p.drawPixmap(0, 0, pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
    else:
        p.fillPath(path, QBrush(QColor("#2b303c")))
    p.end()
    return out


class StaffTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.info = {}              # user id -> profile (name, displayName, description, created, ...)
        self.counts = {}            # user id -> {friends, followers, following}
        self.avatars = {}           # user id -> PNG bytes
        self.loaded = False
        self.current = None
        lay = QHBoxLayout(self)

        left = QVBoxLayout()
        head = QHBoxLayout()
        title = QLabel("Staff")
        title.setProperty("role", "title")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(button("Refresh", self.reload, "Fetch the staff list and their profiles again"))
        left.addLayout(head)
        self.list = QListWidget()
        self.list.setMinimumWidth(250)
        self.list.setIconSize(QSize(32, 32))
        self.list.currentItemChanged.connect(self._picked)
        left.addWidget(self.list, 1)
        self.note = hint("")
        self.note.setWordWrap(True)
        left.addWidget(self.note)
        lay.addLayout(left, 2)

        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        top = QHBoxLayout()
        self.pic = QLabel()
        self.pic.setFixedSize(96, 96)
        top.addWidget(self.pic)
        names = QVBoxLayout()
        self.display = QLabel("Select someone")
        self.display.setProperty("role", "title")
        self.display.setWordWrap(True)
        self.user = hint("")
        self.role = QLabel("")
        names.addWidget(self.display)
        names.addWidget(self.user)
        names.addWidget(self.role)
        names.addStretch()
        top.addLayout(names, 1)
        cl.addLayout(top)
        self.facts = QLabel("")
        self.facts.setWordWrap(True)
        self.facts.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(self.facts)
        cl.addWidget(QLabel("<b>Description</b>"))
        self.about = QPlainTextEdit()
        self.about.setReadOnly(True)
        self.about.setPlaceholderText("No description.")
        self.about.setMinimumHeight(90)
        cl.addWidget(self.about, 1)
        row = QHBoxLayout()
        self.b_open = button("Go to profile", self.open_profile, "Open this person's page on roblox.com", primary=True)
        self.b_copy = button("Copy user id", self.copy_id)
        row.addWidget(self.b_open)
        row.addWidget(self.b_copy)
        row.addStretch()
        cl.addLayout(row)
        lay.addWidget(card, 3)
        self._show(None)

    # ---- the list
    def ensure_loaded(self):
        if not self.loaded:
            self.reload()

    def reload(self):
        """Rebuild the list from the signed role list, then fetch the profiles in the background."""
        self.loaded = True
        staff = roles.staff()
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        last = None
        target = None
        for uid, role, rank in staff:
            if rank != last:
                head = QListWidgetItem(roles.LABELS[role].upper())
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                f = QFont(head.font())
                f.setBold(True)
                f.setPointSize(max(8, f.pointSize() - 2))
                head.setFont(f)
                head.setForeground(QColor(ROLE_COLOURS.get(role, "#8d96a7")))
                self.list.addItem(head)
                last = rank
            it = QListWidgetItem(self._label(uid))
            it.setData(Qt.ItemDataRole.UserRole, uid)
            if uid in self.avatars:
                it.setIcon(round_icon(self.avatars[uid], 32))
            self.list.addItem(it)
            if uid == keep:
                target = it
        self.list.blockSignals(False)
        self.note.setText("" if staff else "The staff list is empty or not downloaded yet. It is fetched when the app starts.")
        first = next((self.list.item(i) for i in range(self.list.count()) if self.list.item(i).data(Qt.ItemDataRole.UserRole) is not None), None)
        pick = target or first
        if pick is not None:
            self.list.setCurrentItem(pick)
        else:
            self._show(None)
        if staff:
            ids = [u for u, _, _ in staff]
            self.ctx.async_.run(lambda: self._fetch(ids), self._fetched, lambda e: self.note.setText(f"Could not load the profiles: {e}"))

    def _label(self, uid):
        i = self.info.get(uid)
        return f"{i.get('displayName') or i['name']}  (@{i['name']})" if i else f"User {uid}"

    def _fetch(self, ids):
        """Profiles and pictures of the staff, public data (no sign-in needed). Runs in the background."""
        c = self.ctx.client
        info, pics = {}, {}
        for uid in ids:
            try:
                info[uid] = c.user_detail(uid)
            except rbx.RobloxError:
                continue
        urls = c.headshots(ids, size="150x150")
        for uid in ids:
            f = rbx.AVATAR_DIR / f"{int(uid)}-150.png"
            try:
                if time.time() - f.stat().st_mtime < rbx.AVATAR_MAX_AGE:
                    pics[uid] = f.read_bytes()
                    continue
            except OSError:
                pass
            if urls.get(uid):
                try:
                    data = c.fetch_bytes(urls[uid])
                except rbx.RobloxError:
                    continue
                if data:
                    pics[uid] = data
                    try:
                        rbx.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(data)
                    except OSError:
                        pass
        return info, pics

    def _fetched(self, result):
        info, pics = result
        self.info.update(info)
        self.avatars.update(pics)
        for i in range(self.list.count()):
            it = self.list.item(i)
            uid = it.data(Qt.ItemDataRole.UserRole)
            if uid is None:
                continue
            it.setText(self._label(uid))
            if uid in self.avatars:
                it.setIcon(round_icon(self.avatars[uid], 32))
        if self.current is not None:
            self._show(self.current)

    # ---- the person on the right
    def _picked(self, item, _prev=None):
        uid = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._show(uid)
        if uid is not None and uid not in self.counts:
            self.ctx.async_.run(lambda: self.ctx.client.counts(uid), lambda d: self._counted(uid, d), lambda e: None)

    def _counted(self, uid, counts):
        self.counts[uid] = counts
        if uid == self.current:
            self._show(uid)

    def _show(self, uid):
        self.current = uid
        for b in (self.b_open, self.b_copy):
            b.setEnabled(uid is not None)
        if uid is None:
            self.display.setText("Select someone")
            self.user.setText("")
            self.role.setText("")
            self.facts.setText("")
            self.about.setPlainText("")
            self.pic.setPixmap(round_icon(None, 96))
            return
        i = self.info.get(uid, {})
        role = roles.load()[1].get(uid, "")
        self.display.setText(i.get("displayName") or i.get("name") or f"User {uid}")
        self.user.setText(f"@{i['name']}" if i.get("name") else "(profile not loaded)")
        self.role.setText(f"<b style='color:{ROLE_COLOURS.get(role, '#8d96a7')}'>{roles.LABELS.get(role, '')}</b>")
        c = self.counts.get(uid)
        fmt = lambda v: "-" if v is None else format(v, ",")          # noqa: E731
        rows = [("User id", str(uid)), ("Joined", when(i.get("created")) if i.get("created") else "-"),
                ("Followers", fmt(c.get("followers")) if c else "..."), ("Following", fmt(c.get("following")) if c else "..."),
                ("Friends", fmt(c.get("friends")) if c else "...")]
        if i.get("hasVerifiedBadge"):
            rows.append(("Verified", "yes"))
        if i.get("isBanned"):
            rows.append(("Roblox account", "banned by Roblox"))
        self.facts.setText("<table cellspacing='6'>" + "".join(f"<tr><td style='color:#8d96a7'>{k}</td><td>&nbsp;&nbsp;{v}</td></tr>" for k, v in rows) + "</table>")
        self.about.setPlainText(i.get("description") or "")
        self.pic.setPixmap(round_icon(self.avatars.get(uid), 96))

    def open_profile(self):
        if self.current is not None:
            open_url(f"https://www.roblox.com/users/{int(self.current)}/profile")

    def copy_id(self):
        if self.current is not None:
            copy_text(str(self.current))
            self.ctx.status("User id copied.")
