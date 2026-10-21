#!/usr/bin/env bash
# Builds the Windows setup program (Roblox-Manager-Setup-VERSION.exe) on Linux, with Inno Setup running under Wine.
#
#   tools/build_installer.sh VERSION PACKAGE_DIR OUTPUT_DIR
#     PACKAGE_DIR is the RobloxManager folder that tools/build_windows.py makes.
#
# The first run downloads Inno Setup (pinned, checksum-checked) and installs it into its own Wine prefix in ~/.cache/roblox-manager-build/wine-inno.
# Needs: wine, curl, sha256sum.
set -euo pipefail
VERSION="${1:?usage: tools/build_installer.sh VERSION PACKAGE_DIR OUTPUT_DIR}"
PKG="$(realpath "${2:?package folder}")"
OUT="$(realpath -m "${3:?output folder}")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$HOME/.cache/roblox-manager-build"
INNO_VERSION="6.7.3"
INNO_SHA256="9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
INNO_EXE="$CACHE/innosetup-$INNO_VERSION.exe"
# winemenubuilder is switched off so that Wine adds no menu entries or file associations to this computer
export WINEPREFIX="$CACHE/wine-inno" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=;winemenubuilder.exe=d" WINEARCH=win64
command -v wine >/dev/null || { echo "wine is needed to build the installer (or set SKIP_INSTALLER=1 in release.sh)"; exit 1; }
mkdir -p "$CACHE" "$OUT"

ISCC="$(find "$WINEPREFIX/drive_c" -iname ISCC.exe 2>/dev/null | head -1 || true)"
if [[ -z "$ISCC" ]]; then
  if [[ ! -f "$INNO_EXE" ]]; then
    curl -fL --retry 3 -o "$INNO_EXE" "https://github.com/jrsoftware/issrc/releases/download/is-${INNO_VERSION//./_}/innosetup-$INNO_VERSION.exe"
  fi
  echo "$INNO_SHA256  $INNO_EXE" | sha256sum -c - >/dev/null || { rm -f "$INNO_EXE"; echo "Inno Setup does not match its checksum"; exit 1; }
  wine wineboot --init >/dev/null 2>&1 || true
  wine "$INNO_EXE" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER >/dev/null 2>&1
  ISCC="$(find "$WINEPREFIX/drive_c" -iname ISCC.exe | head -1)"
fi

wine "$ISCC" /Qp "/DAppVersion=$VERSION" "/DPackageDir=$(winepath -w "$PKG")" "/DOutDir=$(winepath -w "$OUT")" "$(winepath -w "$ROOT/tools/windows/installer.iss")" 2>&1 \
  | grep -v "MESA\|pci id" || true
SETUP="$OUT/Roblox-Manager-Setup-$VERSION.exe"
[[ -s "$SETUP" ]] || { echo "The installer was not built"; exit 1; }
echo "$SETUP  $(( $(stat -c %s "$SETUP") / 1000000 )) MB  sha256 $(sha256sum "$SETUP" | cut -d' ' -f1)"
