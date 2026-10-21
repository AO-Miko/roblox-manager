#!/usr/bin/env bash
# Who is an admin or the owner of Roblox Manager. The list is dist/roles.json, signed with the release key (dist/roles.json.sig);
# an account in it gets the Admin tab in the PC app. Only the key holder (the owner, on this PC) can change it.
#
#   tools/roles.sh set 12345678 owner|admin     give a role (or change it)
#   tools/roles.sh remove 12345678              take the role away
#   tools/roles.sh list
#   add --push to publish (signed commit on `release`, and `main`); without it the change stays local
#
# The file looks like:  {"serial": 3, "roles": {"239345228": "owner", "12345678": "admin"}}   (owner is above admin; see docs/ADMIN.md)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-}"
ID="${2:-}"
ROLE="${3:-}"
PUSH=""
for a in "$@"; do [[ "$a" == "--push" ]] && PUSH=1; done
[[ "$ROLE" == "--push" ]] && ROLE=""
KEY="${ROBLOX_MANAGER_SIGNING_KEY:-$HOME/.config/roblox-manager-release/signing_key}"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
mkdir -p dist

case "$ACTION" in
  list)
    python3 -I - <<'PY'
import json
d = json.load(open("dist/roles.json")) if __import__("os").path.exists("dist/roles.json") else {"serial": 0, "roles": {}}
print(f"serial {d['serial']}, {len(d['roles'])} role(s)")
for k, v in sorted(d["roles"].items(), key=lambda kv: (-{"owner": 2, "admin": 1}.get(kv[1], 0), int(kv[0]))):
    print(f"  {k}  {v}")
PY
    exit 0 ;;
  set) [[ "$ID" =~ ^[0-9]{1,15}$ && "$ROLE" =~ ^(owner|admin)$ ]] || { echo "usage: tools/roles.sh set USER_ID owner|admin"; exit 1; } ;;
  remove) [[ "$ID" =~ ^[0-9]{1,15}$ ]] || { echo "usage: tools/roles.sh remove USER_ID"; exit 1; } ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac

[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
python3 -I - "$ACTION" "$ID" "$ROLE" <<'PY'
import json, sys
action, uid, role = sys.argv[1:4]
d = json.load(open("dist/roles.json")) if __import__("os").path.exists("dist/roles.json") else {"serial": 0, "roles": {}}
if action == "set":
    d["roles"][uid] = role
else:
    if uid not in d["roles"]:
        sys.exit(f"{uid} has no role.")
    del d["roles"][uid]
if not any(v == "owner" for v in d["roles"].values()):
    sys.exit("Refused: there must be at least one owner.")
d["roles"] = dict(sorted(d["roles"].items(), key=lambda kv: int(kv[0])))
d["serial"] += 1
json.dump(d, open("dist/roles.json", "w"), indent=2)
open("dist/roles.json", "a").write("\n")
print(f"{action} {uid} {role}: serial {d['serial']}, {len(d['roles'])} role(s)")
PY
rm -f dist/roles.json.sig
ssh-keygen -q -Y sign -f "$KEY" -n roblox-manager-roles dist/roles.json
git add dist/roles.json dist/roles.json.sig
git commit -q -m "Roles: $ACTION $ID $ROLE"
git verify-commit HEAD
if [[ -n "$PUSH" ]]; then
  git push origin release
  git push origin release:main
  echo "Published. The apps pick it up within about ten minutes (at once at the next start)."
else
  echo "Done locally. Publish with: git push origin release release:main"
fi
