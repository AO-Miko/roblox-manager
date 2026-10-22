"""Can this computer show a notification? Looks at the system's own settings, so the alerts page can say so when the answer is no
(Windows: notifications switched off; Linux: no notification service and no system tray)."""
import sys

WINDOWS_OFF = "Windows notifications are switched off (Settings > System > Notifications), so alerts will not pop up. They still appear at the bottom of the app."
NONE_AVAILABLE = ("This desktop has no notification service or system tray that the app can use, so alerts will not pop up. "
                  "They still appear at the bottom of the app. Install a notification daemon (for example dunst or mako) or a desktop that has one.")


def _windows_toast_enabled():
    """False when Windows says notifications are off for the user (the 'Notifications' switch in Settings); True when it is on or unknown."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PushNotifications") as k:
            return winreg.QueryValueEx(k, "ToastEnabled")[0] != 0
    except (OSError, ImportError):
        return True


def _service_on_dbus():
    """True when something answers as org.freedesktop.Notifications on the session bus."""
    try:
        from PySide6.QtDBus import QDBusConnection
        bus = QDBusConnection.sessionBus()
        return bool(bus.isConnected() and bus.interface().isServiceRegistered("org.freedesktop.Notifications").value())
    except Exception:       # noqa: BLE001 - not knowing is not a problem
        return False


def problem(platform=None, tray_messages=None, windows_toast=None, dbus_service=None):
    """None when notifications can be shown; otherwise one plain sentence saying why not. The arguments let a test give the answers."""
    platform = platform or sys.platform
    if tray_messages is None:
        try:
            from PySide6.QtWidgets import QSystemTrayIcon
            tray_messages = QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages()
        except Exception:       # noqa: BLE001
            tray_messages = False
    if platform.startswith("win"):
        if windows_toast is None:
            windows_toast = _windows_toast_enabled()
        if not windows_toast:
            return WINDOWS_OFF
        return None if tray_messages else NONE_AVAILABLE
    if tray_messages:
        return None
    if dbus_service is None:
        dbus_service = _service_on_dbus()
    return None if dbus_service else NONE_AVAILABLE
