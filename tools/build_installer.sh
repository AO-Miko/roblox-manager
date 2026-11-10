#!/usr/bin/env bash
# Builds the Windows setup program (Roblox-Manager-Setup-VERSION.exe) on Linux, with Inno Setup running under Wine.
#
#   tools/build_installer.sh VERSION PACKAGE_DIR OUTPUT_DIR
#     PACKAGE_DIR is the RobloxManager folder that tools/build_windows.py makes.
#
# The first run downloads Inno Setup (pinned, checksum-checked) and installs it into its own Wine prefix in ~/.cache/roblox-manager-build/wine-inno.
# Needs: wine, curl, sha256sum. In Windows Subsystem for Linux (WSL) Wine is not needed: the Windows Inno Setup is installed and used instead.
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
mkdir -p "$CACHE" "$OUT"

download_inno() {
  if [[ ! -f "$INNO_EXE" ]]; then
    curl -fL --retry 3 -o "$INNO_EXE" "https://github.com/jrsoftware/issrc/releases/download/is-${INNO_VERSION//./_}/innosetup-$INNO_VERSION.exe"
  fi
  echo "$INNO_SHA256  $INNO_EXE" | sha256sum -c - >/dev/null || { rm -f "$INNO_EXE"; echo "Inno Setup does not match its checksum"; exit 1; }
}

FILEVER="$(python3 -I "$ROOT/tools/version.py" file "$VERSION")"

if ! command -v wine >/dev/null && grep -qi microsoft /proc/version 2>/dev/null; then
  # Windows Subsystem for Linux: Inno Setup runs natively on the Windows side (no Wine); WSL starts .exe files itself
  command -v cmd.exe >/dev/null || { echo "Windows programs cannot be started from this WSL (interop is off)"; exit 1; }
  WINHOME="$(wslpath "$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')")"
  ISCC="$(find "$WINHOME/Programs" -maxdepth 3 -iname ISCC.exe 2>/dev/null | head -1 || true)"
  if [[ -z "$ISCC" ]]; then
    download_inno
    "$INNO_EXE" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER >/dev/null 2>&1
    ISCC="$(find "$WINHOME/Programs" -maxdepth 3 -iname ISCC.exe | head -1)"
  fi
  # The files are copied to a Windows folder first: Inno Setup is much faster and more reliable there than on \\wsl$ paths
  WORK="$WINHOME/Temp/roblox-manager-installer"
  rm -rf "$WORK"; mkdir -p "$WORK/out"
  cp -r "$PKG" "$WORK/RobloxManager"
  cp -r "$ROOT/tools/windows" "$WORK/windows"
  "$ISCC" /Qp "/DAppVersion=$VERSION" "/DFileVersion=$FILEVER" "/DPackageDir=$(wslpath -w "$WORK/RobloxManager")" \
    "/DOutDir=$(wslpath -w "$WORK/out")" "$(wslpath -w "$WORK/windows/installer.iss")" 2>&1 | tr -d '\r' || true
  cp "$WORK"/out/Roblox-Manager-Setup-*.exe "$OUT/" 2>/dev/null || true
  rm -rf "$WORK"
else
  command -v wine >/dev/null || { echo "wine is needed to build the installer (or set SKIP_INSTALLER=1 in release.sh)"; exit 1; }
  ISCC="$(find "$WINEPREFIX/drive_c" -iname ISCC.exe 2>/dev/null | head -1 || true)"
  if [[ -z "$ISCC" ]]; then
    download_inno
    wine wineboot --init >/dev/null 2>&1 || true
    wine "$INNO_EXE" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER >/dev/null 2>&1
    ISCC="$(find "$WINEPREFIX/drive_c" -iname ISCC.exe | head -1)"
  fi
  wine "$ISCC" /Qp "/DAppVersion=$VERSION" "/DFileVersion=$FILEVER" "/DPackageDir=$(winepath -w "$PKG")" "/DOutDir=$(winepath -w "$OUT")" "$(winepath -w "$ROOT/tools/windows/installer.iss")" 2>&1 \
    | grep -v "MESA\|pci id" || true
fi
SETUP="$OUT/Roblox-Manager-Setup-$VERSION.exe"
[[ -s "$SETUP" ]] || { echo "The installer was not built"; exit 1; }
echo "$SETUP  $(( $(stat -c %s "$SETUP") / 1000000 )) MB  sha256 $(sha256sum "$SETUP" | cut -d' ' -f1)"
