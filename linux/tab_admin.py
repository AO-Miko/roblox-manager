"""Admin tab: only for accounts whose role in the signed role list (see roles.py) is admin or higher. Ban and unban Roblox user ids, with a reason,
under the hierarchy owner > co-owner > senior admin > admin: a higher role acts on lower roles and on people without a role; nobody acts on
themselves or on the same or a higher role."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import adminops
import bans
import rbx
import roles
import tab_staff
from ui_common import button, fill_table, hint, make_table, row_key, selected_rows


class BanDialog(QDialog):
    """'Are you sure?': the person's Roblox profile (picture, names, joined, followers, description) and the reason, with Cancel and Yes, ban.
    Cancel is the default button: nothing is banned unless it is answered Yes."""

    def __init__(self, parent, uid, profile, reason):
        super().__init__(parent)
        self.setWindowTitle("Ban this user?")
        self.setMinimumWidth(480)
        info = profile.get("info", {})
        lay = QVBoxLayout(self)
        self.ask = QLabel("<b>Are you sure you want to ban this user?</b>")
        self.ask.setProperty("role", "title")
        lay.addWidget(self.ask)
        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        top = QHBoxLayout()
        self.pic = QLabel()
        self.pic.setFixedSize(96, 96)
        self.pic.setPixmap(tab_staff.round_icon(profile.get("avatar"), 96))
        top.addWidget(self.pic)
        names = QVBoxLayout()
        self.display = QLabel(info.get("displayName") or info.get("name") or f"User {uid}")
        self.display.setProperty("role", "title")
        self.display.setWordWrap(True)
        self.user = hint(f"@{info['name']}" if info.get("name") else "")
        names.addWidget(self.display)
        names.addWidget(self.user)
        names.addStretch()
        top.addLayout(names, 1)
        cl.addLayout(top)
        self.facts = QLabel(tab_staff.facts_html(uid, info, profile.get("counts")))
        self.facts.setTextFormat(Qt.TextFormat.RichText)
        self.facts.setWordWrap(True)
        self.facts.setMinimumHeight(165)            # (a rich-text table is measured a little short: five rows, nothing may be cut)
        cl.addWidget(self.facts)
        cl.addWidget(QLabel("<b>Description</b>"))
        self.about = QPlainTextEdit()
        self.about.setReadOnly(True)
        self.about.setPlainText(info.get("description") or "")
        self.about.setPlaceholderText("No description.")
        self.about.setMaximumHeight(100)
        cl.addWidget(self.about)
        lay.addWidget(card)
        self.reason = QLabel(f"<b>Reason:</b> {reason}")
        self.reason.setWordWrap(True)
        self.reason.setProperty("role", "notice")
        lay.addWidget(self.reason)
        self.warn = hint("They are signed out and removed from every PC and phone within about ten minutes.")
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        row.addStretch()
        self.b_no = button("Cancel", self.reject)
        self.b_yes = button("Yes, ban", self.accept, danger=True)
        self.b_no.setDefault(True)
        row.addWidget(self.b_no)
        row.addWidget(self.b_yes)
        lay.addLayout(row)


class UnbanDialog(BanDialog):
    """The same question the other way round: the profile, what the ban says (when, by whom, why), and your note; only Yes, unban lets them back in."""

    def __init__(self, parent, uid, profile, entry, note=""):
        super().__init__(parent, uid, profile, note)
        self.setWindowTitle("Unban this user?")
        self.ask.setText("<b>Are you sure you want to unban this user?</b>")
        by = entry.get("by")
        who = f"{roles.label(int(entry.get('rank', 5))).lower()} {by}" if by else "the owner"
        since = entry.get("since") or "an unknown date"
        why = entry.get("reason") or "(no reason was given)"
        self.reason.setText(f"<b>Banned</b> on {since} by {who}.<br><b>Ban reason:</b> {why}" + (f"<br><b>Your note:</b> {note}" if note else ""))
        self.warn.setText("They can sign in again within about ten minutes.")
        self.b_yes.setText("Yes, unban")
        self.b_yes.setProperty("danger", False)
        self.b_yes.setProperty("primary", True)
        self.b_yes.style().unpolish(self.b_yes)
        self.b_yes.style().polish(self.b_yes)


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
        self.target.setPlaceholderText("Id or username")
        self.target.setMinimumWidth(240)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason")
        self.reason.setToolTip("Shown to them when they are signed out")
        self.reason.setMaxLength(200)
        self.reason.setMinimumWidth(200)
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
        self.b_unban = button("Unban...", self.unban, "Unban the person selected in the list, or the id or username typed above (the reason box is then an optional note). Shows their profile and asks first.")
        row.addWidget(self.b_unban)
        row.addWidget(button("Refresh", self.refresh))
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(QLabel("<b>Roles</b>"))
        self.roles_table = make_table(["User id", "Role"], [160, 120], empty="No roles.")
        self.roles_table.setMaximumHeight(150)
        lay.addWidget(self.roles_table)
        lay.addWidget(hint("Roles are in dist/roles.json (signed). Change them with tools/roles.sh on the PC that has the release key."))
        self.refresh()

    # ---- who is looking
    def my_id(self):
        return (self.ctx.me or {}).get("id")

    def my_rank(self):
        return roles.rank_of(self.my_id()) if self.my_id() else 0

    def allowed(self):
        return self.my_rank() >= roles.MODERATOR

    def refresh(self):
        rank = self.my_rank()
        me = self.ctx.me or {}
        self.who.setText(f"{roles.label(rank)}: {me.get('displayName') or me.get('name')} ({me.get('id')})" if rank else "Admin")
        probs = adminops.problems()
        self.setup.setVisible(bool(probs))
        self.setup.setText("Publishing is not ready on this PC:\n- " + "\n- ".join(probs) if probs else "")
        for b in (self.b_ban, self.b_unban):
            b.setEnabled(not probs and rank >= roles.MODERATOR)
        entries = self._entries()
        fill_table(self.table, [[e["id"], e.get("reason", ""), e.get("since", ""), e.get("by") or "owner", roles.label(int(e.get("rank", 5)))] for e in entries],
                   keys=[e["id"] for e in entries])
        self.roles_table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)          # keep the hierarchy order, not the id order
        fill_table(self.roles_table, [[uid, roles.LABELS[r]] for uid, r, _ in roles.staff()])

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

    def _entries(self):
        """Every ban in force: from the repository when it is ready, else from the last signed list on this PC."""
        return adminops.read_bans() if not adminops.problems() else bans.entries()

    def confirm_unban(self, uid, profile, entry, note):
        """Show the profile and what the ban says, and ask. True only if the answer is Yes (a separate method so it can be replaced in tests)."""
        return UnbanDialog(self.window(), uid, profile, entry, note).exec() == QDialog.DialogCode.Accepted

    def confirm_ban(self, uid, profile, reason):
        """Show the profile and ask. True only if the answer is Yes (a separate method so it can be replaced in tests)."""
        return BanDialog(self.window(), uid, profile, reason).exec() == QDialog.DialogCode.Accepted

    def ban(self):
        text, why = self.target.text().strip(), self.reason.text().strip()
        if not text:
            self._say("Type a user id or a username.", True)
            return
        if not why:
            self._say("A ban needs a reason: it is shown to the person and kept in the list.", True)
            self.reason.setFocus()
            return
        actor = self.my_id()
        self._say("Looking the user up...")

        def work():
            uid, name = self._resolve(text)
            ok, note = roles.may_ban(self.my_rank(), actor, uid, roles.rank_of(uid))
            if not ok:
                return uid, name, ok, note, None
            try:
                profile = tab_staff.fetch_profile(self.ctx.client, uid)
            except rbx.RobloxError:
                return uid, name, False, f"There is no Roblox user with the id {uid}.", None
            return uid, name, ok, note, profile

        def decided(res):
            uid, name, ok, note, profile = res
            if not ok:
                self._say(note, True)
                return
            info = profile["info"]
            label = f"{info.get('name') or name or ''} ({uid})".strip()
            if not self.confirm_ban(uid, profile, why):
                self._say("Cancelled. Nobody was banned.")
                return
            self._say("Publishing the ban...")
            self.ctx.async_.run(lambda: adminops.ban(uid, why, actor), lambda r: self._done(r, "banned", label), self._failed)

        self.ctx.async_.run(work, decided, self._failed)

    def unban(self):
        """Unban whoever is selected in the list, or the id or username typed in the box (the note is optional). The profile is shown and only Yes unbans."""
        text, note = self.target.text().strip(), self.reason.text().strip()
        rows = selected_rows(self.table)
        if not text and not rows:
            self._say("Select someone in the list, or type an id or username.", True)
            return
        actor = self.my_id()
        picked = None if text else row_key(self.table, rows[0])
        self._say("Looking the user up...")

        def work():
            uid, name = self._resolve(text) if text else (int(picked), None)
            entry = next((e for e in self._entries() if int(e["id"]) == uid), None)
            if entry is None:
                return uid, name, False, f"{name or uid} is not banned.", None, None
            ok, why = roles.may_unban(self.my_rank(), int(entry.get("rank", 5)))
            if uid == int(actor):
                ok, why = False, "You cannot unban yourself."
            if not ok:
                return uid, name, False, why, None, None
            try:
                profile = tab_staff.fetch_profile(self.ctx.client, uid)
            except rbx.RobloxError:
                profile = {"info": {}, "counts": {}, "avatar": b""}            # (the account may be gone from Roblox: it can still be unbanned)
            return uid, name, True, "", profile, entry

        def decided(res):
            uid, name, ok, why, profile, entry = res
            if not ok:
                self._say(why, True)
                return
            info = profile["info"]
            label = f"{info.get('name') or name or ''} ({uid})".strip()
            if not self.confirm_unban(uid, profile, entry, note):
                self._say("Cancelled. Nobody was unbanned.")
                return
            self._say("Publishing...")
            self.ctx.async_.run(lambda: adminops.unban(uid, actor, note), lambda r: self._done(r, "unbanned", label), self._failed)

        self.ctx.async_.run(work, decided, self._failed)

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
