"""Test of the Info tab (Settings + Updates with the update log) and the changelog reader. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_info_tab.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="info-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.1.2\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import changelog
import theme
import ui_common

theme.apply(app, tmp / "assets")
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


# the reader
entries = changelog.load()
check("the shipped update log loads, newest first", len(entries) >= 3 and entries[0]["version"] > entries[-1]["version"], [e["version"] for e in entries])
check("every entry has a date and at least one change", all(e["date"] and e["changes"] for e in entries))
bad = tmp / "bad.json"
bad.write_text("{not json")
check("a damaged file gives an empty list, not a crash", changelog.load(bad) == [] and changelog.load(tmp / "missing.json") == [])
odd = tmp / "odd.json"
odd.write_text(json.dumps([{"version": "2.0.0", "changes": ["<b>x</b>", "  "]}, {"nope": 1}, "text"]))
e2 = changelog.load(odd)
check("odd entries are skipped and empty changes dropped", len(e2) == 1 and e2[0]["changes"] == ["<b>x</b>"], e2)
h = changelog.html(e2, "2.0.0")
check("text is escaped and the installed version is marked", "&lt;b&gt;x&lt;/b&gt;" in h and "installed" in h, h)
check("another version is not marked", "installed" not in changelog.html(e2, "1.0.0"))
check("an empty log says so", "No update log" in changelog.html([], "1"))


class Ctx:
    def __init__(self):
        self.async_ = ui_common.Async(print)

    def status(self, *a, **k):
        pass

    def confirm(self, *a, **k):
        return True


import tab_info

tab = tab_info.InfoTab(Ctx())
tab.show()
app.processEvents()
names = [tab.tabText(i) for i in range(tab.count())]
check("the Info tab has Settings and Updates", names == ["Settings", "Updates"], names)
check("the update controls are on the Updates page, not on Settings", tab.settings_tab.update_box.parent() is not None and tab.updates.isAncestorOf(tab.settings_tab.update_box)
      and not tab.settings_tab.isAncestorOf(tab.settings_tab.update_box))
check("the log shows the installed version marked", "Version 1.1.2" in tab.updates.log.text() and "installed" in tab.updates.log.text())
check("the version label of the update box still works", "1.1.2" in tab.settings_tab.upd_version.text(), tab.settings_tab.upd_version.text())
tab.setCurrentIndex(1)
app.processEvents()
check("the Updates page can be shown", tab.currentWidget() is tab.updates)
print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
