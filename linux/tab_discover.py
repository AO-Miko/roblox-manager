"""Discover (a page inside Home): Roblox's own home page rows (Top Trending, Up-and-Coming ...), a search for games, people and groups, and a page for every game with its
stats (players now, likes and dislikes with the bar and the percentage, favorites, visits ...) and a Play button that opens the Roblox launcher and joins the game, or one
of your own VIP servers of that game. All of it is public data: it works without a sign-in. Nothing here buys anything.
"""
import time
import uuid

from PySide6.QtCore import QRectF, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

import rbx
import roblox_launcher
from tab_staff import round_icon
from theme import T
from ui_common import FlowLayout, button, copy_text, esc, hint, open_url, when

ICON_DIR = rbx.STATE_DIR / "gameicons"
ROW_LIMIT = 16               # games shown per row of the home page
ROWS_LIMIT = 8


# ------------------------------------------------------------------ small helpers
def short(n):
    """18,769 -> 18.8K; 4,753,429,786 -> 4.8B"""
    n = int(n or 0)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            v = n / limit
            return (f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{v:.0f}") + suffix
    return str(n)


def like_percent(up, down):
    """Whole percent of the votes that are likes, or None when nobody voted."""
    total = int(up or 0) + int(down or 0)
    return None if total <= 0 else int(round(100 * int(up or 0) / total))


def launch_roblox(ctx, place_id, link_code=None, web_url=None):
    """Open the Roblox launcher and join: the game (place id) or a private/VIP server (place id + link code). First it checks that a launcher is installed (and if not,
    offers to install one: see roblox_launcher.py). If the launcher cannot be opened, the game's page is."""
    if not roblox_launcher.ensure(ctx.window):                  # no launcher on this computer: the install question was shown, nothing is opened
        ctx.status("Roblox is not installed, so nothing was opened.")
        return False
    try:
        url = rbx.launcher_url(place_id, link_code)
    except ValueError:                                           # a join code that does not look like one is never put into a launcher link
        ctx.status("Roblox gave an unusual join code, so nothing was opened.", 12000)
        return False
    if QDesktopServices.openUrl(QUrl(url)):
        ctx.status("Opening the Roblox launcher...")
        return True
    ctx.status("The Roblox launcher could not be opened (is Roblox installed?). Opening the game's page instead.", 12000)
    open_url(web_url or rbx.join_link(place_id, link_code))
    return False


class RatioBar(QWidget):
    """The likes/dislikes bar of a game: the green part is the likes."""

    def __init__(self, up=0, down=0, height=6):
        super().__init__()
        self.up, self.down = int(up or 0), int(down or 0)
        self.setFixedHeight(height)

    def set_votes(self, up, down):
        self.up, self.down = int(up or 0), int(down or 0)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["surface3"]))
        p.drawRoundedRect(r, radius, radius)
        pct = like_percent(self.up, self.down)
        if pct:
            w = max(r.height(), r.width() * pct / 100)
            p.setBrush(QColor(T["success"]))
            p.drawRoundedRect(QRectF(r.x(), r.y(), w, r.height()), radius, radius)


class GameCard(QFrame):
    """One game: its picture, name, players now and the like percentage. Pressing it opens the game's page."""
    clicked = Signal(dict)

    def __init__(self, card):
        super().__init__()
        self.card = card
        self.setProperty("tile", True)
        self.setFixedWidth(168)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(card["name"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.icon = QLabel()
        self.icon.setFixedSize(150, 150)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setPixmap(self._blank())
        lay.addWidget(self.icon)
        self.name = QLabel(card["name"])
        self.name.setWordWrap(True)
        self.name.setFixedHeight(38)
        self.name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.name.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.name)
        pct = like_percent(card["up"], card["down"])
        self.stats = QLabel(f"{short(card['playing'])} playing" + (f"   {pct}%" if pct is not None else ""))
        self.stats.setProperty("role", "hint")
        lay.addWidget(self.stats)
        self.bar = RatioBar(card["up"], card["down"], 4)
        lay.addWidget(self.bar)

    @staticmethod
    def _blank():
        pm = QPixmap(150, 150)
        pm.fill(QColor(T["surface3"]))
        return pm

    def set_icon(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.icon.setPixmap(pm.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation).copy(0, 0, 150, 150))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.card)


# ------------------------------------------------------------------ a game's page
class GameDetail(QWidget):
    back = Signal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.card = None
        self.place_id = None
        self.vip_servers_for = lambda universe_id, place_id: []        # the app connects this to the VIP servers page
        self.vip_link_for = lambda server, done: None
        self._servers = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        top = QHBoxLayout()
        top.addWidget(button("< Back", self.back.emit))
        top.addStretch()
        lay.addLayout(top)

        head = QHBoxLayout()
        self.cover = QLabel()
        self.cover.setFixedSize(480, 270)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(f"background: {T['surface2']}; border-radius: 10px;")
        head.addWidget(self.cover)
        info = QVBoxLayout()
        self.title = QLabel("")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setProperty("role", "title")
        self.title.setWordWrap(True)
        self.creator = hint("")
        self.creator.setTextFormat(Qt.TextFormat.PlainText)
        self.creator.setWordWrap(True)
        info.addWidget(self.title)
        info.addWidget(self.creator)
        row = FlowLayout()
        self.b_play = button("Play", self.play, "Open the Roblox launcher and join this game", primary=True)
        self.b_vip = button("Join my VIP server", self.join_vip, "Open the Roblox launcher and join one of your own VIP servers of this game")
        self.b_vip.hide()
        self.b_open = button("Open on roblox.com", self.open_page)
        self.b_copy = button("Copy link", self.copy_link)
        for b in (self.b_play, self.b_vip, self.b_open, self.b_copy):
            row.addWidget(b)
        info.addSpacing(8)
        info.addLayout(row)
        self.note = hint("")
        self.note.setWordWrap(True)
        info.addWidget(self.note)
        info.addStretch()
        head.addLayout(info, 1)
        lay.addLayout(head)

        # likes and dislikes, with the bar
        lay.addWidget(QLabel("<b>Rating</b>"))
        votes = QHBoxLayout()
        self.likes = QLabel("")
        self.dislikes = QLabel("")
        self.percent = QLabel("")
        self.percent.setProperty("role", "title")
        votes.addWidget(self.likes)
        votes.addSpacing(16)
        votes.addWidget(self.dislikes)
        votes.addStretch()
        votes.addWidget(self.percent)
        lay.addLayout(votes)
        self.bar = RatioBar(0, 0, 10)
        lay.addWidget(self.bar)

        lay.addWidget(QLabel("<b>Stats</b>"))
        grid = QGridLayout()
        self.values = {}
        for i, key in enumerate(("Playing now", "Visits", "Favorites", "Max players", "Created", "Updated", "Genre", "Age rating")):
            cap = QLabel(key)
            cap.setProperty("role", "hint")
            val = QLabel("-")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(cap, i // 4 * 2, i % 4)
            grid.addWidget(val, i // 4 * 2 + 1, i % 4)
            self.values[key] = val
        lay.addLayout(grid)

        lay.addWidget(QLabel("<b>Description</b>"))
        self.about = QPlainTextEdit()
        self.about.setReadOnly(True)
        self.about.setPlaceholderText("No description.")
        self.about.setMinimumHeight(120)
        lay.addWidget(self.about, 1)

    # ---- show a game
    def show_game(self, card):
        self.card = card
        self.place_id = card.get("placeId")
        self.title.setText(card["name"])
        self.creator.setText((f"by {card['creator']}" if card.get("creator") else "") + ("  (verified)" if card.get("verified") else ""))
        self._votes(card["up"], card["down"])
        for k, v in self.values.items():
            v.setText("-")
        self.values["Playing now"].setText(f"{card['playing']:,}")
        self.values["Genre"].setText(card.get("genre") or "-")
        self.values["Age rating"].setText(card.get("age") or "-")
        self.about.setPlainText("")
        self.cover.setPixmap(QPixmap())
        self.cover.setText("")
        self.note.setText("")
        self.b_play.setEnabled(bool(self.place_id))
        self._servers = []
        self.b_vip.hide()
        self._offer_vip()
        uid, c = card["universeId"], self.ctx.client

        def work():
            d = c.games_by_universe([uid]).get(uid, {})
            try:
                v = c.game_votes([uid]).get(uid)
            except rbx.RobloxError:
                v = None
            fav = d.get("favoritedCount")
            if fav is None:
                try:
                    fav = c.game_favorites(uid)
                except rbx.RobloxError:
                    fav = None
            data = b""
            try:
                url = c.game_cover(uid)
                data = c.fetch_bytes(url) if url else b""
            except rbx.RobloxError:
                pass
            return d, v, fav, data

        def ready(res):
            if not self.card or self.card["universeId"] != uid:
                return                                        # (another game was opened meanwhile)
            self._fill(*res)
        self.ctx.async_.run(work, ready, lambda e: self.note.setText(f"Some details could not be loaded: {e}"))

    def _votes(self, up, down):
        pct = like_percent(up, down)
        self.likes.setText(f"Likes  <b>{int(up):,}</b>")
        self.dislikes.setText(f"Dislikes  <b>{int(down):,}</b>")
        self.percent.setText(f"{pct}%" if pct is not None else "No votes yet")
        self.bar.set_votes(up, down)

    def _fill(self, d, votes, fav, cover):
        if votes:
            self._votes(*votes)
        v = self.values
        if d:
            v["Playing now"].setText(f"{int(d.get('playing') or 0):,}")
            v["Visits"].setText(f"{int(d.get('visits') or 0):,}")
            v["Max players"].setText(str(d.get("maxPlayers") or "-"))
            v["Created"].setText(when(d.get("created")) if d.get("created") else "-")
            v["Updated"].setText(when(d.get("updated")) if d.get("updated") else "-")
            v["Genre"].setText(d.get("genre_l1") or d.get("genre") or "-")
            self.about.setPlainText(d.get("description") or "")
            cr = d.get("creator") or {}
            if cr.get("name"):
                self.creator.setText(f"by {cr['name']}" + ("  (verified)" if cr.get("hasVerifiedBadge") else ""))
            if d.get("rootPlaceId"):
                self.place_id = d["rootPlaceId"]
                self.b_play.setEnabled(True)
                self._offer_vip()
        if fav is not None:
            v["Favorites"].setText(f"{int(fav):,}")
        pm = QPixmap()
        if cover and pm.loadFromData(cover):
            self.cover.setPixmap(pm.scaled(480, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ---- play
    def play(self):
        if self.place_id:
            launch_roblox(self.ctx, self.place_id, web_url=self._page())

    def _page(self):
        return f"https://www.roblox.com/games/{int(self.place_id)}" if self.place_id else "https://www.roblox.com/discover"

    def open_page(self):
        open_url(self._page())

    def copy_link(self):
        copy_text(self._page())
        self.ctx.status("Game link copied.")

    def _offer_vip(self):
        """'Join my VIP server' appears only when you have a working VIP server of this game."""
        try:
            self._servers = list(self.vip_servers_for(self.card["universeId"], self.place_id)) if self.card else []
        except Exception:                                  # noqa: BLE001 - the VIP list is a convenience
            self._servers = []
        self.b_vip.setVisible(bool(self._servers))

    def join_vip(self):
        if not self._servers:
            return
        if len(self._servers) == 1:
            return self._join(self._servers[0])
        menu = QMenu(self)
        for s in self._servers:
            menu.addAction(s.get("name") or f"Server {s.get('_vid')}", lambda s=s: self._join(s))
        menu.exec(self.b_vip.mapToGlobal(self.b_vip.rect().bottomLeft()))

    def _join(self, server):
        def got(link):
            place, code = rbx.link_code_of(link)
            if not code:
                self.ctx.status("Roblox did not give a join link for this server yet.")
                return
            launch_roblox(self.ctx, place or self.place_id or server.get("placeId"), code, link)
        self.vip_link_for(server, got)


# ------------------------------------------------------------------ the page
class DiscoverTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.session = str(uuid.uuid4())
        self.loaded = False
        self.cards = {}              # universe id -> its GameCards on screen
        self.icons = {}              # universe id -> image bytes
        self.token = ""              # next page of a search of games
        self.mode = "feed"
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, people and groups")
        self.search.setMinimumWidth(220)
        self.search.returnPressed.connect(self.run_search)
        self.kind = QComboBox()
        for label in ("Games", "People", "Groups"):
            self.kind.addItem(label, label.lower())
        self.b_search = button("Search", self.run_search, primary=True)
        self.b_feed = button("Home", self.show_feed, "Back to Roblox's home page rows")
        self.b_feed.hide()
        top.addWidget(self.search, 1)
        top.addWidget(self.kind)
        top.addWidget(self.b_search)
        top.addWidget(self.b_feed)
        lay.addLayout(top)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.body)
        self.stack.addWidget(self.scroll)
        self.detail = GameDetail(ctx)
        self.detail.back.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.detail)
        self.state = hint("")
        self.state.setWordWrap(True)
        self.body_lay.addWidget(self.state)

    # ---- page plumbing
    def ensure_loaded(self):
        if not self.loaded:
            self.load()

    def load(self):
        """(Re)load what is on screen: the home page rows, or the search that is open."""
        self.loaded = True
        if self.mode == "feed":
            self.load_feed()
        else:
            self.run_search()

    def _clear(self):
        while self.body_lay.count():
            it = self.body_lay.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)                       # gone at once (deleteLater alone leaves it as a child until the event loop gets to it)
                w.deleteLater()
            elif it.layout():
                self._drop(it.layout())
        self.cards = {}
        self.state = hint("")
        self.state.setWordWrap(True)
        self.body_lay.addWidget(self.state)

    def _drop(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _failed(self, what):
        def show(e):
            self.state.setText(f"{what} could not be loaded: {e}")
            self.state.setProperty("role", "warn")
            self.state.style().unpolish(self.state)
            self.state.style().polish(self.state)
        return show

    # ---- Roblox's home page rows
    def show_feed(self):
        self.mode = "feed"
        self.b_feed.hide()
        self.search.clear()
        self.stack.setCurrentIndex(0)
        self.load_feed()

    def load_feed(self):
        self._clear()
        self.state.setText("Loading Roblox's home page...")
        self.ctx.async_.run(lambda: self.ctx.client.discover_sorts(self.session), self._show_feed, self._failed("The home page"))

    def _show_feed(self, sorts):
        if self.mode != "feed":
            return
        self._clear()
        if not sorts:
            self.state.setText("Roblox returned no home page rows right now. Try the search, or reload in a moment.")
            return
        self.state.hide()
        ids = []
        for s in sorts[:ROWS_LIMIT]:
            title = QLabel(s["name"])
            title.setProperty("role", "title")
            self.body_lay.addWidget(title)
            row = QScrollArea()
            row.setWidgetResizable(True)
            row.setFrameShape(QFrame.Shape.NoFrame)
            row.setFixedHeight(300)
            inner = QWidget()
            hl = QHBoxLayout(inner)
            hl.setContentsMargins(0, 0, 0, 0)
            for card in s["games"][:ROW_LIMIT]:
                hl.addWidget(self._card(card))
                ids.append(card["universeId"])
            hl.addStretch()
            row.setWidget(inner)
            self.body_lay.addWidget(row)
        self._load_icons(ids)

    def _card(self, card):
        w = GameCard(card)
        w.clicked.connect(self.open_game)
        self.cards.setdefault(card["universeId"], []).append(w)
        if card["universeId"] in self.icons:
            w.set_icon(self.icons[card["universeId"]])
        return w

    # ---- pictures: a few at a time, kept on disk for a week
    def _load_icons(self, ids):
        need = [i for i in dict.fromkeys(ids) if i not in self.icons]
        for k in range(0, len(need), 8):
            chunk = need[k:k + 8]
            self.ctx.async_.run(lambda ch=chunk: self._fetch_icons(ch), self._icons_ready, lambda e: None)

    def _fetch_icons(self, ids):
        c, out, missing = self.ctx.client, {}, []
        for uid in ids:
            f = ICON_DIR / f"{int(uid)}.png"
            try:
                if time.time() - f.stat().st_mtime < rbx.AVATAR_MAX_AGE:
                    out[uid] = f.read_bytes()
                    continue
            except OSError:
                pass
            missing.append(uid)
        if missing:
            for uid, url in c.game_icons(missing).items():
                try:
                    data = c.fetch_bytes(url)
                except rbx.RobloxError:
                    continue
                if data:
                    out[uid] = data
                    try:
                        ICON_DIR.mkdir(parents=True, exist_ok=True)
                        (ICON_DIR / f"{int(uid)}.png").write_bytes(data)
                    except OSError:
                        pass
        return out

    def _icons_ready(self, got):
        self.icons.update(got)
        for uid, data in got.items():
            for w in self.cards.get(uid, []):
                try:
                    w.set_icon(data)
                except RuntimeError:                       # (the card was cleared meanwhile)
                    pass

    # ---- search
    def run_search(self):
        text, kind = self.search.text().strip(), self.kind.currentData()
        if not text:
            self.show_feed()
            return
        self.mode = "search"
        self.loaded = True
        self.b_feed.show()
        self.stack.setCurrentIndex(0)
        self._clear()
        self.state.setText(f"Searching for '{text}'...")
        self.token = ""
        c = self.ctx.client
        if kind == "games":
            self.ctx.async_.run(lambda: c.omni_search_games(text, self.session), lambda r: self._games_found(text, r, first=True), self._failed("The search"))
        elif kind == "people":
            self.ctx.async_.run(lambda: self._people(text), lambda r: self._people_found(text, r), self._failed("The search"))
        else:
            self.ctx.async_.run(lambda: c.search_groups(text), lambda r: self._groups_found(text, r), self._failed("The search"))

    def _games_found(self, text, result, first):
        if self.mode != "search" or self.search.text().strip() != text:
            return
        cards, self.token = result
        if first:
            self._clear()
            self.flow = FlowLayout(10, 10)
            holder = QWidget()
            holder.setLayout(self.flow)
            self.body_lay.addWidget(holder)
            self.more = button("Load more", self.more_games)
            self.body_lay.addWidget(self.more, 0, Qt.AlignmentFlag.AlignLeft)
            self.state = hint("")
            self.body_lay.addWidget(self.state)
        shown = {c.card["universeId"] for ws in self.cards.values() for c in ws}
        fresh = [c for c in cards if c["universeId"] not in shown]
        for card in fresh:
            self.flow.addWidget(self._card(card))
        self.more.setVisible(bool(self.token))
        self.more.setEnabled(True)
        self.state.setText("" if (fresh or not first) else f"No games found for '{text}'.")
        self._load_icons([c["universeId"] for c in fresh])

    def more_games(self):
        text = self.search.text().strip()
        if not self.token or self.mode != "search":
            return
        self.more.setEnabled(False)                       # (one page at a time)
        token, c = self.token, self.ctx.client
        self.ctx.async_.run(lambda: c.omni_search_games(text, self.session, token), lambda r: self._games_found(text, r, first=False),
                            lambda e: (self.more.setEnabled(True), self.state.setText(f"Could not load more: {e}")))

    def _people(self, text):
        users = self.ctx.client.search_users(text)[:25]
        heads = self.ctx.client.headshots([u["id"] for u in users], size="48x48") if users else {}
        return users, heads

    def _people_found(self, text, result):
        if self.mode != "search" or self.search.text().strip() != text:
            return
        users, heads = result
        self._clear()
        self.state.setText("" if users else f"No people found for '{text}'.")
        for u in users:
            row = QFrame()
            row.setProperty("tile", True)
            hl = QHBoxLayout(row)
            pic = QLabel()
            pic.setFixedSize(40, 40)
            pic.setPixmap(round_icon(None, 40))
            hl.addWidget(pic)
            names = QVBoxLayout()
            names.addWidget(QLabel(f"<b>{esc(u.get('displayName') or u.get('name'))}</b>"))
            names.addWidget(self._plain(hint(f"@{u.get('name')}  -  id {u.get('id')}")))
            hl.addLayout(names, 1)
            hl.addWidget(button("Open profile", lambda _=False, uid=u["id"]: open_url(f"https://www.roblox.com/users/{int(uid)}/profile")))
            self.body_lay.insertWidget(self.body_lay.count() - 1, row)
            if heads.get(u["id"]):
                self.ctx.async_.run(lambda url=heads[u["id"]]: self.ctx.client.fetch_bytes(url), lambda data, pic=pic: self._set_pic(pic, data), lambda e: None)

    @staticmethod
    def _plain(label):
        label.setTextFormat(Qt.TextFormat.PlainText)             # (a text from Roblox is never read as HTML)
        return label

    @staticmethod
    def _set_pic(label, data):
        try:
            label.setPixmap(round_icon(data, 40))
        except RuntimeError:
            pass

    def _groups_found(self, text, groups):
        if self.mode != "search" or self.search.text().strip() != text:
            return
        self._clear()
        self.state.setText("" if groups else f"No groups found for '{text}'.")
        for g in groups:
            row = QFrame()
            row.setProperty("tile", True)
            hl = QHBoxLayout(row)
            names = QVBoxLayout()
            names.addWidget(QLabel(f"<b>{esc(g.get('name'))}</b>"))
            desc = (g.get("description") or "").strip().replace("\n", " ")
            names.addWidget(self._plain(hint(f"{int(g.get('memberCount') or 0):,} members" + (f"  -  {desc[:110]}" if desc else ""))))
            hl.addLayout(names, 1)
            hl.addWidget(button("Open on roblox.com", lambda _=False, gid=g["id"]: open_url(f"https://www.roblox.com/communities/{int(gid)}")))
            self.body_lay.insertWidget(self.body_lay.count() - 1, row)

    # ---- a game
    def open_game(self, card):
        self.detail.show_game(card)
        self.stack.setCurrentIndex(1)
