#!/usr/bin/env python3
"""Writes tools/windows/requirements.lock: every library of the Windows package (the two in requirements.txt and everything they need) pinned to an exact version
and the SHA-256 of its file. The Windows build installs ONLY from that lock (pip --require-hashes), so a changed or replaced file on PyPI is refused instead of
ending up inside the package. Run it on purpose, when a library should be updated:

    python3 tools/windows/update_lock.py

It downloads the newest allowed versions once, records them, and pip-audits nothing by itself: look the result up in https://osv.dev before committing it.
"""
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix="wheels-") as d:
        subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--dest", d, "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp",
                        "--only-binary=:all:", "-r", str(HERE / "requirements.txt")], check=True)
        lines = []
        for w in sorted(Path(d).glob("*.whl"), key=lambda p: p.name.lower()):
            m = re.match(r"^([A-Za-z0-9_.]+)-([0-9][^-]*)-", w.name)
            if not m:
                sys.exit(f"cannot read the name of {w.name}")
            name, version = m.group(1).replace("_", "-"), m.group(2)
            lines.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(w.read_bytes()).hexdigest()}")
    (HERE / "requirements.lock").write_text("# made by tools/windows/update_lock.py: exact versions and file hashes of every library of the Windows package\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
