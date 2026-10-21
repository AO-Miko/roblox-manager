#!/bin/sh
# Installs (or reinstalls) the desktop app from this checkout, with automatic updates from the repository.
#
#   tools/install-linux.sh [UPDATE-REPOSITORY-ADDRESS]
#
# Nothing is needed beyond python3 and git. Your sign-in, settings and logs (in ~/.config and ~/.local/state) are never touched.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/.local/share/roblox-manager"
CFG="${ROBLOX_MANAGER_CONFIG:-$HOME/.config/roblox-manager}"
BIN="$HOME/.local/bin"
mkdir -p "$CFG" "$BIN" "$HOME/.local/share/applications"
chmod 700 "$CFG"

# the app itself (the previous copy is kept next to it, for the updater's rollback)
NEW="$APP.new-$$"
rm -rf "$NEW"
cp -a "$SRC/linux" "$NEW"
find "$NEW" -name '__pycache__' -type d -prune -exec rm -rf {} +
if [ -d "$APP" ]; then
    rm -rf "$APP.previous"
    mv "$APP" "$APP.previous"
fi
mv "$NEW" "$APP"

# which commit this is, so the updater knows what it already has
if git -C "$SRC" rev-parse HEAD >/dev/null 2>&1; then
    COMMIT="$(git -C "$SRC" rev-parse HEAD)"
    printf '{"commit": "%s", "version": "%s"}\n' "$COMMIT" "$(cat "$APP/VERSION")" > "$APP/.installed.json"
fi

# the keys whose signature an update must carry: written once, never changed by an update
if [ ! -s "$CFG/trusted_signers" ]; then
    cp "$SRC/tools/trust/allowed_signers" "$CFG/trusted_signers"
fi
# the update server
if [ ! -f "$CFG/update.json" ]; then
    printf '{"repo": "%s", "branch": "release", "auto": true, "require_signature": true}\n' "${1:-}" > "$CFG/update.json"
elif [ -n "${1:-}" ]; then
    python3 - "$CFG/update.json" "$1" <<'PY'
import json, sys
p, repo = sys.argv[1], sys.argv[2]
d = json.load(open(p)); d["repo"] = repo
json.dump(d, open(p, "w"), indent=1)
PY
fi

# the launcher and the menu entry
cp "$SRC/tools/roblox-manager.sh" "$BIN/roblox-manager"
chmod 755 "$BIN/roblox-manager"
if [ ! -f "$HOME/.local/share/applications/roblox-manager.desktop" ]; then
    cat > "$HOME/.local/share/applications/roblox-manager.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Roblox Manager
GenericName=Roblox account manager
Comment=Friends, groups, VIP servers, Robux and more for your Roblox accounts
Exec=$BIN/roblox-manager
Icon=roblox-manager
Terminal=false
Categories=Game;
Keywords=roblox;friends;groups;vip;robux;
StartupWMClass=roblox-manager
DESKTOP
fi
echo "Installed Roblox Manager $(cat "$APP/VERSION") in $APP"
echo "Updates: $(python3 -I "$APP/updater.py" --status | python3 -c 'import json,sys; c=json.load(sys.stdin)["config"]; print(c["repo"] or "no update server set yet (set one in Settings > Updates)")')"
