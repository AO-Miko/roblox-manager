#!/usr/bin/env python3
"""Builds the Windows package on any computer (no Windows needed): roblox-manager-windows-VERSION.zip

The package is a folder with its own Python and libraries (nothing to install first):

  RobloxManager/
    python/          the official "embeddable" Python for Windows (python.org), configured to use the folders below
    site-packages/   PySide6 (Qt) and requests, the Windows builds from PyPI
    app/             the app itself: the repository's linux/ folder (the same code on both systems)
    trust/           the public key an update must be signed with
    Install.cmd, Uninstall.cmd, "Roblox Manager.cmd"

  python3 tools/build_windows.py [OUTPUT-FOLDER] [--no-prune]
"""
import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYVER = "3.12.8"
EMBED_SHA256 = "8d3f33be9eb810f23c102f08475af2854e50484b8e4e06275e937be61ce3d2fb"
EMBED_URL = f"https://www.python.org/ftp/python/{PYVER}/python-{PYVER}-embed-amd64.zip"
CACHE = Path.home() / ".cache" / "roblox-manager-build"

# Qt parts the app never uses (the web engine, widgets, network and core are kept). Leaving them out saves about half of the download.
UNUSED_QT = [
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender", "QtCharts", "QtDataVisualization", "QtGraphs",
    "QtGraphsWidgets", "QtMultimedia", "QtMultimediaWidgets", "QtSpatialAudio", "QtSensors", "QtBluetooth", "QtNfc", "QtSerialPort",
    "QtSerialBus", "QtTextToSpeech", "QtRemoteObjects", "QtScxml", "QtHttpServer", "QtLocation", "QtVirtualKeyboard", "QtQuick3D",
    "QtDesigner", "QtHelp", "QtUiTools", "QtTest", "QtQuickTest", "QtNetworkAuth", "QtWebView", "QtLabs", "QtCanvasPainter",
]
UNUSED_PLUGIN_DIRS = ["multimedia", "sensors", "texttospeech", "qmltooling", "sceneparsers", "geometryloaders", "renderers", "designer",
                      "virtualkeyboard", "canbus", "position", "scxmldatamodel", "assetimporters", "help"]
DROP_DIRS = ["include", "typesystems", "glue", "scripts", "support", "examples", "qml", "metatypes", "lib"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_python():
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"python-{PYVER}-embed-amd64.zip"
    if not f.exists():
        print("downloading", EMBED_URL)
        urllib.request.urlretrieve(EMBED_URL, f)
    if sha256(f) != EMBED_SHA256:
        f.unlink()
        sys.exit("The downloaded Python does not match the expected checksum; nothing was built.")
    return f


def fetch_wheels():
    """Only the exact files in tools/windows/requirements.lock (versions and SHA-256 hashes): a changed or replaced file on PyPI is refused. Update it on purpose with tools/windows/update_lock.py."""
    wheels = CACHE / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--dest", str(wheels), "--platform", "win_amd64", "--python-version", "3.12",
                    "--implementation", "cp", "--only-binary=:all:", "--require-hashes", "-r", str(ROOT / "tools/windows/requirements.lock")], check=True)
    return sorted(wheels.glob("*.whl"))


def unzip_safely(zf, dest):
    dest = dest.resolve()
    for m in zf.infolist():
        target = (dest / m.filename).resolve()
        if dest not in target.parents and target != dest:
            sys.exit(f"unsafe path in an archive: {m.filename}")
    zf.extractall(dest)


def prune(site):
    ps = site / "PySide6"
    for d in DROP_DIRS:
        shutil.rmtree(ps / d, ignore_errors=True)
    for p in ps.glob("*.pyi"):
        p.unlink()
    for name in UNUSED_QT:
        for pat in (f"{name}.pyd", f"{name}.pyi", f"Qt6{name[2:]}.dll", f"Qt6{name[2:]}*.dll"):
            for p in ps.glob(pat):
                p.unlink()
    for d in UNUSED_PLUGIN_DIRS:
        shutil.rmtree(ps / "plugins" / d, ignore_errors=True)
    tr = ps / "translations"
    if tr.exists():
        for p in tr.glob("*.qm"):
            p.unlink()                                  # (the web engine's own language files are in translations/qtwebengine_locales)
    for p in site.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for exe in ("pyside6-designer.exe", "pyside6-uic.exe", "pyside6-rcc.exe", "pyside6-lupdate.exe", "pyside6-linguist.exe", "assistant.exe", "designer.exe",
                "linguist.exe", "lrelease.exe", "lupdate.exe", "pyside6-assistant.exe", "pyside6-qml.exe", "qmlls.exe", "qmllint.exe", "qmlformat.exe"):
        for p in ps.glob(exe):
            p.unlink()


def make_icon(dest):
    """icon.ico from the app's icon.png (an .ico file can hold a PNG picture as it is)."""
    import struct
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage
    img = QImage(str(ROOT / "linux/icon.png")).scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png = bytes(ba)
    dest.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else ROOT / "build" / "windows"
    version = (ROOT / "linux/VERSION").read_text().strip()
    pkg = out / "RobloxManager"
    shutil.rmtree(out, ignore_errors=True)
    (pkg / "python").mkdir(parents=True)
    (pkg / "site-packages").mkdir()

    print("python", PYVER)
    with zipfile.ZipFile(fetch_python()) as z:
        unzip_safely(z, pkg / "python")
    (pkg / "python" / "python312._pth").write_text("python312.zip\n.\n..\\site-packages\nimport site\n")   # where Python looks: nothing outside this folder

    print("libraries")
    for w in fetch_wheels():
        with zipfile.ZipFile(w) as z:
            unzip_safely(z, pkg / "site-packages")
    if "--no-prune" not in sys.argv:
        prune(pkg / "site-packages")

    print("app", version)
    shutil.copytree(ROOT / "linux", pkg / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".installed.json"))
    (pkg / "trust").mkdir()
    shutil.copy(ROOT / "tools/trust/allowed_signers", pkg / "trust" / "allowed_signers")
    for f in list((ROOT / "tools/windows").glob("*.cmd")) + list((ROOT / "tools/windows").glob("*.ps1")):
        data = f.read_text().replace("\r\n", "\n").replace("\n", "\r\n")          # Windows scripts want CRLF line ends
        (pkg / f.name).write_bytes(data.encode("utf-8"))
    if not (ROOT / "linux/icon.ico").exists():                                    # (kept in linux/ so that updates carry it too)
        make_icon(ROOT / "linux/icon.ico")
    shutil.copy(ROOT / "linux/icon.ico", pkg / "app" / "icon.ico")
    (pkg / "README.txt").write_text(
        "Roblox Manager (Windows)\r\n\r\n"
        "Double-click Install.cmd to install it for your user (Start menu entry; no administrator rights needed),\r\n"
        "or double-click \"Roblox Manager.cmd\" to run it from this folder without installing.\r\n\r\n"
        "It updates itself at every start from https://github.com/AO-Miko/roblox-manager (only signed releases).\r\n"
        "Windows may show a SmartScreen warning because the program is not signed with a paid certificate: choose More info > Run anyway.\r\n")

    zip_path = out / f"roblox-manager-windows-{version}.zip"
    print("zipping", zip_path.name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(out).as_posix())
    print(f"{zip_path}  {zip_path.stat().st_size / 1e6:.0f} MB  sha256 {sha256(zip_path)}")


if __name__ == "__main__":
    main()
