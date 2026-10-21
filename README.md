# Roblox Manager

Manage your Roblox accounts from a Linux desktop app or an Android phone app: friends and requests, followers, blocked users, groups,
VIP servers, Robux and transactions, a request log, and several accounts side by side. Both apps follow Roblox's own rate limits and
update themselves from this repository.

Downloads are on the [Releases page](https://github.com/AO-Miko/roblox-manager/releases/latest).

## Install on Linux

You need `python3` with **PySide6** (and its WebEngine, for the built-in browser sign-in) and **requests**, plus `git` for automatic updates.
`libsecret` (`secret-tool`) is recommended: logins are then kept in KDE Wallet / GNOME Keyring.

```sh
# Fedora / Nobara
sudo dnf install python3-pyside6 python3-requests git libsecret
# Debian / Ubuntu
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtwebenginewidgets python3-requests git libsecret-tools
# anything else
pip install --user PySide6 requests
```

Then install, either from a clone:

```sh
git clone --branch release https://github.com/AO-Miko/roblox-manager.git
cd roblox-manager
tools/install-linux.sh
```

or from the release package (`roblox-manager-linux-X.Y.Z.tar.gz`):

```sh
tar xzf roblox-manager-linux-*.tar.gz
cd roblox-manager-linux-*/
tools/install-linux.sh
```

This puts the app in `~/.local/share/roblox-manager`, the `roblox-manager` command in `~/.local/bin` (make sure that folder is in your `PATH`), and a
menu entry. Start it from the menu or with `roblox-manager`. Sign in on the **Home** tab.

**Updates:** every time you start it, the launcher checks this repository (a few seconds at most, never blocking) and installs a newer version if the
commit is signed by the release key. *Settings → Updates* shows the version, lets you check now, and go back to the previous version.
Uninstall: delete `~/.local/share/roblox-manager`, `~/.local/bin/roblox-manager` and `~/.local/share/applications/roblox-manager.desktop`
(your settings stay in `~/.config/roblox-manager` until you delete them).

## Install on Android

Android 8.0 or newer.

1. On the phone, open the [latest release](https://github.com/AO-Miko/roblox-manager/releases/latest) and download `roblox-manager-X.Y.Z.apk`
   (or copy it from your computer).
2. Open the file. Android asks you to allow installing apps from this source (your browser or file manager): allow it, then press **Install**.
3. Open **Roblox Manager** and sign in with your password (2-step codes supported), the built-in browser (handles CAPTCHA and passkeys), or a pasted cookie.

**Updates:** at every start the app checks this repository for a newer build, downloads it, verifies its checksum and offers an **Install** button
(Android always asks you to confirm an install; it only accepts an update signed with the same key as the installed app, so keep updating from this
repository rather than from other copies). *Settings → Updates* shows the status and the update address.

To verify a download, compare it with `SHA256SUMS.txt` from the same release (`sha256sum -c SHA256SUMS.txt`).

## How your logins are kept

- Passwords are only sent to Roblox for the sign-in and are never stored or logged.
- Linux: the sign-in cookie is stored in the system wallet (encrypted). If no wallet is available the app warns you that it fell back to an owner-only file.
- Android: the cookie is encrypted with an AES-256-GCM key held in the Android Keystore; app backups are turned off.
- The cookie is only ever sent to `roblox.com`. The request log never contains cookies, passwords, codes or request bodies.

## For maintainers

`tools/release.sh 1.2.0 "what changed" --push` builds and signs everything, updates `dist/update.json`, pushes the `release` branch and publishes a
GitHub Release with the APK and the Linux package. See [docs/UPDATES.md](docs/UPDATES.md) for how updates and keys work.
