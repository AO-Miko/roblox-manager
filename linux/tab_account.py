"""Home tab (sign in, your account at a glance) and Friends tab (who is online, in which game, and their VIP servers, bulk unfriend)."""
import re
import time
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate, QItemSelectionModel, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QVBoxLayout, QWidget,
)

import accounts
import plat
import rbx
import settings
from signin import SignInDialog
from ui_common import (
    PRESENCE, PRESENCE_COLOUR, button, cell, copy_text, day_in_range, fill_table, hint, make_table, open_url, row_key, selected_rows, when,
)


def pending_rows(items):
    """Table rows for the pending transactions: date, amount, source, item, game, from."""
    rows = []
    for it in items:
        cur = it.get('currency') or {}
        d = it.get('details') if isinstance(it.get('details'), dict) else {}
        place = d.get('place') if isinstance(d.get('place'), dict) else {}
        agent = it.get('agent') or {}
        rows.append([when(it.get('created')), int(cur.get('amount') or 0), rbx.source_label(it), d.get('name') or '', place.get('name') or '',
                     (agent.get('name') or '') + (' (group)' if str(agent.get('type', '')).lower() == 'group' else '')])
    return rows


# ============================================================ cookie dialog
class CookieDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Set your .ROBLOSECURITY cookie")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        warn = QLabel(
            "<b>Your cookie is the key to your account.</b> Anyone who has it can log in as you, <b>skipping your password and 2-step "
            "verification</b>, and take your Robux and items. Roblox staff never ask for it.<br><br>"
            f"This app keeps it encrypted ({plat.WALLET}; if that is not available, in a file only you can read in <code>{plat.CONFIG_TEXT}</code>), sends it <b>only to roblox.com</b>, "
            "and never shows it or writes it to its log. Do not paste it anywhere else, and never share this file.")
        warn.setWordWrap(True)
        warn.setProperty("role", "notice")
        lay.addWidget(warn)
        lay.addWidget(QLabel("Paste the cookie value (it starts with  _|WARNING:-DO-NOT-SHARE-THIS...):"))
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("paste it here; the text stays hidden")
        lay.addWidget(self.edit)
        lay.addWidget(hint("Where to find it: in your browser, open roblox.com while logged in, press F12, go to Application (Chrome/Brave) "
                           "or Storage (Firefox), then Cookies, then roblox.com, and copy the value of .ROBLOSECURITY. "
                           "If you log out of Roblox in that browser, the cookie stops working."))
        row = QHBoxLayout()
        row.addStretch()
        cancel, ok = QPushButton("Cancel"), QPushButton("Save and sign in")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def value(self):
        return self.edit.text()


# ============================================================ account tab
class NotifyLabel(QLabel):
    """A label that tells the page when its text changes (the header tiles copy these values)."""

    def __init__(self, text=""):
        super().__init__(text)
        self.on_change = None

    def setText(self, text):
        super().setText(text)
        if self.on_change:
            self.on_change()


def plain(text):
    """Text without the HTML tags a label may carry."""
    return re.sub(r"<[^>]+>", "", text or "").replace("&nbsp;", " ").strip()


class AccountTab(QWidget):
    IN_TILES = ("Robux", "Friends", "Followers", "Following")      # these numbers are in the header tiles, so the details do not repeat them

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()                       # a short window scrolls instead of squeezing the lists
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setSpacing(12)
        lay.setContentsMargins(14, 14, 14, 10)
        # ---- header card: who you are, and the numbers that matter at a glance
        head = QFrame()
        head.setProperty("card", True)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 14, 18, 14)
        hl.setSpacing(14)
        self.avatar_big = QLabel()
        self.avatar_big.setFixedSize(76, 76)
        hl.addWidget(self.avatar_big)
        who_col = QVBoxLayout()
        who_col.setSpacing(2)
        self.who = QLabel("Not signed in")
        self.who.setProperty("role", "title")
        self.sub = QLabel("Press Sign in... to start")
        self.sub.setProperty("role", "hint")
        who_col.addStretch()
        who_col.addWidget(self.who)
        who_col.addWidget(self.sub)
        who_col.addStretch()
        hl.addLayout(who_col, 1)
        self.tiles = {}
        for key, caption in (("Robux", "Robux"), ("Pending Robux", "Pending"), ("Friends", "Friends"), ("Followers", "Followers"), ("Following", "Following")):
            tile = QFrame()
            tile.setProperty("tile", True)
            tl_ = QVBoxLayout(tile)
            tl_.setContentsMargins(14, 8, 14, 8)
            tl_.setSpacing(0)
            val = QLabel("-")
            val.setProperty("role", "tile-value")
            cap = QLabel(caption)
            cap.setProperty("role", "tile-caption")
            tl_.addWidget(val)
            tl_.addWidget(cap)
            tile.setMinimumWidth(96)
            hl.addWidget(tile)
            self.tiles[key] = val
        lay.addWidget(head)
        self.set_avatar(None)
        # ---- details
        details = QGroupBox("Details")
        dl = QVBoxLayout(details)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(7)
        # KDE's Breeze style keeps form fields at their smallest size, which squeezed the wrapped Pending Robux text into a 100 px column
        # whose second line was cut off. Let the fields use the width that is there.
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {k: NotifyLabel("-") for k in ("User id", "Username", "Display name", "Joined", "Roblox Plus", "Email", "Robux", "Pending Robux", "Groups' pending", "Friends", "Followers", "Following")}
        for k, w in self.fields.items():
            w.on_change = self.update_tiles
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if k in ("Pending Robux", "Groups' pending"):
                w.setWordWrap(True)
                w.setTextFormat(Qt.TextFormat.RichText)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            if k in self.IN_TILES:
                w.setParent(self)                    # (kept, and kept up to date, but shown in the header tiles instead)
                w.hide()
            else:
                self.form.addRow(("Pending (sources)" if k == "Pending Robux" else k) + ":", w)
        self.pending_report = None
        dl.addLayout(self.form)
        lay.addWidget(details)
        row = QHBoxLayout()
        self.btn_set = button("Sign in...", self.set_cookie, "Sign in with your password (and 2-step code), in a browser window, or with a pasted cookie", primary=True)
        self.btn_test = button("Check sign-in", self.check_sign_in, "Ask Roblox who the saved sign-in belongs to and reload the pending Robux")
        self.btn_pending = button("Pending Robux details...", self.pending_details, "Where your pending Robux comes from, sale by sale")
        self.btn_profile = button("Open my profile", self.open_profile)
        self.btn_out = button("Sign out", self.sign_out, "Signs out the account in use and deletes its saved sign-in (other saved accounts stay)", danger=True)
        for b in (self.btn_set, self.btn_test, self.btn_pending, self.btn_profile, self.btn_out):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.safety = hint("")
        lay.addWidget(self.safety)
        title = QLabel("Accounts signed in on this PC")
        title.setProperty("role", "title")
        lay.addWidget(title)
        self.atable = make_table(["Account", "Username", "In use", "Robux"], [220, 180, 90, 110])
        self.atable.setMinimumHeight(150)
        self.atable.setMaximumHeight(210)
        self.atable.setProperty("export_name", "accounts")
        lay.addWidget(self.atable)
        arow = QHBoxLayout()
        self.btn_switch = button("Switch to selected", self.switch_selected, "Use this account everywhere in the app")
        self.btn_add = button("Add another account...", self.set_cookie, "Sign in to a second (third ...) account without signing out of this one")
        self.btn_remove = button("Remove selected", self.remove_selected, "Forget the selected account's sign-in on this PC")
        self.btn_balances = button("Show balances", self.show_balances, "Ask Roblox for each account's Robux")
        for b in (self.btn_switch, self.btn_add, self.btn_remove, self.btn_balances):
            arow.addWidget(b)
        arow.addStretch()
        lay.addLayout(arow)
        self.balances = {}
        self._pending_cache = {}       # user id -> (time, report): switching back to an account does not repeat the 20+ requests
        self._force_pending = False
        self._previous = None
        self.atable.itemSelectionChanged.connect(self.refresh_buttons)
        self.atable.doubleClicked.connect(lambda _=None: self.switch_selected())
        ctx.accounts_changed.connect(self.refresh_accounts)
        lay.addStretch()
        self.refresh_buttons()
        self.refresh_accounts()

    def update_tiles(self):
        """The header shows the same numbers as the details below, in big type."""
        f = self.fields
        for key, val in self.tiles.items():
            t = plain(f[key].text())
            if key == "Pending Robux" and t[:1].isdigit():
                t = t.split(" ")[0]                           # just the amount, not the sources
            val.setText(t or "-")
        bits = []
        if f["Username"].text() not in ("-", ""):
            bits.append("@" + f["Username"].text())
        if f["User id"].text() not in ("-", ""):
            bits.append("id " + f["User id"].text())
        if f["Roblox Plus"].text() == "yes":
            bits.append("Roblox Plus")
        self.sub.setText("  ·  ".join(bits) if bits else "Press Sign in... to start")

    def set_avatar(self, data):
        """Show the round picture in the header (bytes of a PNG), or a plain circle when there is none."""
        size = self.avatar_big.width()
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
            p.setPen(QColor("#6f788a"))
            f = p.font()
            f.setPointSize(26)
            p.setFont(f)
            p.drawText(out.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        p.end()
        self.avatar_big.setPixmap(out)

    def _load_avatar(self, uid):
        client = self.ctx.client
        f = rbx.AVATAR_DIR / f"{int(uid)}-150.png"

        def work():
            try:
                if time.time() - f.stat().st_mtime < rbx.AVATAR_MAX_AGE:
                    return f.read_bytes()
            except OSError:
                pass
            url = client.headshots([uid], size="150x150").get(int(uid))
            data = client.fetch_bytes(url) if url else b""
            if data:
                try:
                    rbx.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(data)
                except OSError:
                    pass
            return data
        self.ctx.async_.run(work, self.set_avatar, lambda e: None)

    def refresh_buttons(self):
        c = self.ctx
        self.btn_test.setEnabled(c.client.has_cookie)
        self.btn_out.setEnabled(c.client.has_cookie)
        sel = self._selected_account()
        self.btn_switch.setEnabled(sel is not None and sel["id"] != accounts.active_id())
        self.btn_remove.setEnabled(sel is not None)
        self.btn_balances.setEnabled(bool(accounts.list_accounts()))
        self.btn_profile.setEnabled(c.logged_in)
        self.btn_pending.setEnabled(c.logged_in)
        kind, plain = accounts.storage_status()
        if not c.client.has_cookie and not accounts.list_accounts():
            self.safety.setText("Not signed in. Press Sign in... (password with 2-step code, browser, or cookie). Without signing in you can still use the API Explorer and look up public groups.")
            self.safety.setStyleSheet("color: #9a9da6;")
        elif kind == "plain":
            self.safety.setText(f"Warning: {plain} sign-in(s) are stored in plain private files, NOT encrypted, because the safe store ("
                                f"{plat.WALLET}) could not be used. "
                                "Unlock or start the wallet and restart the app: they will be moved into it automatically.")
            self.safety.setStyleSheet("color: #e0a030;")
        else:
            self.safety.setText(f"Your sign-ins are stored encrypted ({plat.WALLET}) and sent only to roblox.com. Your password is never stored.")
            self.safety.setStyleSheet("color: #9a9da6;")

    # ---- several accounts
    def _selected_account(self):
        rows = selected_rows(self.atable)
        return accounts.get(row_key(self.atable, rows[0])) if rows else None

    def refresh_accounts(self):
        active = accounts.active_id()
        rows = accounts.list_accounts()
        fill_table(self.atable, [[a["displayName"] or a["name"], "@" + a["name"], "in use" if a["id"] == active else "",
                                  self.balances.get(a["id"], "")] for a in rows],
                   {(i, 2): "#3ba55d" for i, a in enumerate(rows) if a["id"] == active}, keys=[a["id"] for a in rows])
        self.refresh_buttons()

    def _reset_for_switch(self):
        """Forget everything shown about the previous account (late answers must not repaint it)."""
        self._pending_gen = getattr(self, "_pending_gen", 0) + 1
        self.pending_report = None
        self.ctx.async_.generation += 1          # answers still on their way for the old account are thrown away
        self.ctx.client.invalidate()             # and so are its requests that are waiting or in flight
        self.ctx.client.logout()
        self.who.setText("Not signed in")
        self.set_avatar(None)
        for w in self.fields.values():
            w.setText("-")
        self.ctx.signed_out.emit()

    def switch_to(self, uid):
        c = self.ctx
        if c.busy():
            QMessageBox.information(self, "Busy", "A long action is still running. Wait for it to finish (or press Stop) before switching accounts.")
            return
        value = accounts.cookie_of(uid)
        if not value:
            QMessageBox.warning(self, "Account missing", "This account's saved sign-in could not be found. Remove it and sign in again.")
            return
        self._previous = None
        self._reset_for_switch()
        c.client._cookie = value
        accounts.activate(uid)
        c.accounts_changed.emit()
        self.sign_in()

    def switch_selected(self):
        a = self._selected_account()
        if a:
            self.switch_to(a["id"])

    def remove_selected(self):
        a = self._selected_account()
        if a:
            self._remove_account(a, "Remove account")

    def _remove_account(self, a, title):
        was_active = a["id"] == accounts.active_id()
        if not self.ctx.confirm(title, f"{'Sign out' if title == 'Sign out' else 'Remove'} {a['displayName'] or a['name']} (@{a['name']}) on this PC?\n\n"
                                "Its saved sign-in is deleted. This does not log you out of Roblox in your browser."):
            return
        if was_active and self.ctx.busy():
            QMessageBox.information(self, "Busy", "A long action is still running. Wait for it to finish before signing out the account in use.")
            return
        nxt = accounts.remove(a["id"])
        self.balances.pop(a["id"], None)
        self.ctx.accounts_changed.emit()
        if was_active:
            self._reset_for_switch()
            if nxt is not None:
                self.ctx.client._cookie = accounts.cookie_of(nxt)
                self.sign_in()
            else:
                self.refresh_buttons()
                self.ctx.status("Signed out; the sign-in was deleted.")

    def show_balances(self):
        c = self.ctx
        accts, active = accounts.list_accounts(), accounts.active_id()
        cookies = {a["id"]: accounts.cookie_of(a["id"]) for a in accts}
        mine = c.client

        def work():
            out = {}
            for a in accts:
                try:
                    if a["id"] == active:
                        r = mine.robux()
                    else:
                        other = c.client_factory(cookies[a["id"]])
                        other.login()
                        r = other.robux()
                    out[a["id"]] = f"{r:,}" if r is not None else "-"
                except rbx.RobloxError as e:
                    out[a["id"]] = "sign-in expired" if e.status == 401 else "?"
            return out
        c.async_.run(work, lambda res: (self.balances.update(res), self.refresh_accounts()))

    def set_cookie(self):
        """Add an account (also the first sign-in). The account in use keeps working if the new sign-in does not."""
        c = self.ctx
        if c.busy():
            QMessageBox.information(self, "Busy", "A long action is still running. Wait for it to finish (or press Stop) before adding an account.")
            return
        d = SignInDialog(self, c)
        if d.exec() != QDialog.DialogCode.Accepted or not d.cookie:
            return
        value = rbx.normalise_cookie(d.cookie)
        if not rbx.cookie_looks_valid(value):
            QMessageBox.warning(self, "Not a cookie", "That does not look like a .ROBLOSECURITY cookie (it is a long text starting with _|WARNING).")
            return
        self._previous = c.client._cookie or None
        self._reset_for_switch()
        c.client._cookie = value
        self.sign_in()

    def check_sign_in(self):
        self._force_pending = True
        self.sign_in()

    def sign_in(self):
        self.ctx.status("Checking with Roblox...")
        self.ctx.async_.run(self.ctx.client.login, self._signed_in, self._sign_in_failed)

    def _sign_in_failed(self, e):
        prev, self._previous = self._previous, None
        if prev:                                       # an account was being added: stay on the one that was in use
            self.ctx.status("That sign-in was rejected; back on the previous account.")
            QMessageBox.warning(self, "Sign-in rejected", "Roblox did not accept that sign-in, so nothing was added. You are back on the account you were using.")
            self.ctx.client._cookie = prev
            self.sign_in()
            return
        self.ctx.client.user = None
        self.ctx.signed_out.emit()
        self.who.setText("Not signed in")
        self.set_avatar(None)
        self.refresh_buttons()
        if isinstance(e, rbx.RobloxError) and e.status == 401:
            QMessageBox.warning(self, "Cookie rejected", "Roblox says this cookie is not valid (it may have expired, or you logged out of Roblox "
                                "in the browser it came from). Copy a fresh one and try again.")
        else:
            self.ctx.error(e)

    def _signed_in(self, user):
        self._previous = None
        try:
            accounts.remember(user, self.ctx.client._cookie)        # every account that signs in is kept, ready to switch to
            self.balances.pop(user["id"], None)
        except ValueError:
            pass
        self.ctx.accounts_changed.emit()
        self._load_avatar(user["id"])
        self.who.setText(f"{user.get('displayName') or user['name']}  (@{user['name']})")
        self.fields["User id"].setText(str(user["id"]))
        self.fields["Username"].setText(user["name"])
        self.fields["Display name"].setText(user.get("displayName", ""))
        self.refresh_buttons()
        self.ctx.signed_in.emit()
        self.ctx.status(f"Signed in as {user['name']}")
        uid = user["id"]
        self.ctx.async_.run(lambda: self.ctx.client.user_detail(uid), lambda d: self.fields["Joined"].setText(when(d.get("created"))))
        self.ctx.async_.run(lambda: self.ctx.client.counts(uid), self._counts)
        self.ctx.async_.run(self.ctx.client.has_premium, lambda p: self.fields["Roblox Plus"].setText("yes" if p else "no"),
                            lambda e: self.fields["Roblox Plus"].setText("(not available)"))
        self.ctx.async_.run(self.ctx.client.email_status, lambda d: self.fields["Email"].setText(
            (d["address"] or "none") + ("  (verified)" if d["verified"] else "  (NOT verified)" if d["address"] else "")),
            lambda e: self.fields["Email"].setText("(not available)"))
        self.ctx.async_.run(self.ctx.client.robux, lambda r: self.fields["Robux"].setText(f"{r:,}" if r is not None else "-"),
                            lambda e: self.fields["Robux"].setText("(not available)"))
        self.load_pending()

    # ---- pending Robux: the amount first, then the details; every part ends in a result (never "loading" forever)
    def load_pending(self):
        c = self.ctx
        if not c.logged_in:
            return
        client, me = c.client, c.me["id"]
        cached = self._pending_cache.get(me)
        if cached and time.time() - cached[0] < 600 and not self._force_pending:
            self._pending_gen += 1
            self.pending_report = cached[1]          # looked at in the last 10 minutes: show that, send nothing
            self._show_pending()
            return
        self._force_pending = False
        rep = self.pending_report = {"uid": me, "total": None, "summary": None, "items": [], "groups": [], "notes": [],
                                     "total_done": False, "breakdown_done": False, "groups_done": False}
        self._pending_gen = getattr(self, "_pending_gen", 0) + 1
        gen = self._pending_gen

        def live(fn):
            return lambda *a: fn(*a) if gen == self._pending_gen else None

        def total_ok(n):
            rep["total"], rep["total_done"] = n, True
            self._show_pending()

        def total_fail(e):
            rep["total_done"] = True
            self._show_pending()

        def breakdown_ok(items):
            rep["items"], rep["summary"], rep["breakdown_done"] = items, rbx.summarize_pending(items), True
            self._show_pending()

        def breakdown_fail(e):
            rep["breakdown_done"] = True
            rep["notes"].append(f"The list of pending sales is unavailable ({e}).")
            self._show_pending()

        def groups_ok(res):
            rep["groups"], notes = res
            rep["notes"] += notes
            rep["groups_done"] = True
            self._show_pending()

        def groups_fail(e):
            rep["groups_done"] = True
            self._show_pending()

        self._show_pending()
        c.async_.run(client.pending_total, live(total_ok), live(total_fail))
        t0 = time.time()
        c.async_.run(lambda: client.pending_transactions(deadline=t0 + 25), live(breakdown_ok), live(breakdown_fail))

        def groups_work():
            owned = [{"id": g["group"]["id"], "name": g["group"]["name"]} for g in client.my_groups()
                     if (g["group"].get("owner") or {}).get("userId") == me or g["role"].get("rank") == 255]
            return client.owned_groups_pending(owned, deadline=time.time() + 20)
        c.async_.run(groups_work, live(groups_ok), live(groups_fail))

    def _show_pending(self):
        rep = self.pending_report
        if rep is None:
            return
        s = rep.get("summary")
        amount = rep["total"] if rep.get("total") is not None else (s["total"] if s else None)
        label = self.fields["Pending Robux"]
        if amount is None:
            label.setText("(not available)" if rep["total_done"] and rep["breakdown_done"] else "...")
        else:
            txt = f"<b>{amount:,}</b>"
            if s and s["sources"]:
                if len(s["sources"]) == 1 and s["sources"][0][1]["amount"] == amount:
                    sources = s["sources"][0][0]
                else:
                    sources = rbx.describe_sources(s)
                other = amount - s["total"]
                if other > 0:
                    sources += f", other {other:,}"
                txt += f"  <span style='color:#9a9da6'>({sources})</span>"
            label.setText(txt)
        label.updateGeometry()
        if rep.get("uid") and rep["total_done"] and rep["breakdown_done"] and rep["groups_done"]:
            self._pending_cache[rep["uid"]] = (time.time(), rep)
        g = [x for x in rep.get("groups", []) if x["pending"]]
        gl = self.fields["Groups' pending"]
        if g:
            g.sort(key=lambda x: -x["pending"])
            gl.setText(f"<b>{sum(x['pending'] for x in g):,}</b>  <span style='color:#9a9da6'>({', '.join(f'{x['name']} {x['pending']:,}' for x in g[:5])})</span>")
        elif rep["groups_done"]:
            gl.setText("0" if rep.get("groups") else "none in groups you own")
        else:
            gl.setText("...")

    def pending_details(self):
        rep = self.pending_report
        if rep is None:
            self.ctx.status("Pending Robux is still loading.")
            return
        d = QDialog(self)
        d.setWindowTitle("Pending Robux")
        d.resize(1040, 780)
        lay = QVBoxLayout(d)
        s = rep.get("summary")
        if s:
            shown = rep["total"] if rep.get("total") is not None else s["total"]
            extra = "" if shown == s["total"] else f"  (the list below accounts for {s['total']:,} of it)"
            lay.addWidget(QLabel(f"<b style='font-size:16px'>{shown:,} Robux pending</b>  in {s['count']} transaction(s){extra}"))
            t1 = make_table(["Source", "Pending", "Sales", "Share"], [260, 100, 70, 70])
            fill_table(t1, [[name, v["amount"], v["count"], f"{(100 * v['amount'] / s['total']):.0f}%" if s["total"] else ""] for name, v in s["sources"]])
            t1.sortByColumn(1, Qt.SortOrder.DescendingOrder)
            t1.setMinimumHeight(40 + 30 * min(len(s["sources"]), 6))
            t1.setMaximumHeight(40 + 30 * min(len(s["sources"]), 6))
            lay.addWidget(QLabel("By source:"))
            lay.addWidget(t1)
            if s["games"]:
                t2 = make_table(["Game", "Pending"], [380, 100])
                fill_table(t2, [[g, a] for g, a in s["games"][:15]])
                t2.sortByColumn(1, Qt.SortOrder.DescendingOrder)
                t2.setMinimumHeight(40 + 30 * min(len(s["games"]), 4))
                t2.setMaximumHeight(40 + 30 * min(len(s["games"]), 4))
                lay.addWidget(QLabel("By game:"))
                lay.addWidget(t2)
            lay.addWidget(QLabel("Every pending transaction:"))
            t3 = make_table(["Date", "Robux", "Source", "Item", "Game", "From"], [130, 70, 150, 230, 200, 150])
            fill_table(t3, pending_rows(rep.get("items", [])))
            t3.sortByColumn(0, Qt.SortOrder.DescendingOrder)
            t3.setMinimumHeight(220)
            lay.addWidget(t3, 1)
        elif rep.get("total") is not None:
            lay.addWidget(QLabel(f"<b style='font-size:16px'>{rep['total']:,} Robux pending</b>"))
            lay.addWidget(hint("Roblox did not provide the list of pending sales, so only the total is known."))
        if rep.get("groups"):
            lay.addWidget(QLabel("Pending in groups you own:"))
            t4 = make_table(["Group", "Pending Robux"], [320, 120])
            fill_table(t4, [[x["name"], x["pending"]] for x in sorted(rep["groups"], key=lambda x: -x["pending"])])
            t4.sortByColumn(1, Qt.SortOrder.DescendingOrder)
            t4.setMaximumHeight(40 + 30 * min(len(rep["groups"]), 4))
            lay.addWidget(t4)
        if rep.get("notes"):
            lay.addWidget(hint("Notes: " + " ".join(rep["notes"])))
        row = QHBoxLayout()
        row.addWidget(button("Refresh", lambda: (d.accept(), self.load_pending())))
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(d.accept)
        row.addWidget(close)
        lay.addLayout(row)
        d.exec()

    def _counts(self, c):
        for k, f in (("friends", "Friends"), ("followers", "Followers"), ("following", "Following")):
            self.fields[f].setText("-" if c.get(k) is None else f"{c[k]:,}")
            if c.get(k) is not None:
                self.ctx.set_count(k, c[k])             # shown in the tab titles without opening the tab

    def open_profile(self):
        if self.ctx.logged_in:
            open_url(f"https://www.roblox.com/users/{self.ctx.me['id']}/profile")

    def sign_out(self):
        """Sign out the account in use: its saved sign-in is deleted, and the next saved account (if any) takes over."""
        act = accounts.get(accounts.active_id())
        if act:
            self._remove_account(act, "Sign out")
            return
        if not self.ctx.confirm("Sign out", "Delete the saved sign-in from this PC?\n\nThis does not log you out of Roblox in your browser."):
            return
        rbx.delete_cookie()
        self._reset_for_switch()
        self.refresh_buttons()
        self.ctx.status("Signed out; the sign-in was deleted.")


# ============================================================ friends tab
INACTIVE = [("a month", 30), ("3 months", 90), ("6 months", 182), ("a year", 365), ("2 years", 730)]


def inactive_for(last, days, now=None):
    """True when a friend's 'last online' time is more than `days` ago (unknown times are never counted)."""
    if not last:
        return False
    try:
        d = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d < (now or datetime.now(timezone.utc)) - timedelta(days=days)


last_online_between = day_in_range


class FriendsTab(QWidget):
    progress = Signal(str, int, int, float)      # label, done, total, seconds since start (from the worker thread)
    rate = Signal(str, float, bool, bool)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.running = False
        self.stop_flag = False
        self.rate_hits = 0
        ctx.busy_checks.append(lambda: self.running)
        ctx.stoppers.append(lambda: self.stop_bulk())
        self.rows = []       # list of dicts, one per friend
        self.view = []
        self.icons = {}      # user id -> QIcon (avatar)
        self.details = {}    # user id -> public profile data
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name...")
        self.search.textChanged.connect(self.apply_filter)
        self.only_game = QCheckBox("Only friends in a game")
        self.only_game.toggled.connect(self.apply_filter)
        self.only_on = QCheckBox("Only online")
        self.only_on.toggled.connect(self.apply_filter)
        top.addWidget(self.search, 1)
        top.addWidget(self.only_on)
        top.addWidget(self.only_game)
        top.addWidget(button("Refresh", self.load))
        lay.addLayout(top)
        self.table = make_table(["Friend", "Username", "Status", "Game", "Last online"], [220, 160, 90, 300, 150], empty="No friends to show.")
        self.table.setIconSize(QSize(32, 32))
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self.show_details)
        lay.addWidget(self.table, 1)
        pick = QHBoxLayout()
        pick.addWidget(QLabel("Select:"))
        pick.addWidget(button("All shown", lambda: self.select_where(lambda r: True), "Everything the filter above currently shows"))
        pick.addWidget(button("None", lambda: self.select_where(lambda r: False)))
        pick.addWidget(button("Invert", self.invert_selection))
        pick.addSpacing(12)
        pick.addWidget(QLabel("Not online for over"))
        self.inactive = QComboBox()
        for text, days in INACTIVE:
            self.inactive.addItem(text, days)
        self.inactive.setCurrentIndex(3)
        pick.addWidget(self.inactive)
        pick.addWidget(button("Select them", self.select_inactive, "Selects the shown friends who have not been online for that long"))
        pick.addStretch()
        lay.addLayout(pick)
        bydate = QHBoxLayout()
        bydate.addWidget(QLabel("Last online from"))
        self.date_from = QDateEdit(QDate(2010, 1, 1))
        self.date_to = QDateEdit(QDate.currentDate().addYears(-1))
        for de in (self.date_from, self.date_to):
            de.setCalendarPopup(True)
            de.setDisplayFormat("yyyy-MM-dd")
            de.setMaximumDate(QDate.currentDate())
        bydate.addWidget(self.date_from)
        bydate.addWidget(QLabel("to"))
        bydate.addWidget(self.date_to)
        bydate.addWidget(button("Select by date", self.select_by_date, "Selects the shown friends whose last online day is in this range (both days included)"))
        bydate.addStretch()
        lay.addLayout(bydate)
        pick = QHBoxLayout()
        pick.addStretch()
        self.btn_remove = button("Remove selected friends...", self.remove_selected, "Unfriends everyone selected (asks first; cannot be undone)")
        self.btn_remove.setProperty("danger", True)
        pick.addWidget(self.btn_remove)
        lay.addLayout(pick)
        self.ratenote = QLabel("")
        self.ratenote.setWordWrap(True)
        self.ratenote.setProperty("role", "warn")
        self.ratenote.hide()
        lay.addWidget(self.ratenote)
        prog = QHBoxLayout()
        self.bar = QProgressBar()
        prog.addWidget(self.bar, 1)
        self.btn_stop = button("Stop", self.stop_bulk, "Finish the one in progress, then stop")
        prog.addWidget(self.btn_stop)
        self.progress_box = QWidget()
        prog.setContentsMargins(0, 0, 0, 0)
        self.progress_box.setLayout(prog)
        self.progress_box.hide()
        lay.addWidget(self.progress_box)
        self.progress.connect(self._show_progress)
        self.rate.connect(self._on_rate)
        ctx.client.rate_hooks.append(lambda path, wait, gave_up, proactive=False: self.rate.emit(path, wait, gave_up, proactive))
        self.rate_clear = QTimer(self)
        self.rate_clear.setSingleShot(True)
        self.rate_clear.timeout.connect(self.ratenote.hide)
        # profile panel for the selected friend
        self.panel = QFrame()
        self.panel.setProperty("card", True)
        pl = QHBoxLayout(self.panel)
        self.avatar = QLabel()
        self.avatar.setFixedSize(72, 72)
        pl.addWidget(self.avatar)
        self.profile = QLabel("Select a friend to see their profile.")
        self.profile.setWordWrap(True)
        self.profile.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self.profile, 1)
        lay.addWidget(self.panel)
        row = QHBoxLayout()
        self.btn_profile = button("Open profile", self.open_profile)
        self.btn_join = button("Open their game", self.open_game, "Opens the game page in your browser")
        self.btn_joinfriend = button("Join friend's server", self.join_friend, "Opens a link that starts Roblox in their server")
        self.btn_copy = button("Copy join link", self.copy_link)
        self.btn_vip = button("Find VIP servers in their games", self.scan_vips,
                              "Looks at the games your friends are playing and lists private (VIP) servers, marking the ones friends own")
        for b in (self.btn_profile, self.btn_join, self.btn_joinfriend, self.btn_copy):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.btn_vip)
        lay.addLayout(row)
        self.info = hint("Sign in on the Home tab to see your friends.")
        lay.addWidget(self.info)
        ctx.signed_in.connect(self.load)
        ctx.signed_out.connect(self.clear)

    def clear(self):
        self.rows, self.view = [], []
        self._avatar_run = getattr(self, "_avatar_run", 0) + 1      # stop downloading pictures for the account that was in use
        self._avatar_queue = []
        fill_table(self.table, [])
        self.profile.setText("Select a friend to see their profile.")
        self.avatar.clear()
        self.info.setText("Sign in on the Home tab to see your friends.")

    def load(self):
        c = self.ctx
        if not c.logged_in:
            return
        c.status("Loading friends...")
        client = c.client

        def work():
            friends = client.friends()          # with names, looked up by id
            ids = [f["id"] for f in friends]
            pres = {p["userId"]: p for p in client.presence(ids)}
            games = client.games_by_universe([p.get("universeId") for p in pres.values() if p.get("universeId")])
            return friends, pres, games
        c.async_.run(work, self._loaded)

    def _loaded(self, res):
        friends, pres, games = res
        self.rows = []
        for f in friends:
            p = pres.get(f["id"], {})
            t = p.get("userPresenceType", 0)
            g = games.get(p.get("universeId")) or {}
            self.rows.append({"id": f["id"], "name": f.get("displayName") or f.get("name") or f"User {f['id']}", "username": f.get("name", ""),
                              "verified": f.get("hasVerifiedBadge"), "type": t,
                              "game": g.get("name") or (p.get("lastLocation") if t == 2 else ""), "location": p.get("lastLocation", ""),
                              "place": p.get("rootPlaceId") or p.get("placeId"), "job": p.get("gameId"), "last": p.get("lastOnline")})
        self.apply_filter()
        n_game = sum(1 for r in self.rows if r["type"] == 2)
        self.info.setText(f"{len(self.rows)} friends, {sum(1 for r in self.rows if r['type'] > 0)} online, {n_game} in a game.")
        self.ctx.set_count("friends", len(self.rows))
        self.ctx.status("Friends loaded.")
        self.load_avatars([r["id"] for r in self.rows if r["id"] not in self.icons])

    AVATAR_BATCH = 20

    def load_avatars(self, ids):
        """Show saved headshots at once, then download the missing ones a few at a time (paced), updating the list as they arrive.
        Saved pictures are reused for a week, so reopening the app or switching accounts downloads almost nothing."""
        ids = [i for i in dict.fromkeys(ids) if i not in self.icons]
        if not ids:
            return
        have = {}
        for uid in ids:
            data = rbx.cached_avatar(uid)
            if data:
                have[uid] = data
        if have:
            self._avatars(have)
        missing = [u for u in ids if u not in have]
        if missing:
            self._avatar_queue = missing
            self._avatar_run = getattr(self, "_avatar_run", 0) + 1
            self._next_avatars(self._avatar_run)

    def _next_avatars(self, run):
        if run != self._avatar_run or not self._avatar_queue:
            return
        batch, self._avatar_queue = self._avatar_queue[:self.AVATAR_BATCH], self._avatar_queue[self.AVATAR_BATCH:]
        client = self.ctx.client

        def work():
            urls = client.headshots(batch)
            out = {}
            for uid, u in urls.items():
                data = client.fetch_bytes(u)
                if data:
                    rbx.save_avatar(uid, data)
                out[uid] = data
            return out

        def done(images):
            if run == self._avatar_run:
                self._avatars(images)
                self._next_avatars(run)
        self.ctx.async_.run(work, done, lambda e: None)

    def _avatars(self, images):
        """Put the pictures on the rows that are already shown. The list is not rebuilt, so what you have selected stays selected."""
        for uid, data in images.items():
            pm = QPixmap()
            if data and pm.loadFromData(data):
                self.icons[uid] = QIcon(pm)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            uid = row_key(self.table, r)
            if it is not None and uid in images and uid in self.icons:
                it.setIcon(self.icons[uid])
        sel = self._selected()
        if sel and len(selected_rows(self.table)) == 1 and sel["id"] in images:
            self.show_details()

    def apply_filter(self):
        q = self.search.text().strip().lower()
        shown = [r for r in self.rows if (not q or q in r["name"].lower() or q in r["username"].lower())
                 and (not self.only_game.isChecked() or r["type"] == 2) and (not self.only_on.isChecked() or r["type"] > 0)]
        shown.sort(key=lambda r: (-r["type"] if r["type"] != 0 else 9, r["name"].lower()))
        self.view = shown
        keep = self._selected()["id"] if self._selected() else None
        fill_table(self.table, [[r["name"] + ("  ✔" if r["verified"] else ""), "@" + r["username"] if r["username"] else "", PRESENCE.get(r["type"], "?"),
                                 r["game"], when(r["last"])] for r in shown],
                   {(i, 2): PRESENCE_COLOUR.get(r["type"], "#fff") for i, r in enumerate(shown)},
                   keys=[r["id"] for r in shown], icons={i: self.icons[r["id"]] for i, r in enumerate(shown) if r["id"] in self.icons})
        if keep is not None:
            for i in range(self.table.rowCount()):
                if row_key(self.table, i) == keep:
                    self.table.selectRow(i)
                    break

    def _selected(self):
        rows = selected_rows(self.table)
        if not rows:
            return None
        uid = row_key(self.table, rows[0])
        return next((r for r in self.rows if r["id"] == uid), None)

    def _sels(self):
        ids = {row_key(self.table, i) for i in selected_rows(self.table)}
        return [r for r in self.rows if r["id"] in ids]

    def select_where(self, test):
        self.table.clearSelection()
        sm = self.table.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        by_id = {r["id"]: r for r in self.rows}
        for i in range(self.table.rowCount()):
            if test(by_id.get(row_key(self.table, i), {})) and by_id.get(row_key(self.table, i)):
                sm.select(self.table.model().index(i, 0), flags)
        self.ctx.status(f"{len(self._sels())} friend(s) selected.")

    def invert_selection(self):
        have = {r["id"] for r in self._sels()}
        self.select_where(lambda r: r["id"] not in have)

    def select_by_date(self):
        a, b = self.date_from.date().toPython(), self.date_to.date().toPython()
        if a > b:
            a, b = b, a
        self.select_where(lambda r: last_online_between(r.get("last"), a, b))
        n = len(self._sels())
        self.ctx.status(f"{n} friend(s) were last online between {a} and {b}." if n else
                        f"No shown friend was last online between {a} and {b} (Roblox hides the time for some friends).")

    def select_inactive(self):
        days = self.inactive.currentData()
        self.select_where(lambda r: inactive_for(r.get("last"), days))
        if not self._sels():
            self.ctx.status("No shown friend has been offline for that long (or Roblox hides their last-online time).")

    # ---- profile panel
    def show_details(self):
        r = self._selected()
        if not r:
            return
        n = len(selected_rows(self.table))
        if n > 1:
            self.avatar.setPixmap(QPixmap())
            self.profile.setText(f"<b style='font-size:16px'>{n} friends selected</b><br><span style='color:#9a9da6'>Use \"Remove selected friends...\" "
                                 "to unfriend them, or select a single friend to see their profile.</span>")
            return
        icon = self.icons.get(r["id"])
        self.avatar.setPixmap(icon.pixmap(72, 72) if icon else QPixmap())
        self._render_profile(r, self.details.get(r["id"]))
        if r["id"] not in self.details:
            c = self.ctx
            uid = r["id"]

            def work():
                d = c.client.user_detail(uid)
                d["counts"] = c.client.counts(uid)
                return d
            c.async_.run(work, lambda d: (self.details.__setitem__(uid, d), self._selected() and self._selected()["id"] == uid and self._render_profile(r, d)),
                         lambda e: None)

    def _render_profile(self, r, d):
        lines = [f"<b style='font-size:16px'>{r['name']}</b>" + (f"  <span style='color:#9a9da6'>@{r['username']}</span>" if r["username"] else "")
                 + ("  ✔ verified" if r["verified"] else ""), f"User id {r['id']}  |  {PRESENCE.get(r['type'], '?')}"
                 + (f"  -  {r['game']}" if r["game"] else (f"  -  {r['location']}" if r["location"] and r["type"] else ""))]
        if d:
            cnt = d.get("counts") or {}
            lines.append(f"Joined {when(d.get('created'))[:10]}  |  {cnt.get('friends', '?')} friends  |  {cnt.get('followers', '?')} followers  |  {cnt.get('following', '?')} following"
                         + ("  |  <span style='color:#e5534b'>banned</span>" if d.get("isBanned") else ""))
            if d.get("description"):
                lines.append("<span style='color:#9a9da6'>" + d["description"].replace("<", "&lt;")[:240] + "</span>")
        else:
            lines.append("<span style='color:#9a9da6'>loading profile...</span>")
        self.profile.setText("<br>".join(lines))

    def open_profile(self):
        r = self._selected()
        r and open_url(f"https://www.roblox.com/users/{r['id']}/profile")

    def open_game(self):
        r = self._selected()
        if r and r["place"]:
            open_url(rbx.join_link(r["place"]))

    def join_link_for(self, r):
        return rbx.join_link(r["place"], job_id=r["job"]) if r and r["place"] and r["job"] else None

    def join_friend(self):
        link = self.join_link_for(self._selected())
        if link:
            open_url(link)
        else:
            self.ctx.status("That friend is not in a game you can join.")

    def copy_link(self):
        link = self.join_link_for(self._selected())
        if link:
            copy_text(link)
            self.ctx.status("Join link copied.")

    # ---- removing friends in bulk
    def _show_progress(self, label, done, total, secs):
        if total <= 0:
            return
        left = ""
        if 0 < done < total:
            eta = secs / done * (total - done)
            left = f", about {int(eta // 60)}m {int(eta % 60):02d}s left" if eta >= 60 else f", about {int(eta)}s left"
        text = f"{label}: {done}/{total} done, {total - done} left{left}"
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.bar.setFormat(text)
        self.progress_box.show()
        self.ctx.status(text, 4000)

    def _on_rate(self, path, wait, gave_up, proactive=False):
        if proactive:
            self.ratenote.setText(f"Staying within Roblox's limit: waiting {wait:.0f} s on {path} (Roblox allows only so many of these per minute; nothing was refused).")
            if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
                self.ratenote.show()
            self.rate_clear.start(20000)
            return
        self.rate_hits += 1
        self.run_rate_hits = getattr(self, "run_rate_hits", 0) + 1
        text = ("Roblox is rate-limiting requests (too many in a short time). "
                + (f"Gave up on one request to {path}." if gave_up else f"Waiting {wait:.0f} s before retrying {path}.")
                + f" Times this session: {self.rate_hits}.")
        self.ratenote.setText(text)
        if self.isVisible() and settings.get("ui.rate_notes"):      # only where you are looking: another tab's wait is not news here
            self.ratenote.show()
        self.rate_clear.start(20000)

    def stop_bulk(self):
        self.stop_flag = True
        self.btn_stop.setEnabled(False)
        if self.running:
            self.ctx.client.cancel_pending()
        self.ctx.status("Stopping...")

    def remove_selected(self):
        c = self.ctx
        if c.need_login() or self.running:
            return
        sel = self._sels()
        if not sel:
            c.status("Select the friends to remove first (Ctrl or Shift click, or use the Select buttons).")
            return
        n = len(sel)
        names = "\n".join(f"  {r['name']}" + (f"  (@{r['username']})" if r["username"] else "") for r in sel[:15]) + ("\n  ..." if n > 15 else "")
        if not c.confirm("Remove friends", f"Remove {n} friend(s)?\n\n{names}\n\nThis cannot be undone: to get them back you would have to send "
                         "new friend requests, and they may decline.\nA list of who was removed is saved on this PC.", danger=True):
            return
        if n >= settings.typed_from():
            typed, ok = QInputDialog.getText(self, "Please confirm", f"You are about to remove {n} friends.\nType the number {n} to confirm:")
            if not ok or typed.strip() != str(n):
                c.status("Cancelled: the number did not match, nobody was removed.")
                return
        self.running, self.stop_flag, self.run_rate_hits = True, False, 0
        self.btn_remove.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.emit("Removing friends", 0, n, 0.0)
        c.status(f"Pacing requests (about one every {c.client.SLOW_GAP:.0f} s) to stay under Roblox's limit; {n} friend(s) will take about "
                 f"{int(n * c.client.SLOW_GAP // 60)} min.", 12000)
        client = c.client

        def work():
            removed, failed, t0 = [], [], time.time()
            for k, r in enumerate(sel):
                if self.stop_flag:
                    failed.append(f"- stopped by you: {n - k} friend(s) were not tried")
                    break
                self.progress.emit("Removing friends", k, n, time.time() - t0)
                try:
                    client.unfriend(r["id"])
                    removed.append(r)
                    self._remember_removed(r)
                except rbx.Cancelled:
                    failed.append(f"- stopped by you: {n - k} friend(s) were not tried")
                    break
                except rbx.RobloxError as e:
                    failed.append(f"- {r['name']} (@{r['username']}, id {r['id']}): {rbx.redact(e)}")
                    if e.status == 429:
                        failed.append(f"- stopped: Roblox is rate-limiting; {n - k - 1} friend(s) were not tried. Wait a few minutes and try again.")
                        break
                except Exception as e:          # noqa: BLE001 - reported below
                    failed.append(f"- {r['name']} (id {r['id']}): {rbx.redact(e)}")
            return removed, failed

        def done(res):
            removed, failed = res
            self._finish_remove(n, removed, failed)
        c.async_.run(work, done, lambda e: (self._finish_remove(n, [], [str(e)]), c.error(e)))

    def _remember_removed(self, r):
        try:
            with open(rbx.STATE_DIR / "removed-friends.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\t{r['id']}\t@{r['username']}\t{r['name']}\n")
        except OSError:
            pass

    def _finish_remove(self, n, removed, failed):
        self.running = False
        self.ctx.client.clear_cancel()
        self.progress_box.hide()
        self.btn_remove.setEnabled(True)
        gone = {r["id"] for r in removed}
        self.rows = [r for r in self.rows if r["id"] not in gone]
        self.apply_filter()
        self.info.setText(f"{len(self.rows)} friends.")
        self.ctx.set_count("friends", len(self.rows))
        msg = f"{len(removed)} of {n} friend(s) removed."
        if self.run_rate_hits:
            msg += f" Roblox rate-limited {self.run_rate_hits} request(s) during this (the app waited and retried)."
        self.ctx.status(msg, 15000)
        if failed:
            QMessageBox.warning(self, "Remove friends", msg + "\n\nThese did not work:\n" + "\n".join(failed[:20]))
        elif removed:
            QMessageBox.information(self, "Remove friends", msg + f"\nThe list of who was removed is in {rbx.STATE_DIR / 'removed-friends.txt'}")

    def scan_vips(self):
        c = self.ctx
        if c.need_login():
            return
        places = sorted({r["place"] for r in self.rows if r["type"] == 2 and r["place"]})
        if not places:
            c.status("None of your friends is in a game right now. Use the VIP servers tab to check a specific game.")
            return
        fid = [r["id"] for r in self.rows]
        c.status(f"Looking at VIP servers in {len(places)} game(s)...")
        c.async_.run(lambda: rbx.vip_scan(c.client, places, fid), self._vips)

    def _vips(self, res):
        rows, problems = res
        d = QDialog(self)
        d.setWindowTitle("VIP servers in your friends' games")
        d.resize(900, 460)
        lay = QVBoxLayout(d)
        names = {r["place"]: r["game"] for r in self.rows if r["place"]}
        t = make_table(["Friend's?", "Game", "Server name", "Owner", "Players"], [90, 260, 220, 160, 80])
        fill_table(t, [["YES" if r["friend"] else "", names.get(r["place_id"], r["place_id"]), r["name"], r["owner"],
                        f"{r['playing']}/{r['max']}" if r["max"] else ""] for r in rows],
                   {(i, 0): "#3ba55d" for i, r in enumerate(rows) if r["friend"]})
        lay.addWidget(t, 1)
        if problems:
            lay.addWidget(hint("Some lookups failed: " + "; ".join(f"{names.get(p, p)}: {m[0]}" for p, m in problems.items())))
        n_friend = sum(1 for r in rows if r["friend"])
        lay.addWidget(QLabel(f"{len(rows)} VIP server(s) found, {n_friend} owned by a friend." if rows else "No VIP servers visible to your account in these games."))
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(d.accept)
        row.addWidget(close)
        lay.addLayout(row)
        d.exec()
