"""Join requests of all your groups in one list: the groups you can answer them in are checked, and the requests can be accepted or declined from here."""
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QInputDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

import rbx
import settings
from ui_common import button, fill_table, hint, make_table, row_key, selected_rows, when

PAGES_PER_GROUP = 2          # 100 requests of each group are listed; the rest appear after these are answered


def may_answer(membership):
    p = ((membership or {}).get("permissions") or {}).get("groupMembershipPermissions") or {}
    return bool(p.get("inviteMembers"))


class AllRequestsDialog(QDialog):
    progress = Signal(str, int, int)

    def __init__(self, ctx, groups):
        super().__init__(ctx.window)
        self.ctx = ctx
        self.groups = list(groups)             # the rows of "my groups": {"group": {...}, "role": {...}}
        self.rows = []                         # {gid, group, id, username, display, created}
        self.busy = False
        self._stop = False
        self.setWindowTitle("Join requests in all my groups")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(hint("Only the groups where your role may accept join requests are listed. Requests are answered one group at a time."))
        self.table = make_table(["Group", "Person", "Username", "Requested"], [190, 160, 130, 130], empty="No join requests found yet. Press Check my groups.")
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        lay.addWidget(self.table, 1)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        bar = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.hide()
        bar.addWidget(self.bar, 1)
        self.b_stop = QPushButton("Stop")
        self.b_stop.clicked.connect(self.stop)
        self.b_stop.hide()
        bar.addWidget(self.b_stop)
        lay.addLayout(bar)
        row = QHBoxLayout()
        self.b_scan = button("Check my groups", self.scan, "Looks in every group where you may accept requests")
        self.b_accept = button("Accept selected", lambda: self.answer(True), "Accepts the selected requests", primary=True)
        self.b_decline = button("Decline selected", lambda: self.answer(False), "Declines the selected requests", danger=True)
        self.b_all = button("Select all", self.table.selectAll)
        for b in (self.b_scan, self.b_all, self.b_accept, self.b_decline):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(button("Close", self.close))
        lay.addLayout(row)
        self.progress.connect(self._progress)

    # ---------------------------------------------------------------- checking
    def _progress(self, text, done, total):
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(done)
        self.bar.setFormat(f"{text}: {done}/{total}")

    def _busy(self, on):
        self.busy = on
        for b in (self.b_scan, self.b_accept, self.b_decline, self.b_all):
            b.setEnabled(not on)
        self.bar.setVisible(on)
        self.b_stop.setVisible(on)
        self.b_stop.setEnabled(True)

    def stop(self):
        self._stop = True
        self.b_stop.setEnabled(False)
        self.ctx.client.cancel_pending()

    def scan(self):
        c = self.ctx
        if c.need_login() or self.busy:
            return
        self._busy(True)
        self._stop = False
        self.note.setText("Checking your groups...")
        groups, client = list(self.groups), c.client

        def work():
            rows, checked, failed = [], 0, []
            for k, g in enumerate(groups):
                if self._stop:
                    break
                gr = g["group"]
                self.progress.emit("Checking groups", k, len(groups))
                try:
                    if not may_answer(client.group_membership(gr["id"])):
                        continue
                    checked += 1
                    cursor = None
                    for _ in range(PAGES_PER_GROUP):
                        d = client.group_join_requests(gr["id"], cursor, 100)
                        for r in d.get("data", []):
                            u = r.get("requester") or {}
                            if isinstance(u.get("userId"), int):
                                rows.append({"gid": gr["id"], "group": gr["name"], "id": u["userId"], "username": u.get("username", ""),
                                             "display": u.get("displayName", ""), "created": r.get("created")})
                        cursor = d.get("nextPageCursor")
                        if not cursor or self._stop:
                            break
                except rbx.Cancelled:
                    break
                except rbx.RobloxError as e:
                    failed.append(f"{gr['name']}: {e}")
            return rows, checked, failed, self._stop

        c.async_.run(work, self._scanned, lambda e: (self._busy(False), self.note.setText(f"Could not check: {e}")))

    def _scanned(self, result):
        rows, checked, failed, stopped = result
        self.ctx.client.clear_cancel()
        self._busy(False)
        self.rows = rows
        self.show_rows()
        text = f"{len(rows)} request(s) in {len({r['gid'] for r in rows})} group(s); you may answer requests in {checked} of your {len(self.groups)} groups."
        if stopped:
            text = "Stopped. " + text
        if failed:
            text += f"\n{len(failed)} group(s) could not be checked: " + "; ".join(failed[:3]) + (" ..." if len(failed) > 3 else "")
        self.note.setText(text)

    def show_rows(self):
        fill_table(self.table, [[r["group"], r["display"] or r["username"] or f"User {r['id']}", r["username"], when(r["created"])] for r in self.rows],
                   keys=[f"{r['gid']}:{r['id']}" for r in self.rows])

    # ---------------------------------------------------------------- answering
    def answer(self, accept):
        c = self.ctx
        if c.need_login() or self.busy:
            return
        picked = []
        for row in selected_rows(self.table):
            gid, uid = str(row_key(self.table, row)).split(":")
            picked.append((int(gid), int(uid)))
        if not picked:
            c.status("Select one or more requests first.")
            return
        verb = "Accept" if accept else "Decline"
        n, groups = len(picked), len({g for g, _ in picked})
        if not c.confirm(f"{verb} requests", f"{verb} {n} join request(s) in {groups} group(s)?", danger=not accept):
            return
        if n >= settings.typed_from():
            typed, ok = QInputDialog.getText(self, "Please confirm", f"You are about to {verb.lower()} {n} requests.\nType the number {n} to confirm:")
            if not ok or typed.strip() != str(n):
                c.status("Cancelled: the number did not match, nothing was answered.")
                return
        by_group = {}
        for gid, uid in picked:
            by_group.setdefault(gid, []).append(uid)
        self._busy(True)
        self._stop = False
        client = c.client
        fn = client.accept_join_requests if accept else client.decline_join_requests

        def work():
            done, failed, t0 = [], [], time.time()
            for k, (gid, ids) in enumerate(by_group.items()):
                if self._stop:
                    failed.append(f"stopped: {len(by_group) - k} group(s) were not tried")
                    break
                self.progress.emit(f"{verb}ing" if accept else "Declining", k, len(by_group))
                try:
                    fn(gid, ids)
                    done += [(gid, u) for u in ids]
                except rbx.Cancelled:
                    failed.append("stopped")
                    break
                except rbx.RobloxError as e:
                    name = next((r["group"] for r in self.rows if r["gid"] == gid), str(gid))
                    failed.append(f"{name}: {e}")
            return done, failed

        c.async_.run(work, lambda res: self._answered(verb, res), lambda e: (self._busy(False), self.note.setText(f"Could not answer: {e}")))

    def _answered(self, verb, result):
        done, failed = result
        self.ctx.client.clear_cancel()
        self._busy(False)
        gone = set(done)
        self.rows = [r for r in self.rows if (r["gid"], r["id"]) not in gone]
        self.show_rows()
        text = f"{verb}ed {len(done)} request(s)." if verb == "Accept" else f"Declined {len(done)} request(s)."
        if failed:
            text += "\nNot done: " + "; ".join(failed[:3]) + (" ..." if len(failed) > 3 else "")
        self.note.setText(text)
        self.ctx.status(text.splitlines()[0])
