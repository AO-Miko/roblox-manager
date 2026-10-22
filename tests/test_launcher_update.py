"""Test of what happens at the start after an update was installed: the launcher asks for a restart instead of starting the half-replaced app, and app.py forgets
modules an old launcher loaded from the old folder (the 'Client object has no attribute ...' mix of old and new files). Run: python3 tests/test_launcher_update.py"""
import importlib
import io
import os
import sys
import tempfile
import types
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="launch-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
sys.path.insert(0, str(ROOT / "linux"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:220]) if e else ""))


import launcher
import updater

# ---------------------------------------------------------------- the question after an update
asked, restarted = [], []
ask_yes = lambda v: asked.append(v) or True            # noqa: E731
ask_no = lambda v: asked.append(v) or False           # noqa: E731
rs = lambda: restarted.append(1)                      # noqa: E731
check("nothing installed (no result): no question, the app starts", launcher.after_update(None, ask_yes, rs) is False and not asked)
for status in ("up-to-date", "disabled", "error", "refused", "available"):
    check(f"an update that was not installed ({status}): no question, the app starts", launcher.after_update({"status": status, "message": "x"}, ask_yes, rs) is False and not asked and not restarted)
check("an installed update: the launcher stops here (the app is not started from the replaced folder)", launcher.after_update({"status": "updated", "version": "1.2.3.4.5"}, ask_yes, rs) is True)
check("...it asks about the new version", asked == ["1.2.3.4.5"], asked)
check("...Restart now starts it again", restarted == [1])
asked.clear(); restarted.clear()
check("...No just closes: it stops and starts nothing", launcher.after_update({"status": "updated", "version": "1.2.3.4.5"}, ask_no, rs) is True and restarted == [] and asked == ["1.2.3.4.5"])
check("an installed update without a version still asks", launcher.after_update({"status": "updated"}, ask_yes, rs) is True)

# the text of the popup
err = io.StringIO()
with redirect_stderr(err):
    answer = launcher.ask_restart("1.9.9.9.9")
check("the popup says which version was installed and that a restart completes the update", "1.9.9.9.9" in err.getvalue() and "restart" in err.getvalue().lower() and "complete the update" in err.getvalue(), err.getvalue())
check("...(without a screen it does not block)", answer is True)

# check_for_update hands the result over
fake = types.ModuleType("updater")
fake.boot = lambda: {"status": "updated", "version": "7.7.7.7.7"}
saved = sys.modules["updater"]
sys.modules["updater"] = fake
check("the launcher gets what the update step did", launcher.check_for_update(5) == {"status": "updated", "version": "7.7.7.7.7"})
fake.boot = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
check("an update step that fails never stops the start (no result)", launcher.check_for_update(5) is None)
sys.modules["updater"] = saved
real_apply = updater.apply
updater.apply = lambda cfg=None: {"status": "updated", "version": "2.0.0.0.0", "message": "Updated"}
(tmp / "cfg").mkdir(exist_ok=True)
(tmp / "cfg" / "update.json").write_text('{"repo": "https://github.com/x/y", "auto": true}')
check("updater.boot() returns the result of the update (it used to return nothing)", updater.boot() == {"status": "updated", "version": "2.0.0.0.0", "message": "Updated"})
updater.apply = lambda cfg=None: (_ for _ in ()).throw(OSError("x"))
check("...and None when it fails", updater.boot() is None)
updater.apply = real_apply

# main(): after an installed update the app is not run
import runpy
ran, popups = [], []
real_run = runpy.run_path
runpy.run_path = lambda *a, **k: ran.append(a)
launcher.first_run_setup = lambda: None
launcher.app_is_open = lambda: False
launcher.check_for_update = lambda seconds=40: {"status": "updated", "version": "3.0.0.0.0"}
launcher.ask_restart = lambda v: popups.append(v) or False
sys.argv = ["launcher.py"]
launcher.main()
check("main(): after an installed update the popup is shown and the app is NOT started", popups == ["3.0.0.0.0"] and not ran, (popups, ran))
launcher.check_for_update = lambda seconds=40: {"status": "up-to-date"}
popups.clear()
launcher.main()
check("main(): with nothing installed the app starts, no popup", not popups and len(ran) == 1)
launcher.check_for_update = lambda seconds=40: (_ for _ in ()).throw(AssertionError("must not run"))
launcher.app_is_open = lambda: True
ran.clear()
launcher.main()
check("main(): when the app is already open no update is installed under it", len(ran) == 1)
runpy.run_path = real_run

# ---------------------------------------------------------------- stale modules from an old launcher
src = (ROOT / "linux" / "app.py").read_text()
block = src[src.index("# --- forget stale modules"):src.index("# --- end")]
folder = tmp / "appfolder"
folder.mkdir()
(folder / "app.py").write_text("")
other = tmp / "elsewhere"
other.mkdir()
(folder / "fakerbx.py").write_text("class Client:\n    def old(self): return 1\n")
(other / "fakelib.py").write_text("X = 1\n")
sys.path[:0] = [str(folder), str(other)]
old = importlib.import_module("fakerbx")
lib = importlib.import_module("fakelib")
(folder / "fakerbx.py").write_text("class Client:\n    def old(self): return 1\n    def group_search_members(self): return 2\n")       # the update replaced the file
importlib.invalidate_caches()
check("the bug: after the file was replaced, an import still gives the OLD module (new files would mix with old ones)", not hasattr(importlib.import_module("fakerbx").Client, "group_search_members"))


def run_block(name):
    g = {"os": os, "sys": sys, "__name__": name, "__file__": str(folder / "app.py")}
    exec(compile(block, "app.py", "exec"), g)


run_block("not_main")
check("imported as a module (the tests) nothing is forgotten", "fakerbx" in sys.modules)
run_block("__main__")
check("started as a program: modules from the app folder are forgotten", "fakerbx" not in sys.modules)
check("...modules from anywhere else are left alone", sys.modules.get("fakelib") is lib)
check("...so the next import gives the NEW module (the error 'Client has no attribute group_search_members' cannot happen)", hasattr(importlib.import_module("fakerbx").Client, "group_search_members"))
check("the block does not touch the real modules of this test run (they are not in that folder)", "launcher" in sys.modules and "updater" in sys.modules)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
