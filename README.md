# Roblox Manager

Manage your Roblox accounts from a Linux desktop app or an Android phone app: friends and requests, followers, blocked users, groups,
VIP servers, Robux and transactions, a request log, and several accounts side by side. Both apps follow Roblox's own rate limits and
update themselves from this repository.

Downloads are on the [Releases page](https://github.com/AO-Miko/roblox-manager/releases/latest).

## About this project

This is a **just-for-fun project**. I built it to test how far AI has progressed in the last year, by comparing it with an older private project of
mine whose quality was really, really bad. Most of the code here was written with an AI assistant (Claude), and I check how it behaves by using it.

- I may keep updating it, but I'm not sure yet. Don't expect a support schedule.
- A **Windows version** is planned and should come soon.
- It is an unofficial tool and is **not affiliated with or endorsed by Roblox**. It talks to Roblox's web endpoints the same way the website does, which can
  change at any time and break things. Use it at your own risk, and only with accounts you own.
- Bug reports and ideas are welcome as GitHub issues.

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

## How your data is handled

Short version: everything stays on your own device, and the apps only talk to Roblox and to GitHub (for updates). There is no server of mine, no account
with me, no analytics, no telemetry and no ads.

**Sign-in**
- Your **password** and 2-step codes are sent only to Roblox (`auth.roblox.com`, `twostepverification.roblox.com`, `apis.roblox.com`) over https, to sign in.
  They are never stored and never written to a log, and are dropped from memory when the sign-in ends.
- What is kept afterwards is Roblox's **sign-in cookie** (`.ROBLOSECURITY`), which works like a key to the account. It is stored **encrypted**:
  - Linux: in the system wallet (KDE Wallet / GNOME Keyring through `secret-tool`). If no wallet is available, the app warns you and falls back to a file
    only your user can read.
  - Android: encrypted with an AES-256-GCM key that lives inside the Android Keystore (it cannot be copied out of the phone). Android app backup is turned off.
- The cookie is sent only to `roblox.com` addresses, never anywhere else. Anyone who gets your cookie is signed in as you, so don't share it, and use
  "sign out" on roblox.com to invalidate it if you ever lose a device.
- The built-in browser sign-in (Linux) uses a private profile, so nothing from that page is kept on disk.

**What is saved on your device** (nothing is uploaded)
- A list of your saved accounts (user id and name; the cookies are stored encrypted as above) and the app's settings.
- A cache of names and profile pictures of people the app has shown, so it doesn't ask Roblox again (clear it any time under Info → Settings).
- A **request log** of what the app asked Roblox (address, answer code and timing). It never contains cookies, passwords, codes or request bodies, and
  secret-looking parts of an address are masked. It can be switched off and cleared in Settings.
- On Linux, small records of bulk actions you ran (for example which friends you removed), so you can look back at what happened.
- Where: Linux keeps this in `~/.config/roblox-manager` and `~/.local/state/roblox-manager`. Android keeps it in the app's private storage.
  Removing an account deletes its saved sign-in; uninstalling the Android app, or deleting those Linux folders, removes everything.

**What goes over the network**
- To Roblox: the requests for the features you use (friends, groups, VIP servers, Robux ...), with your cookie. Pictures are downloaded from Roblox's
  image servers without any cookie.
- To GitHub: the update check (`github.com` for Linux, `raw.githubusercontent.com` for Android). It sends no account data; GitHub can of course see your
  IP address like for any download.
- Nothing else. There is no crash reporting and no third-party service.

**Spending**: the apps never buy anything by themselves. The Android app has no purchase feature, and the Linux app always shows the price and asks first
before anything that costs Robux.

**Updates are verified**: Linux only installs commits signed with the release key (and never an older version), Android only installs an APK whose
checksum matches and that is signed with the same key as the installed app. See [docs/UPDATES.md](docs/UPDATES.md).

## For maintainers

`tools/release.sh 1.2.0 "one change|another change" --push` (the `|` splits the bullets of the update log shown in both apps under **Info → Updates**) builds and signs everything, updates `dist/update.json`, pushes the `release` branch and publishes a
GitHub Release with the APK and the Linux package. See [docs/UPDATES.md](docs/UPDATES.md) for how updates and keys work.
