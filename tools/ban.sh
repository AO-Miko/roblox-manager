#!/usr/bin/env bash
# Ban or unban a Roblox user id in all three apps. The list is dist/bans.json, signed with the release key (dist/bans.json.sig);
# the apps check it at every start, every sign-in and every ten minutes, and sign a banned account out and forget it at once.
#
#   tools/ban.sh ban 12345678 "reason shown to the person"     (the reason is optional, at most 200 characters)
#   tools/ban.sh unban 12345678 ["why, optional"]
#   tools/ban.sh list [--json]
#   --by ID     the Roblox user id of whoever does this (the Admin tab passes it); the roles in dist/roles.json decide what is allowed:
#               nobody bans themselves, nobody bans someone with the same or a higher role, an unban needs at least the role of the ban's author.
#               Roles, high to low: owner, co-owner, senior-admin, admin, trusted-friend. From admin up they may ban (trusted friends may not).
#               Without --by the action is the owner's own (the key holder): it can ban everybody with a lower role but not another owner.
#   --push      publish (signed commit on `release`, and `main`); without it the change stays local
#
# No new app version is needed: the apps read the list from GitHub. (GitHub's cache can delay it by a few minutes.)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-}"
ID=""
REASON=""
BY=""
PUSH=""
JSON=""
shift || true
POS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1 ;;
    --json) JSON=1 ;;
    --by) BY="${2:-}"; shift ;;
    *) POS+=("$1") ;;
  esac
  shift
done
ID="${POS[0]:-}"
REASON="${POS[1]:-}"
KEY="${ROBLOX_MANAGER_SIGNING_KEY:-$HOME/.config/roblox-manager-release/signing_key}"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
mkdir -p dist
[[ -f dist/bans.json ]] || printf '{\n  "serial": 0,\n  "bans": []\n}\n' > dist/bans.json

case "$ACTION" in
  list)
    python3 -I - "$JSON" <<'PY'
import json, sys
d = json.load(open("dist/bans.json"))
if sys.argv[1]:
    print(json.dumps(d))
    sys.exit(0)
print(f"serial {d['serial']}, {len(d['bans'])} ban(s)")
for b in d["bans"]:
    print(f"  {b['id']}  {b.get('reason', '')}  ({b.get('since', '')}, by {b.get('by') or 'owner'})")
PY
    exit 0 ;;
  ban|unban) [[ "$ID" =~ ^[0-9]{1,15}$ ]] || { echo "The user id must be a number (the digits in roblox.com/users/NUMBER/profile)"; exit 1; } ;;
  *) sed -n 2,16p "$0"; exit 2 ;;
esac
[[ -z "$BY" || "$BY" =~ ^[0-9]{1,15}$ ]] || { echo "--by must be a user id"; exit 1; }

[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
python3 -I - "$ACTION" "$ID" "$REASON" "$BY" <<'PY'
import datetime, json, sys
action, uid, reason, by = sys.argv[1], int(sys.argv[2]), sys.argv[3][:200], sys.argv[4]
RANKS = {"trusted-friend": 1, "admin": 2, "senior-admin": 3, "co-owner": 4, "owner": 5}
NAMES = {v: k.replace("-", " ") for k, v in RANKS.items()}
try:
    roles = {int(k): RANKS.get(str(v).strip().lower().replace(" ", "-").replace("_", "-"), 0) for k, v in json.load(open("dist/roles.json")).get("roles", {}).items()}
except (OSError, ValueError):
    roles = {}
if by:
    actor_rank = roles.get(int(by), 0)
    if actor_rank < 2:
        sys.exit("Refused: your role has no moderation powers." if actor_rank else "Refused: you are not on the staff.")
else:
    actor_rank = 5                                   # the key holder acting without an account
target_rank = roles.get(uid, 0)
d = json.load(open("dist/bans.json"))
old = next((b for b in d["bans"] if b["id"] == uid), None)
if action == "ban":
    if by and int(by) == uid:
        sys.exit("Refused: you cannot ban yourself.")
    if target_rank >= actor_rank:
        sys.exit(f"Refused: {uid} is a {NAMES[target_rank]}, with the same role as you or a higher one.")
else:
    if by and int(by) == uid:
        sys.exit("Refused: you cannot unban yourself.")
    if old is None:
        sys.exit(f"{uid} is not banned.")
    if actor_rank < int(old.get("rank", 5)):
        sys.exit("Refused: this ban was placed by someone with a higher role than yours.")
d["bans"] = [b for b in d["bans"] if b["id"] != uid]
if action == "ban":
    d["bans"].append({"id": uid, "reason": reason, "since": datetime.date.today().isoformat(), "by": int(by) if by else None, "rank": actor_rank})
d["bans"].sort(key=lambda b: b["id"])
d["serial"] += 1
json.dump(d, open("dist/bans.json", "w"), indent=2, ensure_ascii=False)
open("dist/bans.json", "a").write("\n")
print(f"{action} {uid}: serial {d['serial']}, {len(d['bans'])} ban(s)")
PY
rm -f dist/bans.json.sig
ssh-keygen -q -Y sign -f "$KEY" -n roblox-manager-bans dist/bans.json
git add dist/bans.json dist/bans.json.sig
git commit -q -m "Ban list: $ACTION $ID${BY:+ (by $BY)}${REASON:+: $REASON}"
git verify-commit HEAD
if [[ -n "$PUSH" ]]; then
  git push origin release
  git push origin release:main
  echo "Published. The apps pick it up within about ten minutes (at once at the next sign-in or start)."
else
  echo "Done locally. Publish with: git push origin release release:main"
fi
