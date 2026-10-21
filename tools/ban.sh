#!/usr/bin/env bash
# Ban or unban a Roblox user id in all three apps. The list is dist/bans.json, signed with the release key (dist/bans.json.sig);
# the apps check it at every start, every sign-in and every ten minutes, and sign a banned account out and forget it at once.
#
#   tools/ban.sh ban 12345678 "reason shown to the person"     (the reason is optional, at most 200 characters)
#   tools/ban.sh unban 12345678
#   tools/ban.sh list
#   add --push to publish (signed commit on `release`, and `main`); without it the change stays local
#
# No new app version is needed: the apps read the list from GitHub. (GitHub's cache can delay it by a few minutes.)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-}"
ID="${2:-}"
REASON="${3:-}"
PUSH=""
for a in "$@"; do [[ "$a" == "--push" ]] && PUSH=1; done
[[ "$REASON" == "--push" ]] && REASON=""
KEY="$HOME/.config/roblox-manager-release/signing_key"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
mkdir -p dist
[[ -f dist/bans.json ]] || printf '{\n  "serial": 0,\n  "bans": []\n}\n' > dist/bans.json

case "$ACTION" in
  list)
    python3 -I - <<'PY'
import json
d = json.load(open("dist/bans.json"))
print(f"serial {d['serial']}, {len(d['bans'])} ban(s)")
for b in d["bans"]:
    print(f"  {b['id']}  {b.get('reason', '')}  ({b.get('since', '')})")
PY
    exit 0 ;;
  ban|unban) [[ "$ID" =~ ^[0-9]{1,15}$ ]] || { echo "The user id must be a number (the digits in roblox.com/users/NUMBER/profile)"; exit 1; } ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac

[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
python3 -I - "$ACTION" "$ID" "$REASON" <<'PY'
import datetime, json, sys
action, uid, reason = sys.argv[1], int(sys.argv[2]), sys.argv[3][:200]
d = json.load(open("dist/bans.json"))
d["bans"] = [b for b in d["bans"] if b["id"] != uid]
if action == "ban":
    d["bans"].append({"id": uid, "reason": reason, "since": datetime.date.today().isoformat()})
d["bans"].sort(key=lambda b: b["id"])
d["serial"] += 1
json.dump(d, open("dist/bans.json", "w"), indent=2, ensure_ascii=False)
open("dist/bans.json", "a").write("\n")
print(f"{action} {uid}: serial {d['serial']}, {len(d['bans'])} ban(s)")
PY
rm -f dist/bans.json.sig
ssh-keygen -q -Y sign -f "$KEY" -n roblox-manager-bans dist/bans.json
git add dist/bans.json dist/bans.json.sig
git commit -q -m "Ban list: $ACTION $ID"
git verify-commit HEAD
if [[ -n "$PUSH" ]]; then
  git push origin release
  git push origin release:main
  echo "Published. The apps pick it up within about ten minutes (at once at the next sign-in or start)."
else
  echo "Done locally. Publish with: git push origin release release:main"
fi
