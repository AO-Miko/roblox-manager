#!/usr/bin/env python3
"""The version of Roblox Manager has five numbers:  R.B.S.F.D

    R  complete rework          (a new start: the numbers after it go back to 0)
    B  big feature change
    S  small feature change
    F  bug fix
    D  design rework

An update raises exactly one of them by 1. The numbers never go down; the only exception is that a complete rework (R) sets the other four back to 0.
Older versions with three numbers (1.7.0) are read as R.B.S with 0.0 after them (1.7.0.0.0).

  tools/version.py next KIND [CURRENT]   the next version after CURRENT (default: linux/VERSION); KIND: rework, big, small, fix or design
  tools/version.py check NEW [CURRENT]   exit 0 if NEW is a valid next version of CURRENT, else say why
  tools/version.py file NEW              the first four numbers (what a Windows file-version field can hold)
"""
import re
import sys
from pathlib import Path

KINDS = ("rework", "big", "small", "fix", "design")
NAMES = ("complete rework", "big feature change", "small feature change", "bug fix", "design rework")


def parse(text):
    """[R, B, S, F, D] from '1.7.0' or '1.8.0.0.0'; ValueError if it is not made of 3 to 5 numbers."""
    if not re.fullmatch(r"\d+(\.\d+){2,4}", str(text).strip()):
        raise ValueError(f"'{text}' is not a version (five numbers like 1.8.0.0.0; older ones have three)")
    parts = [int(x) for x in str(text).strip().split(".")]
    return parts + [0] * (5 - len(parts))


def text(parts):
    return ".".join(str(p) for p in parts)


def next_version(kind, current):
    i = KINDS.index(kind)
    parts = parse(current)
    parts[i] += 1
    if i == 0:
        parts[1:] = [0, 0, 0, 0]
    return text(parts)


def why_not(new, current):
    """None if `new` is a valid next version of `current`, else the reason."""
    try:
        n, c = parse(new), parse(current)
    except ValueError as e:
        return str(e)
    if len(str(new).split(".")) != 5:
        return "the version needs five numbers (R.B.S.F.D)"
    changed = [i for i in range(5) if n[i] != c[i]]
    if not changed:
        return "that is the current version"
    if n[0] != c[0]:
        if n[0] != c[0] + 1 or n[1:] != [0, 0, 0, 0]:
            return "a complete rework raises the first number by 1 and sets the other four to 0"
        return None
    if len(changed) != 1 or n[changed[0]] != c[changed[0]] + 1:
        return f"an update raises exactly one number by 1 ({', '.join(NAMES)}); the numbers never go down"
    return None


def current_version():
    return (Path(__file__).resolve().parent.parent / "linux" / "VERSION").read_text().strip()


def main(argv):
    if len(argv) >= 3 and argv[1] == "next" and argv[2] in KINDS:
        print(next_version(argv[2], argv[3] if len(argv) > 3 else current_version()))
        return 0
    if len(argv) >= 3 and argv[1] == "check":
        reason = why_not(argv[2], argv[3] if len(argv) > 3 else current_version())
        if reason:
            print(reason)
            return 1
        return 0
    if len(argv) == 3 and argv[1] == "file":
        print(text(parse(argv[2])[:4]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except ValueError as e:
        print(e)
        sys.exit(1)
