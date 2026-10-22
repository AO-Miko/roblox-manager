#!/usr/bin/env bash
# The update policy: which versions were released to everybody (dist/policy.json, signed with the release key as dist/policy.json.sig).
# An app that has missed `limit` (2) of them cannot be used until it is updated (see linux/policy.py and docs/UPDATES.md). Betas are not in the list.
#
#   tools/policy.sh                       rewrite dist/policy.json from the stable GitHub releases (needs `gh`), sign it
#   tools/policy.sh --with 1.10.0.0.0     ... and count this version too (a release that is being made: release.sh does this for stable releases)
#   tools/policy.sh --all --with 1.11.0.0.0   also write the "beta" list (every release, betas included): the apps on the Beta channel count it. release.sh does this
#                                         for every beta release, on the beta branch (--with then counts the version in the beta list only)
#   tools/policy.sh --limit 3             change the number of updates an app may miss (default 2)
#   tools/policy.sh --commit [--push]     also commit it on `release` (signed), and push `release` and `main`
#
# promote.sh runs `tools/policy.sh --commit --push` after a beta became the stable version.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WITH=""; LIMIT=""; COMMIT=""; PUSH=""; ALL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with) WITH="${2:?--with needs a version}"; shift ;;
    --limit) LIMIT="${2:?--limit needs a number}"; shift ;;
    --all) ALL=1 ;;
    --commit) COMMIT=1 ;;
    --push) PUSH=1; COMMIT=1 ;;
    *) sed -n 2,12p "$0"; exit 2 ;;
  esac
  shift
done
KEY="${ROBLOX_MANAGER_SIGNING_KEY:-$HOME/.config/roblox-manager-release/signing_key}"
if [[ -n "$COMMIT" ]]; then
  [[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
  [[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
fi
mkdir -p dist
python3 -I - "$WITH" "$LIMIT" "$ALL" <<'PY'
import json, os, re, subprocess, sys
sys.path.insert(0, "tools")
import version
with_v, limit, want_all = sys.argv[1], sys.argv[2], sys.argv[3]
out = subprocess.run(["gh", "release", "list", "--exclude-pre-releases", "--limit", "300", "--json", "tagName"], capture_output=True, text=True)
if out.returncode:
    sys.exit("Could not list the releases: " + out.stderr.strip())
versions = [r["tagName"].lstrip("v") for r in json.loads(out.stdout)]
if with_v:
    version.parse(with_v)
    if not want_all:
        versions.append(with_v)


def spelled(names):
    best = {}
    for v in names:
        if not re.fullmatch(r"\d+(\.\d+){1,4}", v):
            continue
        k = tuple(version.parse(v))
        if k not in best or len(v.split(".")) > len(best[k].split(".")):        # (1.9.0.0 and 1.9.0.0.0 are one version: keep the five-number spelling)
            best[k] = v
    return [best[k] for k in sorted(best)]


best = {tuple(version.parse(v)): v for v in spelled(versions)}
old = {"serial": 0, "limit": 2}
if os.path.exists("dist/policy.json"):
    old = json.load(open("dist/policy.json"))
new = {"serial": int(old.get("serial", 0)) + 1, "limit": int(limit) if limit else int(old.get("limit", 2)), "stable": [best[k] for k in sorted(best)]}
if want_all:
    every = subprocess.run(["gh", "release", "list", "--exclude-drafts", "--limit", "300", "--json", "tagName"], capture_output=True, text=True)
    if every.returncode:
        sys.exit("Could not list the releases: " + every.stderr.strip())
    names = [r["tagName"].lstrip("v") for r in json.loads(every.stdout)] + ([with_v] if with_v else [])
    new["beta"] = spelled(names)
json.dump(new, open("dist/policy.json", "w"), indent=2)
open("dist/policy.json", "a").write("\n")
print(f"policy serial {new['serial']}: limit {new['limit']}, {len(new['stable'])} stable versions, newest {new['stable'][-1] if new['stable'] else '-'}")
PY
rm -f dist/policy.json.sig
ssh-keygen -q -Y sign -f "$KEY" -n roblox-manager-policy dist/policy.json
if [[ -n "$COMMIT" ]]; then
  git add dist/policy.json dist/policy.json.sig
  git commit -q -m "Update policy: $(python3 -I -c 'import json;d=json.load(open("dist/policy.json"));print("serial", d["serial"], "newest", d["stable"][-1])')"
  git verify-commit HEAD
  if [[ -n "$PUSH" ]]; then
    git push origin release
    git push origin release:main
    echo "Published. The apps pick it up within about ten minutes."
  fi
fi
