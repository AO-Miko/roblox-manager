#!/usr/bin/env bash
# Make the newest BETA build the stable version, exactly as it was tested: no rebuild, the same commit, the same files.
#
#   tools/promote.sh            check and merge `beta` into `release` here (stays local)
#   tools/promote.sh --push     ... and publish: push `release` (and `main`), and turn the beta pre-release into the latest release
#
# Run it on the `release` branch. It refuses unless `beta` is a straight continuation of `release` (merge release into beta first if a fix went
# to release directly), the newest beta release (tag vX.Y.Z.F.D) is the very last commit of `beta`, and the commit is signed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PUSH=""
for a in "$@"; do [[ "$a" == "--push" ]] && PUSH=1; done
[[ "$(git rev-parse --abbrev-ref HEAD)" == "release" ]] || { echo "Run this on the 'release' branch"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Commit or stash your changes first"; exit 1; }
git rev-parse -q --verify refs/heads/beta >/dev/null || { echo "There is no beta branch"; exit 1; }
git merge-base --is-ancestor release beta || { echo "beta does not contain everything that is on release. Merge release into beta first."; exit 1; }
VERSION="$(git show beta:linux/VERSION | tr -d '[:space:]')"
TAG="v$VERSION"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "The newest beta ($VERSION) has no release tag $TAG"; exit 1; }
[[ "$(git rev-list -n1 "$TAG")" == "$(git rev-parse beta)" ]] || { echo "beta has commits after its newest beta release ($TAG). Release a new beta first: tools/release.sh KIND \"notes\" --beta"; exit 1; }
if [[ "$(git rev-parse release)" == "$(git rev-parse beta)" ]]; then echo "release is already at $VERSION"; exit 0; fi
git merge --ff-only beta
git verify-commit HEAD
echo "release is now at $VERSION (the same commit as the beta)"
if [[ -n "$PUSH" ]]; then
  git push origin release
  gh release edit "$TAG" --prerelease=false --latest
  git push origin release:main
  tools/policy.sh --commit --push          # the newest stable version is now in the update policy (apps two updates behind are asked to update)
  echo "Published: $VERSION is the stable version. Stable users get it at their next start. (Merge release into beta before the next promotion: git checkout beta && git merge release)"
else
  echo "Done locally. Publish with: tools/promote.sh --push"
fi
