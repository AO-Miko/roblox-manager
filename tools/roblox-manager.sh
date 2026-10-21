#!/bin/sh
# The launcher for Roblox Manager (installed as ~/.local/bin/roblox-manager).
# At every start it first looks for a newer signed version in the update repository (quietly, for at most a few seconds, and never as
# an obstacle: any problem just means the installed version starts as it is), then starts the app.
APP="${ROBLOX_MANAGER_APP_DIR:-$HOME/.local/share/roblox-manager}"
# Do not swap files under a copy that is already running (starting again only brings its window to the front).
if ! pgrep -u "$(id -u)" -f "$APP/app.py" >/dev/null 2>&1; then
    timeout 45 python3 -I "$APP/updater.py" --boot >/dev/null 2>&1
fi
exec python3 -I "$APP/app.py" "$@"
