"""Starts Roblox Manager on Windows (Linux uses tools/roblox-manager.sh, which does the same). Run with pythonw.exe, no console window.

  1. If the app is not already open, look for a newer signed version and install it (quietly, for at most a short while; any problem just
     means the installed version starts as it is).
  2. Start the app.
  --selftest   start everything without a screen, print "selftest ok" and exit (used to check a package)
"""
import os
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE.parent)                       # never run from inside the app folder: the updater replaces that folder

if "--selftest" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("ROBLOX_MANAGER_UPDATE_BACKEND", "off")


def crash_report(text):
    """Without a console there is nowhere to print: write it next to the logs and tell the person."""
    try:
        import plat
        d = plat.state_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "crash.log").write_text(text, encoding="utf-8")
        where = str(d / "crash.log")
    except Exception:                                  # noqa: BLE001
        where = "(could not be saved)"
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Roblox Manager could not start.\n\n{text.strip().splitlines()[-1]}\n\nDetails: {where}", "Roblox Manager", 0x10)
        except Exception:                              # noqa: BLE001
            pass
    else:
        print(text, file=sys.stderr)


def app_is_open():
    from PySide6.QtCore import QLockFile
    import rbx
    lock = QLockFile(str(rbx.STATE_DIR / "instance.lock"))
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        lock.unlock()
        return False
    return True


def first_run_setup():
    """A fresh Windows install: remember which key updates must be signed with, and where the updates are. Never changes them afterwards."""
    try:
        import json
        import plat
        cfg = plat.config_dir()
        cfg.mkdir(parents=True, exist_ok=True)
        trust, src = cfg / "trusted_signers", HERE.parent / "trust" / "allowed_signers"
        if src.is_file() and (not trust.exists() or trust.stat().st_size == 0):
            trust.write_bytes(src.read_bytes())
        update = cfg / "update.json"
        if not update.exists():
            update.write_text(json.dumps({"repo": "https://github.com/AO-Miko/roblox-manager", "branch": "release", "auto": True, "require_signature": True}, indent=1))
    except Exception:                                  # noqa: BLE001 - the app still starts
        pass


def check_for_update(seconds=40):
    def work():
        try:
            import updater
            updater.boot()
        except Exception:                              # noqa: BLE001 - an update must never keep the app from starting
            pass
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(seconds)


def selftest():
    import browser_login  # noqa: F401  (the web engine must be imported before the application exists)
    from PySide6.QtWidgets import QApplication
    import app as appmod
    import updater
    qapp = QApplication([])
    w = appmod.MainWindow(auto_login=False)
    w.show()
    qapp.processEvents()
    tabs = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    print("selftest ok", updater.version(), tabs)
    sys.stdout.flush()
    os._exit(0)


def main():
    if sys.platform == "win32":
        try:                                           # groups the window with its own icon in the taskbar
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RobloxManager.App")
        except Exception:                              # noqa: BLE001
            pass
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        first_run_setup()
        if not app_is_open():
            check_for_update()
        import runpy
        sys.argv = [str(HERE / "app.py")] + [a for a in sys.argv[1:]]
        runpy.run_path(str(HERE / "app.py"), run_name="__main__")
    except SystemExit:
        raise
    except BaseException:                              # noqa: BLE001
        crash_report(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
