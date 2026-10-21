"""What is different on Windows: folders, DPAPI encryption of sign-ins, signature checks without ssh-keygen, TLS to GitHub.
Runs on Windows (also under Wine) and on Linux (then the Windows-only checks are skipped).
  python tests/test_windows_native.py           (RM_SRC = the app folder, default linux/ next to tests/)"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("RM_SRC") or HERE.parent / "linux")
FIX = Path(os.environ.get("RM_FIXTURES") or HERE / "fixtures")
tmp = Path(tempfile.mkdtemp(prefix="wintest-"))
sys.path.insert(0, str(SRC))
res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


import plat

# ---- folders
os.environ.pop("ROBLOX_MANAGER_CONFIG", None)
os.environ.pop("ROBLOX_MANAGER_STATE", None)
os.environ.pop("ROBLOX_MANAGER_UPDATE_CACHE", None)
if plat.IS_WIN:
    check("settings go to %APPDATA%\\RobloxManager", plat.config_dir().name == "RobloxManager" and "AppData" in str(plat.config_dir()) or str(plat.config_dir()).startswith(os.environ.get("APPDATA", "?")), plat.config_dir())
    check("state and cache go to %LOCALAPPDATA%\\RobloxManager", plat.state_dir().parts[-2:] == ("RobloxManager", "state") and plat.cache_dir().parts[-2:] == ("RobloxManager", "cache"), (plat.state_dir(), plat.cache_dir()))
    check("the update backend on Windows is the release one", plat.update_backend() == "release")
else:
    check("on Linux the folders are the XDG ones", ".config/roblox-manager" in plat.config_dir().as_posix() and ".local/state/roblox-manager" in plat.state_dir().as_posix())
    check("on Linux the update backend is git", plat.update_backend() == "git")
os.environ["ROBLOX_MANAGER_CONFIG"] = str(tmp / "cfg")
check("an environment variable overrides the folder", plat.config_dir() == tmp / "cfg")

# ---- encrypted sign-ins
os.environ.update({"ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
os.environ.pop("ROBLOX_MANAGER_VAULT", None)
import vault

if plat.IS_WIN:
    check("DPAPI is available", vault.available(refresh=True))
    secret = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you|_" + "x" * 900 + "é€"
    check("a sign-in can be stored", vault.put("account:1", secret))
    files = list((tmp / "cfg" / "vault").glob("*.bin"))
    check("...as one file in the settings folder", len(files) == 1, files)
    raw = files[0].read_bytes()
    check("...that does not contain the secret in any readable form", b"WARNING" not in raw and b"DO-NOT-SHARE" not in raw and secret.encode() not in raw and len(raw) > 100)
    check("...and reads back exactly", vault.get("account:1") == secret)
    check("another key has its own entry", vault.get("account:2") == "" and vault.put("account:2", "other") and vault.get("account:2") == "other" and vault.get("account:1") == secret)
    raw2 = files[0].read_bytes()
    vault.put("account:1", secret)
    check("storing again replaces it", vault.get("account:1") == secret and len(list((tmp / "cfg" / "vault").glob("*.bin"))) == 2)
    files[0].write_bytes(raw[:-5] + b"xxxxx")
    check("a damaged or foreign file gives nothing, not a crash", vault.get("account:1") == "")
    vault.delete("account:1")
    check("deleting removes it", vault.get("account:1") == "" and len(list((tmp / "cfg" / "vault").glob("*.bin"))) == 1)
    p = tmp / "plain-cookie"
    p.write_text("PLAINCOOKIE")
    check("a cookie in an old plain file moves into the encrypted store and the file is wiped", vault.read("account:9", p) == "PLAINCOOKIE" and not p.exists() and vault.get("account:9") == "PLAINCOOKIE")
    check("write() reports that it is encrypted", vault.write("account:10", tmp / "c10", "value") is True and not (tmp / "c10").exists())
else:
    print("SKIP  (DPAPI checks run on Windows only)")

# ---- signatures without ssh-keygen
import sshsig

data, sig, allowed = (FIX / "sample.bin").read_bytes(), (FIX / "sample.bin.sig").read_text(), (FIX / "allowed_signers").read_text()
check("a signature made by ssh-keygen verifies here", sshsig.verify(data, sig, allowed, "roblox-manager-release") == "fixture@test")
check("a changed file does not", sshsig.verify(data + b"!", sig, allowed, "roblox-manager-release") is None)

# ---- the update server over TLS, with this system's certificates
import updater

try:
    r = updater.release_latest({"repo": "https://github.com/AO-Miko/roblox-manager.git"})
    check("GitHub answers over https (the newest release is found)", bool(r["version"]), r["version"])
except updater.UpdateError as e:
    # any answer from GitHub (even an HTTP error such as a rate limit on a shared test machine) proves that TLS and the certificates work
    check("GitHub answers over https (a release without a package, or an HTTP error, is fine here)", "could not reach" not in str(e) or "HTTPError" in str(e), e)

print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
