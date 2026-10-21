"""Finds text that does not fit (cut off at the edge) on every tab and sub-tab of the window, at several window widths.
  QT_QPA_PLATFORM=offscreen python3 tests/test_text_fit.py [widths...]     (default widths: 1180 960 800)
The window cannot be made narrower than its tabs need; below MIN_WIDTH nothing is promised."""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("RM_SRC") or HERE.parent / "linux")
tmp = Path(tempfile.mkdtemp(prefix="fit-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_UPDATE_BACKEND": "off"})
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(HERE))
import browser_login  # noqa: F401
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import app as appmod
import textfit

widths = [int(a) for a in sys.argv[1:] if a.isdigit()] or [1180, 960, 800]
MIN_WIDTH = 760
problems = {}
win = appmod.MainWindow(auto_login=False)
win.show()
textfit.check_window(win, widths, problems, app)
for line in textfit.lines(problems):
    print(line)
print(f"\n{len(problems)} problem(s) at widths {widths}")
sys.exit(1 if any(p[0][0] >= MIN_WIDTH for p in problems) else 0)
