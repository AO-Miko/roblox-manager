#!/usr/bin/env bash
# Publish a new version of Roblox Manager (Linux, Android and Windows) to the update server.
#
#   tools/release.sh KIND "one change|another change"   build, sign and commit (stays local); "|" separates the update-log bullets
#   tools/release.sh KIND "what changed" --push  ... and push to the `origin` remote
#   tools/release.sh KIND "what changed" --beta [--push]   a BETA release: from the `beta` branch, published as a GitHub pre-release; people who chose the
#       beta channel in Settings get it, everybody else does not. Later `tools/promote.sh` makes exactly that build the stable one.
#
# The version has five numbers, R.B.S.F.D = complete rework . big feature change . small feature change . bug fix . design rework (see tools/version.py).
# KIND says which one this update raises by 1: rework | big | small | fix | design. The numbers never go down; only a rework sets the other four back to 0.
# (A full version like 1.8.0.1.0 is accepted too, if it is exactly one step from the current one.)
#
# What it does: bumps linux/VERSION and android/version.properties, runs the Android unit tests, builds the signed release APK,
# writes dist/update.json (version, APK name, SHA-256, notes), makes a SSH-signed commit and tag on the `release` branch, and
# optionally pushes. The Linux app follows the branch itself (it checks the commit signature); the Android app reads dist/update.json;
# the Windows app downloads the signed app package (roblox-manager-app-X.Y.Z.tar.gz + .sig) of the newest GitHub release. The release
# also carries the Windows zip (its own Python and Qt inside, built by tools/build_windows.py), the Linux package, the APK and checksums.
# Signing keys live outside the repository: ~/.config/roblox-manager-release/ (back that folder up: without the Android keystore,
# installed phones can never be updated again).
set -euo pipefail

KIND="${1:?usage: tools/release.sh rework|big|small|fix|design \"notes\" [--push] [--beta]}"
NOTES="${2:-}"
PUSH=""
BETA=""
for a in "${@:3}"; do
  case "$a" in --push) PUSH="--push" ;; --beta) BETA=1 ;; *) echo "Unknown option $a"; exit 1 ;; esac
done
BRANCH="release"
[[ -n "$BETA" ]] && BRANCH="beta"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. tools/android-env.sh

if [[ "$KIND" =~ ^(rework|big|small|fix|design)$ ]]; then
  VERSION="$(python3 -I tools/version.py next "$KIND")"
else
  VERSION="$KIND"
  python3 -I tools/version.py check "$VERSION" || { echo "Not a valid next version (rework, big, small, fix or design, or the full five numbers)"; exit 1; }
fi
echo "Version: $(cat linux/VERSION) -> $VERSION"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] || { echo "Run this on the '$BRANCH' branch"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
[[ -f "$HOME/.config/roblox-manager-release/android-signing.properties" ]] || { echo "Missing the Android signing properties"; exit 1; }

CODE=$(( $(grep '^versionCode=' android/version.properties | cut -d= -f2) + 1 ))
echo "$VERSION" > linux/VERSION
printf 'versionName=%s\nversionCode=%s\n' "$VERSION" "$CODE" > android/version.properties

# The update log (shown in both apps under Info > Updates): notes are separated by "|", one bullet each.
python3 -I - "$VERSION" "$NOTES" <<'PY'
import datetime, json, sys
v, notes = sys.argv[1:3]
log = [e for e in json.load(open("CHANGELOG.json")) if e["version"] != v]
changes = [n.strip() for n in notes.split("|") if n.strip()] or ["Maintenance release"]
log.insert(0, {"version": v, "date": datetime.date.today().isoformat(), "changes": changes})
open("CHANGELOG.json", "w").write(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
PY
cp CHANGELOG.json linux/CHANGELOG.json
mkdir -p android/app/src/main/assets
cp CHANGELOG.json android/app/src/main/assets/changelog.json

echo "== Android tests"
(cd android && ./gradlew --console=plain -q :app:testDebugUnitTest)
echo "== Android release build"
(cd android && ./gradlew --console=plain -q :app:assembleRelease)

mkdir -p dist
cp android/app/build/outputs/apk/release/app-release.apk dist/roblox-manager.apk
SHA="$(sha256sum dist/roblox-manager.apk | cut -d' ' -f1)"
python3 -I - "$VERSION" "$CODE" "$SHA" "$NOTES" <<'PY'
import json, sys
v, c, sha, notes = sys.argv[1:5]
json.dump({"versionName": v, "versionCode": int(c), "apk": "roblox-manager.apk", "sha256": sha, "notes": notes},
          open("dist/update.json", "w"), indent=2)
open("dist/update.json", "a").write("\n")
PY

POLICY_FILES=""
if [[ -z "$BETA" ]]; then
  echo "== Update policy (which versions were released to everybody)"
  tools/policy.sh --with "$VERSION"
  POLICY_FILES="dist/policy.json dist/policy.json.sig"
fi

echo "== Commit and tag (signed)"
git add $POLICY_FILES linux/VERSION android/version.properties dist/roblox-manager.apk dist/update.json CHANGELOG.json linux/CHANGELOG.json android/app/src/main/assets/changelog.json linux/icon.ico
git commit -q -m "Release $VERSION" -m "${NOTES}"
git tag -s "v$VERSION" -m "Release $VERSION"
git verify-commit HEAD

echo "== Release packages"
OUT="build/release"
rm -rf "$OUT"; mkdir -p "$OUT"
cp dist/roblox-manager.apk "$OUT/roblox-manager-$VERSION.apk"
git archive --format=tar.gz --prefix="roblox-manager-linux-$VERSION/" -o "$OUT/roblox-manager-linux-$VERSION.tar.gz" HEAD \
  linux tools/install-linux.sh tools/roblox-manager.sh tools/trust README.md

echo "== Signed app package (what the Windows app updates from)"
git archive --format=tar.gz -o "$OUT/roblox-manager-app-$VERSION.tar.gz" HEAD linux
ssh-keygen -q -Y sign -f "$HOME/.config/roblox-manager-release/signing_key" -n roblox-manager-release "$OUT/roblox-manager-app-$VERSION.tar.gz"
ssh-keygen -Y check-novalidate -n roblox-manager-release -s "$OUT/roblox-manager-app-$VERSION.tar.gz.sig" < "$OUT/roblox-manager-app-$VERSION.tar.gz" >/dev/null

echo "== Windows package"
python3 tools/build_windows.py "$OUT/win"
mv "$OUT/win/roblox-manager-windows-$VERSION.zip" "$OUT/"
if [[ -z "${SKIP_INSTALLER:-}" ]]; then
  echo "== Windows installer (Inno Setup under Wine)"
  tools/build_installer.sh "$VERSION" "$OUT/win/RobloxManager" "$OUT"
fi
rm -rf "$OUT/win"

(cd "$OUT" && sha256sum roblox-manager-* Roblox-Manager-Setup-* 2>/dev/null > SHA256SUMS.txt)

if [[ "$PUSH" == "--push" ]]; then
  git push origin "$BRANCH" "v$VERSION"
  # created as a draft and published after the upload, so nothing sees a release with files still missing
  gh release create "v$VERSION" "$OUT"/roblox-manager-* "$OUT"/Roblox-Manager-Setup-*.exe "$OUT/SHA256SUMS.txt" --draft ${BETA:+--prerelease} --title "Roblox Manager $VERSION${BETA:+ (beta)}" --notes "$(printf '%s' "${NOTES:-Release $VERSION}" | tr '|' '\n' | sed 's/^ */- /')" --verify-tag
  if [[ -n "$BETA" ]]; then
    gh release edit "v$VERSION" --draft=false --prerelease --latest=false
  else
    gh release edit "v$VERSION" --draft=false --latest
  fi
  if [[ -n "$BETA" ]]; then
    echo "Pushed as a beta. The apps on the beta channel pick it up at their next start. Make it the stable version with: tools/promote.sh --push"
  else
    echo "Pushed and released. Linux, Android and Windows apps will pick it up at their next start."
  fi
else
  echo "Done locally. Publish with:  git push origin $BRANCH v$VERSION"
fi
