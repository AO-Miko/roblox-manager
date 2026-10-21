"""Test of the five-number version R.B.S.F.D (tools/version.py) and how the updater compares versions. Run: python3 tests/test_versions.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "linux"))
import version
import updater

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


check("an old three-number version is read as R.B.S.0.0", version.parse("1.7.0") == [1, 7, 0, 0, 0] and version.parse("1.8.0.0.0") == [1, 8, 0, 0, 0])
bad = 0
for x in ("1.2", "1.2.3.4.5.6", "a.b.c", "", "1..2", "1.2.x"):
    try:
        version.parse(x)
        bad += 1
    except ValueError:
        pass
check("...3 to 5 numbers only", bad == 0)

cur = "1.8.2.3.4"
check("each kind raises its own number by 1 and leaves the others alone",
      [version.next_version(k, cur) for k in ("big", "small", "fix", "design")] == ["1.9.2.3.4", "1.8.3.3.4", "1.8.2.4.4", "1.8.2.3.5"])
check("a complete rework raises the first number and sets the other four to 0", version.next_version("rework", cur) == "2.0.0.0.0")
check("the first update after an old 1.7.0 is 1.8.0.0.0 (big) or 1.7.0.1.0 (fix)", version.next_version("big", "1.7.0") == "1.8.0.0.0" and version.next_version("fix", "1.7.0") == "1.7.0.1.0")

ok_cases = ["1.9.2.3.4", "1.8.3.3.4", "1.8.2.4.4", "1.8.2.3.5", "2.0.0.0.0"]
check("valid next versions are accepted", all(version.why_not(v, cur) is None for v in ok_cases), [(v, version.why_not(v, cur)) for v in ok_cases])
bad_cases = {"1.8.2.3.4": "same", "1.7.2.3.4": "down (big)", "1.8.2.3.3": "down (design)", "1.8.2.5.4": "skips one", "1.9.3.3.4": "two at once",
             "1.9.0.0.0": "big resets the rest (only a rework may)", "2.0.2.3.4": "rework without resetting", "3.0.0.0.0": "rework skips one", "1.8.2": "three numbers",
             "1.8.2.3.4.1": "six numbers", "0.0.0.0.0": "down (rework)"}
check("everything else is refused: same, down, skipping, two at once, a reset that is not a rework", all(version.why_not(v, cur) for v in bad_cases),
      [v for v in bad_cases if not version.why_not(v, cur)])
check("the numbers never go down: a small feature after a big one keeps the big number", version.next_version("small", version.next_version("big", "1.7.0")) == "1.8.1.0.0")

# the Windows file-version field holds four numbers
check("file version: the first four numbers", version.text(version.parse("1.8.2.3.4")[:4]) == "1.8.2.3")
out = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "version.py"), "next", "design", "1.8.0.0.0"], capture_output=True, text=True)
check("the command line tool works", out.stdout.strip() == "1.8.0.0.1" and out.returncode == 0, out.stdout + out.stderr)
out = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "version.py"), "check", "1.8.0.0.5", "1.8.0.0.0"], capture_output=True, text=True)
check("...and says why a version is refused", out.returncode == 1 and "exactly one" in out.stdout, out.stdout)

# how the updater compares
k = updater.version_key
check("updater: numbers compare as numbers, number by number", k("1.10.0.0.0") > k("1.9.0.0.0") and k("1.8.0.1.0") > k("1.8.0.0.9") and k("2.0.0.0.0") > k("1.99.99.99.99"))
check("updater: an old 1.7.0 equals 1.7.0.0.0 and is older than 1.8.0.0.0", k("1.7.0") == k("1.7.0.0.0") and k("1.7.0") < k("1.8.0.0.0") and k("1.7.0") < k("1.7.0.0.1"))
check("updater: the version in the repository is one the tool understands", version.parse(version.current_version()) is not None, version.current_version())

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
