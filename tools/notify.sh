#!/usr/bin/env bash
# Send a notification to everybody who uses the app (Linux, Windows and Android). The list is dist/notifications.json, signed with the release key
# (dist/notifications.json.sig); the apps fetch it at every start and every ten minutes, show a red number for the ones not read yet, and a pop-up
# for a new one. Only a list signed with the release key is believed, so nobody else can put a message into the apps.
#
#   tools/notify.sh send "Title" "Text of the message" [options] [--push]
#       --level info|important|warning     default info (important and warning are tinted)
#       --link https://...                 a button "Open link" (https only)
#       --channel all|beta|stable          who gets it: everybody (default), or only the Beta or only the Stable channel
#       --expires YYYY-MM-DD               hidden after that day
#       --id NAME                          letters, digits . _ - (at most 40); default: today's date and the title
#   tools/notify.sh remove ID [--push]     take a notification away (it disappears from the apps)
#   tools/notify.sh list [--json]
#   --push      publish (signed commit on `release`, and `main`); without it the change stays local
#
# Title: at most 80 characters. Text: at most 1000, shown as plain text. The newest 50 are kept. No new app version is needed: the apps read the list
# from GitHub (its cache can delay a change by a few minutes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-}"
shift || true
POS=()
LEVEL="info"; LINK=""; CHANNEL="all"; EXPIRES=""; NID=""; PUSH=""; JSON=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1 ;;
    --json) JSON=1 ;;
    --level) LEVEL="${2:-}"; shift ;;
    --link) LINK="${2:-}"; shift ;;
    --channel) CHANNEL="${2:-}"; shift ;;
    --expires) EXPIRES="${2:-}"; shift ;;
    --id) NID="${2:-}"; shift ;;
    *) POS+=("$1") ;;
  esac
  shift
done
KEY="${ROBLOX_MANAGER_SIGNING_KEY:-$HOME/.config/roblox-manager-release/signing_key}"
case "$ACTION" in
  list)
    python3 -I - "$JSON" <<'PY'
import json, sys
try:
    d = json.load(open("dist/notifications.json"))
except OSError:
    d = {"serial": 0, "notifications": []}
if sys.argv[1]:
    print(json.dumps(d))
    sys.exit(0)
print(f"serial {d['serial']}, {len(d['notifications'])} notification(s)")
for n in d["notifications"]:
    extra = ", ".join(f"{k} {n[k]}" for k in ("channel", "expires") if n.get(k) and n[k] != "all")
    print(f"  {n['id']}  [{n.get('level', 'info')}]  {n['title']}" + (f"  ({extra})" if extra else ""))
PY
    exit 0 ;;
  send) [[ ${#POS[@]} -ge 2 ]] || { sed -n 2,19p "$0"; exit 2; } ;;
  remove) [[ ${#POS[@]} -ge 1 ]] || { sed -n 2,19p "$0"; exit 2; } ;;
  *) sed -n 2,19p "$0"; exit 2 ;;
esac
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
mkdir -p dist
[[ -f dist/notifications.json ]] || printf '{\n  "serial": 0,\n  "notifications": []\n}\n' > dist/notifications.json

python3 -I - "$ACTION" "$LEVEL" "$LINK" "$CHANNEL" "$EXPIRES" "$NID" "${POS[@]}" <<'PY'
import datetime, json, re, sys
action, level, link, channel, expires, nid = sys.argv[1:7]
pos = sys.argv[7:]
d = json.load(open("dist/notifications.json"))
if action == "send":
    title, body = pos[0].strip(), pos[1].strip()
    if not title or len(title) > 80:
        sys.exit("Refused: the title must be 1 to 80 characters.")
    if len(body) > 1000:
        sys.exit("Refused: the text can be at most 1000 characters.")
    if level not in ("info", "important", "warning"):
        sys.exit("Refused: --level is info, important or warning.")
    if channel not in ("all", "beta", "stable"):
        sys.exit("Refused: --channel is all, beta or stable.")
    if link and (not link.lower().startswith("https://") or len(link) > 300):
        sys.exit("Refused: the link must start with https:// and be at most 300 characters.")
    if expires and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires):
        sys.exit("Refused: --expires is a day like 2026-12-31.")
    today = datetime.date.today().isoformat()
    if not nid:
        nid = (today + "-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"))[:40].rstrip("-")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", nid):
        sys.exit("Refused: the id is 1 to 40 letters, digits, dots, dashes or underscores.")
    d["notifications"] = [n for n in d["notifications"] if n["id"] != nid]        # the same id again replaces the old one
    entry = {"id": nid, "date": today, "title": title, "body": body, "level": level}
    if link:
        entry["link"] = link
    if channel != "all":
        entry["channel"] = channel
    if expires:
        entry["expires"] = expires
    d["notifications"].insert(0, entry)
    d["notifications"] = d["notifications"][:50]
    note = f"send {nid}"
else:
    nid = pos[0]
    if not any(n["id"] == nid for n in d["notifications"]):
        sys.exit(f"There is no notification '{nid}'.")
    d["notifications"] = [n for n in d["notifications"] if n["id"] != nid]
    note = f"remove {nid}"
d["serial"] += 1
json.dump(d, open("dist/notifications.json", "w"), indent=2, ensure_ascii=False)
open("dist/notifications.json", "a").write("\n")
open("/dev/stderr", "w").write(f"{note}: serial {d['serial']}, {len(d['notifications'])} notification(s)\n")
print(note)
PY
NOTE="$(python3 -I -c 'import json; print(json.load(open("dist/notifications.json"))["serial"])')"
rm -f dist/notifications.json.sig
ssh-keygen -q -Y sign -f "$KEY" -n roblox-manager-notifications dist/notifications.json
git add dist/notifications.json dist/notifications.json.sig
git commit -q -m "Notifications: serial $NOTE ($ACTION${NID:+ $NID}${POS[0]:+ ${POS[0]:0:50}})"
git verify-commit HEAD
if [[ -n "$PUSH" ]]; then
  git push origin release
  git push origin release:main
  echo "Published. The apps pick it up within about ten minutes (at once at the next start)."
else
  echo "Done locally. Publish with: git push origin release release:main"
fi
