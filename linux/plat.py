"""Where the app keeps things, and the few other differences between Windows and Linux. Everything else in the app is the same on both.

  Linux:    settings ~/.config/roblox-manager, state ~/.local/state/roblox-manager, cache ~/.cache/roblox-manager
  Windows:  settings %APPDATA%\\RobloxManager, state %LOCALAPPDATA%\\RobloxManager\\state, cache %LOCALAPPDATA%\\RobloxManager\\cache

The environment variables ROBLOX_MANAGER_CONFIG / _STATE / _UPDATE_CACHE override the folders (the tests use them).
"""
import os
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"


def _win_dir(var, fallback):
    return Path(os.environ.get(var) or (Path.home() / fallback))


def config_dir():
    if os.environ.get("ROBLOX_MANAGER_CONFIG"):
        return Path(os.environ["ROBLOX_MANAGER_CONFIG"])
    if IS_WIN:
        return _win_dir("APPDATA", "AppData/Roaming") / "RobloxManager"
    return Path.home() / ".config/roblox-manager"


def state_dir():
    if os.environ.get("ROBLOX_MANAGER_STATE"):
        return Path(os.environ["ROBLOX_MANAGER_STATE"])
    if IS_WIN:
        return _win_dir("LOCALAPPDATA", "AppData/Local") / "RobloxManager" / "state"
    return Path.home() / ".local/state/roblox-manager"


def cache_dir():
    if os.environ.get("ROBLOX_MANAGER_UPDATE_CACHE"):
        return Path(os.environ["ROBLOX_MANAGER_UPDATE_CACHE"])
    if IS_WIN:
        return _win_dir("LOCALAPPDATA", "AppData/Local") / "RobloxManager" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "roblox-manager" / "update-repo"


# what the user is told, in the app's texts
WALLET = "Windows data protection (DPAPI)" if IS_WIN else "KDE Wallet"
CONFIG_TEXT = r"%APPDATA%\RobloxManager" if IS_WIN else "~/.config/roblox-manager"


def update_backend():
    """'release': signed release packages from GitHub (Windows has no git). 'git': the signed commits of the repository."""
    return os.environ.get("ROBLOX_MANAGER_UPDATE_BACKEND") or ("release" if IS_WIN else "git")
