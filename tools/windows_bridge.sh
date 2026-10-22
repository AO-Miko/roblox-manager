#!/usr/bin/env bash
# One-time helper for Windows installs older than 1.9.0.0.0.
#
# Their built-in updater only accepts release tags of up to FOUR numbers (it was written before the five-number versions R.B.S.F.D), so it cannot see
# v1.9.0.0.0. A version whose last number is 0 has a four-number spelling (1.9.0.0.0 = 1.9.0.0), and the newer updater treats both as the same
# version. This script publishes that spelling: a release v1.9.0.0 that holds the same signed app package, with 1.9.0.0 in its VERSION file,
# and makes it the latest release. The older installs update to it, and from then on they have the updater that understands five numbers.
#
#   tools/windows_bridge.sh 1.9.0.0.0            prepare it here (build/bridge)
#   tools/windows_bridge.sh 1.9.0.0.0 --push     ... and publish it as the latest GitHub release
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
V5="${1:?usage: tools/windows_bridge.sh VERSION [--push]   (a version whose last number is 0)}"
PUSH=""
for a in "${@:2}"; do [[ "$a" == "--push" ]] && PUSH=1; done
[[ "$V5" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\.0$ ]] || { echo "The version must have five numbers and end in .0 (the last number is dropped)"; exit 1; }
V4="${V5%.0}"
OUT="build/bridge"
rm -rf "$OUT"; mkdir -p "$OUT/unpack"
gh release download "v$V5" -p "roblox-manager-app-$V5.tar.gz" -D "$OUT"
tar -xzf "$OUT/roblox-manager-app-$V5.tar.gz" -C "$OUT/unpack"
echo "$V4" > "$OUT/unpack/linux/VERSION"
tar -czf "$OUT/roblox-manager-app-$V4.tar.gz" -C "$OUT/unpack" linux
ssh-keygen -q -Y sign -f "$HOME/.config/roblox-manager-release/signing_key" -n roblox-manager-release "$OUT/roblox-manager-app-$V4.tar.gz"
ssh-keygen -Y check-novalidate -n roblox-manager-release -s "$OUT/roblox-manager-app-$V4.tar.gz.sig" < "$OUT/roblox-manager-app-$V4.tar.gz" >/dev/null
echo "Prepared $OUT/roblox-manager-app-$V4.tar.gz (+ .sig): VERSION $V4"
if [[ -n "$PUSH" ]]; then
  SHA="$(git rev-list -n1 "v$V5")"
  gh release create "v$V4" "$OUT/roblox-manager-app-$V4.tar.gz" "$OUT/roblox-manager-app-$V4.tar.gz.sig" --target "$SHA" --latest \
    --title "Roblox Manager $V4 (update helper for older Windows installs)" \
    --notes "The same app as $V5, spelled with four numbers so that Windows installs older than $V5 can update to it. Nothing else to download: the apps update by themselves. New installs: use the setup of $V5."
  echo "Published v$V4 as the latest release."
else
  echo "Publish with: tools/windows_bridge.sh $V5 --push"
fi
