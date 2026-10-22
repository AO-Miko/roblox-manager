"""Groups tab: your groups, members and ranks, join requests, roles, audit log and bans."""
import json
import time
from datetime import datetime

from PySide6.QtCore import QDate, QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QTableWidget, QTabWidget,
    QVBoxLayout, QWidget,
)

import rbx
import settings
from ui_common import BulkBar, FlowLayout, button, cell, day_in_range, copy_text, fill_table, hint, make_table, open_url, parse_id, row_key, selected_rows, when


def perm(p, section, key):
    return bool(((p or {}).get(section) or {}).get(key))


class GroupsTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.gid = None
        self.membership = {}
        self.roles = []
        self.members, self.members_cursor = [], None
        self.requests, self.requests_cursor = [], None
        self.audit, self.audit_cursor = [], None
        self.bans = []
        self._gen, self._busy = {}, {}                 # per list: which load is the current one, and whether a page is being fetched
        self.search_hits, self._search_gen = [], 0     # members found by Roblox's own search (they may not be loaded yet)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(450)
        self._search_timer.timeout.connect(self.search_server)
        self.created = {}        # group id -> ISO creation time

        outer = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split)

        # ---- left: the list of groups
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.glist = make_table(["Group", "My role", "Rank", "Members", "Created"], [185, 120, 60, 90, 125], empty="No groups to show.")
        left.setMinimumWidth(330)
        self.glist.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.glist.itemSelectionChanged.connect(self.pick_group)
        self.gfilter = QLineEdit()
        self.gfilter.setPlaceholderText("Filter by name...")
        self.gfilter.textChanged.connect(lambda _=None: self._show_groups())
        ll.addWidget(self.gfilter)
        ll.addWidget(self.glist, 1)
        pick = FlowLayout()
        pick.addWidget(QLabel("Select:"))
        pick.addWidget(button("All shown", lambda: self.select_groups_where(lambda g: True)))
        pick.addWidget(button("None", lambda: self.select_groups_where(lambda g: False)))
        pick.addWidget(button("Invert", self.invert_group_selection))
        pick.addWidget(button("Plain members", lambda: self.select_groups_where(lambda g: g["role"]["rank"] <= 1),
                              "Groups where you have no special role (rank 1 or lower)"))
        pick.addStretch()
        ll.addLayout(pick)
        bydate = FlowLayout()
        bydate.addWidget(QLabel("Created from"))
        self.date_from = QDateEdit(QDate(2006, 1, 1))
        self.date_to = QDateEdit(QDate.currentDate().addYears(-3))
        for de in (self.date_from, self.date_to):
            de.setCalendarPopup(True)
            de.setDisplayFormat("yyyy-MM-dd")
            de.setMaximumDate(QDate.currentDate())
        bydate.addWidget(self.date_from)
        bydate.addWidget(QLabel("to"))
        bydate.addWidget(self.date_to)
        bydate.addWidget(button("Select by date", self.select_by_date,
                                "Selects the shown groups created in this range (Roblox does not say when you joined, only when the group was made)"))
        bydate.addStretch()
        ll.addLayout(bydate)
        self.bulk = BulkBar(ctx)
        ll.addWidget(self.bulk)
        row = QHBoxLayout()
        self.b_leave = button("Leave selected groups...", self.leave_selected, "Leaves every selected group (asks first). Groups you own are skipped.")
        self.b_leave.setProperty("danger", True)
        row.addWidget(self.b_leave)
        ll.addLayout(row)
        row = FlowLayout()
        row.addWidget(button("Refresh", self.load_groups))
        row.addWidget(button("Open another group...", self.open_other, "Look at any group by id or link"))
        ll.addLayout(row)
        split.addWidget(left)

        # ---- right: details
        self.tabs = QTabWidget()
        self.tabs.setProperty("sub", True)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 3)
        split.setSizes([560, 680])
        self._build_overview()
        self._build_members()
        self._build_requests()
        self._build_roles()
        self._build_audit()
        self._build_bans()
        self.set_enabled(False)
        ctx.signed_in.connect(self.load_groups)
        ctx.signed_out.connect(self.clear)

    # ============================================================ layout of the sub-tabs
    def _build_overview(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.title = QLabel("Select a group")
        self.title.setProperty("role", "title")
        lay.addWidget(self.title)
        self.facts = QLabel("")
        self.facts.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.facts)
        self.desc = QPlainTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setMaximumHeight(140)
        lay.addWidget(QLabel("Description:"))
        lay.addWidget(self.desc)
        self.perms = QLabel("")
        self.perms.setWordWrap(True)
        lay.addWidget(QLabel("What you can do here:"))
        lay.addWidget(self.perms)
        row = QHBoxLayout()
        self.b_desc = button("Edit description...", self.edit_description)
        self.b_shout = button("Set shout...", self.set_status)
        self.b_open = button("Open on roblox.com", lambda: self.gid and open_url(f"https://www.roblox.com/communities/{self.gid}"))
        self.b_copy = button("Copy group id", lambda: self.gid and copy_text(str(self.gid)))
        for b in (self.b_desc, self.b_shout, self.b_open, self.b_copy):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.tabs.addTab(w, "Overview")

    def _build_members(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.role_pick = QComboBox()
        self.role_pick.activated.connect(lambda _: self.load_members(reset=True))
        self.member_filter = QLineEdit()
        self.member_filter.setPlaceholderText("Filter members...")
        self.member_filter.setMinimumWidth(150)
        self.member_filter.textChanged.connect(lambda _=None: (self.show_members(), self._search_timer.start()))
        top.addWidget(QLabel("Role:"))
        top.addWidget(self.role_pick)
        top.addWidget(self.member_filter, 1)
        top.addWidget(button("Find a user...", self.find_member, "Look up one username in this group"))
        lay.addLayout(top)
        self.mtable = make_table(["Display name", "Username", "Role", "Rank", "User id"], [180, 160, 150, 60, 100])
        lay.addWidget(self.mtable, 1)
        row = QHBoxLayout()
        self.b_more_m = button("Load more", lambda: self.load_members(reset=False))
        self.b_rank = button("Change rank...", self.change_rank)
        self.b_kick = button("Remove from group", self.kick)
        self.b_ban = button("Ban", self.ban)
        self.b_profile = button("Open profile", lambda: self._open_profile(self.mtable, 4))
        for b in (self.b_more_m, self.b_profile, self.b_rank, self.b_kick, self.b_ban):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.mcount = hint("")
        lay.addWidget(self.mcount)
        self.tabs.addTab(w, "Members")

    def _build_requests(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.rtable = make_table(["Display name", "Username", "Requested", "User id"], [180, 160, 150, 100])
        self.rtable.setSelectionMode(self.rtable.SelectionMode.ExtendedSelection)
        lay.addWidget(self.rtable, 1)
        row = QHBoxLayout()
        self.b_more_r = button("Load more", lambda: self.load_requests(reset=False))
        self.b_accept = button("Accept selected", lambda: self.answer(True))
        self.b_decline = button("Decline selected", lambda: self.answer(False))
        self.b_accept_all = button("Accept all loaded...", lambda: self.answer(True, everyone=True))
        for b in (self.b_more_r, self.b_accept, self.b_decline, self.b_accept_all):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.rcount = hint("")
        lay.addWidget(self.rcount)
        self.tabs.addTab(w, "Join requests")

    def _build_roles(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        self.roletable = make_table(["Rank", "Role", "Members", "Id"], [60, 200, 80, 100])
        self.roletable.itemSelectionChanged.connect(self.show_role_perms)
        left.addWidget(self.roletable, 1)
        lay.addLayout(left, 2)
        right = QVBoxLayout()
        right.addWidget(QLabel("Permissions of the selected role:"))
        self.roleperms = QPlainTextEdit()
        self.roleperms.setReadOnly(True)
        right.addWidget(self.roleperms, 1)
        lay.addLayout(right, 2)
        self.tabs.addTab(w, "Roles")

    def _build_audit(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.audit_filter = QComboBox()
        self.audit_filter.addItem("All actions")
        self.audit_filter.activated.connect(lambda _: self.show_audit())
        top.addWidget(QLabel("Show:"))
        top.addWidget(self.audit_filter)
        top.addStretch()
        lay.addLayout(top)
        self.atable = make_table(["Time", "Who", "Action", "Details"], [140, 150, 170, 400])
        lay.addWidget(self.atable, 1)
        row = QHBoxLayout()
        self.b_more_a = button("Load more", lambda: self.load_audit(reset=False))
        row.addWidget(self.b_more_a)
        row.addStretch()
        lay.addLayout(row)
        self.acount = hint("")
        lay.addWidget(self.acount)
        self.tabs.addTab(w, "Audit log")

    def _build_bans(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.btable = make_table(["Display name", "Username", "Banned", "User id"], [180, 160, 150, 100])
        lay.addWidget(self.btable, 1)
        row = QHBoxLayout()
        self.b_unban = button("Unban selected", self.unban)
        row.addWidget(button("Refresh", self.load_bans))
        row.addWidget(self.b_unban)
        row.addStretch()
        lay.addLayout(row)
        self.tabs.addTab(w, "Bans")

    # ============================================================ state
    def set_enabled(self, on):
        self.tabs.setEnabled(on)

    def clear(self):
        fill_table(self.glist, [])
        self.clear_details()

    def clear_details(self):
        """Empty the right-hand side (overview, members, roles ...) so it no longer shows a group."""
        self.gid = None
        self.membership, self.roles = {}, []
        for key in ("members", "requests", "audit"):
            self._gen[key] = self._gen.get(key, 0) + 1
            self._busy[key] = False
        self.search_hits, self._search_gen = [], self._search_gen + 1
        for t in (self.mtable, self.rtable, self.roletable, self.atable, self.btable):
            fill_table(t, [])
        self.title.setText("Select a group")
        self.facts.setText("")
        self.desc.setPlainText("")
        self.apply_permissions()               # no group: nothing that needs a permission is shown
        self.perms.setText("")
        self.role_pick.clear()
        self.set_enabled(False)

    def can(self, section, key):
        return perm(self.membership.get("permissions"), section, key)

    def my_rank(self):
        """Your rank in this group (0 to 255; the owner has 255). Unknown counts as 0, so nothing that needs a rank is allowed."""
        try:
            return int(((self.membership.get("userRole") or {}).get("role") or {}).get("rank") or 0)
        except (TypeError, ValueError):
            return 0

    def assignable_roles(self):
        """The roles you may give: only those BELOW your own rank (and never Guest). You cannot give a role as high as yours or higher."""
        mine = self.my_rank()
        return [r for r in self.roles if 0 < r["rank"] < mine]

    def may_manage(self, m):
        """You may change, remove or ban a member only if their rank is below yours."""
        return int(m.get("rank") or 0) < self.my_rank()

    def _deny(self, text):
        self.ctx.status(text)
        QMessageBox.information(self, "Not allowed", text)
        return False

    def _allowed(self, ok, what):
        """The permission is checked again at the moment of the action (what is shown is only a convenience)."""
        return True if ok else self._deny(f"You do not have permission to {what} in this group.")

    def _may_act_on(self, m, what):
        if self.may_manage(m):
            return True
        return self._deny(f"You cannot {what} {m['username'] or m['id']}: their role ({m['role']}) is the same as yours or higher.")

    def apply_permissions(self):
        """Show only what this person may do in this group: a button or a page they have no permission for is not there at all (not just greyed out)."""
        can_rank = self.can("groupMembershipPermissions", "changeRank")
        can_remove = self.can("groupMembershipPermissions", "removeMembers")
        can_invite = self.can("groupMembershipPermissions", "inviteMembers")
        can_audit = self.can("groupManagementPermissions", "viewAuditLogs")
        can_shout = self.can("groupPostsPermissions", "postToStatus")
        can_conf = bool(self.membership.get("canConfigure"))
        for b, ok in ((self.b_rank, can_rank), (self.b_kick, can_remove), (self.b_ban, can_remove), (self.b_accept, can_invite),
                      (self.b_decline, can_invite), (self.b_accept_all, can_invite), (self.b_shout, can_shout),
                      (self.b_desc, can_conf), (self.b_unban, can_remove)):
            b.setVisible(ok)
            b.setEnabled(ok)
        # the pages: Overview (0) and Members (1) are for everybody; the rest only for who may use them
        for index, ok in ((2, can_invite or can_remove), (3, can_conf or can_rank), (4, can_audit), (5, can_remove)):
            self.tabs.setTabVisible(index, ok)
        if not self.tabs.isTabVisible(self.tabs.currentIndex()):
            self.tabs.setCurrentIndex(0)
        names = [("change ranks", can_rank), ("remove members", can_remove), ("accept join requests", can_invite),
                 ("view the audit log", can_audit), ("post the shout", can_shout), ("edit group settings", can_conf)]
        yes = [n for n, ok in names if ok]
        self.perms.setText("You can: " + (", ".join(yes) if yes else "only look (no management permissions)") + ".")

    # ============================================================ groups list
    def load_groups(self):
        c = self.ctx
        if not c.logged_in:
            return
        c.status("Loading your groups...")
        c.async_.run(c.client.my_groups, self._groups)

    def _groups(self, data):
        self.group_rows = data
        self.ctx.set_count("groups", len(data))
        self._show_groups()
        self.ctx.status(f"{len(data)} groups.")
        self._load_created()

    def _show_groups(self):
        q = self.gfilter.text().strip().lower()
        data = [g for g in getattr(self, "group_rows", []) if not q or q in g["group"]["name"].lower()]
        rows = [[g["group"]["name"], g["role"]["name"], g["role"]["rank"], g["group"].get("memberCount", 0),
                 (self.created.get(g["group"]["id"]) or "")[:10]] for g in data]
        fill_table(self.glist, rows, keys=[g["group"]["id"] for g in data])

    def _load_created(self):
        """Fetch every group's creation date (one request per 100 groups) and show it in the Created column."""
        ids = [g["group"]["id"] for g in getattr(self, "group_rows", []) if g["group"]["id"] not in self.created]
        if not ids:
            return

        def got(res):
            self.created.update(res)
            self._show_groups()
        self.ctx.async_.run(lambda: self.ctx.client.groups_created(ids), got, lambda e: None)

    def select_by_date(self):
        a, b = self.date_from.date().toPython(), self.date_to.date().toPython()
        if a > b:
            a, b = b, a
        if not self.created:
            self.ctx.status("The creation dates are still loading; try again in a moment.")
            return
        self.select_groups_where(lambda g: day_in_range(self.created.get(g["group"]["id"]), a, b))
        n = len(self._group_sels())
        self.ctx.status(f"{n} group(s) were created between {a} and {b}." if n else f"No shown group was created between {a} and {b}.")

    # ---- picking and leaving several groups
    def _group_sels(self):
        ids = {row_key(self.glist, r) for r in selected_rows(self.glist)}
        return [g for g in getattr(self, "group_rows", []) if g["group"]["id"] in ids]

    def select_groups_where(self, test):
        self.glist.clearSelection()
        sm = self.glist.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        by_id = {g["group"]["id"]: g for g in getattr(self, "group_rows", [])}
        for i in range(self.glist.rowCount()):
            g = by_id.get(row_key(self.glist, i))
            if g and test(g):
                sm.select(self.glist.model().index(i, 0), flags)
        self.ctx.status(f"{len(self._group_sels())} group(s) selected.")

    def invert_group_selection(self):
        have = {g["group"]["id"] for g in self._group_sels()}
        self.select_groups_where(lambda g: g["group"]["id"] not in have)

    def _owned(self, g):
        me = self.ctx.me["id"] if self.ctx.me else None
        return g["role"].get("rank") == 255 or (g["group"].get("owner") or {}).get("userId") == me

    def leave_selected(self):
        c = self.ctx
        if c.need_login() or self.bulk.running:
            return
        sel = self._group_sels()
        owned = [g for g in sel if self._owned(g)]
        todo = [g for g in sel if not self._owned(g)]
        if not sel:
            c.status("Select the groups to leave first (Ctrl or Shift click, or use the Select buttons).")
            return
        if not todo:
            QMessageBox.information(self, "Cannot leave", "You own every selected group, and Roblox does not let an owner leave. "
                                    "Hand the group to someone else first.")
            return
        n = len(todo)
        names = "\n".join(f"  {g['group']['name']}  (your role: {g['role']['name']})" for g in todo[:15]) + ("\n  ..." if n > 15 else "")
        extra = f"\n\n{len(owned)} selected group(s) are owned by you and will be skipped." if owned else ""
        if not c.confirm("Leave groups", f"Leave {n} group(s)?\n\n{names}{extra}\n\nSome groups need approval to rejoin, and some cost "
                         "Robux or have no way back at all. Your roles and rank in them are lost.\nA list of the groups you left is saved on this PC.", danger=True):
            return
        if n >= settings.typed_from():
            typed, ok = QInputDialog.getText(self, "Please confirm", f"You are about to leave {n} groups.\nType the number {n} to confirm:")
            if not ok or typed.strip() != str(n):
                c.status("Cancelled: the number did not match, no group was left.")
                return
        self.b_leave.setEnabled(False)
        self.bulk.start("Leaving groups", n)
        client = c.client

        def work():
            left, failed, t0 = [], [], time.time()
            for k, g in enumerate(todo):
                if self.bulk.stop_flag:
                    failed.append(f"- stopped by you: {n - k} group(s) were not tried")
                    break
                self.bulk.report("Leaving groups", k, n, t0)
                gr = g["group"]
                try:
                    client.leave_group(gr["id"])
                    left.append(g)
                    self._remember_left(g)
                except rbx.Cancelled:
                    failed.append(f"- stopped by you: {n - k} group(s) were not tried")
                    break
                except rbx.RobloxError as e:
                    failed.append(f"- {gr['name']} (id {gr['id']}, your role {g['role']['name']}): {rbx.redact(e)}")
                    if e.status == 429:
                        failed.append(f"- stopped: Roblox is rate-limiting; {n - k - 1} group(s) were not tried. Wait a few minutes and try again.")
                        break
                except Exception as e:          # noqa: BLE001 - reported below
                    failed.append(f"- {gr['name']} (id {gr['id']}): {rbx.redact(e)}")
            return left, failed
        c.async_.run(work, lambda res: self._left(n, *res), lambda e: (self._left(n, [], [str(e)]), c.error(e)))

    def _remember_left(self, g):
        try:
            with open(rbx.STATE_DIR / "left-groups.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\t{g['group']['id']}\t{g['group']['name']}\t{g['role']['name']}\n")
        except OSError:
            pass

    def _left(self, n, left, failed):
        self.bulk.finish()
        self.b_leave.setEnabled(True)
        gone = {g["group"]["id"] for g in left}
        self.group_rows = [g for g in getattr(self, "group_rows", []) if g["group"]["id"] not in gone]
        self.ctx.set_count("groups", len(self.group_rows))
        if self.gid in gone:
            self.clear_details()            # do not keep showing a group you are no longer in
        self._show_groups()
        msg = f"{len(left)} of {n} group(s) left."
        if self.bulk.run_rate_hits:
            msg += f" Roblox rate-limited {self.bulk.run_rate_hits} request(s) during this (the app waited and retried)."
        self.ctx.status(msg, 15000)
        if failed:
            QMessageBox.warning(self, "Leave groups", msg + "\n\nThese did not work:\n" + "\n".join(failed[:20]))
        elif left:
            QMessageBox.information(self, "Leave groups", msg + f"\nThe list of groups you left is in {rbx.STATE_DIR / 'left-groups.txt'}")

    def open_other(self):
        text, ok = QInputDialog.getText(self, "Open a group", "Group id or link:")
        gid = parse_id(text) if ok else None
        if gid:
            self.select(gid)

    def pick_group(self):
        rows = selected_rows(self.glist)
        if len(rows) == 1:
            gid = row_key(self.glist, rows[0])
            if gid and gid != self.gid:
                self.select(gid)

    def select(self, gid):
        c = self.ctx
        self.gid = int(gid)
        self.title.setText("Loading...")
        client = c.client

        def work():
            info = client.get(f"https://groups.roblox.com/v1/groups/{gid}", auth=False)
            membership = client.group_membership(gid) if c.logged_in else {}
            roles = client.group_roles(gid)
            return info, membership, roles
        c.async_.run(work, lambda r: self._group_loaded(gid, *r))

    def _group_loaded(self, gid, info, membership, roles):
        if gid != self.gid:
            return
        self.membership, self.roles = membership or {}, sorted(roles, key=lambda r: r["rank"])
        self.title.setText(info["name"])
        owner = (info.get("owner") or {}).get("username", "?")
        sh = (info.get("shout") or {}).get("body") or "(none)"
        me = ((self.membership.get("userRole") or {}).get("role") or {})
        self.facts.setText(f"Id {gid}  |  {info.get('memberCount', 0):,} members  |  owner {owner}  |  your role: "
                           f"{me.get('name', 'not a member')} (rank {me.get('rank', '-')})\nShout: {sh}")
        self.desc.setPlainText(info.get("description") or "")
        self.set_enabled(True)
        self.apply_permissions()
        self.role_pick.clear()
        self.role_pick.addItem("All members", None)
        for r in self.roles:
            self.role_pick.addItem(f"{r['name']} ({r.get('memberCount', 0)})", r["id"])
        fill_table(self.roletable, [[r["rank"], r["name"], r.get("memberCount", 0), r["id"]] for r in self.roles], keys=[r["id"] for r in self.roles])
        self.load_members(reset=True)
        self.load_requests(reset=True)
        self.load_audit(reset=True)
        self.load_bans()

    def _resolve(self, rows, redraw):
        """Roblox sometimes leaves names out of a list; look the missing ones up by id and redraw."""
        missing = list(dict.fromkeys(r["id"] for r in rows if r.get("id") and not r.get("username")))[:200]
        if not missing:
            return
        c = self.ctx

        def done(users):
            by = {u["id"]: u for u in users}
            for r in rows:
                u = by.get(r["id"])
                if u:
                    r["username"], r["display"] = u["name"], u.get("displayName") or u["name"]
            redraw()
        c.async_.run(lambda: c.client.lookup_names(missing), done, lambda e: None)

    # ============================================================ members
    # ---- paged lists: one page at a time, never the same page twice
    def _begin(self, key, reset):
        """Start loading a page of a list. Returns this load's number, or None if a page of this list is already on its way: pressing 'Load more' again
        meanwhile would ask Roblox for the same page (the cursor has not moved yet) and everybody on it would be listed twice. A reset (other group or
        role) starts a new load and the answers of the old one are thrown away."""
        if reset:
            self._gen[key] = self._gen.get(key, 0) + 1
        elif self._busy.get(key):
            return None
        self._busy[key] = True
        return self._gen.get(key, 0)

    def _current(self, key, gen):
        """True if the answer belongs to the load that is current (and then the list may take another page)."""
        if gen != self._gen.get(key, 0):
            return False
        self._busy[key] = False
        return True

    def _failed(self, key, gen, label, e):
        if self._current(key, gen):
            label.setText("Could not load: " + str(e))

    def load_members(self, reset=True):
        c = self.ctx
        gid = self.gid
        if not gid:
            return
        gen = self._begin("members", reset)
        if gen is None:
            return
        if reset:
            self.members, self.members_cursor = [], None
            self.search_hits = []
        self.b_more_m.setEnabled(False)                  # (until this page is here)
        role_id = self.role_pick.currentData()
        cursor = self.members_cursor
        c.async_.run(lambda: c.client.group_members(gid, role_id, cursor), lambda d: self._members(gid, role_id, gen, d),
                     lambda e: (self._failed("members", gen, self.mcount, e), self.b_more_m.setEnabled(bool(self.members_cursor))))

    def _member_row(self, m, role_by_id, role_id=None):
        u = m.get("user") or m
        role = m.get("role") or role_by_id.get(role_id) or {}
        return {"id": u.get("userId") or u.get("id"), "username": u.get("username") or u.get("name", ""),
                "display": u.get("displayName") or u.get("username", ""), "role": role.get("name", ""),
                "role_id": role.get("id"), "rank": role.get("rank", 0)}

    def _members(self, gid, role_id, gen, d):
        if gid != self.gid or not self._current("members", gen):
            return
        role_by_id = {r["id"]: r for r in self.roles}
        have = {m["id"] for m in self.members}
        for m in d.get("data", []):
            row = self._member_row(m, role_by_id, role_id)
            if row["id"] not in have:                          # (never the same person twice)
                have.add(row["id"])
                self.members.append(row)
        self.members_cursor = d.get("nextPageCursor")
        self.b_more_m.setEnabled(bool(self.members_cursor))
        self.show_members()
        self._resolve(self.members, self.show_members)
        if self.member_filter.text().strip():
            self._search_timer.start()                         # a name is typed: search again for people that are not loaded

    # ---- search: also finds members that 'Load more' has not reached
    def search_server(self):
        """Ask Roblox for the members that match what is typed in the filter box (loaded or not) and show them with the loaded ones."""
        q = self.member_filter.text().strip()
        gid = self.gid
        if not gid or len(q) < 2:
            if self.search_hits:
                self.search_hits = []
                self.show_members()
            return
        self._search_gen += 1
        gen, c = self._search_gen, self.ctx

        def work():
            try:
                return c.client.group_search_members(gid, q).get("data", [])
            except rbx.RobloxError:                            # (the search is not available: look the exact username up instead)
                u = c.client.user_by_name(q)
                if not u:
                    return []
                groups = c.client.get(f"https://groups.roblox.com/v1/users/{u['id']}/groups/roles", auth=False).get("data", [])
                g = next((x for x in groups if x["group"]["id"] == gid), None)
                return [{"user": {"userId": u["id"], "username": u["name"], "displayName": u.get("displayName", "")}, "role": g["role"]}] if g else []

        def done(rows):
            if gen != self._search_gen or gid != self.gid or q != self.member_filter.text().strip():
                return                                         # (the box changed meanwhile: this answer is old)
            role_by_id = {r["id"]: r for r in self.roles}
            self.search_hits = [self._member_row(m, role_by_id) for m in rows]
            self.show_members()
            self._resolve(self.search_hits, self.show_members)
        c.async_.run(work, done, lambda e: self.mcount.setText("Search failed: " + str(e)))

    def show_members(self):
        q = self.member_filter.text().strip().lower()
        role_id = self.role_pick.currentData()
        loaded = {m["id"] for m in self.members}
        extra = [m for m in self.search_hits if m["id"] not in loaded and (not role_id or m["role_id"] == role_id)] if q else []
        self.mview = [m for m in self.members if not q or q in m["username"].lower() or q in m["display"].lower()] + extra
        fill_table(self.mtable, [[m["display"] or m["username"] or f"User {m['id']}", m["username"], m["role"], m["rank"], m["id"]] for m in self.mview],
                   keys=[m["id"] for m in self.mview])
        self.mcount.setText(f"{len(self.members)} loaded" + ("  (more available: Load more)" if self.members_cursor else "")
                            + (f"  +  {len(extra)} found by search" if extra else ""))

    def _member_selected(self):
        rows = selected_rows(self.mtable)
        if not rows:
            self.ctx.status("Select a member first.")
            return None
        uid = row_key(self.mtable, rows[0])
        return next((m for m in self.members + self.search_hits if m["id"] == uid), None)

    def _open_profile(self, table, col):
        rows = selected_rows(table)
        if rows:
            open_url(f"https://www.roblox.com/users/{cell(table, rows[0], col)}/profile")

    def find_member(self):
        c = self.ctx
        text, ok = QInputDialog.getText(self, "Find a user", "Username:")
        if not ok or not text.strip():
            return
        gid = self.gid

        def work():
            u = c.client.user_by_name(text.strip())
            if not u:
                return None, None
            groups = c.client.get(f"https://groups.roblox.com/v1/users/{u['id']}/groups/roles", auth=False).get("data", [])
            return u, next((g for g in groups if g["group"]["id"] == gid), None)

        def done(res):
            u, g = res
            if not u:
                c.status("No such user.")
            elif not g:
                c.status(f"{u['name']} is not in this group.")
            else:
                c.status(f"{u['name']} is {g['role']['name']} (rank {g['role']['rank']}) in this group.", 12000)
                self.member_filter.setText(u["name"])
        c.async_.run(work, done)

    def change_rank(self):
        if not self._allowed(self.can("groupMembershipPermissions", "changeRank"), "change ranks"):
            return
        m = self._member_selected()
        if not m or not self._may_act_on(m, "change the rank of"):
            return
        roles = self.assignable_roles()
        if not roles:
            self._deny("There is no role below yours that you could give.")
            return
        names = [f"{r['name']} (rank {r['rank']})" for r in roles]
        pick, ok = QInputDialog.getItem(self, "Change rank", f"New role for {m['username']} (now {m['role']}):", names, 0, False)
        if not ok:
            return
        role = roles[names.index(pick)]
        if role["rank"] >= self.my_rank():                  # (cannot happen: only lower roles are offered)
            self._deny("You cannot give a role as high as yours or higher.")
            return
        if role["id"] == m["role_id"]:
            return
        if not self.ctx.confirm("Change rank", f"Change {m['username']} from {m['role']} to {role['name']}?"):
            return
        c, gid = self.ctx, self.gid
        c.async_.run(lambda: c.client.set_rank(gid, m["id"], role["id"]), lambda _: (c.status(f"{m['username']} is now {role['name']}."), self.load_members(True)))

    def kick(self):
        if not self._allowed(self.can("groupMembershipPermissions", "removeMembers"), "remove members"):
            return
        m = self._member_selected()
        if m and self._may_act_on(m, "remove") and self.ctx.confirm("Remove from group", f"Remove {m['username']} from the group?\n\nThey can join again unless you also ban them.", danger=True):
            c, gid = self.ctx, self.gid
            c.async_.run(lambda: c.client.kick(gid, m["id"]), lambda _: (c.status(f"Removed {m['username']}."), self.load_members(True)))

    def ban(self):
        if not self._allowed(self.can("groupMembershipPermissions", "removeMembers"), "ban members"):
            return
        m = self._member_selected()
        if m and self._may_act_on(m, "ban") and self.ctx.confirm("Ban from group", f"Ban {m['username']}? They are removed and cannot rejoin until you unban them.", danger=True):
            c, gid = self.ctx, self.gid
            c.async_.run(lambda: c.client.ban(gid, m["id"]), lambda _: (c.status(f"Banned {m['username']}."), self.load_members(True), self.load_bans()))

    # ============================================================ join requests
    def load_requests(self, reset=True):
        c, gid = self.ctx, self.gid
        if not gid or not (self.can("groupMembershipPermissions", "inviteMembers") or self.can("groupMembershipPermissions", "removeMembers")):
            fill_table(self.rtable, [])
            return
        gen = self._begin("requests", reset)
        if gen is None:
            return
        if reset:
            self.requests, self.requests_cursor = [], None
        self.b_more_r.setEnabled(False)
        cursor = self.requests_cursor
        c.async_.run(lambda: c.client.group_join_requests(gid, cursor), lambda d: self._requests(gid, gen, d),
                     lambda e: (self._failed("requests", gen, self.rcount, e), self.b_more_r.setEnabled(bool(self.requests_cursor))))

    def _requests(self, gid, gen, d):
        if gid != self.gid or not self._current("requests", gen):
            return
        have = {r["id"] for r in self.requests}
        for r in d.get("data", []):
            u = r.get("requester") or {}
            if u.get("userId") in have:
                continue
            have.add(u.get("userId"))
            self.requests.append({"id": u.get("userId"), "username": u.get("username", ""), "display": u.get("displayName", ""), "created": r.get("created")})
        self.requests_cursor = d.get("nextPageCursor")
        self.b_more_r.setEnabled(bool(self.requests_cursor))
        self.show_requests()
        self._resolve(self.requests, self.show_requests)
        self.rcount.setText(f"{len(self.requests)} pending request(s) loaded" + ("  (more available)" if self.requests_cursor else ""))

    def show_requests(self):
        fill_table(self.rtable, [[r["display"] or r["username"] or f"User {r['id']}", r["username"], when(r["created"]), r["id"]] for r in self.requests],
                   keys=[r["id"] for r in self.requests])

    def answer(self, accept, everyone=False):
        if not self._allowed(self.can("groupMembershipPermissions", "inviteMembers"), "accept or decline join requests"):
            return
        if everyone:
            rows = list(range(self.rtable.rowCount()))
        else:
            rows = selected_rows(self.rtable)
        ids = [int(row_key(self.rtable, r)) for r in rows]
        if not ids:
            self.ctx.status("Select one or more requests first.")
            return
        verb = "Accept" if accept else "Decline"
        if not self.ctx.confirm(f"{verb} requests", f"{verb} {len(ids)} join request(s)?", danger=not accept):
            return
        c, gid = self.ctx, self.gid
        fn = c.client.accept_join_requests if accept else c.client.decline_join_requests
        c.async_.run(lambda: fn(gid, ids), lambda _: (c.status(f"{verb}ed {len(ids)} request(s)." if accept else f"Declined {len(ids)} request(s)."),
                                                       self.load_requests(True), self.load_members(True)))

    # ============================================================ roles
    def show_role_perms(self):
        rows = selected_rows(self.roletable)
        if not rows or not self.gid:
            return
        rid, gid, c = int(row_key(self.roletable, rows[0])), self.gid, self.ctx

        def done(d):
            lines = []
            for section, vals in (d.get("permissions") or {}).items():
                on = [k for k, v in vals.items() if v]
                lines.append(f"{section}:\n   " + (", ".join(on) if on else "(none)"))
            self.roleperms.setPlainText("\n".join(lines) or json.dumps(d, indent=1))
        c.async_.run(lambda: c.client.get(f"https://groups.roblox.com/v1/groups/{gid}/roles/{rid}/permissions"), done,
                     lambda e: self.roleperms.setPlainText("Not available: " + str(e)))

    # ============================================================ audit log
    def load_audit(self, reset=True):
        c, gid = self.ctx, self.gid
        if not gid or not self.can("groupManagementPermissions", "viewAuditLogs"):
            fill_table(self.atable, [])
            return
        gen = self._begin("audit", reset)
        if gen is None:
            return
        if reset:
            self.audit, self.audit_cursor = [], None
        self.b_more_a.setEnabled(False)
        cursor = self.audit_cursor
        c.async_.run(lambda: c.client.audit_log(gid, cursor), lambda d: self._audit(gid, gen, d),
                     lambda e: (self._failed("audit", gen, self.acount, e), self.b_more_a.setEnabled(bool(self.audit_cursor))))

    def _audit(self, gid, gen, d):
        if gid != self.gid or not self._current("audit", gen):
            return
        seen = {(a["time"], a["who"], a["action"], a["detail"]) for a in self.audit}
        for e in d.get("data", []):
            actor = ((e.get("actor") or {}).get("user") or {}).get("username", "")
            desc = e.get("description") or {}
            detail = ", ".join(f"{k}: {v}" for k, v in desc.items() if v not in (None, "", 0)) if isinstance(desc, dict) else str(desc)
            entry = {"time": e.get("created"), "who": actor, "action": e.get("actionType", ""), "detail": detail}
            key = (entry["time"], entry["who"], entry["action"], entry["detail"])
            if key in seen:                                    # (never the same entry twice)
                continue
            seen.add(key)
            self.audit.append(entry)
        self.audit_cursor = d.get("nextPageCursor")
        self.b_more_a.setEnabled(bool(self.audit_cursor))
        kinds = sorted({a["action"] for a in self.audit})
        cur = self.audit_filter.currentText()
        self.audit_filter.clear()
        self.audit_filter.addItems(["All actions"] + kinds)
        self.audit_filter.setCurrentText(cur if cur in kinds else "All actions")
        self.show_audit()

    def show_audit(self):
        f = self.audit_filter.currentText()
        rows = [a for a in self.audit if f == "All actions" or a["action"] == f]
        fill_table(self.atable, [[when(a["time"]), a["who"], a["action"], a["detail"]] for a in rows])
        self.acount.setText(f"{len(rows)} shown, {len(self.audit)} loaded" + ("  (more available)" if self.audit_cursor else ""))

    # ============================================================ bans
    def load_bans(self):
        c, gid = self.ctx, self.gid
        if not gid or not self.can("groupMembershipPermissions", "removeMembers"):
            fill_table(self.btable, [])
            return

        def done(d):
            if gid != self.gid:
                return
            self.bans = [{"id": (b.get("user") or {}).get("userId"), "username": (b.get("user") or {}).get("username", ""),
                          "display": (b.get("user") or {}).get("displayName", ""), "created": b.get("created")} for b in d.get("data", [])]
            self.show_bans()
            self._resolve(self.bans, self.show_bans)
        c.async_.run(lambda: c.client.get(f"https://groups.roblox.com/v1/groups/{gid}/bans", {"limit": 100}), done, lambda e: None)

    def show_bans(self):
        fill_table(self.btable, [[b["display"] or b["username"] or f"User {b['id']}", b["username"], when(b["created"]), b["id"]] for b in self.bans],
                   keys=[b["id"] for b in self.bans])

    def unban(self):
        if not self._allowed(self.can("groupMembershipPermissions", "removeMembers"), "unban members"):
            return
        rows = selected_rows(self.btable)
        if not rows:
            return
        uid = int(row_key(self.btable, rows[0]))
        name = next((b["username"] or str(uid) for b in self.bans if b["id"] == uid), str(uid))
        if self.ctx.confirm("Unban", f"Unban {name}?"):
            c, gid = self.ctx, self.gid
            c.async_.run(lambda: c.client.delete(f"https://groups.roblox.com/v1/groups/{gid}/bans/{uid}"), lambda _: (c.status(f"Unbanned {name}."), self.load_bans()))

    # ============================================================ overview actions
    def edit_description(self):
        if not self._allowed(bool(self.membership.get("canConfigure")), "edit the group settings"):
            return
        text, ok = QInputDialog.getMultiLineText(self, "Group description", "New description:", self.desc.toPlainText())
        if ok and self.ctx.confirm("Change description", "Replace the group's description?"):
            c, gid = self.ctx, self.gid
            c.async_.run(lambda: c.client.set_group_description(gid, text), lambda _: (c.status("Description updated."), self.desc.setPlainText(text)))

    def set_status(self):
        if not self._allowed(self.can("groupPostsPermissions", "postToStatus"), "post the shout"):
            return
        text, ok = QInputDialog.getText(self, "Group shout", "Shout (leave empty to clear it):")
        if ok and self.ctx.confirm("Post shout", "Post this shout to the group?\n\n" + (text or "(clear the shout)")):
            c, gid = self.ctx, self.gid
            c.async_.run(lambda: c.client.set_group_status(gid, text), lambda _: c.status("Shout posted."))
