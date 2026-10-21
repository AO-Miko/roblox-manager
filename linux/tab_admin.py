"""Admin tab: only for accounts that have a role in the signed role list (see roles.py). Ban and unban Roblox user ids, with a reason,
under the hierarchy owner > admin: nobody bans themselves or someone of the same or a higher role."""
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

import adminops
import bans
import roles
from ui_common import button, fill_table, hint, make_table, row_key, selected_rows


class AdminTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        self.who = QLabel("")
        self.who.setProperty("role", "title")
        lay.addWidget(self.who)
        self.setup = QLabel("")
        self.setup.setWordWrap(True)
        self.setup.setProperty("role", "notice")
        lay.addWidget(self.setup)
        row = QHBoxLayout()
        self.b_repo = button("Choose repository folder...", self.choose_repo, "The folder with tools/ban.sh (your checkout, on the release branch)")
        row.addWidget(self.b_repo)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(QLabel("<b>Ban someone</b>"))
        form = QHBoxLayout()
        self.target = QLineEdit()
        self.target.setPlaceholderText("User id or username")
        self.target.setMinimumWidth(150)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (shown to them)")
        self.reason.setMaxLength(200)
        self.reason.setMinimumWidth(150)
        self.b_ban = button("Ban", self.ban, "Signs them out and removes them from every PC and phone within about ten minutes", danger=True)
        form.addWidget(self.target, 1)
        form.addWidget(self.reason, 2)
        form.addWidget(self.b_ban)
        lay.addLayout(form)
        self.msg = hint("")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)

        lay.addWidget(QLabel("<b>Banned</b>"))
        self.table = make_table(["User id", "Reason", "Since", "By", "Role"], [120, 300, 100, 120, 80], empty="Nobody is banned.")
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_unban = button("Unban selected", self.unban, "Lets them back in")
        row.addWidget(self.b_unban)
        row.addWidget(button("Refresh", self.refresh))
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(QLabel("<b>Roles</b>"))
        self.roles_table = make_table(["User id", "Role"], [160, 120], empty="No roles.")
        self.roles_table.setMaximumHeight(130)
        lay.addWidget(self.roles_table)
        lay.addWidget(hint("Roles are in dist/roles.json (signed). Change them with tools/roles.sh on the PC that has the release key."))
        self.refresh()

    # ---- who is looking
    def my_id(self):
        return (self.ctx.me or {}).get("id")

    def my_rank(self):
        return roles.rank_of(self.my_id()) if self.my_id() else 0

    def allowed(self):
        return self.my_rank() >= 1

    def refresh(self):
        rank = self.my_rank()
        role = roles.NAMES.get(rank)
        me = self.ctx.me or {}
        self.who.setText(f"{role.capitalize()}: {me.get('displayName') or me.get('name')} ({me.get('id')})" if role else "Admin")
        probs = adminops.problems()
        self.setup.setVisible(bool(probs))
        self.setup.setText("Publishing is not ready on this PC:\n- " + "\n- ".join(probs) if probs else "")
        for b in (self.b_ban, self.b_unban):
            b.setEnabled(not probs and rank >= 1)
        entries = adminops.read_bans() if not probs else self._cached_entries()
        names = {1: "admin", 2: "owner"}
        fill_table(self.table, [[e["id"], e.get("reason", ""), e.get("since", ""), e.get("by") or "owner", names.get(int(e.get("rank", 2)), "")] for e in entries],
                   keys=[e["id"] for e in entries])
        rows = sorted(roles.load()[1].items(), key=lambda kv: (-roles.RANKS[kv[1]], kv[0]))
        fill_table(self.roles_table, [[k, v] for k, v in rows])

    def _cached_entries(self):
        return bans.entries()

    def choose_repo(self):
        folder = QFileDialog.getExistingDirectory(self, "Your Roblox Manager repository")
        if folder:
            adminops.save_repo(folder)
            self.refresh()

    # ---- actions
    def _say(self, text, bad=False):
        self.msg.setText(text)
        self.msg.setProperty("role", "warn" if bad else "hint")
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)

    def _resolve(self, text):
        """(id, name) from a number or a username."""
        text = text.strip().lstrip("@")
        if text.isdigit():
            return int(text), None
        u = self.ctx.client.user_by_name(text)
        if not u:
            raise ValueError(f"No Roblox user is called '{text}'.")
        return int(u["id"]), u["name"]

    def ban(self):
        text, why = self.target.text().strip(), self.reason.text().strip()
        if not text:
            self._say("Type a user id or a username.", True)
            return
        actor = self.my_id()

        def work():
            uid, name = self._resolve(text)
            ok, note = roles.may_ban(self.my_rank(), actor, uid, roles.rank_of(uid))
            return uid, name, ok, note

        def decided(res):
            uid, name, ok, note = res
            if not ok:
                self._say(note, True)
                return
            label = f"{name} ({uid})" if name else str(uid)
            if not self.ctx.confirm("Ban", f"Ban {label}?\n\nThey are signed out and removed from every PC and phone within about ten minutes.\nReason: {why or '(none)'}", danger=True):
                return
            self._say("Publishing the ban...")
            self.ctx.async_.run(lambda: adminops.ban(uid, why, actor), lambda r: self._done(r, "banned", label), self._failed)

        self.ctx.async_.run(work, decided, self._failed)

    def unban(self):
        rows = selected_rows(self.table)
        if not rows:
            self._say("Select who to unban.", True)
            return
        uid = row_key(self.table, rows[0])
        entry = next((e for e in adminops.read_bans() if e["id"] == uid), {})
        ok, note = roles.may_unban(self.my_rank(), int(entry.get("rank", 2)))
        if int(uid) == int(self.my_id()):
            ok, note = False, "You cannot unban yourself."
        if not ok:
            self._say(note, True)
            return
        if not self.ctx.confirm("Unban", f"Let {uid} back in?"):
            return
        self._say("Publishing...")
        self.ctx.async_.run(lambda: adminops.unban(uid, self.my_id()), lambda r: self._done(r, "unbanned", str(uid)), self._failed)

    def _done(self, result, verb, label):
        ok, text = result
        if ok:
            self._say(f"{label} {verb}. The apps pick it up within about ten minutes.")
            self.target.clear()
            self.reason.clear()
        else:
            self._say(text or "That did not work.", True)
        self.refresh()

    def _failed(self, e):
        self._say(str(e), True)
