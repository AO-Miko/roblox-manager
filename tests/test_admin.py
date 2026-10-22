"""Test of the roles, the Admin page and the Staff List: the signed role list, the hierarchy owner > co-owner > senior admin > admin > trusted friend
in tools/ban.sh, in roles.py and in the pages. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_admin.py   (needs git, bash and ssh-keygen)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="admin-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.7.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication(sys.argv)
import adminops
import bans
import rbx
import roles
import tab_staff
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:220]) if e else ""))


def spin(s=0.1):
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(fn, t=8):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        if fn():
            return True
        time.sleep(0.02)
    return False


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


# ---------------------------------------------------------------- a throw-away repository with its own key
OWNER, COOWNER, SENIOR, ADMIN_A, ADMIN_B, FRIEND, NOBODY, VICTIM, VICTIM2 = 1001, 1002, 1003, 2002, 3003, 4004, 9009, 5005, 6006
ROLES = {OWNER: "owner", COOWNER: "co-owner", SENIOR: "senior-admin", ADMIN_A: "admin", ADMIN_B: "admin", FRIEND: "trusted-friend"}
key = tmp / "key"
sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", "t")
pub = (tmp / "key.pub").read_text().split()
trusted = f"t {pub[0]} {pub[1]}\n"
repo = tmp / "repo"
(repo / "tools").mkdir(parents=True)
(repo / "dist").mkdir()
shutil.copy(ROOT / "tools" / "ban.sh", repo / "tools" / "ban.sh")
(repo / "dist" / "bans.json").write_text('{"serial": 0, "bans": []}\n')
(repo / "dist" / "roles.json").write_text(json.dumps({"serial": 1, "roles": {str(k): v for k, v in ROLES.items()}}))
(tmp / "allowed").write_text(f"t {pub[0]} {pub[1]}\n")
sh("git", "init", "-q", "-b", "release", cwd=repo)
for k, v in (("user.name", "t"), ("user.email", "t@t"), ("gpg.format", "ssh"), ("user.signingkey", str(key)), ("commit.gpgsign", "true"),
             ("gpg.ssh.allowedSignersFile", str(tmp / "allowed"))):
    sh("git", "config", k, v, cwd=repo)
sh("git", "add", "-A", cwd=repo)
r = sh("git", "commit", "-q", "-m", "start", cwd=repo)
check("the test repository is ready", r.returncode == 0, r.stderr)
os.environ["ROBLOX_MANAGER_SIGNING_KEY"] = str(key)


def ban(by, target, why="x"):
    return adminops.run(["ban", str(target), why, "--by", str(by)], repo)


def unban(by, target):
    return adminops.run(["unban", str(target), "--by", str(by)], repo)


def entries():
    return {e["id"]: e for e in adminops.read_bans(repo)}


check("nothing is missing for publishing in this setup", adminops.problems(repo) == [], adminops.problems(repo))

# the five roles in order
check("the roles in order: owner > co-owner > senior admin > admin > trusted friend",
      [n for n, _, _ in roles.ORDER] == ["owner", "co-owner", "senior-admin", "admin", "trusted-friend"] and [r for _, r, _ in roles.ORDER] == [5, 4, 3, 2, 1])
check("role names are forgiving: 'Senior Admin', 'senior_admin'", roles.normalize("Senior Admin") == roles.normalize("senior_admin") == "senior-admin")

# a higher role acts on lower roles and on people without a role
ok, text = ban(ADMIN_A, VICTIM, "spam")
check("an admin bans someone without a role", ok and entries()[VICTIM]["by"] == ADMIN_A and entries()[VICTIM]["rank"] == 2, text)
ok, text = ban(FRIEND, VICTIM2)
check("a trusted friend has no moderation powers", not ok and "no moderation powers" in text and VICTIM2 not in entries(), text)
ok, text = ban(NOBODY, VICTIM2)
check("someone without a role is not on the staff", not ok and "not on the staff" in text and VICTIM2 not in entries(), text)
ok, text = ban(ADMIN_A, FRIEND)
check("an admin can ban a trusted friend (lower role)", ok and entries()[FRIEND]["rank"] == 2, text)
ok, text = unban(OWNER, FRIEND)
check("(the owner lifts it)", ok and FRIEND not in entries(), text)
for who, target, name in ((ADMIN_A, ADMIN_A, "themselves"), (ADMIN_A, ADMIN_B, "another admin (same role)"), (ADMIN_A, SENIOR, "a senior admin"), (ADMIN_A, COOWNER, "a co-owner"),
                          (ADMIN_A, OWNER, "the owner"), (SENIOR, ADMIN_A, None), (SENIOR, SENIOR, "themselves"), (SENIOR, COOWNER, "a co-owner"), (SENIOR, OWNER, "the owner"),
                          (COOWNER, COOWNER, "themselves"), (COOWNER, OWNER, "the owner"), (OWNER, OWNER, "themselves")):
    ok, text = ban(who, target)
    if name is None:                                  # senior admin on admin: allowed
        check("a senior admin can ban an admin", ok and target in entries(), text)
        unban(OWNER, target)
    else:
        check(f"{ROLES[who]} cannot ban {name}", not ok and target not in entries(), text)
ok, text = ban(COOWNER, SENIOR, "x")
check("a co-owner can ban a senior admin", ok and entries()[SENIOR]["rank"] == 4, text)
ok, text = unban(SENIOR, SENIOR)
check("nobody unbans themselves", not ok, text)
ok, text = unban(ADMIN_A, SENIOR)
check("an admin cannot lift a ban placed by a co-owner", not ok and SENIOR in entries(), text)
ok, text = unban(SENIOR, SENIOR)
ok, text = unban(COOWNER, SENIOR)
check("the co-owner can lift their own ban", ok and SENIOR not in entries(), text)
ok, text = ban(OWNER, COOWNER)
check("the owner bans a co-owner", ok and entries()[COOWNER]["rank"] == 5, text)
ok, text = unban(COOWNER, COOWNER)
ok2, text2 = unban(SENIOR, COOWNER)
check("...which neither they nor a lower role can lift", not ok and not ok2 and COOWNER in entries())
ok, text = unban(OWNER, COOWNER)
check("...but the owner can", ok and COOWNER not in entries(), text)
ok, text = unban(ADMIN_A, VICTIM)
check("an admin lifts a ban placed by an admin", ok and VICTIM not in entries(), text)
ok, text = unban(ADMIN_A, VICTIM)
check("unbanning someone who is not banned says so", not ok and "not banned" in text, text)
ok, text = adminops.run(["ban", str(VICTIM2), "plain"], repo)
check("without --by it is the key holder's own action: bans a plain user, not an owner", ok and entries()[VICTIM2]["by"] is None and entries()[VICTIM2]["rank"] == 5
      and not adminops.run(["ban", str(OWNER)], repo)[0], text)
sh("git", "reset", "-q", "--hard", cwd=repo)
log = sh("git", "log", "--format=%s", cwd=repo).stdout.split("\n")
check("every change is a signed commit with the actor in the message", any("(by 2002)" in x for x in log))
signed = (repo / "dist" / "bans.json").read_bytes()
check("the published list carries a valid signature", bans.parse(signed, (repo / "dist" / "bans.json.sig").read_text(), trusted) is not None)
check("...a changed list does not", bans.parse(signed.replace(b"6006", b"7007"), (repo / "dist" / "bans.json.sig").read_text(), trusted) is None)

# ---------------------------------------------------------------- the rules in roles.py
check("may_ban: self, equal and higher are refused; lower and unranked are allowed",
      not roles.may_ban(3, 5, 5, 0)[0] and not roles.may_ban(3, 5, 6, 3)[0] and not roles.may_ban(3, 5, 6, 5)[0] and roles.may_ban(4, 5, 6, 3)[0]
      and roles.may_ban(2, 5, 6, 0)[0] and roles.may_ban(2, 5, 6, 1)[0] and not roles.may_ban(1, 5, 6, 0)[0] and not roles.may_ban(0, 5, 6, 0)[0])
check("may_unban: needs the role of the ban's author, and a role with powers",
      roles.may_unban(2, 2)[0] and roles.may_unban(5, 2)[0] and roles.may_unban(4, 4)[0] and not roles.may_unban(3, 4)[0] and not roles.may_unban(1, 1)[0])

real = (ROOT / "dist" / "roles.json").read_bytes()
real_sig = (ROOT / "dist" / "roles.json.sig").read_text()
got = roles.parse(real, real_sig)
check("the shipped role list is signed by the release key and has an owner", got is not None and "owner" in got[1].values(), got)
check("a changed role list is refused", roles.parse(real.replace(b"owner", b"admin"), real_sig) is None)
check("a role list signed in another namespace (the ban list's) is refused", roles.parse(signed, (repo / "dist" / "bans.json.sig").read_text(), trusted) is None)

state = tmp / "state"
served = {"roles.json": real, "roles.json.sig": real_sig.encode()}


def fake_get(url, limit=0, timeout=0):
    name = url.rsplit("/", 1)[1]
    if name not in served:
        raise OSError("down")
    return served[name]


check("before the first download nobody has a role", roles.role_of(239345228) is None and roles.staff() == [])
check("refresh stores a valid list", roles.refresh(get=fake_get) is True and roles.role_of(239345228) == "owner" and roles.rank_of(239345228) == 5)
check("...the same list again changes nothing", roles.refresh(get=fake_get) is False)
served["roles.json"] = real.replace(b"owner", b"admin")
check("...a tampered list is refused and the old one stays", roles.refresh(get=fake_get) is None and roles.role_of(239345228) == "owner")
served.clear()
check("...no network changes nothing", roles.refresh(get=fake_get) is None and roles.role_of(239345228) == "owner")


def publish_roles(mapping, serial):
    """Make the app believe a role list signed with the test key (the real key is the only one it trusts otherwise)."""
    data = tmp / "r.json"
    data.write_text(json.dumps({"serial": serial, "roles": {str(k): v for k, v in mapping.items()}}))
    (tmp / "r.json.sig").unlink(missing_ok=True)
    sh("ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", "roblox-manager-roles", str(data))
    served.update({"roles.json": data.read_bytes(), "roles.json.sig": (tmp / "r.json.sig").read_bytes()})
    return roles.refresh(get=fake_get)


bans.TRUSTED = trusted                                  # from here on the test key is the trusted one
check("a list with roles in every spelling is read", publish_roles({7: "Senior Admin", 8: "OWNER", 9: "king", 10: "trusted_friend"}, 9) is True
      and roles.role_of(7) == "senior-admin" and roles.role_of(8) == "owner" and roles.role_of(9) is None and roles.role_of(10) == "trusted-friend", roles.load())

# ---------------------------------------------------------------- the pages in the window
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
w = MainWindow(rbx.Client(), auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)
admin_idx = w.tabs.indexOf(w.holders[w.admin])
staff_idx = w.tabs.indexOf(w.holders[w.staff])
names = [w.tabs.tabText(i) for i in range(w.tabs.count())]
check("the pages end with Staff List, Admin, Info", names[-3:] == ["Staff List", "Admin", "Info"], names)
check("signed out: Admin is hidden (tab and side bar entry), Staff List is there", not w.tabs.isTabVisible(admin_idx) and w.tabs.isTabVisible(staff_idx)
      and not [i for i in w.sidebar.items if i.title == "Admin"][0].isVisible() and [i for i in w.sidebar.items if i.title == "Staff List"][0].isVisible())
check("...the STAFF group name stays (Staff List is in it)", [lab for lab in w.sidebar.group_labels if lab.text() == "STAFF"][0].isVisible())
check("...and the search does not offer Admin", "Admin" not in [e[0] for e in w._search_entries()] and "Staff List" in [e[0] for e in w._search_entries()])

publish_roles({239345228: "owner", 2002: "admin", 3003: "senior-admin", 4004: "trusted-friend", 5005: "co-owner"}, 10)
for uid, rank, shown in ((9009, 0, False), (4004, 1, False), (2002, 2, True), (3003, 3, True), (5005, 4, True), (239345228, 5, True)):
    w.ctx.client.user = {"id": uid, "name": f"u{uid}", "displayName": f"U{uid}"}
    w.ctx.signed_in.emit(); spin(0.1)
    check(f"rank {rank}: the Admin page is {'there' if shown else 'hidden'}", w.tabs.isTabVisible(admin_idx) == shown and w.admin.my_rank() == rank, (uid, rank))
w.ctx.client.user = {"id": 4004, "name": "friend", "displayName": "Friend"}
w.ctx.signed_in.emit(); spin(0.1)
QTest.keyClick(w, Qt.Key.Key_9, Qt.KeyboardModifier.ControlModifier); spin(0.1)
check("a trusted friend has no Admin page, and Ctrl+9 counts only the pages that are there", w.tabs.tabText(w.tabs.currentIndex()) == "Info", w.tabs.tabText(w.tabs.currentIndex()))

w.ctx.client.user = {"id": 3003, "name": "senior", "displayName": "Senior"}
w.ctx.signed_in.emit(); spin(0.2)
check("a senior admin sees the page, says who they are, and sees the roles", "Senior admin" in w.admin.who.text() and w.admin.roles_table.rowCount() == 5, w.admin.who.text())
check("...the roles table is in hierarchy order", [w.admin.roles_table.item(i, 1).text() for i in range(5)] == ["Owner", "Co-owner", "Senior admin", "Admin", "Trusted friend"])
w.admin.target.setText("3003"); w.admin.reason.setText("x")
w.admin.ban()
check("banning themselves is explained and nothing is published", wait(lambda: "yourself" in w.admin.msg.text()), w.admin.msg.text())
w.admin.target.setText("5005")
w.admin.ban()
check("...so is banning a co-owner", wait(lambda: "co-owner" in w.admin.msg.text()), w.admin.msg.text())
# profiles come from Roblox's public API: replaced here by canned answers
canned = {239345228: ("Kyl3ST", "AKMikoOFC", "Hello, I make the app.\nSecond line."), 2002: ("adm", "The Admin", "Admin bio"), 3003: ("sen", "Senior One", "Senior bio"),
          4004: ("fri", "Friendly", "Trusted"), 5005: ("coo", "Co Owner", "Co bio"), 7777: ("plain", "Plain Person", "I am nobody special")}


def user_detail(uid):
    if uid not in canned:
        raise rbx.RobloxError("no such user", 404)
    return {"id": uid, "name": canned[uid][0], "displayName": canned[uid][1], "description": canned[uid][2], "created": "2020-05-06T10:00:00Z"}


w.ctx.client.user_detail = user_detail
w.ctx.client.headshots = lambda ids, size="48x48": {i: "https://example.invalid/%d.png" % i for i in ids}
w.ctx.client.fetch_bytes = lambda url: b""
w.ctx.client.counts = lambda uid: {"friends": 12, "followers": 3456, "following": 7}
published = []
adminops.ban = lambda uid, why, actor, **k: published.append((uid, why, actor)) or (True, "ok")
shown = []
answer = {"yes": False}
w.admin.confirm_ban = lambda uid, profile, reason: shown.append((uid, profile, reason)) or answer["yes"]

w.admin.target.setText("7777"); w.admin.reason.setText("")
w.admin.ban(); spin(0.2)
check("a ban needs a reason: no reason, no question, nothing is looked up or published", "needs a reason" in w.admin.msg.text() and not shown and not published, w.admin.msg.text())
w.admin.reason.setText("   ")
w.admin.ban(); spin(0.2)
check("...spaces are not a reason", "needs a reason" in w.admin.msg.text() and not shown)
w.admin.reason.setText("spamming")
w.admin.target.setText("999999")
w.admin.ban()
check("an id that is nobody says so", wait(lambda: "no Roblox user" in w.admin.msg.text()) and not shown and not published, w.admin.msg.text())
w.admin.target.setText("3003")
w.admin.ban()
check("(the hierarchy is checked before anything is shown)", wait(lambda: "yourself" in w.admin.msg.text()) and not shown)

w.admin.target.setText("7777")
answer["yes"] = False
w.admin.ban()
check("a valid ban shows the profile and asks (with the reason)", wait(lambda: len(shown) == 1) and shown[0][0] == 7777 and shown[0][2] == "spamming"
      and shown[0][1]["info"]["displayName"] == "Plain Person" and shown[0][1]["counts"]["followers"] == 3456, shown)
check("answering no cancels: nothing is published and the list is as it was", wait(lambda: "Cancelled" in w.admin.msg.text()) and not published, w.admin.msg.text())
answer["yes"] = True
w.admin.ban()
check("answering yes publishes the ban once, with the reason and who did it", wait(lambda: len(published) == 1) and published[0] == (7777, "spamming", 3003), published)
check("...and says so", wait(lambda: "banned" in w.admin.msg.text() and "plain" in w.admin.msg.text()), w.admin.msg.text())

# the question itself
prof = tab_staff.fetch_profile(w.ctx.client, 7777)
dlg = admin_dialog = None
import tab_admin
dlg = tab_admin.BanDialog(w, 7777, prof, "spamming")
check("the question shows the profile: names, id, joined, followers, description and the reason", dlg.display.text() == "Plain Person" and dlg.user.text() == "@plain"
      and "7777" in dlg.facts.text() and "2020" in dlg.facts.text() and "3,456" in dlg.facts.text() and dlg.about.toPlainText() == "I am nobody special"
      and "spamming" in dlg.reason.text(), (dlg.display.text(), dlg.facts.text()))
check("...Cancel is the default button, the other says Yes, ban", dlg.b_no.isDefault() and dlg.b_no.text() == "Cancel" and dlg.b_yes.text() == "Yes, ban" and not dlg.b_yes.isDefault())
dlg.b_no.click()
check("Cancel rejects", dlg.result() == tab_admin.QDialog.DialogCode.Rejected)
dlg2 = tab_admin.BanDialog(w, 7777, prof, "x")
dlg2.b_yes.click()
check("Yes, ban accepts", dlg2.result() == tab_admin.QDialog.DialogCode.Accepted)
dlg3 = tab_admin.BanDialog(w, 7777, {"info": {"name": "n", "isBanned": True}, "counts": {}, "avatar": b""}, "x")
check("a profile that is half empty (no counts, no picture, banned by Roblox) still shows", "banned by Roblox" in dlg3.facts.text() and dlg3.display.text() == "n")
w.admin.target.setText("")
w.admin.ban(); spin(0.2)
check("an empty box asks for an id or a name", "Type a user id" in w.admin.msg.text(), w.admin.msg.text())

# ---------------------------------------------------------------- the Staff List
opened = []
tab_staff.open_url = lambda url: opened.append(url)
w.tabs.setCurrentIndex(staff_idx)
check("opening the page builds the list from the signed roles", wait(lambda: w.staff.list.count() == 10), w.staff.list.count())
heads = [w.staff.list.item(i).text() for i in range(w.staff.list.count()) if w.staff.list.item(i).data(Qt.ItemDataRole.UserRole) is None]
check("...with one heading per role, from the top of the hierarchy down", heads == ["OWNER", "CO-OWNER", "SENIOR ADMIN", "ADMIN", "TRUSTED FRIEND"], heads)
check("...the profiles fill in the names (display name and @username)", wait(lambda: "AKMikoOFC  (@Kyl3ST)" in [w.staff.list.item(i).text() for i in range(w.staff.list.count())]))
check("...the first person is shown: name, role, joined date", w.staff.display.text() == "AKMikoOFC" and w.staff.user.text() == "@Kyl3ST" and "Owner" in w.staff.role.text() and "2020" in w.staff.facts.text(), (w.staff.display.text(), w.staff.facts.text()))
check("...followers, following and friends arrive", wait(lambda: "3,456" in w.staff.facts.text() and "12" in w.staff.facts.text()), w.staff.facts.text())
check("...and the description", w.staff.about.toPlainText().startswith("Hello, I make the app."))
w.staff.list.setCurrentRow(3)
check("picking another person shows theirs", wait(lambda: w.staff.display.text() == "Co Owner" and "Co-owner" in w.staff.role.text()), w.staff.display.text())
w.staff.b_open.click()
check("Go to profile opens their roblox.com profile", opened == ["https://www.roblox.com/users/5005/profile"], opened)
check("the search finds staff by name and jumps to them", any(e[0].startswith("Senior One") for e in w._search_entries()))
for e in w._search_entries():
    if e[0].startswith("Senior One"):
        e[3]()
spin(0.2)
check("...opening the Staff List with them picked", w.current_page() is w.staff and w.staff.display.text() == "Senior One", w.staff.display.text())

# a role taken away while the app is open takes the page away
publish_roles({239345228: "owner"}, 11)
w.update_admin(); spin(0.2)
check("when the role is gone the Admin page goes (and the app moves off it)", not w.tabs.isTabVisible(admin_idx) and w.tabs.currentIndex() != admin_idx)
check("...and the Staff List follows the new list", wait(lambda: w.staff.list.count() == 2), w.staff.list.count())

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
