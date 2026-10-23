"""Discover (a page inside Home): Roblox's own home page rows (Top Trending, Up-and-Coming ...), a search for games, people and groups, and a page for every game with its
stats (players now, likes and dislikes with the bar and the percentage, favorites, visits ...) and a Play button that opens the Roblox launcher and joins the game, or one
of your own VIP servers of that game. All of it is public data: it works without a sign-in. Nothing here buys anything.
"""
import time
import uuid

from PySide6.QtCore import QRectF, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

import games_store
import geo
import rbx
import roblox_launcher
import roseal_links
import settings
from worldmap import WorldMap, group_places
from tab_staff import round_icon
from theme import T
from ui_common import FlowLayout, button, copy_text, esc, fill_table, hint, make_table, open_url, row_key, selected_rows, when

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


def launch_roblox(ctx, place_id, link_code=None, web_url=None, job_id=None):
    """Open the Roblox launcher and join: the game (place id) or a private/VIP server (place id + link code). First it checks that a launcher is installed (and if not,
    offers to install one: see roblox_launcher.py). If the launcher cannot be opened, the game's page is."""
    if not roblox_launcher.ensure(ctx.window):                  # no launcher on this computer: the install question was shown, nothing is opened
        ctx.status("Roblox is not installed, so nothing was opened.")
        return False
    try:
        url = rbx.launcher_url(place_id, link_code, job_id)
    except ValueError:                                           # a join code that does not look like one is never put into a launcher link
        ctx.status("Roblox gave an unusual join code or server id, so nothing was opened.", 12000)
        return False
    if QDesktopServices.openUrl(QUrl(url)):
        ctx.status("Opening the Roblox launcher...")
        return True
    ctx.status("The Roblox launcher could not be opened (is Roblox installed?). Opening the game's page instead.", 12000)
    open_url(web_url or rbx.join_link(place_id, link_code, job_id))
    return False


SERVER_ORDERS = [("roblox", "Roblox's order"), ("ping", "Lowest ping first"), ("fps", "Highest FPS first"), ("most", "Most players first"), ("fewest", "Fewest players first"),
                 ("oldest", "Running longest first"), ("newest", "Started most recently first")]


def sort_servers(servers, mode, started=None):
    """The servers in the order asked for. A server without a ping, FPS or start time (not looked up yet, or Roblox leaves it out) goes last; ties keep Roblox's order.
    `started` is {server id: start time in Unix milliseconds}."""
    started = started or {}

    def last(value, flip=1):
        return (value is None, 0 if value is None else value * flip)
    keys = {"ping": lambda s: last(s.get("ping")), "fps": lambda s: last(s.get("fps"), -1),
            "most": lambda s: -s["playing"], "fewest": lambda s: s["playing"],
            "oldest": lambda s: last(started.get(s["id"])), "newest": lambda s: last(started.get(s["id"]), -1)}
    return sorted(servers, key=keys[mode]) if mode in keys else list(servers)


def version_text(version, newest):
    """'v1805' for the version of the place a server runs, with '(older)' when other servers run a newer one (the newest one that was looked up)."""
    if not version:
        return ""
    return f"v{version}" + (" (older)" if newest and version < newest else "")


def age_text(started_ms, now=None):
    """How long a server has been running: '12 min', '6 h 12 min', '2 d 3 h' ('' when not known)."""
    if not started_ms:
        return ""
    secs = max(0, int(((time.time() if now is None else now) * 1000 - started_ms) // 1000))
    if secs < 60:
        return "under a minute"
    mins = secs // 60
    if mins < 60:
        return f"{mins} min"
    hours, mins = divmod(mins, 60)
    if hours < 24:
        return f"{hours} h {mins:02d} min"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"


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


class FriendCard(QFrame):
    """A friend who is in a game: the game's picture, the friend's name, the game, and a Join button that opens the launcher on their server."""
    join = Signal(dict)

    def __init__(self, f):
        super().__init__()
        self.f = f
        self.setProperty("tile", True)
        self.setFixedWidth(168)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.icon = QLabel()
        self.icon.setFixedSize(150, 150)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(150, 150)
        pm.fill(QColor(T["surface3"]))
        self.icon.setPixmap(pm)
        lay.addWidget(self.icon)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.head = QLabel()                                  # (the friend's picture, before the name)
        self.head.setFixedSize(24, 24)
        name_row.addWidget(self.head)
        who = QLabel(f"<b>{esc(f.get('displayName') or f.get('name'))}</b>")
        who.setToolTip(f"@{f.get('name')}")
        name_row.addWidget(who, 1)
        lay.addLayout(name_row)
        game = QLabel(f.get("game") or "In a game")
        game.setTextFormat(Qt.TextFormat.PlainText)
        game.setProperty("role", "hint")
        game.setWordWrap(True)
        game.setFixedHeight(34)
        lay.addWidget(game)
        self.b_join = button("Join", lambda: self.join.emit(self.f), "Open the Roblox launcher on this friend's server", primary=True)
        lay.addWidget(self.b_join)

    def set_icon(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.icon.setPixmap(pm.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation).copy(0, 0, 150, 150))

    def set_head(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.head.setPixmap(pm.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


# ------------------------------------------------------------------ a game's page
class ServerMapDialog(QDialog):
    """The located servers on a world map. Pressing a dot lists the servers there; one of them can be joined."""

    def __init__(self, parent, servers, places, join, started=None):
        super().__init__(parent)
        self.started = started or {}
        self.setWindowTitle("Where the servers are")
        self.resize(820, 640)
        self.servers = {s["id"]: s for s in servers}
        self.join = join
        lay = QVBoxLayout(self)
        groups = group_places(servers, places)
        self.map = WorldMap()
        self.map.set_dots([{"lat": p["lat"], "lon": p["lon"], "label": geo.label(p), "ids": ids} for p, ids in groups])
        lay.addWidget(self.map)
        located = sum(len(ids) for _, ids in groups)
        self.note = hint(f"{located} of {len(servers)} loaded servers are located, in {len(groups)} place(s). Press a dot to see its servers." if groups
                         else "No server is located yet. Close this window and press Location and uptime first.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.table = make_table(["Players", "Max", "Ping (ms)", "FPS", "Server", "Running for"], [80, 60, 90, 60, 250, 110], empty="Press a dot on the map.")
        self.table.setMinimumHeight(110)
        self.table.doubleClicked.connect(lambda _=None: self.join_selected())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_join = button("Join selected", self.join_selected, "Open the Roblox launcher on the selected server", primary=True)
        row.addWidget(self.b_join)
        row.addStretch()
        row.addWidget(button("Close", self.close))
        lay.addLayout(row)
        self.map.picked.connect(self.show_ids)

    def show_ids(self, ids):
        rows = []
        for i in ids:
            s = self.servers.get(i)
            if s:
                rows.append([s["playing"], s["max"], int(s["ping"]) if s.get("ping") is not None else "-", int(s["fps"]) if s.get("fps") is not None else "-", i, age_text(self.started.get(i))])
        fill_table(self.table, rows, keys=[r[4] for r in rows])

    def join_selected(self):
        rows = selected_rows(self.table)
        if rows:
            self.join(row_key(self.table, rows[0]))


class GameDetail(QWidget):
    back = Signal()
    locating = Signal(int, int)                      # (done, total): progress from the worker thread

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.places, self.started, self.versions, self._locating, self._locate_stop, self._auto_again = {}, {}, {}, False, False, False
        self._map_after, self._wiki_for = False, None
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
        self.b_wiki = button("Game wiki", self.open_wiki, "Open the game's community wiki (from RoSeal's list of game links)")
        self.b_wiki.hide()                                    # (shown only for a game that has one)
        self.wiki_url = None
        self.b_copy = button("Copy link", self.copy_link)
        self.b_fav = button("Favorite", self.toggle_favorite, "Add this game to (or remove it from) your Roblox favorites")
        self.b_fav.hide()
        self.favorited = None
        for b in (self.b_play, self.b_vip, self.b_fav, self.b_open, self.b_wiki, self.b_copy):
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

        # the public servers: pick one and join it
        lay.addWidget(QLabel("<b>Servers</b>"))
        srow = FlowLayout()
        self.sort = QComboBox()
        self.sort.addItem("Fewest players first", "Asc")
        self.sort.addItem("Most players first", "Desc")
        self.order = QComboBox()
        for key, label in SERVER_ORDERS:
            self.order.addItem("Sort: " + label, key)
        self.order.setToolTip("Sorts the servers loaded so far (Load more brings in more). The running time and the start time need 'Location and uptime' first.")
        self.order.currentIndexChanged.connect(lambda _=None: self._show_servers())
        self.b_servers = button("Find servers", lambda: self.find_servers(True), "List the public servers of this game")
        self.b_join_server = button("Join selected", self.join_selected, "Open the Roblox launcher on the selected server")
        self.b_join_emptiest = button("Join the emptiest", self.join_emptiest, "Open the launcher on the server with the fewest players (not full)")
        self.b_more_servers = button("Load more", lambda: self.find_servers(False))
        self.b_locate = button("Location and uptime", self.locate_servers, "Find out where the selected servers (or the loaded ones) are and how long they have been running. Asks Roblox about each server, like pressing Play, but nothing is joined.")
        self.b_stop_locate = button("Stop", self.stop_locate)
        self.b_stop_locate.hide()
        self.b_map = button("Show map", self.show_map, "Show the located servers on a world map")
        self.b_copy_link = button("Copy join link", self.copy_server_link, "Copy a link that opens Roblox on the selected server (anyone with Roblox can use it while the server is open)")
        for w_ in (self.sort, self.order, self.b_servers, self.b_join_server, self.b_join_emptiest, self.b_more_servers, self.b_locate, self.b_stop_locate, self.b_map, self.b_copy_link):
            srow.addWidget(w_)
        lay.addLayout(srow)
        self.server_table = make_table(["Players", "Max", "Ping (ms)", "FPS", "Server", "Location", "Running for", "Version"], [80, 60, 90, 60, 250, 170, 100, 100], empty="Press Find servers.")
        self.server_table.setMinimumHeight(150)
        self.server_table.doubleClicked.connect(lambda _=None: self.join_selected())
        lay.addWidget(self.server_table)
        self.server_note = hint("")
        self.server_note.setWordWrap(True)
        lay.addWidget(self.server_note)
        self.servers, self.server_cursor, self.server_gen, self.server_busy = [], "", 0, False
        self.locating.connect(lambda k, n: self.server_note.setText(f"Locating servers: {k}/{n}..."))

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
        self.b_wiki.hide()
        self.wiki_url = None
        self._check_wiki()
        self._servers = []
        self.b_vip.hide()
        self._offer_vip()
        games_store.add(card)                                 # (the 'Recently viewed' row)
        self.servers, self.server_cursor, self.server_busy = [], "", False
        self.server_gen += 1
        fill_table(self.server_table, [])
        self.server_note.setText("")
        self.b_more_servers.setEnabled(False)
        self.favorited = None
        self.b_fav.setVisible(self.ctx.logged_in)
        self.b_fav.setText("Favorite")
        uid, c = card["universeId"], self.ctx.client
        if self.ctx.logged_in:
            self.ctx.async_.run(lambda: c.game_favorite_state(uid), lambda on: self._favorite_state(uid, on), lambda e: self.b_fav.hide())

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

    # ---- favorite (the account in use)
    def _favorite_state(self, uid, on):
        if self.card and self.card["universeId"] == uid:
            self.favorited = bool(on)
            self.b_fav.setText("Favorited" if on else "Favorite")

    def toggle_favorite(self):
        if not self.card or self.favorited is None:
            return
        uid, want, c = self.card["universeId"], not self.favorited, self.ctx.client
        self.b_fav.setEnabled(False)

        def done(_):
            self.b_fav.setEnabled(True)
            self._favorite_state(uid, want)
            self.ctx.status("Added to your favorites." if want else "Removed from your favorites.")
        self.ctx.async_.run(lambda: c.set_game_favorite(uid, want), done, lambda e: (self.b_fav.setEnabled(True), self.ctx.error(e)))

    # ---- servers
    def find_servers(self, reset=True):
        """Ask Roblox for the public servers of this game, 50 at a time (one request at a time: pressing Load more again does not ask twice)."""
        if not self.place_id:
            return
        if reset:
            self.server_gen += 1
            self.servers, self.server_cursor, self.places, self.started, self.versions = [], "", {}, {}, {}
            self._locate_stop = True                      # (a look-up of the old list ends; the new list is looked up when it arrives)
        elif self.server_busy or not self.server_cursor:
            return
        self.server_busy = True
        self.b_more_servers.setEnabled(False)
        self.b_servers.setEnabled(False)
        gen, place, cursor, sort, c = self.server_gen, self.place_id, self.server_cursor if not reset else None, self.sort.currentData(), self.ctx.client
        self.server_note.setText("Looking for servers...")

        def done(res):
            if gen != self.server_gen:
                return                                        # (another game, or a new search: this answer is old)
            self.server_busy = False
            self.b_servers.setEnabled(True)
            servers, self.server_cursor = res
            have = {s["id"] for s in self.servers}
            self.servers += [s for s in servers if s["id"] not in have]
            self._show_servers()
            self._auto_locate()

        def failed(e):
            if gen == self.server_gen:
                self.server_busy = False
                self.b_servers.setEnabled(True)
                self.b_more_servers.setEnabled(bool(self.server_cursor))
                self.server_note.setText(f"The servers could not be loaded: {e}")
        self.ctx.async_.run(lambda: c.game_servers(place, sort, cursor), done, failed)

    def _show_servers(self):
        shown = sort_servers(self.servers, self.order.currentData(), self.started)
        rows = [[s["playing"], s["max"], int(s["ping"]) if s.get("ping") is not None else "-", int(s["fps"]) if s.get("fps") is not None else "-", s["id"],
                 geo.label(self.places[s["id"]]) if s["id"] in self.places else "", age_text(self.started.get(s["id"])),
                 version_text(self.versions.get(s["id"]), max(self.versions.values(), default=0))] for s in shown]
        self.server_table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)         # (the order chosen above; click a header to sort by it instead)
        fill_table(self.server_table, rows, keys=[s["id"] for s in shown])
        self.b_more_servers.setEnabled(bool(self.server_cursor))
        self.server_note.setText(f"{len(self.servers)} servers" + ("  (more available: Load more)" if self.server_cursor else "") if self.servers else "No public servers are open right now (or the game has none).")

    # ---- where the servers are, and how long they have been running
    LOCATE_AT_ONCE = 25

    def ask_geo_source(self):
        """Which service may say where a server is. Asked once, until the person changes it in Settings. Returns 'roseal', 'ipwho' or None (cancel)."""
        box = QMessageBox(QMessageBox.Icon.Question, "Where should server locations come from?",
                          "Roblox's answer says which data centre a server runs in and its public address. To turn that into a city, one of these services can be used:\n\n"
                          "- RoSeal's list (data.roseal.live): the app downloads the public list of Roblox data centres kept by the RoSeal extension. Nothing about you, your account or "
                          "the server is sent: it is one plain download. This service is run by RoSeal, not by Roblox or by this app.\n\n"
                          "- ipwho.is: the server's public address is sent there, and it says which city the address is in. Nothing else is sent.\n\n"
                          "Nothing is contacted until you choose. You can change this later in Settings.", self.window())
        b_roseal = box.addButton("Use RoSeal's list", QMessageBox.ButtonRole.AcceptRole)
        b_ip = box.addButton("Use ipwho.is", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is b_roseal:
            return "roseal"
        return "ipwho" if box.clickedButton() is b_ip else None

    def _auto_locate(self):
        """With 'look up by themselves' on (and a service allowed, and signed in), the servers that were just listed are looked up without pressing the button."""
        if geo.auto_wanted(settings.get("geo.auto"), settings.get("geo.roseal"), settings.get("geo.allowed"), self.ctx.logged_in):
            self.locate_servers(auto=True)

    def locate_servers(self, auto=False, map_after=False):
        """The selected servers (or, if none is selected, the loaded ones not looked up yet; 25 at a time): Roblox's join answer gives each one's data centre, address and start time;
        the place comes from RoSeal's list or ipwho.is, whichever the person allowed. With auto=True (by itself, after the list arrived) the selection is ignored and nothing is asked."""
        c = self.ctx
        if not self.place_id or (not auto and c.need_login()):
            return
        if self._locating:
            self._map_after = self._map_after or map_after
            self._auto_again = self._auto_again or auto           # (the look-up of the old list is ending: this one follows)
            return
        picked = [] if auto else [row_key(self.server_table, r) for r in selected_rows(self.server_table)]
        ids = picked or [s["id"] for s in self.servers if s["id"] not in self.started]
        ids = [i for i in ids if i not in self.started][:None if map_after else self.LOCATE_AT_ONCE]       # (the map wants every loaded server)
        if not ids:
            if map_after:
                self._open_map()
            elif not auto:
                c.status("Every loaded server is looked up already." if self.servers else "Press Find servers first.")
            return
        if not settings.get("geo.roseal") and not settings.get("geo.allowed"):
            if auto and not map_after:
                return
            choice = self.ask_geo_source()
            if choice is None:
                if map_after:
                    self._open_map()                          # (nothing allowed: the map shows what is known)
                return
            settings.set("geo.roseal" if choice == "roseal" else "geo.allowed", True)
            self._check_wiki()
        use_roseal, use_ipwho = settings.get("geo.roseal"), settings.get("geo.allowed")
        self._locating, self._locate_stop = True, False
        self._map_after = self._map_after or map_after
        self.b_locate.setEnabled(False)
        self.b_stop_locate.show()
        gen, place, client = self.server_gen, self.place_id, c.client

        def work():
            found, when, ver, problems = {}, {}, {}, []
            for k, sid in enumerate(ids):
                if self._locate_stop:
                    break
                self.locating.emit(k, len(ids))
                try:
                    info = client.server_info(place, sid)
                    when[sid] = info["started_ms"] or 0
                    ver[sid] = info["place_version"] or 0
                    found[sid] = geo.resolve(info, use_roseal, use_ipwho)
                except rbx.Cancelled:
                    break
                except rbx.RobloxError as e:
                    problems.append(str(e))
                    if e.status == 401:
                        break
                except (geo.GeoError, ValueError) as e:
                    problems.append(str(e))
            return found, when, ver, len(ids), problems

        c.async_.run(work, lambda res: self._located(gen, *res), lambda e: (setattr(self, '_map_after', False), self._locate_done(), c.error(e)))

    def stop_locate(self):
        self._locate_stop = True
        self.b_stop_locate.setEnabled(False)
        self.ctx.client.cancel_pending()

    def _locate_done(self):
        self._locating = False
        again, self._auto_again = self._auto_again, False
        if again:
            QTimer.singleShot(0, self._auto_locate)
        self.b_locate.setEnabled(True)
        self.b_stop_locate.hide()
        self.b_stop_locate.setEnabled(True)
        self.ctx.client.clear_cancel()

    def _located(self, gen, found, when, ver, tried, problems):
        map_after, self._map_after = self._map_after, False
        self._locate_done()
        if gen != self.server_gen:
            return                                            # (another game, or a new search: this answer is old)
        self.places.update(found)
        self.started.update(when)
        self.versions.update(ver)
        self._show_servers()
        text = f"Looked up {len(when)} of {tried} server(s), {len(found)} located."
        if problems:
            text += f" {len(problems)} could not be located: {problems[0]}"
        self.server_note.setText(text)
        if map_after:
            self._open_map()

    def copy_server_link(self):
        rows = selected_rows(self.server_table)
        if not rows or not self.place_id:
            self.ctx.status("Select a server first.")
            return
        job = row_key(self.server_table, rows[0])
        if not rbx.safe_code(job):
            self.ctx.status("That server id looks odd, so no link was made.")
            return
        copy_text(rbx.join_link(self.place_id, job_id=job))
        self.ctx.status("Join link copied.")

    def _check_wiki(self):
        """With RoSeal's data service allowed, the game's wiki is looked for as the game opens; the button appears only for a game that has one. Without the permission nothing is contacted."""
        uid = (self.card or {}).get("universeId")
        if not uid or not settings.get("geo.roseal"):
            return
        self._wiki_for = uid

        def done(links):
            if self._wiki_for != uid or not links:
                return
            self.wiki_url = links[0]["url"]
            self.b_wiki.show()
        self.ctx.async_.run(lambda: roseal_links.links_for(uid), done, lambda e: None)

    def open_wiki(self):
        if self.wiki_url:
            open_url(self.wiki_url)
            self.ctx.status("Opened " + self.wiki_url)

    def show_map(self):
        """The map shows the servers' places: the ones not looked up yet are looked up first (the same way as 'Location and uptime'), then the map opens."""
        if not self.servers:
            self.ctx.status("Press Find servers first.")
            return
        if any(s["id"] not in self.started for s in self.servers) and self.ctx.logged_in:
            self.locate_servers(auto=True, map_after=True)
            return
        self._open_map()

    def _open_map(self):
        dlg = ServerMapDialog(self, self.servers, self.places, self._join_server, self.started)
        dlg.exec()

    def _join_server(self, server_id):
        if self.place_id and server_id:
            launch_roblox(self.ctx, self.place_id, job_id=server_id, web_url=self._page())

    def join_selected(self):
        rows = selected_rows(self.server_table)
        if not rows:
            self.ctx.status("Select a server first.")
            return
        self._join_server(row_key(self.server_table, rows[0]))

    def join_emptiest(self):
        """The server with the fewest players that is not full (asks Roblox for the emptiest ones first)."""
        if not self.place_id:
            return
        place, c = self.place_id, self.ctx.client
        self.server_note.setText("Looking for the emptiest server...")

        def found(res):
            servers, _ = res
            open_ = [s for s in servers if s["playing"] < s["max"]]
            if not open_:
                self.server_note.setText("No server with room was found right now.")
                return
            best = min(open_, key=lambda s: s["playing"])
            self.server_note.setText(f"Joining a server with {best['playing']} of {best['max']} players.")
            self._join_server(best["id"])
        self.ctx.async_.run(lambda: c.game_servers(place, "Asc", None, 25), found, lambda e: self.server_note.setText(f"The servers could not be loaded: {e}"))

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
        self.detail.back.connect(self._back_from_game)
        self.boxes = {}
        ctx.signed_in.connect(lambda: self._load_extras() if self.mode == "feed" and self.boxes else None)
        ctx.signed_out.connect(lambda: self._load_extras() if self.boxes else None)
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
        self.boxes = {k: self._box() for k in ("friends", "favorites", "recent")}          # your own rows, above Roblox's
        ids = []
        for s in sorts[:ROWS_LIMIT]:
            title = QLabel(s["name"])
            title.setProperty("role", "title")
            self.body_lay.addWidget(title)
            cards = [self._card(card) for card in s["games"][:ROW_LIMIT]]
            ids += [c.card["universeId"] for c in cards]
            self.body_lay.addWidget(self._scroll_row(cards))
        self._load_icons(ids)
        self._load_extras()

    @staticmethod
    def _scroll_row(widgets):
        row = QScrollArea()
        row.setWidgetResizable(True)
        row.setFrameShape(QFrame.Shape.NoFrame)
        row.setFixedHeight(300)
        inner = QWidget()
        hl = QHBoxLayout(inner)
        hl.setContentsMargins(0, 0, 0, 0)
        for w_ in widgets:
            hl.addWidget(w_)
        hl.addStretch()
        row.setWidget(inner)
        return row

    def _box(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        box.hide()
        self.body_lay.addWidget(box)
        return box

    def _fill_box(self, key, title, widgets):
        """Put a titled row into one of the boxes above Roblox's rows (an empty list hides it)."""
        box = self.boxes.get(key)
        if box is None:
            return
        lay = box.layout()
        while lay.count():
            it = lay.takeAt(0)
            w_ = it.widget()
            if w_:
                w_.hide()
                w_.setParent(None)
                w_.deleteLater()
        if not widgets:
            box.hide()
            return
        head = QLabel(title)
        head.setProperty("role", "title")
        lay.addWidget(head)
        lay.addWidget(self._scroll_row(widgets))
        box.show()

    def _load_extras(self):
        """Friends in games and your favorites (signed in), and the games you looked at lately (always)."""
        self.refresh_recent()
        c = self.ctx.client
        if not self.ctx.logged_in:
            self._fill_box("friends", "", [])
            self._fill_box("favorites", "", [])
            return
        self.ctx.async_.run(c.friends_in_games, self._friends_ready, lambda e: None)
        self.ctx.async_.run(c.favorite_games, self._favorites_ready, lambda e: None)

    def refresh_recent(self):
        cards = [self._card(c) for c in games_store.recent()[:ROW_LIMIT]]
        self._fill_box("recent", "Recently viewed", cards)
        self._load_icons([c.card["universeId"] for c in cards])

    def _favorites_ready(self, games):
        if self.mode != "feed":
            return
        cards = [self._card(g) for g in games[:ROW_LIMIT]]
        self._fill_box("favorites", "Your favorites", cards)
        self._load_icons([c.card["universeId"] for c in cards])

    def _friends_ready(self, friends):
        if self.mode != "feed":
            return
        widgets = []
        for f in friends[:ROW_LIMIT]:
            w_ = FriendCard(f)
            w_.join.connect(self._join_friend)
            widgets.append(w_)
            if f.get("universe"):
                self.cards.setdefault(int(f["universe"]), []).append(w_)
        self._fill_box("friends", "Friends in games", widgets)
        self._load_icons([int(f["universe"]) for f in friends[:ROW_LIMIT] if f.get("universe")])
        self._load_heads(widgets)

    def _load_heads(self, widgets):
        """The friends' pictures (kept on disk for a week, like the people lists)."""
        c = self.ctx.client
        todo = {}
        for w_ in widgets:
            uid = w_.f.get("id")
            if uid:
                data = rbx.cached_avatar(uid)
                if data:
                    w_.set_head(data)
                else:
                    todo.setdefault(int(uid), []).append(w_)
        if not todo:
            return

        def work():
            out = {}
            for uid, url in c.headshots(list(todo)).items():
                try:
                    out[uid] = c.fetch_bytes(url)
                except rbx.RobloxError:
                    pass
            return out

        def done(got):
            for uid, data in got.items():
                rbx.save_avatar(uid, data)
                for w_ in todo.get(uid, []):
                    try:
                        w_.set_head(data)
                    except RuntimeError:
                        pass                                  # (the row was rebuilt meanwhile)
        self.ctx.async_.run(work, done, lambda e: None)

    def _join_friend(self, f):
        launch_roblox(self.ctx, f["place"], job_id=f.get("job"), web_url=f"https://www.roblox.com/games/{int(f['place'])}")

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
    def _back_from_game(self):
        self.stack.setCurrentIndex(0)
        if self.mode == "feed" and self.boxes:
            self.refresh_recent()                              # the game just viewed is first now

    def open_game(self, card):
        self.detail.show_game(card)
        self.stack.setCurrentIndex(1)
