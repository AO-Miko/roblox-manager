# Roblox Manager

Manage your Roblox accounts from a desktop app (Linux and Windows) or an Android phone app: friends and requests, followers, blocked users, groups,
VIP servers, Robux and transactions, a request log, and several accounts side by side. The apps follow Roblox's own rate limits and
update themselves from this repository, on a **Stable** or an early-access **Beta** channel of your choice.

Downloads are on the [Releases page](https://github.com/AO-Miko/roblox-manager/releases/latest) (the files are named with the version, for example
`Roblox-Manager-Setup-1.9.0.0.0.exe`; see [Versions](#versions)).

## What is in it

| Page | What it does |
|---|---|
| **Home** | sign in (password + 2-step, built-in browser, or cookie), your account at a glance, several accounts side by side |
| **People** | friends, requests, followers, following, blocked users, find a user, all with bulk actions |
| **Groups** | your groups: members and ranks, join requests, roles, audit log, bans, shout; leave several at once |
| **VIP servers** | every private server you have: switch on/off, renew, duplicates, bulk actions |
| **Money** | Robux balance, pending, totals per period, transaction history, CSV export |
| **Request log** | every request the app sends to Roblox and how Roblox answered |
| **API Explorer** (PC) | send any Roblox web API request and read the answer |
| **Staff List** | who is on the staff, from the owner down, with their Roblox profiles (see [docs/ADMIN.md](docs/ADMIN.md)) |
| **Admin** (PC; overview on the phone) | ban and unban Roblox user ids; only for accounts with the admin role or higher |
| **Info** | settings, updates (with the Beta channel choice) and the update log: what changed in each version |

## About this project

This is a **just-for-fun project**. I built it to test how far AI has progressed in the last year, by comparing it with an older private project of
mine whose quality was really, really bad. Most of the code here was written with an AI assistant (Claude), and I check how it behaves by using it.

- I may keep updating it, but I'm not sure yet. Don't expect a support schedule.
- There is a **Windows version** too. It is newer than the Linux one: it is built on Linux and checked on a real Windows machine by an automatic test run
  on every release, but I don't use Windows myself, so please report problems.
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

or from the release package (`roblox-manager-linux-X.Y.Z.F.D.tar.gz`):

```sh
tar xzf roblox-manager-linux-*.tar.gz
cd roblox-manager-linux-*/
tools/install-linux.sh
```

This puts the app in `~/.local/share/roblox-manager`, the `roblox-manager` command in `~/.local/bin` (make sure that folder is in your `PATH`), and a
menu entry. Start it from the menu or with `roblox-manager`. Sign in on the **Home** page.

**Updates:** every time you start it, the launcher checks this repository (a few seconds at most, never blocking) and installs a newer version if the
commit is signed by the release key. *Info → Updates* shows the version, lets you check now, choose the **Stable or Beta channel**, and go back to the previous version.
Uninstall: delete `~/.local/share/roblox-manager`, `~/.local/bin/roblox-manager` and `~/.local/share/applications/roblox-manager.desktop`
(your settings stay in `~/.config/roblox-manager` until you delete them).

## Install on Windows

Windows 10 or 11 (64-bit). Nothing else needs to be installed: it brings its own Python and libraries.

1. Download **`Roblox-Manager-Setup-X.Y.Z.F.D.exe`** from the [latest release](https://github.com/AO-Miko/roblox-manager/releases/latest) (about 140 MB) and run it.
2. Windows SmartScreen may say "Windows protected your PC", because the program is not signed with a paid certificate. Choose **More info → Run anyway**.
   You can check the download against `SHA256SUMS.txt` from the release (`Get-FileHash Roblox-Manager-Setup-*.exe` in PowerShell).
3. The setup asks where to install (**any folder you can write to**; the default is `%APPDATA%\RobloxManager\App`) and offers, all optional:
   - a **Start menu entry**, so you can press the Windows key, type "Roblox Manager" and open it (on by default),
   - a **desktop icon** (off by default),
   - starting the app when the setup finishes.
   It needs no administrator rights and installs for your Windows user only (the app updates itself, so it can't live in Program Files).
   While it installs, the setup shows live details: every folder it creates and every file it puts in place with its size, the shortcuts, and the
   entry in the Apps list (nothing is downloaded: everything is inside the setup). The uninstaller shows every file and folder it deletes the same way.
4. It appears in **Settings → Apps → Installed apps**, where you can uninstall it. The uninstaller asks whether to delete your settings and saved accounts too.
   Silent install for scripts: `Roblox-Manager-Setup-X.Y.Z.F.D.exe /VERYSILENT /DIR="D:\Apps\RobloxManager" /TASKS="startmenu,desktopicon"`
   (leave `/TASKS=` empty for no shortcuts); silent uninstall: `unins000.exe /VERYSILENT /REMOVEDATA=yes` (omit `/REMOVEDATA` to keep your data).

**No installer?** `roblox-manager-windows-X.Y.Z.F.D.zip` is a portable copy: extract it and run `Roblox Manager.cmd` (or `Install.cmd` for a simple install).

**Updates:** every time you start it, the app asks GitHub for the newest release (a few seconds at most, never blocking). If there is one, it
downloads the signed update package, checks that it is signed with the release key and is newer, and installs it; the next start uses it.
*Info → Updates* shows the version, checks now, lets you choose the **Stable or Beta channel**, and goes back to the previous version. Re-running a newer setup also works.

## Install on Android

Android 8.0 or newer.

1. On the phone, open the [latest release](https://github.com/AO-Miko/roblox-manager/releases/latest) and download `roblox-manager-X.Y.Z.F.D.apk`
   (or copy it from your computer).
2. Open the file. Android asks you to allow installing apps from this source (your browser or file manager): allow it, then press **Install**.
3. Open **Roblox Manager** and sign in with your password (2-step codes supported), the built-in browser (handles CAPTCHA and passkeys), or a pasted cookie.

**Updates:** at every start the app checks this repository for a newer build, downloads it, verifies its checksum and offers an **Install** button
(Android always asks you to confirm an install; it only accepts an update signed with the same key as the installed app, so keep updating from this
repository rather than from other copies). *Info → Updates* shows the status and the update address, and has the **Beta channel** switch.

To verify a download, compare it with `SHA256SUMS.txt` from the same release (`sha256sum -c SHA256SUMS.txt`).

## Finding your way around

- **PC:** the pages are in a side bar with counts next to the names (a pending-requests count on People, the number of groups and servers). The button at the top of the side bar
  collapses it to icons, and every group (Social, Roblox, Tools, Staff) has an arrow that folds it; both are remembered. A narrow window collapses it by itself and a page that
  does not fit scrolls instead of forcing the window wide.
- **Ctrl+K** opens a search that jumps to any page, setting or account, and to any friend, group, VIP server or staff member that is loaded. **Ctrl+1 ... Ctrl+9** open the
  pages in order and **F5** (or the reload button in the page header) reloads the page you are on.
- **Phone:** four main pages and **More** (Money, Request log, Staff List, Admin overview, Info) are in a bottom bar. The magnifier at the top searches pages and settings, the
  round button switches accounts from any page, sections have arrows that fold them (More, Settings, Home), and pages you have opened keep what they loaded.

## Versions

The version has five numbers, `R.B.S.F.D` = **R**ework . **B**ig feature . **S**mall feature . bug **F**ix . **D**esign. An update raises exactly one of them by 1, and they never
go down; only a complete rework (R) sets the other four back to 0. Details in [docs/UPDATES.md](docs/UPDATES.md).

## Stable and Beta

In *Info → Updates* (PC and phone) you can join the **Beta channel**: you get every new version before it goes to everybody else (less tested, may have bugs). Beta versions live on the
`beta` branch and are published as GitHub pre-releases. You can go back to Stable at any time and keep your version until Stable catches up: nothing older is ever installed.

## How your data is handled

Short version: everything stays on your own device, and the apps only talk to Roblox and to GitHub (for updates). There is no server of mine, no account
with me, no analytics, no telemetry and no ads.

**Sign-in**
- Your **password** and 2-step codes are sent only to Roblox (`auth.roblox.com`, `twostepverification.roblox.com`, `apis.roblox.com`) over https, to sign in.
  They are never stored and never written to a log, and are dropped from memory when the sign-in ends.
- What is kept afterwards is Roblox's **sign-in cookie** (`.ROBLOSECURITY`), which works like a key to the account. It is stored **encrypted**:
  - Linux: in the system wallet (KDE Wallet / GNOME Keyring through `secret-tool`). If no wallet is available, the app warns you and falls back to a file
    only your user can read.
  - Windows: encrypted with Windows data protection (DPAPI), which only your own Windows user account can decrypt (not another account, not another PC).
    The encrypted files are in `%APPDATA%\RobloxManager\vault`.
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
- Where: Linux keeps this in `~/.config/roblox-manager` and `~/.local/state/roblox-manager`. Windows keeps it in `%APPDATA%\RobloxManager` and
  `%LOCALAPPDATA%\RobloxManager`. Android keeps it in the app's private storage.
  Removing an account deletes its saved sign-in; uninstalling the Android app, or deleting those folders, removes everything.

**What goes over the network**
- To Roblox: the requests for the features you use (friends, groups, VIP servers, Robux ...), with your cookie. Pictures are downloaded from Roblox's
  image servers without any cookie.
- To Roblox, for the Staff List: the public profile, picture and counts of the people on the staff (the same pages anyone can open on roblox.com), without your cookie.
- To GitHub: the update check (`github.com` for Linux, `api.github.com` and the release download for Windows, `raw.githubusercontent.com` for Android), and the ban
  list and staff roles (`raw.githubusercontent.com`). It sends no account data; GitHub can of course see your IP address like for any download.
- Nothing else. There is no crash reporting and no third-party service.

**Ban list**: the maintainer and the admins can ban a Roblox user id from using the apps (for example for abusing them). The list is a small public file in this repository
(`dist/bans.json`, with the user id, the reason, who banned them and when), signed with the release key so nobody else can add to it. The apps download it at start, at every sign-in and
every ten minutes; a banned account is signed out and forgotten at once, even in the middle of a session, and is told why. Nothing about you is sent (it is a plain
download), the last good list is kept on your device, and if it cannot be downloaded nobody is locked out. It is a check in open-source code, so it stops casual misuse,
not someone who modifies the program.

**Staff roles**: a second small signed file, `dist/roles.json`, lists the Roblox user ids of the staff and their role (owner, co-owner, senior admin, admin, trusted friend). It is
signed with the same release key and downloaded like the ban list. It drives the Staff List page that everybody can see, and the Admin page that only admin and up get. Bans can only
be published by someone who holds the release key; the roles decide who may ban whom in the Admin page (a higher role acts on lower ones, nobody acts on themselves or on the same
or a higher role, and a ban needs a reason). See [docs/ADMIN.md](docs/ADMIN.md).

**Spending**: the apps never buy anything by themselves. The Android app has no purchase feature, and the Linux app always shows the price and asks first
before anything that costs Robux.

**Updates are verified**: Linux only installs commits signed with the release key (and never an older version), Windows only installs an update package
signed with that key (and never an older version), Android only installs an APK whose checksum matches and that is signed with the same key as the
installed app. See [docs/UPDATES.md](docs/UPDATES.md).

## Contributing and security

Pull requests from forks are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). They go to the `main` branch and only the maintainer can merge them.
The apps update from two other branches that only receive signed release commits: `release` (Stable) and `beta` (Beta). To report a security problem privately, see
[SECURITY.md](SECURITY.md). Everyone is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## For maintainers

```
tools/release.sh KIND "one change|another change" [--beta] [--push]     KIND: rework | big | small | fix | design
tools/promote.sh --push                                                the tested beta build becomes the stable version
tools/ban.sh ban|unban|list ...                                        the signed ban list (the Admin page runs this)
tools/roles.sh set|remove|list ...                                     the signed staff roles
```

`release.sh` works out the next version from the kind of change, builds and signs everything, updates `dist/update.json`, pushes the branch and publishes a GitHub release (a
**pre-release** with `--beta`, from the `beta` branch). The `|` splits the bullets of the update log shown in the apps under **Info → Updates**. See
[docs/UPDATES.md](docs/UPDATES.md) for how updates, channels and keys work, and [docs/ADMIN.md](docs/ADMIN.md) for roles and bans.
