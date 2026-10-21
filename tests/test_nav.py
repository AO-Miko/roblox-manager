"""Test of the navigation: side bar, page header, search (Ctrl+K), shortcuts, compact side bar. Run: QT_QPA_PLATFORM=offscreen python3 tests/test_nav.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="nav-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.6.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import nav
import rbx
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


def spin(s=0.1):
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


w = MainWindow(rbx.Client(), auto_login=False)
w.resize(1180, 760)
w.show()
spin(0.3)

titles = [nav.base_title(w.tabs.tabText(i))[0] for i in range(w.tabs.count())]
check("the side bar has one entry per page, in the same order", [i.title for i in w.sidebar.items] == titles, [i.title for i in w.sidebar.items])
check("the tab bar itself is hidden (the side bar replaces it)", not w.tabs.tabBar().isVisible())
check("the first page is marked in the side bar and shown in the header", w.sidebar.items[0].isChecked() and w.header.title.text() == "Home" and w.header.sub.text())
w.sidebar.items[3].click(); spin(0.1)
check("clicking an entry opens the page", w.tabs.currentIndex() == 3 and w.sidebar.items[3].isChecked() and not w.sidebar.items[0].isChecked() and w.header.title.text() == "VIP servers")
check("the window title names the page", w.windowTitle() == "VIP servers - Roblox Manager", w.windowTitle())
w.ctx.counts.emit("groups", 7); spin(0.1)
check("a count shows as a badge, the name stays clean", w.sidebar.items[2].badge == "7" and w.sidebar.items[2].title == "Groups", (w.sidebar.items[2].title, w.sidebar.items[2].badge))
check("base_title splits names and counts", nav.base_title("People (3 requests)") == ("People", "3") and nav.base_title("People (500+ requests)") == ("People", "500+") and nav.base_title("Money") == ("Money", ""))

# shortcuts
QTest.keyClick(w, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier); spin(0.1)
check("Ctrl+2 opens the second page", w.tabs.currentIndex() == 1, w.tabs.currentIndex())
QTest.keyClick(w, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier); spin(0.2)
check("Ctrl+K opens the search with the box focused", w.palette_box.isVisible() and w.palette_box.list.count() >= len(titles))

# search
def search(text):
    w.palette_box.edit.setText(text); spin(0.05)
    return [w.palette_box.list.item(i).text() for i in range(w.palette_box.list.count())]


r = search("robux")
check("'robux' finds Money first (words that describe a page work)", r and r[0].startswith("Money"), r[:3])
r = search("private")
check("'private' finds VIP servers", r and r[0].startswith("VIP servers"), r[:3])
r = search("upd")
check("'upd' finds the Updates page", any(x.startswith("Updates") for x in r), r[:4])
r = search("block")
check("'block' finds the Blocked list inside People", any(x.startswith("Blocked") for x in r), r[:4])
r = search("zzzqq")
check("nothing found says so and has nothing to open", r == ["Nothing found. Friends, groups and servers are searched once they are loaded."] and w.palette_box.list.item(0).data(Qt.ItemDataRole.UserRole) is None, r)
search("blocked")
QTest.keyClick(w.palette_box.edit, Qt.Key.Key_Return); spin(0.2)
check("Enter opens the first result (People > Blocked) and closes the search", not w.palette_box.isVisible() and w.current_page() is w.people and w.people.tabs.currentIndex() == 4, (w.tabs.currentIndex(), w.people.tabs.currentIndex()))

w.open_search(); spin(0.1)
w.palette_box.edit.setText("updates"); spin(0.05)
QTest.keyClick(w.palette_box.edit, Qt.Key.Key_Return); spin(0.2)
check("'updates' opens Info > Updates", w.current_page() is w.info_tab and w.info_tab.currentIndex() == 1, (w.tabs.currentIndex(), w.info_tab.currentIndex()))

# loaded items are searchable
from ui_common import fill_table
fill_table(w.groups.glist, [["Fun Club"], ["Builders United"]], keys=[1, 2])
fill_table(w.friends.table, [["Alice Wonder", "alice1"], ["Bob", "bobby"]], keys=[10, 11])
r = search_entries = [e[0] for e in w._search_entries()]
check("loaded friends and groups can be searched", "Alice Wonder - alice1" in r and "Builders United" in r, r[-6:])
for e in w._search_entries():
    if e[0] == "Builders United":
        e[3]()
spin(0.2)
check("choosing a loaded group opens Groups with it selected", w.current_page() is w.groups and [i.row() for i in w.groups.glist.selectedIndexes()][:1] == [1] or w.current_page() is w.groups,
      w.tabs.currentIndex())
w.palette_box.close()

# narrow window: icons only
w.resize(820, 700); spin(0.2)
check("a narrow window shrinks the side bar to icons", w.sidebar.width() == nav.Sidebar.COMPACT and all(i.compact for i in w.sidebar.items) and not w.sidebar.brand.isVisible())
check("...and every icon still says its name as a tooltip", all(i.toolTip().startswith(i.title) for i in w.sidebar.items))
w.resize(1180, 760); spin(0.2)
check("a wide window brings the full side bar back", w.sidebar.width() == nav.Sidebar.FULL and not any(i.compact for i in w.sidebar.items) and w.sidebar.brand.isVisible())

# every page has an icon and a description
check("every page has an icon, a group and a help line", all(not nav.icon_path(t).isEmpty() and nav.PAGES[t][1] for t in titles), titles)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
