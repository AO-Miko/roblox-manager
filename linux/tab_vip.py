"""VIP (private) servers tab: all your VIP servers across every game, with the controls you would want,
plus a lookup for any game (to see which of your friends have a VIP server there)."""
import json
import queue
import threading
import time
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, Signal

import rbx
import settings
from ui_common import FlowLayout, button, copy_text, fill_table, hint, make_table, open_url, parse_id, row_key, selected_rows, when


def vip_id(item):
    """The id of a private server in Roblox's list (the field name differs between answers)."""
    for k in ("vipServerId", "privateServerId", "id", "serverId"):
        v = item.get(k)
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
            return int(v)
    return None


def expiry(item):
    sub = item.get("subscription") if isinstance(item.get("subscription"), dict) else {}
    return item.get("expirationDate") or sub.get("expirationDate") or sub.get("expiresAt") or ""


def server_state(item, names):
    """'' for a working server, otherwise why it is no longer usable: 'Unavailable' (the game is gone or has switched
    VIP servers off) or 'Expired' (the subscription ended)."""
    if item.get("_renewed"):
        return ""
    if "content deleted" in str(item.get("universeName") or item.get("gameName") or "").lower() or item.get("_unavailable"):
        return "Unavailable"
    pid = item.get("placeId")
    if pid and names and int(pid) not in names:
        return "Unavailable"
    sub = item.get("subscription") if isinstance(item.get("subscription"), dict) else {}
    if sub.get("expired"):
        return "Expired"
    exp = expiry(item)
    if exp:
        try:
            d = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d < datetime.now(timezone.utc):
                return "Expired"
        except ValueError:
            pass
    return ""


def cost_kind(item):
    """What the server costs, as far as Roblox's data tells. Roblox has no field for this, so it is worked out from the numbers it does give:
    a discount means Roblox Plus made it free, an expiry about 100 years away means the game offers it free, a price means it is paid."""
    sub = item.get("subscription") if isinstance(item.get("subscription"), dict) else {}
    price = item.get("priceInRobux") or sub.get("price") or 0
    discount = item.get("totalDiscountAmountInRobux") or sub.get("totalDiscountAmountInRobux") or 0
    if price and price > 0:
        return f"Paid {int(price)} R$"
    if discount and discount > 0:
        return "Free (Roblox Plus)"
    exp = expiry(item)
    try:
        d = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if d.year >= datetime.now().year + 50:
            return "Free (game)"
    except ValueError:
        pass
    return "Unknown"


FREE_COSTS = ("Free (Roblox Plus)", "Free (game)")


def is_free(item):
    return cost_kind(item) in FREE_COSTS


def is_paid(item):
    return cost_kind(item).startswith("Paid")


def best_per_game(servers):
    """The servers that are the keeper of their game (see keeper_score)."""
    by = {}
    for sv in servers:
        by.setdefault(game_key(sv), []).append(sv)
    return {id(sorted(v, key=keeper_score, reverse=True)[0]) for v in by.values()}


def free_only_plan(servers):
    """What 'only free servers on' would do: (to switch on, to switch off).
    On: working servers that are free (through Roblox Plus or from the game), currently off, and the keeper of their game.
    Off: working servers that are paid and currently on. Servers whose cost is not known are left alone, and so are expired and
    unavailable ones."""
    best = best_per_game(servers)
    working = [s for s in servers if not s["_state"] and s["_vid"] is not None]
    on = [s for s in working if is_free(s) and not s.get("active") and id(s) in best]
    off = [s for s in working if is_paid(s) and s.get("active")]
    return on, off


def game_key(item):
    return item.get("universeId") or item.get("placeId") or ("name", item.get("universeName") or item.get("gameName"))


def keeper_score(item):
    """How good a server is to keep when a game has several: working, then switched on, then renewing, then the later expiry."""
    return (not item.get("_state"), bool(item.get("active")), bool(item.get("willRenew")), str(expiry(item)))


def duplicate_groups(servers):
    """{game key: [servers, best first]} for games that have more than one VIP server."""
    by = {}
    for sv in servers:
        by.setdefault(game_key(sv), []).append(sv)
    return {k: sorted(v, key=keeper_score, reverse=True) for k, v in by.items() if len(v) > 1}


def reason_text(err):
    """Roblox's own words from an error, without the 'HTTP 400:' in front."""
    t = str(err)
    return t.split(": ", 1)[1] if t.startswith("HTTP ") and ": " in t else t


def verdict(item, reason=""):
    """What the app concluded about a server and why, in plain words (shown as a tooltip and in the Details window)."""
    state = item.get("_state") or ""
    if state == "Unavailable":
        return reason or "The game this server belongs to is gone or no longer offers VIP servers."
    if state == "Expired":
        return f"The subscription ended on {when(expiry(item))[:10]}."
    return "Working."


FREE_LIMIT = "more active free private servers"


def unavailable_reason(err):
    """True when Roblox's answer for a server says its game no longer offers VIP servers."""
    m = str(err).lower()
    return "disabled private servers" in m or "does not exist" in m or "content deleted" in m or "not found" in m


class CreateDialog(QDialog):
    def __init__(self, parent, game_text=""):
        super().__init__(parent)
        self.setWindowTitle("Create a VIP server")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.game = QLineEdit(game_text)
        self.game.setPlaceholderText("place id or link of the game")
        self.name = QLineEdit("My VIP server")
        self.price = QSpinBox()
        self.price.setRange(0, 1_000_000)
        self.price.setSuffix(" Robux")
        form.addRow("Game:", self.game)
        form.addRow("Server name:", self.name)
        form.addRow("Price you expect:", self.price)
        lay.addLayout(form)
        warn = QLabel("<b>This can spend Robux.</b> VIP servers have a price set by the game. Enter the price shown on the game's page; "
                      "Roblox refuses to create the server if the real price is different, so you can't be charged more than what you enter. "
                      "If the price is above 0, your Robux are spent when you press Create.")
        warn.setWordWrap(True)
        warn.setProperty("role", "notice")
        lay.addWidget(warn)
        row = QHBoxLayout()
        row.addStretch()
        cancel, ok = QPushButton("Cancel"), QPushButton("Create")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)


class PermissionsDialog(QDialog):
    """Who may join a VIP server: your friends, and specific people you add by username."""

    def __init__(self, parent, ctx, name, perms, users):
        super().__init__(parent)
        self.ctx = ctx
        self.users = list(users)    # [{id, name, displayName}]
        self.setWindowTitle(f"Who can join '{name}'")
        self.setMinimumSize(460, 420)
        lay = QVBoxLayout(self)
        self.friends = QCheckBox("All my friends can join")
        self.friends.setChecked(bool(perms.get("friendsAllowed")))
        lay.addWidget(self.friends)
        lay.addWidget(QLabel("These people can join as well:"))
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("Add a person...", self.add))
        row.addWidget(button("Remove selected", self.remove))
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(hint("Roblox only lets you add people who allow it in their privacy settings."))
        end = QHBoxLayout()
        end.addStretch()
        cancel, ok = QPushButton("Cancel"), QPushButton("Save")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        end.addWidget(cancel)
        end.addWidget(ok)
        lay.addLayout(end)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for u in self.users:
            self.list.addItem(f"{u.get('displayName') or u.get('name') or '?'}  (@{u.get('name', '?')}, id {u['id']})")

    def add(self):
        text, ok = QInputDialog.getText(self, "Add a person", "Their username:")
        if not ok or not text.strip():
            return
        c = self.ctx

        def work():
            u = c.client.user_by_name(text.strip())
            if not u:
                return None, None
            try:
                chk = c.client.can_invite(u["id"])
            except rbx.RobloxError:
                chk = {}
            return u, chk

        def done(res):
            u, chk = res
            if not u:
                QMessageBox.information(self, "Not found", f"There is no user called '{text.strip()}'.")
            elif chk.get("canInvite") is False:
                QMessageBox.information(self, "Cannot add", f"{u['name']} cannot be added to a private server (their privacy settings do not allow it).")
            elif any(x["id"] == u["id"] for x in self.users):
                QMessageBox.information(self, "Already there", f"{u['name']} is already on the list.")
            else:
                self.users.append({"id": u["id"], "name": u["name"], "displayName": u.get("displayName", u["name"])})
                self.refresh()
        c.async_.run(work, done)

    def remove(self):
        r = self.list.currentRow()
        if r >= 0:
            del self.users[r]
            self.refresh()


class VipTab(QWidget):
    rate = Signal(str, float, bool, bool)         # Roblox said 'too many requests', or the app waits by itself (path, seconds, gave up, proactive)
    background = Signal(object)                  # (kind, vip id, value) from the slow background lookups
    progress = Signal(str, int, int, float)      # label, done, total, seconds since start (sent from the worker thread)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.mine = []               # my private servers, as Roblox gives them
        self.names = {}              # place id -> game name
        self._queued = set()
        self._lookups_total = self._lookups_done = 0
        self._checked_at = {}
        self.reasons = {}            # vip id -> Roblox's own message when the lookup said the game no longer offers VIP servers
        self._bgq = queue.Queue()
        self._bg_gen = 0
        self._bg_pause_until = 0.0
        self._bg_thread = None
        self._bg_dirty = False
        self.background.connect(self._bg_apply)
        self.rate_hits = 0
        ctx.busy_checks.append(lambda: self.running)
        ctx.stoppers.append(lambda: self.stop_bulk())
        self.rate.connect(self._on_rate)
        ctx.client.rate_hooks.append(lambda path, wait, gave_up, proactive=False: self.rate.emit(path, wait, gave_up, proactive))
        self.rate_clear = QTimer(self)
        self.rate_clear.setSingleShot(True)
        self.rate_clear.timeout.connect(lambda: self.ratenote.hide())
        self.links = {}              # vip id -> join link ("-" when Roblox gave none)
        self._caches = {}            # user id -> {"links": {...}, "checked": {...}}: switching back to an account repeats no lookups
        self.checked = {}            # vip id -> True if Roblox said its game no longer offers VIP servers
        self.place = self.universe = None
        self.game = {}
        self.rows = []
        self.view = []
        self.loaded_once = False

        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(split)

        # ---------------------------------------------------------------- my servers (the default view)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        head = FlowLayout()
        title = QLabel("My VIP servers")
        title.setProperty("role", "title")
        head.addWidget(title)
        head.addStretch()
        self.hide = {}
        for state, tip in (("Expired", "Servers whose subscription has ended"),
                           ("Unavailable", "Servers whose game no longer exists or can't be found")):
            cb = QCheckBox(f"Hide {state.lower()}")
            cb.setChecked(True)
            cb.setToolTip(tip + ". Roblox has no way to delete a VIP server, so they are only hidden here.")
            cb.toggled.connect(lambda _=False: self.show_mine())
            self.hide[state] = cb
            head.addWidget(cb)
        head.addWidget(button("Refresh", self.load_mine))
        self.b_create = button("Create VIP server...", self.create, primary=True)
        head.addWidget(self.b_create)
        tl.addLayout(head)
        self.mfilter = QLineEdit()
        self.mfilter.setPlaceholderText("Filter by game, server name or id...")
        self.mfilter.textChanged.connect(lambda _=None: self.show_mine())
        frow = QHBoxLayout()
        frow.addWidget(self.mfilter, 1)
        self.b_alllinks = button("Load all links", lambda: self._ask_lookups("link"), "Look up every working server's join link (one request each, paced)")
        self.b_findgone = button("Check for unavailable", lambda: self._ask_lookups("check"),
                                 "Ask Roblox about each server not checked yet, to find the ones whose game removed VIP servers (one request each; this also "
                                 "runs by itself in the background after the list loads)")
        frow.addWidget(self.b_alllinks)
        frow.addWidget(self.b_findgone)
        tl.addLayout(frow)
        self.mtable = make_table(["Game", "Server", "Status", "Expires", "VIP id", "VIP link", "Copies", "Cost"], [230, 190, 90, 140, 105, 240, 70, 175],
                                empty="No VIP servers to show.\nSign in on the Home tab, or loosen the filters above.")
        self.mtable.setSelectionMode(self.mtable.SelectionMode.ExtendedSelection)
        self.apply_column_order()
        tl.addWidget(self.mtable, 1)
        row = FlowLayout()
        self.b_active = button("Switch on/off", self.toggle_active, "A VIP server that is switched off cannot be joined")
        self.b_allow = button("Allow people...", self.allow_people, "Choose who can join: your friends and specific people")
        self.b_copy = button("Copy join link", self.copy_join)
        self.b_open = button("Open join link", self.open_join)
        self.b_rename = button("Rename...", self.rename)
        self.b_link = button("New join link", self.new_link, "Makes a new link; the old link stops working")
        self.b_cancel = button("Cancel renewal", self.cancel_renewal)
        self.b_renew = button("Renew...", self.renew, "Renew an expired server (may cost Robux; free servers with Roblox Plus cost 0)")
        self.b_game = button("Open game", self.open_game, "Open the game's page on roblox.com")
        self.b_details = button("Details", self.details, "Everything Roblox knows about this server")
        for b in (self.b_active, self.b_allow, self.b_copy, self.b_open, self.b_rename, self.b_link, self.b_cancel, self.b_renew, self.b_game, self.b_details):
            row.addWidget(b)
        row.addStretch()
        tl.addLayout(row)
        pick = FlowLayout()
        pick.addWidget(QLabel("Select:"))
        for text, what in (("All expired", "expired"), ("All disabled", "disabled"), ("All enabled", "enabled"), ("One per game", "best"), ("Duplicates", "extras"), ("All", "all"), ("None", "none")):
            pick.addWidget(button(text, lambda w=what: self.select_group(w)))
        pick.addSpacing(16)
        pick.addWidget(QLabel("For the selected:"))
        self.bulk = [button("Switch on", lambda: self.bulk_active(True)), button("Switch off", lambda: self.bulk_active(False)),
                     button("Cancel renewal", self.bulk_cancel), button("Renew...", self.bulk_renew)]
        for b in self.bulk:
            pick.addWidget(b)
        pick.addStretch()
        tl.addLayout(pick)
        cost = FlowLayout()
        cost.addWidget(QLabel("By cost:"))
        for text, what, tip in (("Plus-free", "plus", "Servers that are free because of Roblox Plus"), ("Game-free", "gamefree", "Servers the game itself offers for free"),
                                ("All free", "free", "Both kinds of free server"), ("Paid", "paid", "Servers that cost Robux")):
            cost.addWidget(button(text, lambda w=what: self.select_group(w), tip + " (only the keeper of each game; the same rule as the other selections)"))
        cost.addSpacing(16)
        cost.addWidget(QLabel("Show:"))
        self.cost_filter = QComboBox()
        for text, key in (("All costs", ""), ("Free (Plus + game)", "free"), ("Free (Roblox Plus)", "Free (Roblox Plus)"), ("Free (game)", "Free (game)"),
                          ("Paid", "paid"), ("Unknown", "Unknown")):
            self.cost_filter.addItem(text, key)
        self.cost_filter.currentIndexChanged.connect(lambda _=0: self.show_mine())
        cost.addWidget(self.cost_filter)
        cost.addStretch()
        self.b_freeonly = button("Only free servers on...", self.free_only,
                                 "Switch on the free servers (Roblox Plus and game-free) and switch off the paid ones. Servers whose cost is unknown are left alone.")
        cost.addWidget(self.b_freeonly)
        tl.addLayout(cost)
        self.mnote = hint("Sign in on the Home tab to see your VIP servers.")
        tl.addWidget(self.mnote)
        self.ratenote = QLabel("")
        self.ratenote.setWordWrap(True)
        self.ratenote.setProperty("role", "warn")
        self.ratenote.hide()
        tl.addWidget(self.ratenote)
        prog = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        prog.addWidget(self.bar, 1)
        self.b_stop = button("Stop", self.stop_bulk, "Finish the one in progress, then stop")
        prog.addWidget(self.b_stop)
        self.progress_box = QWidget()
        self.progress_box.setLayout(prog)
        prog.setContentsMargins(0, 0, 0, 0)
        self.progress_box.hide()
        tl.addWidget(self.progress_box)
        self.stop_flag = False
        self.running = False
        self.progress.connect(self._show_progress)
        split.addWidget(top)

        # ---------------------------------------------------------------- look up any game
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        head2 = QHBoxLayout()
        t2 = QLabel("Look up a game (see its VIP servers, and which are your friends')")
        t2.setStyleSheet("font-weight: bold;")
        head2.addWidget(t2)
        bl.addLayout(head2)
        look = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Game: place id or link (for example https://www.roblox.com/games/920587237/...)")
        self.entry.returnPressed.connect(self.load_game)
        look.addWidget(self.entry, 1)
        look.addWidget(button("Look up", self.load_game))
        bl.addLayout(look)
        self.gameinfo = QLabel("")
        bl.addWidget(self.gameinfo)
        self.table = make_table(["Mine", "Friend's", "Name", "Owner", "Players", "VIP id"], [60, 70, 260, 170, 80, 110])
        bl.addWidget(self.table, 1)
        self.gnote = hint("")
        bl.addWidget(self.gnote)
        split.addWidget(bottom)
        split.setSizes([520, 200])

        ctx.signed_in.connect(self.load_mine)
        ctx.signed_out.connect(self.clear)
        self.update_buttons()
        self.mtable.itemSelectionChanged.connect(self.update_buttons)
        self.mtable.itemSelectionChanged.connect(self._fetch_selected_links)

    # ============================================================ state
    def clear(self):
        self.mine, self.rows, self.view = [], [], []
        self.links, self.checked, self.reasons = {}, {}, {}           # (each account's own caches are kept in self._caches)
        self._queued = set()
        self._lookups_total = self._lookups_done = 0
        self._bg_gen += 1
        fill_table(self.mtable, [])
        fill_table(self.table, [])
        self.mnote.setText("Sign in on the Home tab to see your VIP servers.")
        self.update_buttons()

    # what the person sees, left to right: Game, Status, Expires, Cost, Server, VIP id, VIP link, Copies (the table's own numbering stays as it
    # was, so sorting, tooltips and the link column keep working; only the order on screen changes)
    COLUMN_ORDER = ["Game", "Status", "Expires", "Cost", "Server", "VIP id", "VIP link", "Copies"]

    def apply_column_order(self):
        head = self.mtable.horizontalHeader()
        names = [self.mtable.horizontalHeaderItem(c).text() for c in range(self.mtable.columnCount())]
        head.setSectionsMovable(True)                       # drag a column header to arrange them your own way (remembered)
        for visual, name in enumerate(self.COLUMN_ORDER):
            head.moveSection(head.visualIndex(names.index(name)), visual)
        head.setStretchLastSection(False)
        head.setSectionResizeMode(names.index("VIP link"), head.ResizeMode.Stretch)       # the link column takes the spare width

    def update_buttons(self):
        sel = self._sel() is not None
        for b in (self.b_active, self.b_allow, self.b_copy, self.b_open, self.b_rename, self.b_link, self.b_cancel, self.b_renew, self.b_game,
                  self.b_details):
            b.setEnabled(sel)
        n = len(self._sels())
        for b in self.bulk:
            b.setEnabled(n > 0 and not self.running)
            b.setToolTip(f"Applies to the {n} selected server(s) it fits; the rest are skipped" if n else "Select servers first")
        cur = self._sel()
        if cur is not None and cur.get("_state") == "Expired":
            for b in (self.b_active, self.b_allow, self.b_rename, self.b_link, self.b_cancel):
                b.setEnabled(False)
                b.setToolTip("This server's subscription has expired; Roblox only allows changes after it is renewed")
        else:
            for b in (self.b_active, self.b_allow, self.b_rename, self.b_link, self.b_cancel):
                b.setToolTip("")
        self.b_renew.setEnabled(cur is not None and cur.get("_state") == "Expired")
        if cur is None:
            self.b_active.setText("Switch on/off")
        else:
            self.b_active.setText("Switch off" if cur.get("active") else "Switch on")

    def _sels(self):
        keys = [row_key(self.mtable, r) for r in selected_rows(self.mtable)]
        return [s for s in self.mine if s["_key"] in keys]

    def _sel(self):
        """The selected server, when exactly one is selected."""
        rows = self._sels()
        return rows[0] if len(rows) == 1 else None

    def _need(self):
        self._bg_pause_until = max(self._bg_pause_until, time.time() + 5)      # your action goes first
        s = self._sel()
        if not s:
            self.ctx.status("Select one of your servers first.")
            return None
        if s["_vid"] is None:
            QMessageBox.information(self, "Cannot identify this server",
                                    "Roblox's list did not include this server's id, so it cannot be managed from here yet. Press Details and "
                                    "tell me what it shows, and I will adapt the app.")
            return None
        return s

    # ============================================================ my servers
    def load_mine(self):
        c = self.ctx
        if not c.logged_in:
            return
        self.mnote.setText("Loading your VIP servers...")
        client = c.client
        cache = self._caches.setdefault(c.me["id"], {"links": {}, "checked": {}, "reasons": {}})
        self.links, self.checked, self.reasons = cache["links"], cache["checked"], cache.setdefault("reasons", {})
        if not cache.get("from_disk"):
            cache["from_disk"] = True
            for v, (u, ts, why) in self._checks_load(c.me["id"]).items():
                self.checked.setdefault(v, u)
                self._checked_at.setdefault(v, ts)
                if why:
                    self.reasons.setdefault(v, why)

        def work():
            items = client.my_private_servers()
            names = client.place_names([i.get("placeId") for i in items])
            return items, names
        c.async_.run(work, self._mine_loaded, lambda e: (self.mnote.setText("Could not load your VIP servers: " + str(e)), c.error(e)))

    def _mine_loaded(self, res):
        items, names = res
        self.names.update(names)
        self.mine = []
        for n, it in enumerate(items):
            it = dict(it)
            it["_vid"] = vip_id(it)
            it["_unavailable"] = bool(self.checked.get(it["_vid"]))
            it["_key"] = it["_vid"] if it["_vid"] is not None else f"row{n}"
            self.mine.append(it)
        self.ctx.set_count("vip", len(self.mine))
        self.show_mine()
        self.loaded_once = True
        self.fetch_links()

    def show_mine(self):
        for s in self.mine:
            s["_state"] = server_state(s, self.names)
        shown = [s for s in self.mine if not (s["_state"] and self.hide[s["_state"]].isChecked())]
        ck = self.cost_filter.currentData()
        if ck:
            shown = [s for s in shown if (is_free(s) if ck == "free" else is_paid(s) if ck == "paid" else cost_kind(s) == ck)]
        q = self.mfilter.text().strip().lower()
        if q:
            def hay(s):
                pid = s.get("placeId")
                return " ".join(str(x) for x in (self.names.get(int(pid)) if pid else "", s.get("universeName"), s.get("name"), s.get("_vid"))).lower()
            shown = [s for s in shown if q in hay(s)]
        rows, colours = [], {}
        dups = duplicate_groups(self.mine)
        for i, s in enumerate(shown):
            active = s.get("active")
            status = s["_state"] or ("ON" if active else ("OFF" if active is not None else "?"))
            colours[(i, 2)] = "#3ba55d" if (active and not s["_state"]) else "#e5534b"
            rows.append([self.names.get(int(s["placeId"])) if s.get("placeId") else (s.get("gameName") or "?"), s.get("name", ""),
                         status, when(expiry(s)), s["_vid"] if s["_vid"] is not None else "", self.links.get(s["_vid"], ""),
                         ("x%d" % len(dups[game_key(s)]) if game_key(s) in dups else ""), cost_kind(s)])
            if game_key(s) in dups:
                colours[(i, 6)] = "#e0a030"
        fill_table(self.mtable, rows, colours, keys=[s["_key"] for s in shown])
        by_key = {s["_key"]: s for s in shown}
        for r in range(self.mtable.rowCount()):
            sv, it = by_key.get(row_key(self.mtable, r)), self.mtable.item(r, 2)
            if sv is not None and it is not None:
                it.setToolTip(verdict(sv, self.reasons.get(sv["_vid"], "")))
        on = sum(1 for s in shown if s.get("active") and not s["_state"])
        note = f"{len(shown)} VIP server(s), {on} switched on." if shown else "You do not own any working VIP servers (or Roblox returned none)."
        extra = []
        for state in ("Expired", "Unavailable"):
            n = sum(1 for s in self.mine if s["_state"] == state)
            if n:
                extra.append(f"{n} {state.lower()} " + ("hidden" if self.hide[state].isChecked() else "shown"))
        if extra:
            note += " " + ", ".join(extra) + ". Roblox offers no way to delete a VIP server."
        if dups:
            note += (f" {len(dups)} game(s) have more than one VIP server ({sum(len(v) - 1 for v in dups.values())} extra); "
                     "you can only keep one free server on at a time.")
        self.mnote.setText(note)
        self.update_buttons()

    # ============================================================ actions on my servers
    def toggle_active(self):
        s = self._need()
        if not s:
            return
        c, vid = self.ctx, s["_vid"]
        want = not bool(s.get("active"))
        if not want and not c.confirm("Switch off", f"Switch '{s.get('name')}' off? Nobody can join it until you switch it on again."):
            return

        def done(_):
            s["active"] = want
            self.show_mine()
            self._reselect(s["_key"])
            c.status(f"'{s.get('name')}' is now {'ON' if want else 'OFF'}.")
        c.async_.run(lambda: c.client.update_vip_server(vid, active=want), done,
                     lambda e: self.offer_swap(s) if want and FREE_LIMIT in str(e) else c.error(e))

    def _reselect(self, key):
        for i in range(self.mtable.rowCount()):
            if row_key(self.mtable, i) == key:
                self.mtable.selectRow(i)
                return

    def allow_people(self):
        s = self._need()
        if not s:
            return
        c, vid = self.ctx, s["_vid"]

        def work():
            d = c.client.vip_server(vid)
            perms = d.get("permissions") or {}
            users = perms.get("users") or []
            ids = [u["id"] for u in users if isinstance(u, dict) and u.get("id") and not u.get("name")] + [u for u in users if isinstance(u, int)]
            info = {u["id"]: u for u in c.client.lookup_names(ids)} if ids else {}
            full = []
            for u in users:
                uid = u["id"] if isinstance(u, dict) else u
                base = u if isinstance(u, dict) and u.get("name") else info.get(uid, {"id": uid})
                full.append({"id": uid, "name": base.get("name", ""), "displayName": base.get("displayName", base.get("name", ""))})
            return perms, full

        def ready(res):
            perms, users = res
            dlg = PermissionsDialog(self, c, s.get("name", ""), perms, users)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            fa, new_users = dlg.friends.isChecked(), dlg.users
            c.async_.run(lambda: c.client.set_vip_permissions(vid, fa, new_users, current=perms),
                         lambda how: c.status("Saved who can join " + f"'{s.get('name')}'."),
                         lambda e: QMessageBox.warning(self, "Roblox refused the change",
                                                       f"{e}\n\nRoblox does not document this request, so the app tried the likely formats and none was accepted."
                                                       "\nThe API Explorer (games: PATCH /v1/vip-servers/{id}/permissions) lets you try a body by hand."))
        c.async_.run(work, ready)

    def _fetch_link(self, s, retries=3):
        d = self.ctx.client.vip_server(s["_vid"], retries=retries)
        return d.get("link") or (rbx.join_link(s.get("placeId") or 0, link_code=d.get("joinCode")) if d.get("joinCode") and s.get("placeId") else "")

    def _link(self, s, done):
        c, vid = self.ctx, s["_vid"]
        if self.links.get(vid, "") not in ("", "-"):
            return done(self.links[vid])

        def got(link):
            if link:
                self.links[vid] = link
                self._set_link_cell(vid, link)
                done(link)
            else:
                c.status("Roblox did not give a join link for this server.")
        c.async_.run(lambda: self._fetch_link(s), got)

    # ---------------------------------------------------------------- slow lookups, one at a time, out of the way
    CHECK_TTL = 7 * 24 * 3600      # a server's 'game removed VIP servers' answer is reused for a week

    # ---------------------------------------------------------------- one lookup per server: is it still offered, and what is its link
    def _enqueue(self, servers):
        """Queue background lookups (one request each; Roblox allows about 3 a second and the app follows that). A lookup answers two
        things at once: whether the game still offers VIP servers (a server whose game removed them is 'Unavailable', whatever its
        subscription says) and the server's join link. Returns how many were queued."""
        wanted = [s for s in servers if s["_vid"] is not None and s["_vid"] not in self._queued]
        for s in wanted:
            self._queued.add(s["_vid"])
            self._bgq.put((self._bg_gen, "detail", s["_vid"], s))
        if wanted:
            self._lookups_total += len(wanted)
            if self._bg_thread is None or not self._bg_thread.is_alive():
                self._bg_thread = threading.Thread(target=self._bg_loop, daemon=True)
                self._bg_thread.start()
        return len(wanted)

    def _needs_check(self, s):
        return s["_vid"] is not None and s["_vid"] not in self.checked

    def _needs_link(self, s):
        return s["_vid"] is not None and not s["_state"] and self.links.get(s["_vid"], "") == ""

    def fetch_links(self):
        """After a load: check every server that has not been checked in the last week (expired ones first, then working ones). It
        runs in the background, waits while you run an action, and the servers found unavailable disappear from the list if
        'Hide unavailable' is on."""
        self._bg_gen += 1
        self._queued = set()
        self._lookups_total = self._lookups_done = 0
        while True:
            try:
                self._bgq.get_nowait()
            except queue.Empty:
                break
        todo = [s for s in self.mine if self._needs_check(s)]
        todo.sort(key=lambda s: not s["_state"])                   # the expired ones first: there are few, and most 'game removed VIP servers' answers are there
        self._enqueue(todo)
        self._lookup_buttons()
        self._lookup_progress()

    def _lookup_progress(self):
        left = len(self._queued) - self._lookups_done
        if self._queued and left > 0:
            self.ctx.status(f"Checking your VIP servers in the background: {self._lookups_done} of {len(self._queued)}...", 3000)

    def _lookup_buttons(self):
        check = sum(1 for s in self.mine if self._needs_check(s))
        link = sum(1 for s in self.mine if self._needs_link(s))
        self.b_alllinks.setText(f"Load all links ({link})" if link else "Load all links")
        self.b_alllinks.setEnabled(link > 0)
        self.b_findgone.setText(f"Check for unavailable ({check})" if check else "Check for unavailable")
        self.b_findgone.setEnabled(check > 0)

    def _ask_lookups(self, kind):
        """The buttons: 'check' looks up every server not checked yet; 'link' every working server whose link is not known."""
        servers = [s for s in self.mine if (self._needs_check(s) if kind == "check" else self._needs_link(s))]
        self._queued -= {s["_vid"] for s in servers}               # they may have been done before: ask again where something is missing
        n = self._enqueue(servers)
        eta = n * 0.5                                              # about 3 a second
        self.ctx.status(f"Looking up {n} server(s) in the background (about {int(eta // 60)} min {int(eta % 60)} s). "
                        "You can keep working; it waits while you run an action.", 12000)
        self._lookup_buttons()

    def _fetch_selected_links(self):
        """Selecting a row looks that server up if its link is not known yet (at most 25 rows at a time)."""
        sel = [s for s in self._sels() if self._needs_link(s)][:25]
        if sel:
            self._queued -= {s["_vid"] for s in sel}
            self._enqueue(sel)

    def _bg_loop(self):
        client = self.ctx.client
        while True:
            try:
                gen, kind, vid, s = self._bgq.get(timeout=5)
            except queue.Empty:
                self.background.emit(("idle", None, None))
                return
            while gen == self._bg_gen and (self.running or time.time() < self._bg_pause_until):
                time.sleep(0.5)                      # yield to whatever the user is doing
            if gen != self._bg_gen:
                continue
            try:
                try:
                    d = client.vip_server(vid, retries=0)
                    link = d.get("link") or (rbx.join_link(s.get("placeId") or 0, link_code=d.get("joinCode")) if d.get("joinCode") and s.get("placeId") else "")
                    res = (False, link or "-", "")
                except rbx.RobloxError as e:
                    if e.status == 429 or getattr(e, "local", False):
                        raise
                    res = (unavailable_reason(e), "-", reason_text(e))      # (the game removed VIP servers / the server is gone: Roblox's words are kept)
                self.background.emit(("detail", vid, res))
            except rbx.RobloxError as e:
                if e.status == 429 or getattr(e, "local", False):
                    self._bg_pause_until = time.time() + 30
                    self._bgq.put((gen, kind, vid, s))
                    rbx.log.info("background lookups paused for 30 s (rate limited)")
            except Exception:                       # noqa: BLE001 - these lookups are optional
                pass

    def _bg_apply(self, res):
        kind, vid, val = res
        if kind == "idle":
            if self._bg_dirty and not selected_rows(self.mtable) and not self.running:
                self._bg_dirty = False
                self.show_mine()
            return
        unavailable, link, why = val
        self._lookups_done += 1
        self.checked[vid] = unavailable
        if unavailable and why:
            self.reasons[vid] = why
        self._checked_at[vid] = time.time()
        if not unavailable:
            self.links[vid] = link
            self._set_link_cell(vid, link)
        if unavailable:
            for s in self.mine:
                if s["_vid"] == vid and not s.get("_unavailable"):
                    s["_unavailable"] = True
                    self._bg_dirty = True
        self._lookup_buttons()
        if self._lookups_done % 10 == 0 or self._lookups_done >= len(self._queued):
            self._checks_save()
            self._lookup_progress()
            if self._bg_dirty and not selected_rows(self.mtable) and not self.running:
                self._bg_dirty = False
                self.show_mine()                     # servers found unavailable leave the list as they are found (when 'Hide unavailable' is on)

    # ---- the answers are kept for a week, per account, so the next start does not repeat them
    def _checks_file(self):
        return rbx.STATE_DIR / "vip-checks.json"

    def _checks_load(self, uid):
        try:
            raw = json.loads(self._checks_file().read_text()).get(str(uid), {})
        except (OSError, ValueError):
            return {}
        now = time.time()
        return {int(v): (bool(x[0]), x[1], x[2] if len(x) > 2 else "") for v, x in raw.items() if now - x[1] < self.CHECK_TTL}

    def _checks_save(self):
        if not self.ctx.me:
            return
        f, uid = self._checks_file(), str(self.ctx.me["id"])
        try:
            try:
                data = json.loads(f.read_text())
            except (OSError, ValueError):
                data = {}
            now = time.time()
            mine = {str(v): [bool(u), self._checked_at.get(v, now), self.reasons.get(v, "")] for v, u in self.checked.items()}
            data[uid] = {k: x for k, x in mine.items() if now - x[1] < self.CHECK_TTL}
            f.write_text(json.dumps(data))
        except OSError:
            pass

    def _set_link_cell(self, vid, link):
        for r in range(self.mtable.rowCount()):
            it = self.mtable.item(r, 4)
            if it is not None and it.text() == str(vid):
                self.mtable.setSortingEnabled(False)
                self.mtable.setItem(r, 5, QTableWidgetItem(link))
                self.mtable.setSortingEnabled(True)
                return

    def copy_join(self):
        s = self._need()
        s and self._link(s, lambda l: (copy_text(l), self.ctx.status("Join link copied.")))

    def open_join(self):
        s = self._need()
        s and self._link(s, open_url)

    def open_game(self):
        s = self._need()
        if s and s.get("placeId"):
            open_url(f"https://www.roblox.com/games/{int(s['placeId'])}")
        elif s:
            self.ctx.status("Roblox did not say which game this server is in.")

    # ---------------------------------------------------------------- several servers at once
    def select_group(self, what):
        dups = duplicate_groups(self.mine)
        by_game = {}
        for sv in self.mine:
            by_game.setdefault(game_key(sv), []).append(sv)
        best = {id(sorted(v, key=keeper_score, reverse=True)[0]) for v in by_game.values()}
        wanted = {"best": lambda s: id(s) in best,
                  "extras": lambda s: game_key(s) in dups and id(s) not in best,
                  # the category selections never include a duplicate that has a better copy (see keeper_score)
                  "expired": lambda s: s["_state"] == "Expired" and id(s) in best,
                  "disabled": lambda s: not s["_state"] and not s.get("active") and id(s) in best,
                  "enabled": lambda s: not s["_state"] and bool(s.get("active")) and id(s) in best,
                  "plus": lambda s: not s["_state"] and cost_kind(s) == "Free (Roblox Plus)" and id(s) in best,
                  "gamefree": lambda s: not s["_state"] and cost_kind(s) == "Free (game)" and id(s) in best,
                  "free": lambda s: not s["_state"] and is_free(s) and id(s) in best,
                  "paid": lambda s: not s["_state"] and is_paid(s) and id(s) in best,
                  "all": lambda s: True, "none": lambda s: False}[what]
        for state in ("Expired", "Unavailable"):       # hidden rows cannot be selected, so show the kinds being selected
            if self.hide[state].isChecked() and any(s["_state"] == state and wanted(s) for s in self.mine):
                self.hide[state].setChecked(False)
        self.mtable.clearSelection()
        keys = {s["_key"] for s in self.mine if wanted(s)}
        sm = self.mtable.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for r in range(self.mtable.rowCount()):
            if row_key(self.mtable, r) in keys:
                sm.select(self.mtable.model().index(r, 0), flags)
        self.ctx.status(f"{len(self._sels())} server(s) selected.")

    def _on_rate(self, path, wait, gave_up, proactive=False):
        if proactive:
            self.ratenote.setText(f"Staying within Roblox's limit: waiting {wait:.0f} s on {path} (Roblox allows only so many of these per minute; nothing was refused).")
            if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
                self.ratenote.show()
            self.rate_clear.start(20000)
            return
        self.rate_hits += 1
        self.run_rate_hits = getattr(self, "run_rate_hits", 0) + 1
        what = "background lookups are paused for a while" if self._bg_pause_until > time.time() else "it will retry"
        text = (f"Roblox is rate-limiting requests (too many in a short time). "
                + (f"Gave up on one request to {path}; {what}." if gave_up else f"Waiting {wait:.0f} s before retrying {path}.")
                + f" Times this session: {self.rate_hits}.")
        self.ratenote.setText(text)
        if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
            self.ratenote.show()
        self.ctx.status(text, 8000)
        self.rate_clear.start(20000)

    def _show_progress(self, label, done, total, secs):
        if total <= 0:
            return
        left = ""
        if done > 0 and done < total:
            eta = secs / done * (total - done)
            left = f", about {int(eta // 60)}m {int(eta % 60):02d}s left" if eta >= 60 else f", about {int(eta)}s left"
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        text = f"{label}: {done}/{total} done, {total - done} left{left}"
        self.bar.setFormat(text)
        self.progress_box.show()
        self.ctx.status(text, 4000)

    def _begin(self, label, total):
        self.running, self.stop_flag = True, False
        self.run_rate_hits = 0
        if total > 3:
            gap = self.ctx.client.SLOW_GAP
            self.ctx.status(f"Pacing requests (about one every {gap:.0f} s) to stay under Roblox's limit; this will take about "
                            f"{int(total * gap // 60)} min.", 12000)
        self.update_buttons()
        self.progress.emit(label, 0, total, 0.0)

    def _end(self):
        self.running = False
        self.ctx.client.clear_cancel()
        self.progress_box.hide()
        self.update_buttons()

    def stop_bulk(self):
        self.stop_flag = True
        self.b_stop.setEnabled(False)
        if self.running:
            self.ctx.client.cancel_pending()
        self.ctx.status("Stopping...")

    def _bulk_run(self, title, servers, action, after=None):
        """Run action(server) for each server on a worker, then report how many worked and why the others did not."""
        c = self.ctx
        self._begin(title, len(servers))

        def work():
            ok, failed = 0, []
            hit = []
            t0 = time.time()
            for n, sv in enumerate(servers):
                if self.stop_flag:
                    failed.append(f"- stopped by you: {len(servers) - n} server(s) were not tried")
                    break
                self.progress.emit(title, n, len(servers), time.time() - t0)
                try:
                    action(sv)
                    ok += 1
                except rbx.Cancelled:
                    failed.append(f"- stopped by you: {len(servers) - n} server(s) were not tried")
                    break
                except Exception as e:      # noqa: BLE001 - each failure is reported below
                    pid = sv.get("placeId")
                    game = self.names.get(int(pid)) if pid else None
                    game = game or sv.get("universeName") or sv.get("gameName") or "unknown game"
                    exp = when(expiry(sv))
                    failed.append(f"- {sv.get('name', '?')}\n    game: {game}\n    place id: {pid}   VIP id: {sv.get('_vid')}"
                                  f"   state: {sv.get('_state') or ('ON' if sv.get('active') else 'OFF')}"
                                  + (f"   expired/expires: {exp}" if exp else "") + f"\n    Roblox said: {rbx.redact(e)}")
                    if FREE_LIMIT in str(e):
                        hit.append(sv)
                        failed.append(f"- stopped: {len(servers) - n - 1} more server(s) were not tried, they would be refused for the same reason")
                        break
            return ok, failed, hit

        def done(res):
            ok, failed, hit = res
            self._end()
            self.show_mine()
            msg = f"{ok} of {len(servers)} done."
            if self.run_rate_hits:
                msg += f" Roblox rate-limited {self.run_rate_hits} request(s) during this, which slowed it down (the app waited and retried)."
            c.status(f"{title}: {msg}")
            if failed or self.run_rate_hits:
                hint_txt = ""
                if any(FREE_LIMIT in f for f in failed):
                    hint_txt += ("\n\nRoblox only lets you have a limited number of free VIP servers switched on at once (with Roblox Plus, "
                                 "one free server). Switch another one off first, or pick fewer servers.")
                if any("wait a few minutes" in f or "recently purchased" in f for f in failed):
                    hint_txt += "\n\nRoblox asks for a short wait after a purchase: select those servers again in a few minutes and retry."
                if failed:
                    QMessageBox.warning(self, title, msg + "\n\nThese did not work:\n" + "\n".join(failed[:20]) + hint_txt)
            if hit:
                self.offer_swap(hit[0], extra=len(servers) > 1)
            else:
                self.load_mine()
        c.async_.run(work, done, lambda e: (self._end(), c.error(e)))

    def offer_swap(self, target, extra=False):
        """Roblox refused to switch `target` on because the free-server limit is reached: offer to switch the one(s) that are
        on off first, then switch `target` on."""
        c = self.ctx
        active = [x for x in self.mine if x.get("active") and not x["_state"] and x is not target and x["_vid"] is not None]

        def line(x):
            pid = x.get("placeId")
            return f"  {x.get('name', '?')}  ({self.names.get(int(pid)) if pid else x.get('universeName') or '?'})"
        if not active:
            QMessageBox.information(self, "Free server limit",
                                    "Roblox says you have reached the limit of free VIP servers switched on, but none of the servers in this list "
                                    "is on. One may be on in a game this list does not show; check roblox.com.")
            self.load_mine()
            return
        what = f"'{target.get('name', '?')}'" + (" (the first one that was refused)" if extra else "")
        if not c.confirm("Free server limit reached",
                         f"Roblox allows only a limited number of free VIP servers switched on at once, and these are on now:\n\n"
                         + "\n".join(line(x) for x in active[:10]) + ("\n  ..." if len(active) > 10 else "")
                         + f"\n\nSwitch them off and switch on {what} instead?"
                         + ("\n\nOnly one server can be switched on this way; the rest of your selection stays off." if extra else "")):
            self.load_mine()
            return
        self._begin("Swapping", len(active) + 1)

        def work():
            t0 = time.time()
            for n, x in enumerate(active):
                self.progress.emit("Swapping", n, len(active) + 1, time.time() - t0)
                c.client.update_vip_server(x["_vid"], active=False)
                x["active"] = False
            self.progress.emit("Swapping", len(active), len(active) + 1, time.time() - t0)
            c.client.update_vip_server(target["_vid"], active=True)
            target["active"] = True

        def done(_):
            self._end()
            self.show_mine()
            c.status(f"Switched {len(active)} off and '{target.get('name', '?')}' on.")
            self.load_mine()
        c.async_.run(work, done, lambda e: (self._end(), c.error(e), self.load_mine()))

    def _usable(self, servers):
        return [s for s in servers if s["_vid"] is not None and s["_state"] != "Expired"]

    def bulk_active(self, want):
        c = self.ctx
        todo = [s for s in self._usable(self._sels()) if bool(s.get("active")) != want]
        if not todo:
            c.status("Nothing to change: the selected servers are already " + ("on" if want else "off") + " (or expired).")
            return
        word = "on" if want else "off"
        if not c.confirm(f"Switch {word}", f"Switch {word} {len(todo)} server(s)?"):
            return

        def act(sv):
            c.client.update_vip_server(sv["_vid"], active=want)
            sv["active"] = want
        self._bulk_run(f"Switch {word}", todo, act)

    def free_only(self):
        """Only the free servers on: switch on the free ones (Roblox Plus and game-free), switch off the paid ones."""
        c = self.ctx
        on, off = free_only_plan(self.mine)
        if not on and not off:
            c.status("Already the way you want it: every free server is on and no paid server is on (servers of unknown cost are left alone).")
            return
        unknown = sum(1 for s in self.mine if not s["_state"] and cost_kind(s) == "Unknown")
        lines = [f"Switch ON {len(on)} free server(s) (Roblox Plus and game-free; one per game)."] if on else []
        lines += [f"Switch OFF {len(off)} paid server(s)."] if off else []
        if unknown:
            lines.append(f"{unknown} server(s) of unknown cost are left as they are.")
        note = ("\n\nRoblox only lets a limited number of free servers be on at once. If it refuses one, the app stops there and offers to "
                "swap it with the one that is on.") if on else ""
        if not c.confirm("Only free servers on", "\n".join(lines) + note, danger=bool(off)):
            return
        for sv in off:
            sv["_want"] = False
        for sv in on:
            sv["_want"] = True

        def act(sv):
            c.client.update_vip_server(sv["_vid"], active=sv["_want"])
            sv["active"] = sv["_want"]
        self._bulk_run("Only free servers on", off + on, act)         # the paid ones go off first, then the free ones come on

    def bulk_cancel(self):
        c = self.ctx
        todo = self._usable(self._sels())
        if not todo:
            c.status("No selected server can have its renewal cancelled (expired servers cannot).")
            return
        if not c.confirm("Cancel renewal", f"Stop {len(todo)} server(s) from renewing? When their current period ends they expire.", danger=True):
            return
        self._bulk_run("Cancel renewal", todo,
                       lambda sv: c.client.patch(f"https://games.roblox.com/v1/vip-servers/{sv['_vid']}/subscription", {"active": False}))

    def bulk_renew(self):
        c = self.ctx
        todo = [s for s in self._sels() if s["_vid"] is not None and s["_state"] == "Expired"]
        if not todo:
            c.status("None of the selected servers is expired, so there is nothing to renew.")
            return
        client = c.client
        self._begin("Checking prices", len(todo))

        def look():
            out, t0 = [], time.time()
            for n, sv in enumerate(todo):
                if self.stop_flag:
                    break
                self.progress.emit("Checking prices", n, len(todo), time.time() - t0)
                sub = (client.vip_server(sv["_vid"]).get("subscription") or {})
                out.append((sv, int(sub.get("price") or 0), sub.get("canRenew", True)))
            return out

        def ask(found):
            stopped = self.stop_flag
            self._end()
            if stopped:
                c.status("Stopped: nothing was renewed.")
                return
            ok = [(sv, price) for sv, price, can in found if can]
            skipped = len(found) - len(ok)
            if not ok:
                QMessageBox.information(self, "Cannot renew", "Roblox says none of these servers can be renewed any more.")
                return
            total = sum(price for _, price in ok)
            cost = f"{total} Robux in total will be spent." if total else "It costs 0 Robux."
            lines = "\n".join(f"  {sv.get('name', '?')}: {price} Robux" for sv, price in ok[:15])
            if not c.confirm("Renew VIP servers", f"Renew {len(ok)} server(s)?\n\n{lines}\n\n{cost}"
                             + (f"\n{skipped} cannot be renewed and are skipped." if skipped else "")
                             + "\nRoblox refuses any renewal whose real price differs from the one shown.", danger=total > 0):
                return
            prices = {sv["_key"]: price for sv, price in ok}

            def act(sv):
                client.renew_vip_server(sv["_vid"], prices[sv["_key"]])
                sv["_renewed"] = True
                sv["active"] = False
                try:
                    client.update_vip_server(sv["_vid"], active=True)
                    sv["active"] = True
                except rbx.RobloxError:
                    pass                     # renewed but left off; the user can switch it on
            self._bulk_run("Renew", [sv for sv, _ in ok], act)
        c.async_.run(look, ask, lambda e: (self._end(), c.error(e)))

    def rename(self):
        s = self._need()
        if not s:
            return
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=s.get("name", ""))
        if ok and name.strip():
            c = self.ctx

            def done(_):
                s["name"] = name.strip()
                self.show_mine()
                self._reselect(s["_key"])
                c.status("Renamed.")
            c.async_.run(lambda: c.client.update_vip_server(s["_vid"], name=name.strip()), done)

    def new_link(self):
        s = self._need()
        if s and self.ctx.confirm("New join link", f"Make a new join link for '{s.get('name')}'?\n\nThe old link stops working for everyone who has it."):
            c = self.ctx
            c.async_.run(lambda: c.client.update_vip_server(s["_vid"], newJoinCode=True), lambda _: c.status("New link made. Use 'Copy join link' to get it."))

    def cancel_renewal(self):
        s = self._need()
        if s and self.ctx.confirm("Cancel renewal", f"Stop '{s.get('name')}' from renewing? When the current period ends, the server expires.", danger=True):
            c = self.ctx
            c.async_.run(lambda: c.client.patch(f"https://games.roblox.com/v1/vip-servers/{s['_vid']}/subscription", {"active": False}),
                         lambda _: (c.status("Renewal cancelled."), self.load_mine()))

    def renew(self):
        s = self._need()
        if not s:
            return
        c, vid, client = self.ctx, s["_vid"], self.ctx.client

        def look():
            d = client.vip_server(vid)
            try:
                plus = client.has_premium()
            except rbx.RobloxError:
                plus = None
            return d, plus

        def ask(res):
            d, plus = res
            sub = d.get("subscription") or {}
            if not sub.get("canRenew", True):
                QMessageBox.information(self, "Cannot renew", "Roblox says this server cannot be renewed any more.")
                return
            price = int(sub.get("price") or 0)
            tail = {True: "You have Roblox Plus, which includes one free VIP server.", False: "You do not have Roblox Plus.",
                    None: "Could not check whether you have Roblox Plus."}[plus]
            cost = f"{price} Robux will be spent." if price else "It costs 0 Robux."
            if not c.confirm("Renew VIP server", f"Renew '{s.get('name')}'?\n\n{cost}\n{tail}\n\n"
                             "Roblox refuses the renewal if the real price differs from the one shown.", danger=price > 0):
                return
            def renewed(_):
                s["subscription"] = dict(s.get("subscription") or {}, expired=False, active=True)
                s["active"] = False
                s["_renewed"] = True
                self.show_mine()
                self._reselect(s["_key"])
                c.status("Server renewed. Switching it on...")

                def on(_):
                    s["active"] = True
                    self.show_mine()
                    self._reselect(s["_key"])
                    c.status(f"'{s.get('name')}' is renewed and switched on.")
                    self.load_mine()

                def on_failed(e):
                    c.status("Renewed, but it could not be switched on automatically.")
                    c.error(e)
                c.async_.run(lambda: client.update_vip_server(vid, active=True), on, on_failed)
            c.async_.run(lambda: client.renew_vip_server(vid, price), renewed)
        c.async_.run(look, ask)

    def details(self):
        s = self._sel()
        if not s:
            return
        c = self.ctx
        shown = {k: v for k, v in s.items() if not k.startswith("_")}

        def show(extra):
            dlg = QDialog(self)
            dlg.setWindowTitle(f"VIP server {s.get('name', '')}")
            dlg.resize(620, 480)
            lay = QVBoxLayout(dlg)
            box = QPlainTextEdit(json.dumps({"what the app concluded": {"status": s.get("_state") or "working", "why": verdict(s, self.reasons.get(s["_vid"], ""))},
                                             "from the list": shown, "full details": extra}, indent=2, ensure_ascii=False))
            box.setReadOnly(True)
            box.setStyleSheet("font-family: monospace;")
            lay.addWidget(box)
            row = QHBoxLayout()
            row.addStretch()
            close = QPushButton("Close")
            close.clicked.connect(dlg.accept)
            row.addWidget(close)
            lay.addLayout(row)
            dlg.exec()
        if s["_vid"] is None:
            show(None)
        else:
            def failed(e):
                if isinstance(e, rbx.RobloxError) and unavailable_reason(e):       # Roblox's own message says the game removed VIP servers
                    self.checked[s["_vid"]] = True
                    self.reasons[s["_vid"]] = reason_text(e)
                    s["_unavailable"] = True
                    self._checks_save()
                    s["_state"] = "Unavailable"
                    self.show_mine()
                show({"error": str(e)})
            c.async_.run(lambda: c.client.vip_server(s["_vid"]), show, failed)

    def create(self):
        c = self.ctx
        if c.need_login():
            return
        d = CreateDialog(self, str(self.place or ""))
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        pid = parse_id(d.game.text())
        if not pid:
            QMessageBox.information(self, "Which game?", "Enter the game's place id or link.")
            return
        sname, price = d.name.text().strip() or "My VIP server", d.price.value()
        client = c.client

        def find():
            uni = client.place_universe(pid)
            return uni, (client.game_info(uni) or {}).get("name") or f"place {pid}"

        def ready(res):
            uni, gname = res
            cost = f"{price} Robux will be spent." if price else "It is free (0 Robux)."
            if not c.confirm("Create VIP server", f"Create '{sname}' in {gname}?\n\n{cost}", danger=price > 0):
                return
            c.async_.run(lambda: client.create_vip_server(uni, sname, price),
                         lambda r: (c.status(f"Created '{r.get('name', sname)}'."), self.load_mine()))
        c.async_.run(find, ready)

    # ============================================================ look up a game
    def load_game(self):
        c = self.ctx
        pid = parse_id(self.entry.text())
        if not pid:
            c.status("Enter a place id or a game link.")
            return
        if c.need_login():
            return
        self.place = pid
        self.gameinfo.setText("Loading...")
        client = c.client

        def work():
            uni = client.place_universe(pid)
            game = client.game_info(uni) or {}
            friend_ids = [f["id"] for f in client.friends()]
            rows, problems = rbx.vip_scan(client, [pid], friend_ids)
            return uni, game, rows, problems
        c.async_.run(work, self._game_loaded, lambda e: (self.gameinfo.setText("Could not load this game."), c.error(e)))

    def _game_loaded(self, res):
        self.universe, self.game, rows, problems = res
        self.gameinfo.setText(f"{self.game.get('name') or 'Place ' + str(self.place)}   (place {self.place}, universe {self.universe})")
        me = self.ctx.me["id"]
        self.view = sorted([dict(r, mine=r["owner_id"] == me) for r in rows], key=lambda r: (not r["mine"], not r["friend"], r["name"].lower()))
        fill_table(self.table, [["YES" if r["mine"] else "", "YES" if r["friend"] else "", r["name"], r["owner"],
                                 f"{r['playing']}/{r['max']}" if r["max"] else "", r["vip_id"]] for r in self.view],
                   {**{(i, 0): "#3ba55d" for i, r in enumerate(self.view) if r["mine"]}, **{(i, 1): "#5ab0ff" for i, r in enumerate(self.view) if r["friend"]}},
                   keys=[r["vip_id"] for r in self.view])
        friends = sum(1 for r in self.view if r["friend"])
        msg = f"{len(self.view)} VIP server(s) visible here: {sum(1 for r in self.view if r['mine'])} yours, {friends} owned by friends."
        if problems:
            msg += "  Some lookups failed: " + "; ".join(m for ms in problems.values() for m in ms)
        self.gnote.setText(msg)
