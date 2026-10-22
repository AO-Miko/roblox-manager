"""People tab: friends, friend requests, followers, who you follow, blocked users, and a user search.

Every list here works the same way: filter it, select several rows (Ctrl or Shift click, or the Select buttons), and run an action on
all of them. Long batches are paced to stay under Roblox's rate limit and show progress with a time estimate.
"""
import json
import time
from datetime import datetime

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QTableWidget, QTabWidget, QVBoxLayout, QWidget,
)

import rbx
import settings
from tab_account import FriendsTab
from tab_alerts import AlertsTab
from ui_common import BulkBar, button, copy_text, fill_table, hint, make_table, open_url, row_key, selected_rows, when


def person(u, cells=()):
    """One row for a user dict from Roblox (any of the list endpoints)."""
    name = u.get("displayName") or u.get("name") or f"User {u.get('id')}"
    return {"id": u["id"], "name": name, "username": u.get("name") or "", "cells": list(cells), "raw": u}


class UserListTab(QWidget):
    """A list of users with filter, multi-select and bulk actions.

    load(client) -> list of person() rows.   actions: dicts with label, verb, run(client, row), and optionally
    danger (asks twice for 5 or more), remove (the row disappears when it worked), warn (extra text in the question), log (file name).
    selectors: (label, tooltip, predicate(row, all_rows)) buttons that select rows."""

    NAME_CHUNK = 200          # ids per name lookup (the profile route takes 200)
    NAME_GAP_MS = 250         # between two lookups: that route allows 200 a minute and says so; the rate table does the pacing

    def __init__(self, ctx, columns, load, actions, selectors=(), empty="Nobody here.", signed_out="Sign in on the Home tab to see this list."):
        super().__init__()
        self._names_run = 0
        self._names_pending, self._names_total = [], 0
        self.ctx, self.load_fn, self.actions, self.empty, self.signed_out = ctx, load, actions, empty, signed_out
        self.rows, self.loaded = [], False
        self.on_changed = None            # optional callback(count) when the list changes
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name...")
        self.filter.textChanged.connect(lambda _=None: self.show_rows())
        top.addWidget(self.filter, 1)
        top.addWidget(button("Refresh", self.load))
        lay.addLayout(top)
        self.table = make_table(["Name", "Username"] + list(columns), [240, 180] + [130] * len(columns), empty=empty)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _=None: self.open_profile())
        lay.addWidget(self.table, 1)
        pick = QHBoxLayout()
        pick.addWidget(QLabel("Select:"))
        pick.addWidget(button("All shown", lambda: self.select_where(lambda r: True)))
        pick.addWidget(button("None", lambda: self.select_where(lambda r: False)))
        pick.addWidget(button("Invert", self.invert))
        for label, tip, pred in selectors:
            pick.addWidget(button(label, lambda p=pred: self.select_where(lambda r: p(r, self.rows)), tip))
        pick.addStretch()
        lay.addLayout(pick)
        self.bulk = BulkBar(ctx)
        lay.addWidget(self.bulk)
        row = QHBoxLayout()
        self.buttons = []
        for a in actions:
            b = button(a["label"], lambda a=a: self.run_action(a), a.get("tip", ""), primary=bool(a.get("primary")))
            if a.get("danger"):
                b.setProperty("danger", True)
            self.buttons.append(b)
            row.addWidget(b)
        row.addStretch()
        row.addWidget(button("Open profile", self.open_profile))
        row.addWidget(button("Copy user id", self.copy_id))
        lay.addLayout(row)
        self.info = hint(signed_out)
        lay.addWidget(self.info)
        ctx.signed_out.connect(self.clear)
        self._update_buttons()

    # ---------------------------------------------------------------- data
    def clear(self):
        self._names_run += 1                      # stop looking up names for the account that was in use
        self._names_pending = []
        self.rows, self.loaded = [], False
        fill_table(self.table, [])
        self.info.setText(self.signed_out)
        if self.on_changed:
            self.on_changed(None)

    def ensure_loaded(self):
        if not self.loaded and self.ctx.logged_in:
            self.load()

    def load(self):
        c = self.ctx
        if not c.logged_in:
            return
        self.info.setText("Loading...")
        client = c.client
        c.async_.run(lambda: self.load_fn(client), self._loaded, lambda e: (self.info.setText(f"Could not load: {e}"), c.error(e)))

    def _loaded(self, rows):
        self.rows, self.loaded = rows, True
        self.show_rows()
        if self.on_changed:
            self.on_changed(len(rows))
        self._start_names()

    # ---------------------------------------------------------------- names, looked up in the background
    def _start_names(self):
        """Roblox's lists leave names blank. Saved names are used at once; the rest are looked up a chunk of 200 at a time in the background
        (the profile route takes 200 per request and allows 200 requests a minute)."""
        self._names_run += 1
        self._names_pending = [r["id"] for r in self.rows if not r["raw"].get("name")]
        self._names_total = len(self._names_pending)
        if self._names_pending:
            self.info.setText(f"{len(self.rows)} people. Looking up names in the background: 0 of {self._names_total}...")
            self._next_names(self._names_run, 0)

    def _next_names(self, run, failures):
        if run != self._names_run or not self._names_pending:
            return
        if self.bulk.running:                                         # do not compete with a batch the person is running
            QTimer.singleShot(2000, lambda: self._next_names(run, failures))
            return
        chunk, self._names_pending = self._names_pending[:self.NAME_CHUNK], self._names_pending[self.NAME_CHUNK:]
        c = self.ctx

        def done(users):
            if run != self._names_run:
                return
            self._apply_names(users)
            left = len(self._names_pending)
            self.info.setText(f"{len(self.rows)} people. Looking up names in the background: {self._names_total - left} of {self._names_total}"
                              + ("..." if left else " (done)."))
            if left:
                QTimer.singleShot(self.NAME_GAP_MS, lambda: self._next_names(run, 0))

        def failed(e):
            if run != self._names_run:
                return
            if failures >= 5:
                self.info.setText(f"{len(self.rows)} people. Could not look up the remaining names: {e}")
                return
            self._names_pending = chunk + self._names_pending         # try this chunk again a little later
            QTimer.singleShot(10000, lambda: self._next_names(run, failures + 1))
        c.async_.run(lambda: c.client.lookup_names(chunk), done, failed)

    def _apply_names(self, users):
        by_id = {u["id"]: u for u in users}
        for r in self.rows:
            u = by_id.get(r["id"])
            if u:
                r["raw"]["name"], r["raw"]["displayName"] = u["name"], u.get("displayName") or u["name"]
                r["name"], r["username"] = u.get("displayName") or u["name"], u["name"]
        self.table.setSortingEnabled(False)                          # (a changed cell must not move the row under the mouse)
        for i in range(self.table.rowCount()):
            u = by_id.get(row_key(self.table, i))
            if u:
                self.table.item(i, 0).setText(u.get("displayName") or u["name"])
                self.table.item(i, 1).setText("@" + u["name"])
        self.table.setSortingEnabled(True)

    def show_rows(self):
        q = self.filter.text().strip().lower()
        shown = [r for r in self.rows if not q or q in r["name"].lower() or q in r["username"].lower()]
        fill_table(self.table, [[r["name"], "@" + r["username"] if r["username"] else ""] + r["cells"] for r in shown], keys=[r["id"] for r in shown])
        self.info.setText((f"{len(self.rows)} people." if self.rows else self.empty) + (f" {len(shown)} shown." if q else ""))
        self._update_buttons()

    # ---------------------------------------------------------------- selecting
    def sels(self):
        ids = {row_key(self.table, r) for r in selected_rows(self.table)}
        return [r for r in self.rows if r["id"] in ids]

    def select_where(self, test):
        self.table.clearSelection()
        sm = self.table.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        by_id = {r["id"]: r for r in self.rows}
        for i in range(self.table.rowCount()):
            r = by_id.get(row_key(self.table, i))
            if r and test(r):
                sm.select(self.table.model().index(i, 0), flags)
        self.ctx.status(f"{len(self.sels())} selected.")

    def invert(self):
        have = {r["id"] for r in self.sels()}
        self.select_where(lambda r: r["id"] not in have)

    def _update_buttons(self):
        n = len(self.sels()) if hasattr(self, "buttons") else 0
        for b in self.buttons:
            b.setEnabled(n > 0 and not self.bulk.running)

    def open_profile(self):
        s = self.sels()
        if s:
            open_url(f"https://www.roblox.com/users/{s[0]['id']}/profile")

    def copy_id(self):
        s = self.sels()
        if s:
            copy_text("\n".join(str(r["id"]) for r in s))
            self.ctx.status(f"Copied {len(s)} user id(s).")

    # ---------------------------------------------------------------- bulk actions
    def run_action(self, a):
        c = self.ctx
        if c.need_login() or self.bulk.running:
            return
        sel = self.sels()
        if not sel:
            c.status("Select people first (Ctrl or Shift click, or use the Select buttons).")
            return
        n = len(sel)
        names = "\n".join(f"  {r['name']}" + (f"  (@{r['username']})" if r["username"] else "") for r in sel[:15]) + ("\n  ..." if n > 15 else "")
        text = f"{a['verb']} {n} {'person' if n == 1 else 'people'}?\n\n{names}" + (f"\n\n{a['warn']}" if a.get("warn") else "")
        if (n > 1 or a.get("danger")) and not c.confirm(a["label"].rstrip("."), text, danger=bool(a.get("danger"))):
            return
        if a.get("danger") and n >= settings.typed_from():
            typed, ok = QInputDialog.getText(self, "Please confirm", f"You are about to change {n} people.\nType the number {n} to confirm:")
            if not ok or typed.strip() != str(n):
                c.status("Cancelled: the number did not match, nobody was changed.")
                return
        self.bulk.start(a["label"].rstrip("."), n)
        self._update_buttons()
        client = c.client

        def work():
            done, failed, t0 = [], [], time.time()
            for k, r in enumerate(sel):
                if self.bulk.stop_flag:
                    failed.append(f"- stopped by you: {n - k} were not tried")
                    break
                self.bulk.report(a["label"].rstrip("."), k, n, t0)
                try:
                    a["run"](client, r)
                    done.append(r)
                    if a.get("log"):
                        self._remember(a["log"], r)
                except rbx.Cancelled:
                    failed.append(f"- stopped by you: {n - k} were not tried")
                    break
                except rbx.RobloxError as e:
                    failed.append(f"- {r['name']} (@{r['username']}, id {r['id']}): {rbx.redact(e)}")
                    if e.status == 429:
                        failed.append(f"- stopped: Roblox is rate-limiting; {n - k - 1} were not tried. Wait a few minutes and try again.")
                        break
                except Exception as e:          # noqa: BLE001 - reported below
                    failed.append(f"- {r['name']} (id {r['id']}): {rbx.redact(e)}")
            return done, failed
        c.async_.run(work, lambda res: self._finished(a, n, *res), lambda e: (self._finished(a, n, [], [str(e)]), c.error(e)))

    @staticmethod
    def _remember(name, r):
        try:
            with open(rbx.STATE_DIR / f"{name}.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\t{r['id']}\t@{r['username']}\t{r['name']}\n")
        except OSError:
            pass

    def _finished(self, a, n, done, failed):
        self.bulk.finish()
        if a.get("remove"):
            gone = {r["id"] for r in done}
            self.rows = [r for r in self.rows if r["id"] not in gone]
            if self.on_changed:
                self.on_changed(len(self.rows))
        elif a.get("after"):
            a["after"](done, self.rows)
        self.show_rows()
        msg = f"{len(done)} of {n} done."
        if self.bulk.run_rate_hits:
            msg += f" Roblox rate-limited {self.bulk.run_rate_hits} request(s) during this (the app waited and retried)."
        self.ctx.status(msg, 15000)
        if failed:
            QMessageBox.warning(self, a["label"].rstrip("."), msg + "\n\nThese did not work:\n" + "\n".join(failed[:20]))


# ============================================================ the lists
def _requests_tab(ctx):
    def load(client):
        out = []
        for u in client.friend_requests():
            fr = u.get("friendRequest") or {}
            mutual = u.get("mutualFriendsList") or []
            out.append(person(u, [when(fr.get("sentAt")), str(len(mutual)) if mutual else ""]))
        return out
    t = UserListTab(ctx, ["Sent", "Mutual friends"], load, [
        {"label": "Accept selected", "verb": "Accept the friend requests of", "run": lambda c, r: c.accept_friend_request(r["id"]), "remove": True,
         "tip": "Accepts every selected request", "primary": True},
        {"label": "Decline selected", "verb": "Decline the friend requests of", "run": lambda c, r: c.decline_friend_request(r["id"]),
         "remove": True, "danger": True, "tip": "Declines every selected request"},
    ], empty="No pending friend requests.")
    row = QHBoxLayout()
    row.addWidget(button("Decline ALL requests...", lambda: _decline_all(t), "One request to Roblox that declines every pending friend request", danger=True))
    row.addStretch()
    t.layout().insertLayout(t.layout().count() - 1, row)
    return t


def _decline_all(t):
    c = t.ctx
    if c.need_login():
        return
    if not c.confirm("Decline all", "Decline EVERY pending friend request?\n\nThis cannot be undone.", danger=True):
        return
    c.async_.run(c.client.decline_all_friend_requests, lambda _: (c.status("All friend requests declined."), t.load()))


def _followers_tab(ctx):
    def load(client):
        followers, following = client.followers(), {u["id"] for u in client.followings()}
        return [person(u, ["yes" if u["id"] in following else ""]) for u in followers]
    t = UserListTab(ctx, ["You follow them"], load, [
        {"label": "Follow back", "verb": "Follow", "run": lambda c, r: c.follow(r["id"]),
         "after": lambda done, rows: [r["cells"].__setitem__(0, "yes") for r in rows if r["id"] in {d["id"] for d in done}]},
    ], selectors=[("Not followed back", "People who follow you that you do not follow", lambda r, rows: not r["cells"][0])],
        empty="Nobody follows you.")
    return t


def _following_tab(ctx):
    def load(client):
        following, followers = client.followings(), {u["id"] for u in client.followers()}
        return [person(u, ["yes" if u["id"] in followers else ""]) for u in following]
    t = UserListTab(ctx, ["Follows you"], load, [
        {"label": "Unfollow selected", "verb": "Unfollow", "run": lambda c, r: c.unfollow(r["id"]), "remove": True, "danger": True,
         "log": "unfollowed"},
    ], selectors=[("Not following me back", "People you follow who do not follow you", lambda r, rows: not r["cells"][0])],
        empty="You do not follow anyone.")
    return t


BLOCKED_FILE = "blocked-by-app.json"


def _blocked_local():
    try:
        return json.loads((rbx.STATE_DIR / BLOCKED_FILE).read_text())
    except (OSError, ValueError):
        return []


def _blocked_local_save(rows):
    try:
        (rbx.STATE_DIR / BLOCKED_FILE).write_text(json.dumps(rows))
    except OSError:
        pass


def remember_blocked(u, blocked=True):
    """Keep a list of who was blocked or unblocked from this app: Roblox does not offer a dependable way to read your blocked list."""
    rows = [r for r in _blocked_local() if r["id"] != u["id"]]
    if blocked:
        rows.append({"id": u["id"], "name": u.get("name", ""), "displayName": u.get("displayName", ""), "blockedAt": datetime.now().isoformat()})
    _blocked_local_save(rows)


def _blocked_tab(ctx):
    state = {"fallback": False}

    def load(client):
        try:
            rows, state["fallback"] = client.blocked_users(), False
        except rbx.RobloxError as e:
            if e.status in (401, 403):
                raise
            rows, state["fallback"] = _blocked_local(), True      # Roblox would not give the list: show what this app blocked
        return [person(b, [when(b.get("blockedAt"))]) for b in rows]

    def run_unblock(c, r):
        c.unblock_user(r["id"])
        remember_blocked(r["raw"], blocked=False)

    t = UserListTab(ctx, ["Blocked since"], load, [
        {"label": "Unblock selected", "verb": "Unblock", "run": run_unblock, "remove": True, "danger": True,
         "warn": "They will be able to message you and see your profile again.", "log": "unblocked"},
    ], empty="You have not blocked anyone.")
    t.state = state
    base = t.show_rows

    def show_rows():
        base()
        if state["fallback"]:
            t.info.setText("Roblox does not let apps read your full blocked list, so this shows only people blocked or unblocked from this app. "
                           + t.info.text())
    t.show_rows = show_rows
    row = QHBoxLayout()
    row.addWidget(button("Unblock by name or id...", lambda: _unblock_by_name(t), "Unblock someone who is not in the list above"))
    row.addStretch()
    t.layout().insertLayout(t.layout().count() - 1, row)
    return t


def _unblock_by_name(t):
    c = t.ctx
    if c.need_login():
        return
    text, ok = QInputDialog.getText(t, "Unblock", "Username or user id:")
    if not ok or not text.strip():
        return

    def work():
        found = c.client.search_users(text.strip())
        exact = [u for u in found if str(u["id"]) == text.strip() or (u.get("name") or "").lower() == text.strip().lower()]
        if not exact:
            raise rbx.RobloxError(404, f"No user called '{text.strip()}'")
        u = exact[0]
        c.client.unblock_user(u["id"])
        return u

    def done(u):
        remember_blocked(u, blocked=False)
        c.status(f"Unblocked {u.get('name')}.")
        t.load()
    c.async_.run(work, done)


# ============================================================ find a user
class FindTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.results = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Username, part of a name, or a user id")
        self.entry.returnPressed.connect(self.search)
        row.addWidget(self.entry, 1)
        row.addWidget(button("Search", self.search))
        lay.addLayout(row)
        self.table = make_table(["Name", "Username", "User id", "Verified"], [240, 200, 120, 80], empty="Type a name above and press Enter to find someone.")
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_friend = button("Send friend request", lambda: self.act("Friend request sent to", lambda c, u: c.send_friend_request(u["id"])))
        self.b_follow = button("Follow", lambda: self.act("Now following", lambda c, u: c.follow(u["id"])))
        self.b_block = button("Block...", self.block)
        self.b_block.setProperty("danger", True)
        for b in (self.b_friend, self.b_follow, self.b_block, button("Open profile", self.open_profile), button("Copy user id", self.copy_id)):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.info = hint("Type a name and press Enter.")
        lay.addWidget(self.info)

    def search(self):
        c, text = self.ctx, self.entry.text().strip()
        if not text:
            return
        self.info.setText("Searching...")
        c.async_.run(lambda: c.client.search_users(text), self._found, lambda e: (self.info.setText(f"Search failed: {e}"), c.error(e)))

    def _found(self, users):
        self.results = users
        fill_table(self.table, [[u.get("displayName") or u.get("name", ""), "@" + u.get("name", ""), u["id"], "yes" if u.get("hasVerifiedBadge") else ""] for u in users],
                   keys=[u["id"] for u in users])
        self.info.setText(f"{len(users)} found." if users else "Nobody found with that name.")

    def current(self):
        rows = selected_rows(self.table)
        if not rows:
            self.ctx.status("Select a person in the list first.")
            return None
        return next((u for u in self.results if u["id"] == row_key(self.table, rows[0])), None)

    def act(self, done_text, fn):
        u, c = self.current(), self.ctx
        if not u or c.need_login():
            return
        c.async_.run(lambda: fn(c.client, u), lambda _: c.status(f"{done_text} {u.get('name')}."))

    def block(self):
        u, c = self.current(), self.ctx
        if not u or c.need_login():
            return
        if c.confirm("Block", f"Block {u.get('name')}?\n\nThey will not be able to message you or see your profile, and you will not see them.", danger=True):
            c.async_.run(lambda: c.client.block_user(u["id"]), lambda _: (remember_blocked(u), c.status(f"Blocked {u.get('name')}.")))

    def open_profile(self):
        u = self.current()
        if u:
            open_url(f"https://www.roblox.com/users/{u['id']}/profile")

    def copy_id(self):
        u = self.current()
        if u:
            copy_text(str(u["id"]))
            self.ctx.status("User id copied.")


# ============================================================ the tab
class PeopleTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setProperty("sub", True)
        lay.addWidget(self.tabs)
        self.friends = FriendsTab(ctx)
        self.requests = _requests_tab(ctx)
        self.followers = _followers_tab(ctx)
        self.following = _following_tab(ctx)
        self.blocked = _blocked_tab(ctx)
        self.find = FindTab(ctx)
        self.alerts = AlertsTab(ctx)
        self.pages = [(self.friends, "Friends"), (self.requests, "Requests"), (self.followers, "Followers"), (self.following, "Following"),
                      (self.blocked, "Blocked"), (self.find, "Find a user"), (self.alerts, "Alerts")]
        for w, name in self.pages:
            self.tabs.addTab(w, name)
        self.requests.on_changed = lambda n: ctx.set_count("requests", n)
        self.followers.on_changed = lambda n: ctx.set_count("followers", n)
        self.following.on_changed = lambda n: ctx.set_count("following", n)
        self.blocked.on_changed = lambda n: ctx.set_count("blocked", n)
        self.tabs.currentChanged.connect(self._shown)
        ctx.signed_in.connect(self._signed_in)
        self.bases = [name for _, name in self.pages]
        ctx.counts.connect(self.set_count)

    SUB = {"friends": 0, "requests": 1, "followers": 2, "following": 3, "blocked": 4}

    def set_count(self, what, n):
        """Put how many there are in the sub-tab's title, so it is visible without opening it."""
        i = self.SUB.get(what)
        if i is not None:
            self.tabs.setTabText(i, f"{self.bases[i]} ({n if isinstance(n, str) else format(n, ',')})" if n else self.bases[i])

    def _signed_in(self):
        c = self.ctx
        c.async_.run(c.client.friend_request_count, lambda n: c.set_count("requests", "500+" if n >= 500 else n), lambda e: None)     # (Roblox's count stops at 500)
        self._shown(self.tabs.currentIndex())

    def _shown(self, i):
        w = self.pages[i][0]
        if hasattr(w, "ensure_loaded"):
            w.ensure_loaded()
