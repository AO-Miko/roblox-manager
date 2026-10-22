"""Is there a Roblox launcher on this computer? Play (see tab_discover.py) asks first, and if there is none it offers to install one:

  Windows  the Roblox download page opens (the official installer)
  Linux    there is no official Roblox for Linux; the community runtime Sober (Flatpak) is offered, with the exact command shown, which runs only if you press Install
  (Android is the phone app's business: it offers the Play Store page of Roblox.)

Roblox registers its launcher as the handler of roblox:// links, so that is what is looked for.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

import plat
from ui_common import button, hint, open_url

DOWNLOAD_PAGE = "https://www.roblox.com/download"
SOBER_ID = "org.vinegarhq.Sober"
LINUX_COMMAND = ["flatpak", "install", "--user", "-y", "flathub", SOBER_ID]
FLATHUB_SETUP = "https://flathub.org/setup"
_cache = {"at": 0.0, "value": None}


def _run(args, timeout=6):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.returncode, (p.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _windows_installed():
    """The roblox:// protocol has a handler (the registry says which program), and that program exists."""
    try:
        import winreg
        for name in ("roblox", "roblox-player"):
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name + r"\shell\open\command") as k:
                    cmd = winreg.QueryValueEx(k, "")[0]
            except OSError:
                continue
            m = re.match(r'^\s*"([^"]+)"', cmd) or re.match(r"^\s*(\S+)", cmd)
            if m and os.path.isfile(m.group(1)):
                return True, m.group(1)
    except ImportError:
        pass
    return False, ""


def _linux_installed():
    if shutil.which("sober"):
        return True, "sober"
    code, out = _run(["xdg-mime", "query", "default", "x-scheme-handler/roblox"])
    if code == 0 and out:
        return True, out
    if shutil.which("flatpak"):
        code, out = _run(["flatpak", "list", "--app", "--columns=application"])
        if code == 0 and any(line.strip() == SOBER_ID for line in out.splitlines()):
            return True, SOBER_ID
    return False, ""


def status(fresh=False):
    """{'installed': bool, 'how': what was found, 'platform': 'windows'|'linux', 'command': list or None, 'url': page to open or None, 'can_install': bool}
    Remembered for half a minute (asking the system takes a moment)."""
    now = time.time()
    if not fresh and _cache["value"] is not None and now - _cache["at"] < 30:
        return _cache["value"]
    if plat.IS_WIN:
        ok, how = _windows_installed()
        value = {"installed": ok, "how": how, "platform": "windows", "command": None, "url": DOWNLOAD_PAGE, "can_install": False}
    else:
        ok, how = _linux_installed()
        has_flatpak = shutil.which("flatpak") is not None
        value = {"installed": ok, "how": how, "platform": "linux", "command": LINUX_COMMAND if has_flatpak else None, "url": FLATHUB_SETUP if not has_flatpak else None,
                 "can_install": has_flatpak}
    _cache.update(at=now, value=value)
    return value


def forget():
    _cache.update(at=0.0, value=None)


class InstallDialog(QDialog):
    """'Roblox is not installed': what to do about it. Windows: open the download page. Linux: the command, and Install runs exactly that command."""

    def __init__(self, parent, st):
        super().__init__(parent)
        self.st = st
        self.setWindowTitle("Roblox is not installed")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        title = QLabel("Roblox is not installed on this computer")
        title.setProperty("role", "title")
        lay.addWidget(title)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.hide()
        row = QHBoxLayout()
        row.addStretch()
        self.b_cancel = button("Cancel", self.reject)
        row.addWidget(self.b_cancel)
        self.command = None
        if st["platform"] == "windows":
            self.text.setText("Play needs the Roblox app. Do you want to open the Roblox download page? The official installer is there; run it, then press Play again.")
            self.b_go = button("Open the download page", self.open_page, primary=True)
            row.addWidget(self.b_go)
        elif st.get("command"):
            self.command = " ".join(st["command"])
            self.text.setText("There is no official Roblox for Linux. Sober, a community runtime for the Roblox app, can be installed from Flathub. "
                              "Do you want to install it? This is the command that will run (it needs the Flatpak tool, which you have):")
            self.cmd_box = QPlainTextEdit(self.command)
            self.cmd_box.setReadOnly(True)
            self.cmd_box.setMaximumHeight(44)
            lay.addWidget(self.cmd_box)
            self.b_copy = button("Copy command", self.copy_command)
            self.b_go = button("Install", self.install, primary=True)
            row.insertWidget(1, self.b_copy)
            row.addWidget(self.b_go)
        else:
            self.text.setText("There is no official Roblox for Linux, and Flatpak (needed for the community runtime Sober) is not installed. "
                              "Set up Flatpak and Flathub first (the page shows how), then press Play again.")
            self.b_go = button("Open the Flatpak setup page", self.open_page, primary=True)
            row.addWidget(self.b_go)
        lay.addWidget(self.log)
        self.status = hint("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addLayout(row)
        self.process = None

    def open_page(self):
        open_url(self.st["url"] or DOWNLOAD_PAGE)
        self.accept()

    def copy_command(self):
        from ui_common import copy_text
        copy_text(self.command)
        self.status.setText("Command copied.")

    def install(self):
        """Runs the command shown above, nothing else, and shows what it says."""
        self.b_go.setEnabled(False)
        self.b_copy.setEnabled(False)
        self.log.show()
        self.status.setText("Installing... this can take a few minutes.")
        threading.Thread(target=self._worker, daemon=True).start()
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(300)
        self._lines, self._done = [], None

    def _worker(self):
        try:
            p = subprocess.Popen(self.st["command"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                self._lines.append(line.rstrip())
            self._done = p.wait()
        except OSError as e:
            self._lines.append(str(e))
            self._done = 1

    def _poll(self):
        if self._lines:
            self.log.appendPlainText("\n".join(self._lines))
            self._lines.clear()
        if self._done is not None:
            self._timer.stop()
            forget()
            if self._done == 0 and status(fresh=True)["installed"]:
                self.status.setText("Installed. Press Play again.")
                self.b_cancel.setText("Close")
            else:
                self.status.setText("The install did not finish (see above). You can copy the command and run it in a terminal.")
                self.b_copy.setEnabled(True)
                self.b_cancel.setText("Close")


def ensure(parent):
    """True if a launcher is there. If not, the install dialog is shown and False is returned (the person presses Play again afterwards)."""
    st = status()
    if st["installed"]:
        return True
    InstallDialog(parent, st).exec()
    forget()
    return False
