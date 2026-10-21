"""Tests of the release-package updater (the Windows backend: no git, signed tar.gz from GitHub releases). Real ssh-keygen signatures,
a fake update server. Run: python3 tests/test_updater_release.py"""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="relupd-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"),
                   "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache"), "ROBLOX_MANAGER_UPDATE_BACKEND": "release"})
sys.path.insert(0, str(ROOT / "linux"))
import updater

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:220]) if e else ""))


def keygen(name):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(tmp / name)], check=True)
    return (tmp / (name + ".pub")).read_text().strip()


def sign(name, data):
    f = tmp / ("blob-" + name)
    f.write_bytes(data)
    (tmp / ("blob-" + name + ".sig")).unlink(missing_ok=True)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(tmp / name), "-n", "roblox-manager-release", str(f)], check=True)
    return (tmp / ("blob-" + name + ".sig")).read_bytes()


def package(version, extra=None, links=False, evil_path=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        files = {"linux/app.py": b"print('app')\n", "linux/VERSION": (version + "\n").encode(), "linux/ok.py": b"x = 1\n", **(extra or {})}
        if evil_path:
            files[evil_path] = b"evil"
        for n, b in files.items():
            ti = tarfile.TarInfo(n); ti.size = len(b); tf.addfile(ti, io.BytesIO(b))
        if links:
            ti = tarfile.TarInfo("linux/link"); ti.type = tarfile.SYMTYPE; ti.linkname = "/etc/passwd"; tf.addfile(ti)
    return buf.getvalue()


pub = keygen("release")
keygen("mallory")
(tmp / "cfg").mkdir()
(tmp / "cfg" / "trusted_signers").write_text(f'release@test namespaces="git,roblox-manager-release" {pub}\n')
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.0.0\n")
(tmp / "app" / "app.py").write_text("print('old')\n")
updater.save_config({"repo": "https://github.com/someone/rm.git", "branch": "release", "auto": True, "require_signature": True})

served = {}


def serve_release(version, data, sig, with_sig_asset=True):
    base = f"https://dl.example/{version}/"
    assets = [{"name": f"roblox-manager-app-{version}.tar.gz", "browser_download_url": base + "pkg.tar.gz"}]
    if with_sig_asset:
        assets.append({"name": f"roblox-manager-app-{version}.tar.gz.sig", "browser_download_url": base + "pkg.sig"})
    served.clear()
    served["https://api.github.com/repos/someone/rm/releases/latest"] = json.dumps({"tag_name": "v" + version, "assets": assets}).encode()
    served[base + "pkg.tar.gz"] = data
    served[base + "pkg.sig"] = sig


real_get = updater._http_get


def fake_get(url, limit=updater.MAX_BYTES, timeout=25):
    if not url.startswith("https://"):
        raise updater.UpdateError("refusing an address that is not https")
    if url not in served:
        raise updater.UpdateError("could not reach the update server (404)")
    return served[url]


updater._http_get = fake_get

# up to date / nothing newer
serve_release("1.0.0", package("1.0.0"), b"")
r = updater.check()
check("the same version is up to date", r["status"] == "up-to-date", r)
serve_release("0.9.0", package("0.9.0"), b"")
check("an older release is never offered (no going back)", updater.check()["status"] == "up-to-date")

# a good update
good = package("1.1.0")
serve_release("1.1.0", good, sign("release", good))
r = updater.check()
check("a newer release is available", r["status"] == "available" and r["remote"] == "v1.1.0", r)
r = updater.apply()
check("a package signed by the trusted key installs", r["status"] == "updated" and r["signer"] == "release@test" and updater.version() == "1.1.0", r)
check("...the previous version is kept and the marker says what is installed", (tmp / "app.previous" / "VERSION").read_text().strip() == "1.0.0" and updater.installed()["version"] == "1.1.0")
check("...and nothing is left behind in staging", not [p for p in tmp.iterdir() if ".new-" in p.name])
rb = updater.rollback()
check("rolling back puts 1.0.0 back", rb["status"] == "rolled-back" and updater.version() == "1.0.0", rb)

# refused ones: the installed version stays
def refused(name, data, sig, version="1.2.0", **kw):
    serve_release(version, data, sig, **kw)
    r = updater.apply()
    check(name, r["status"] in ("refused", "error") and updater.version() == "1.0.0", r)
    return r


pkg = package("1.2.0")
refused("a package signed by an untrusted key is refused", pkg, sign("mallory", pkg))
refused("a package with a damaged signature is refused", pkg, b"-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n")
refused("a package changed after signing is refused", pkg + b"\0", sign("release", pkg))
signed_other = package("1.2.0")
refused("a package whose version differs from its release is refused (replay of an old signed package)", package("1.0.5"), sign("release", package("1.0.5")), version="1.2.0")
refused("a package with a path outside the app folder is refused", package("1.2.0", evil_path="../evil.py"), sign("release", package("1.2.0", evil_path="../evil.py")))
lk = package("1.2.0", links=True)
refused("a package with a link is refused", lk, sign("release", lk))
bad_py = package("1.2.0", extra={"linux/broken.py": b"def (:\n"})
refused("a package with a broken Python file is refused", bad_py, sign("release", bad_py))
serve_release("1.2.0", pkg, b"", with_sig_asset=False)
r = updater.check()
check("a release without a signature file is reported, not installed", r["status"] == "error" and "signed" in r["message"], r)
check("(the failed attempts changed nothing)", (tmp / "app" / "app.py").read_text() == "print('old')\n" and not (tmp / "app" / "broken.py").exists())

# switching the signature check off
updater.save_config({"repo": "https://github.com/someone/rm.git", "branch": "release", "auto": True, "require_signature": False})
serve_release("1.3.0", package("1.3.0"), b"")
r = updater.apply()
check("(only with the signature requirement off) an unsigned package installs", r["status"] == "updated" and updater.version() == "1.3.0", r)
updater.save_config({"repo": "https://github.com/someone/rm.git", "branch": "release", "auto": True, "require_signature": True})

# the server address
updater.save_config({"repo": "https://example.com/not-github", "branch": "release", "auto": True, "require_signature": True})
r = updater.check()
check("an address that is not GitHub is explained", r["status"] == "error" and "GitHub" in r["message"], r)
try:
    real_get("http://example.com/x")
    check("plain http is refused", False)
except updater.UpdateError:
    check("plain http is refused", True)
check("version numbers compare as numbers, not text", updater.version_key("1.10.0") > updater.version_key("1.9.0") and updater.version_key("2.0") > updater.version_key("1.99.9"))
updater.save_config({"repo": "https://github.com/someone/rm.git", "branch": "release", "auto": True, "require_signature": True})
os.environ["ROBLOX_MANAGER_UPDATE_BACKEND"] = "release"
updater.boot()
check("boot() never raises", True)

print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
