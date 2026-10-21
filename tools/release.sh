#!/usr/bin/env bash
# Publish a new version of Roblox Manager (Linux and Android) to the update server.
#
#   tools/release.sh 1.2.0 "what changed"        build, sign and commit (stays local)
#   tools/release.sh 1.2.0 "what changed" --push  ... and push to the `origin` remote
#
# What it does: bumps linux/VERSION and android/version.properties, runs the Android unit tests, builds the signed release APK,
# writes dist/update.json (version, APK name, SHA-256, notes), makes a SSH-signed commit and tag on the `release` branch, and
# optionally pushes. The Linux app follows the branch itself (it checks the commit signature); the Android app reads dist/update.json.
# Signing keys live outside the repository: ~/.config/roblox-manager-release/ (back that folder up: without the Android keystore,
# installed phones can never be updated again).
set -euo pipefail

VERSION="${1:?usage: tools/release.sh VERSION \"notes\" [--push]}"
NOTES="${2:-}"
PUSH="${3:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. tools/android-env.sh

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Version must look like 1.2.3"; exit 1; }
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
[[ -f "$HOME/.config/roblox-manager-release/android-signing.properties" ]] || { echo "Missing the Android signing properties"; exit 1; }

CODE=$(( $(grep '^versionCode=' android/version.properties | cut -d= -f2) + 1 ))
echo "$VERSION" > linux/VERSION
printf 'versionName=%s\nversionCode=%s\n' "$VERSION" "$CODE" > android/version.properties

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

echo "== Commit and tag (signed)"
git add linux/VERSION android/version.properties dist/roblox-manager.apk dist/update.json
git commit -q -m "Release $VERSION" -m "${NOTES}"
git tag -s "v$VERSION" -m "Release $VERSION"
git verify-commit HEAD

if [[ "$PUSH" == "--push" ]]; then
  git push origin release "v$VERSION"
  echo "Pushed. Linux and Android apps will pick it up at their next start."
else
  echo "Done locally. Publish with:  git push origin release v$VERSION"
fi
