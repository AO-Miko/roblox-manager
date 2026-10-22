"""GUI test of the Updates box in Settings (the updater itself is tested in test_updater.py). Run: QT_QPA_PLATFORM=offscreen python3 tests/test_settings_updates.py"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="updui-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.2.3\n")
(tmp / "app" / ".installed.json").write_text(json.dumps({"commit": "abcdef0123456789" * 2 + "abcdef01", "version": "1.2.3", "installed_at": "2026-10-21 12:00:00"}))
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401  (imports the web engine before the application exists)
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import theme
import ui_common
import updater
import tab_settings

theme.apply(app, tmp / "assets")
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


def spin(t):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        spin(0.02)
        if cond():
            return True
    return False


from PySide6.QtCore import QObject, Signal


class Ctx(QObject):
    alerts_changed = Signal()
    data_restored = Signal()

    def __init__(self):
        super().__init__()
        self.async_ = ui_common.Async(print)
        self.answers, self.asked = True, []

    def status(self, *a, **k):
        pass

    def confirm(self, title, text, danger=False):
        self.asked.append((title, text))
        return self.answers


ctx = Ctx()
tab = tab_settings.SettingsTab(ctx)
tab.show()
check("the Updates box shows the installed version and commit", "1.2.3" in tab.upd_version.text() and "abcdef0123" in tab.upd_version.text(), tab.upd_version.text())
check("by default automatic updates and the signature check are both on", tab.upd_auto.isChecked() and tab.upd_sig.isChecked() and tab.upd_branch.text() == "release")
tab.upd_repo.setText("https://example.invalid/roblox-manager.git")
tab.upd_repo.editingFinished.emit()
saved = json.loads((tmp / "cfg" / "update.json").read_text())
check("editing the update server saves it", saved["repo"] == "https://example.invalid/roblox-manager.git" and saved["branch"] == "release" and saved["auto"] and saved["require_signature"], saved)
tab.upd_auto.setChecked(False)
check("switching off automatic updates is saved", json.loads((tmp / "cfg" / "update.json").read_text())["auto"] is False)
tab.upd_auto.setChecked(True)
ctx.answers = False
tab.upd_sig.setChecked(False)
check("turning the signature check off asks first, and 'no' keeps it on", ctx.asked and "anyone who can write" in ctx.asked[-1][1] and tab.upd_sig.isChecked() and json.loads((tmp / "cfg" / "update.json").read_text())["require_signature"] is True, ctx.asked[-1:])
ctx.answers = True
tab.upd_sig.setChecked(False)
check("...and 'yes' turns it off", json.loads((tmp / "cfg" / "update.json").read_text())["require_signature"] is False)
tab.upd_sig.setChecked(True)

updater.check = lambda cfg=None: {"status": "available", "message": "A newer version is available.", "remote": "x" * 40, "installed": ""}
tab.check_updates()
check("'Check now' shows the answer and enables 'Update now' when there is a newer version", wait(lambda: "newer version" in tab.upd_status.text()) and tab.b_upd_apply.isEnabled())
updater.apply = lambda cfg=None: {"status": "updated", "message": "Updated to version 1.3.0. Restart the app to use it.", "version": "1.3.0"}
tab.apply_update()
check("'Update now' reports success and offers 'Restart now'", wait(lambda: "Updated to version 1.3.0" in tab.upd_status.text()) and not tab.b_upd_restart.isHidden(), tab.upd_status.text())
updater.apply = lambda cfg=None: {"status": "refused", "message": "the newest version is not signed with a key you trust, so it was NOT installed"}
tab.b_upd_restart.hide()
tab.apply_update()
check("a refused update says why, in the warning colour, and offers no restart", wait(lambda: "NOT installed" in tab.upd_status.text()) and tab.b_upd_restart.isHidden() and tab.upd_status.property("role") == "warn", tab.upd_status.property("role"))
updater.check = lambda cfg=None: {"status": "error", "message": "could not reach the update server: boom"}
tab.check_updates()
check("an unreachable server is shown as a problem and 'Update now' stays off", wait(lambda: "could not reach" in tab.upd_status.text()) and not tab.b_upd_apply.isEnabled() and tab.upd_status.property("role") == "warn")
updater.rollback = lambda: {"status": "rolled-back", "version": "1.2.3", "message": "Back to version 1.2.3. Restart the app to use it."}
ctx.answers = False
tab.roll_back()
check("going back asks first", ctx.asked[-1][0] == "Go back" and "Back to version" not in tab.upd_status.text())
ctx.answers = True
tab.roll_back()
check("...and then goes back and offers a restart", "Back to version 1.2.3" in tab.upd_status.text() and not tab.b_upd_restart.isHidden())

# ---- the channel
check("the Updates box has a Channel choice: Stable (the default) and Beta", [tab.upd_channel.itemData(i) for i in range(tab.upd_channel.count())] == ["stable", "beta"]
      and tab.upd_channel.currentData() == "stable" and updater.load_config()["channel"] == "stable")
ctx.answers, ctx.asked = False, []
tab.upd_channel.setCurrentIndex(1); tab.channel_changed()
check("choosing Beta asks first (less tested; you can go back), and 'no' keeps Stable", ctx.asked and ctx.asked[-1][0] == "Beta versions" and tab.upd_channel.currentData() == "stable" and updater.load_config()["channel"] == "stable")
ctx.answers = True
tab.upd_channel.setCurrentIndex(1); tab.channel_changed()
check("'yes' joins the beta: saved, explained", updater.load_config()["channel"] == "beta" and "first" in tab.upd_channel_note.text() and "Channel changed" in tab.upd_status.text())
tab.load_update_settings()
check("...and it is still Beta after the box is loaded again", tab.upd_channel.currentData() == "beta")
ctx.asked = []
tab.upd_channel.setCurrentIndex(0); tab.channel_changed()
check("going back to Stable does not ask and is saved", not ctx.asked and updater.load_config()["channel"] == "stable" and "released to everybody" in tab.upd_channel_note.text())
print("\n%d/%d checks passed" % (sum(res), len(res)))
