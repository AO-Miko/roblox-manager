"""Tests of the pure-Python signature check against OpenSSH itself (ssh-keygen). Run: python3 tests/test_sshsig.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linux"))
import sshsig

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


# RFC 8032 section 7.1, test vectors 1 and 2
v1 = (bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"), b"",
      bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"))
v2 = (bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"), bytes.fromhex("72"),
      bytes.fromhex("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"))
check("RFC 8032 vector 1 verifies", sshsig.ed25519_verify(*v1))
check("RFC 8032 vector 2 verifies", sshsig.ed25519_verify(*v2))
check("a changed message does not verify", not sshsig.ed25519_verify(v2[0], b"73", v2[2]))
bad = bytearray(v2[2]); bad[40] ^= 1
check("a changed signature does not verify", not sshsig.ed25519_verify(v2[0], v2[1], bytes(bad)))
check("garbage input is refused, not a crash", not sshsig.ed25519_verify(b"x", b"m", b"y") and not sshsig.ed25519_verify(b"\xff" * 32, b"m", b"\xff" * 64))

tmp = Path(tempfile.mkdtemp(prefix="sshsig-"))


def keygen(name):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(tmp / name)], check=True)
    pub = (tmp / (name + ".pub")).read_text().strip()
    return pub


def sign(name, data, ns):
    f = tmp / ("data-" + name)
    f.write_bytes(data)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(tmp / name), "-n", ns, str(f)], check=True)
    return (tmp / ("data-" + name + ".sig")).read_text()


pub_a = keygen("alice")
pub_b = keygen("mallory")
allowed = f'release@example namespaces="git,roblox-manager-release" {pub_a}\n'
data = b"the update package " * 1000
sig = sign("alice", data, "roblox-manager-release")

check("a real ssh-keygen signature by a trusted key verifies", sshsig.verify(data, sig, allowed, "roblox-manager-release") == "release@example")
check("openssh agrees (reference check)", subprocess.run(
    ["ssh-keygen", "-Y", "verify", "-f", str(tmp / "allowed"), "-I", "release@example", "-n", "roblox-manager-release", "-s", str(tmp / "data-alice.sig")],
    input=data, capture_output=True).returncode == 0 if (tmp / "allowed").write_text(allowed) else False)
check("a changed file is refused", sshsig.verify(data + b"x", sig, allowed, "roblox-manager-release") is None)
check("another namespace is refused", sshsig.verify(data, sig, allowed, "git") is None)
check("a key that is not trusted is refused", sshsig.verify(data, sign("mallory", data, "roblox-manager-release"), allowed, "roblox-manager-release") is None)
check("a trusted key limited to other namespaces is refused", sshsig.verify(data, sig, f'release@example namespaces="git" {pub_a}\n', "roblox-manager-release") is None)
check("a line without namespace options is trusted for any", sshsig.verify(data, sig, f"release@example {pub_a}\n", "roblox-manager-release") == "release@example")
check("a damaged signature is refused", sshsig.verify(data, sig.replace("A", "B", 3), allowed, "roblox-manager-release") is None and sshsig.verify(data, "nonsense", allowed, "x") is None)
check("an empty trust list trusts nobody", sshsig.verify(data, sig, "", "roblox-manager-release") is None)
real = (ROOT / "tools/trust/allowed_signers").read_text()
check("the project's allowed_signers file parses", len(sshsig.parse_allowed_signers(real)) == 1, sshsig.parse_allowed_signers(real)[:1] and sshsig.parse_allowed_signers(real)[0][:2])
print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
