"""Static check of the whole desktop app: every `module.name` it uses exists in that module, and every method it calls on the Roblox client exists on rbx.Client.
A call to something that does not exist is an error waiting for the first person who clicks that button (a test that replaces the method with a stand-in would
never notice). Run: QT_QPA_PLATFORM=offscreen python3 tests/test_api_surface.py"""
import ast
import importlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="surface-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache"), "QT_QPA_PLATFORM": "offscreen"})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0.0.0\n")
LINUX = ROOT / "linux"
sys.path.insert(0, str(LINUX))
import browser_login  # noqa: F401
from PySide6.QtWidgets import QApplication

qapp = QApplication(sys.argv)
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:400]) if e else ""))


files = sorted(p for p in LINUX.glob("*.py") if p.name not in ("launcher.py",))
names = {p.stem for p in files}
mods = {}
for n in sorted(names):
    try:
        mods[n] = importlib.import_module(n)
    except Exception as e:                                # noqa: BLE001
        check(f"{n} imports", False, f"{e.__class__.__name__}: {e}")
check("every module of the app imports", len(mods) == len(names), sorted(names - set(mods)))

import rbx
import ui_common
if os.environ.get("SURFACE_NEGATIVE"):                    # (a control: take a method away, the check must then fail)
    delattr(rbx.Client, os.environ["SURFACE_NEGATIVE"])
client_attrs = set(dir(rbx.Client())) | set(dir(rbx.Client))
ctx_attrs = set(dir(ui_common.Context)) | {"client", "window", "async_", "client_factory", "busy_checks", "stoppers"}

problems = []
for p in files:
    tree = ast.parse(p.read_text(encoding="utf-8"))
    local = {}                                            # names in this file that stand for a module of the app
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in mods:
                    local[a.asname or a.name] = mods[a.name]
        elif isinstance(node, ast.ImportFrom) and node.module in mods and node.level == 0:
            for a in node.names:
                if a.name != "*" and not hasattr(mods[node.module], a.name):
                    problems.append(f"{p.name}:{node.lineno} from {node.module} import {a.name}: no such name")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        v = node.value
        # module.name
        if isinstance(v, ast.Name) and v.id in local and not isinstance(node.ctx, ast.Store):
            if not hasattr(local[v.id], node.attr):
                problems.append(f"{p.name}:{node.lineno} {v.id}.{node.attr}: the module has no such name")
        # <something>.client.method  or  client.method
        is_client = (isinstance(v, ast.Attribute) and v.attr == "client") or (isinstance(v, ast.Name) and v.id == "client")
        if is_client and not isinstance(node.ctx, ast.Store) and node.attr not in client_attrs:
            problems.append(f"{p.name}:{node.lineno} client.{node.attr}: rbx.Client has no such method or attribute")
        # ctx.name / self.ctx.name
        is_ctx = (isinstance(v, ast.Attribute) and v.attr == "ctx") or (isinstance(v, ast.Name) and v.id == "ctx")
        if is_ctx and not isinstance(node.ctx, ast.Store) and node.attr not in ctx_attrs:
            problems.append(f"{p.name}:{node.lineno} ctx.{node.attr}: Context has no such name")

check("every module.name the app uses exists, and every client method it calls exists", not problems, "\n  " + "\n  ".join(problems))
check("the guard sees the calls (the app calls the client in many places)", sum(1 for p in files for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.Attribute)
                                                                                 and isinstance(n.value, ast.Attribute) and n.value.attr == "client") > 40)

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
