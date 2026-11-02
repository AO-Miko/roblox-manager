"""The Terms of use and the Privacy policy question: asked once per account, again when the texts change, and a decline signs the account out.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_legal.py"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
here = tempfile.mkdtemp(prefix="legaltest-")
os.environ["ROBLOX_MANAGER_CONFIG"] = os.path.join(here, "cfg")
os.environ["ROBLOX_MANAGER_STATE"] = os.path.join(here, "state")
sys.path.insert(0, str(ROOT / "linux"))

from PySide6.QtWidgets import QApplication, QDialog

import legal
import legal_dialog

app = QApplication.instance() or QApplication([])
res = []


def check(name, ok, extra=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  " + str(extra)[:200]) if extra else ""))


# --- the stored acceptance
legal.FILE.parent.mkdir(parents=True, exist_ok=True)
check("nobody has accepted on a new device", not legal.accepted(1) and not legal.accepted(2))
legal.accept(1)
check("an account that accepted is not asked again", legal.accepted(1))
check("...and another account still is", not legal.accepted(2))
legal.accept(2)
check("each account is remembered on its own", legal.accepted(1) and legal.accepted(2))
legal.forget(1)
check("taking one back asks that account again and only that one", not legal.accepted(1) and legal.accepted(2))
real = legal.VERSION
legal.VERSION = "2099-01-01"
check("a change of the texts asks everybody again", not legal.accepted(2))
legal.VERSION = real
check("...and nothing was lost meanwhile", legal.accepted(2))
legal.FILE.write_text("not json")
check("a damaged file counts as 'not accepted' (never as accepted)", not legal.accepted(2))
legal.FILE.write_text('{"accounts": {"2": "yes"}}')
check("so does a wrong shape", not legal.accepted(2))
legal.forget()
check("everything can be taken back at once", not legal.accepted(1) and not legal.accepted(2))

# --- the dialog
d = legal_dialog.LegalDialog("tester")
from PySide6.QtWidgets import QLabel
check("the dialog names the account", any("@tester" in lab.text() for lab in d.findChildren(QLabel)))
check("Accept cannot be pressed before the box is ticked", not d.b_accept.isEnabled())
d.check.setChecked(True)
check("...and can be once it is", d.b_accept.isEnabled())
d.check.setChecked(False)
check("...and not again after unticking", not d.b_accept.isEnabled())
check("Enter would decline, never accept", d.b_decline.isDefault() and not d.b_accept.isDefault())
check("both documents can be read from the dialog", "TERMS.md" in legal.TERMS_URL and "PRIVACY.md" in legal.PRIVACY_URL and d.b_terms and d.b_privacy)

shown = []
orig_exec = legal_dialog.LegalDialog.exec


def fake(answer):
    def run(self):
        shown.append(self)
        if answer:
            self.check.setChecked(True)
            self.b_accept.click()
            return QDialog.DialogCode.Accepted
        self.b_decline.click()
        return QDialog.DialogCode.Rejected
    return run


user = {"id": 77, "name": "tester"}
legal_dialog.LegalDialog.exec = fake(False)
check("declining returns False", legal_dialog.ask(user) is False and len(shown) == 1)
check("...and nothing is remembered", not legal.accepted(77))
legal_dialog.LegalDialog.exec = fake(True)
check("accepting returns True", legal_dialog.ask(user) is True and len(shown) == 2)
check("...and is remembered", legal.accepted(77))
legal_dialog.LegalDialog.exec = lambda self: (_ for _ in ()).throw(AssertionError("asked again"))
try:
    again = legal_dialog.ask(user)
except AssertionError:
    again = None
check("the same account is not asked a second time", again is True)
legal.VERSION = "2099-01-01"
legal_dialog.LegalDialog.exec = fake(False)
check("when the texts change it is asked again (and can decline)", legal_dialog.ask(user) is False)
legal.VERSION = real
legal_dialog.LegalDialog.exec = orig_exec

# --- where it is used
acct = (ROOT / "linux/tab_account.py").read_text(encoding="utf-8")
signed_in = acct[acct.index("    def _signed_in(self, user):"):]
signed_in = signed_in[:signed_in.index("\n    def ", 10)]
check("every sign-in is checked before the account is saved or shown",
      "legal_dialog.ask(user, self)" in signed_in and signed_in.index("legal_dialog.ask") < signed_in.index("accounts.remember") < signed_in.index("signed_in.emit"))
check("a decline signs the account out without deleting its saved sign-in", "_declined_legal" in acct and "accounts.remove" not in acct[acct.index("def _declined_legal"):acct.index("def enforce_bans")])
check("the app does not ask at start (only per account)", "legal" not in (ROOT / "linux/app.py").read_text(encoding="utf-8"))

# --- the texts and the version
for name in ("TERMS.md", "PRIVACY.md"):
    text = (ROOT / name).read_text(encoding="utf-8")
    m = re.search(r"Last updated: (\d{1,2}) (\w+) (\d{4})", text)
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    date = f"{m.group(3)}-{months.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}" if m else ""
    check(f"{name}: its 'Last updated' date equals legal.VERSION (change one, change the other: everybody is asked again)", date == legal.VERSION, f"{date} vs {legal.VERSION}")
kt = (ROOT / "android/app/src/main/java/app/robloxmanager/core/Legal.kt").read_text(encoding="utf-8")
check("Android asks for the same version", f'VERSION = "{legal.VERSION}"' in kt)

print("\n%d/%d checks passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
