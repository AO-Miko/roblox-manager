# How updates work

One GitHub repository is the update server for all three apps. Everything is published on the `release` branch and in its GitHub Releases.

| | Linux app | Windows app | Android app |
|---|---|---|---|
| Reads | the `linux/` folder of the newest commit (needs `git`) | the newest GitHub release: `roblox-manager-app-X.Y.Z.tar.gz` + `.sig` | `dist/update.json` and `dist/roblox-manager.apk` |
| When | every launch (`roblox-manager` launcher runs `updater.py --boot`) | every launch (`launcher.py` runs the same updater) | every start of the app |
| Trust | the commit must be SSH-signed by the key in `tools/trust/allowed_signers`, and descend from the installed one (no rollbacks) | the package must be SSH-signed (`ssh-keygen -Y sign -n roblox-manager-release`) by that key, checked in plain Python (`sshsig.py`), must be newer, and its `VERSION` must match the release | APK SHA-256 must match `update.json`; Android only installs it if signed with the same key as the installed app |
| Install | automatic, previous version kept for rollback (Info → Updates → Go back) | automatic, previous version kept for rollback | Android always asks the user to confirm the install (one-time "allow installs from this app") |

The Linux and Windows apps are the same code (`linux/` folder). The differences are isolated in `linux/plat.py` (folders), `linux/vault.py` (DPAPI instead of
a Secret Service wallet) and `linux/updater.py` (release backend instead of git).

## Branches

- **`main`** is where development happens and where pull requests go. It is protected: changes need a pull request, the checks (Linux, Windows, Android)
  and the maintainer's review; no force-pushes, no deletion, linear history.
- **`release`** is what the Linux app updates from (it follows the head of this branch). It only gets **signed** release commits made by `tools/release.sh`,
  never a web-merged pull request: a commit merged on github.com is signed by GitHub, not by the release key, and the Linux app would refuse it.
  To release: `git checkout release && git merge --ff-only main` (or merge `main` and sign the merge), then run `tools/release.sh`.
- Tags `v*` are protected: nobody but the maintainer can create, move or delete them.

## Publishing a release

```
tools/release.sh 1.2.0 "one change|another change" --push
```

It bumps the versions, adds the entry to the update log (`CHANGELOG.json`, shown in the apps under Info → Updates), runs the Android unit tests, builds the
signed APK, writes `dist/update.json`, makes a signed commit and tag, builds the signed app package and the Windows zip (`tools/build_windows.py`, no Windows
machine needed), pushes, and publishes the GitHub Release with the APK, the Linux package, the Windows zip, the signed app package and `SHA256SUMS.txt`.
The release starts as a draft and is published after all files are uploaded; publishing starts the `Windows` workflow, which tests the Windows package on a
real Windows machine.

## The ban list

`dist/bans.json` (+ `dist/bans.json.sig`, signed for the namespace `roblox-manager-bans`) lists Roblox user ids that may not use the apps, each with an optional reason shown to
the person. The apps verify it with the release key built into them (`linux/bans.py`, `core/Bans.kt`), only accept a higher `serial` than the one they have, keep the last good
list on the device, and sign a banned account out and delete it at once (at start, at every sign-in, every ten minutes). If the list cannot be fetched nobody is locked out.

```
tools/ban.sh ban 12345678 "reason shown to the person" --push
tools/ban.sh unban 12345678 --push
tools/ban.sh list
```

No new version is needed. GitHub's cache can delay a change by a few minutes. The ids and reasons are public, so keep reasons short and factual.

## The Windows installer

`Roblox-Manager-Setup-X.Y.Z.exe` is a normal Windows setup program made with Inno Setup (`tools/windows/installer.iss`, built by `tools/build_installer.sh`, which runs
Inno Setup under Wine so a release can be made on Linux; Wine's menu-builder is switched off so the build adds nothing to the build computer). It contains the same
folder as the zip. The wizard and the uninstaller show live details (every folder created or deleted, every file with its size, totals), also written to the
setup log (`/LOG=file`); the setup finds new files by looking at the install folder at every progress step, because Inno Setup has no per-file event. Per-user install (no administrator rights) into a folder the person chooses (default `%APPDATA%\RobloxManager\App`), optional Start menu entry and
desktop icon, an entry in Windows' Apps list, and an uninstaller that can also remove the person's data. The `installer` job of the Windows workflow installs and uninstalls
the released file on a real Windows machine (defaults, custom folder, optional items, data removal). It is not signed with a paid code-signing certificate; the release's
`SHA256SUMS.txt` lets people check it.

## The Windows package

`roblox-manager-windows-X.Y.Z.zip` holds a folder with the official embeddable Python, PySide6 and requests (Windows builds from PyPI, with the Qt parts the
app does not use left out), the app (`app/`), the trusted public key (`trust/`) and `Install.cmd` / `Uninstall.cmd` / `Roblox Manager.cmd`.
Updates only replace `app/`; Python and the libraries change only with a new zip, so a release that needs a new library must say so in its notes.
The program is not signed with a paid code-signing certificate, so Windows SmartScreen asks for confirmation on the first run.

## Hosting

The server is the public GitHub repository `AO-Miko/roblox-manager`, branch `release` (`origin`). The old local bare repository is kept as the
`local` remote.

- Linux: Info → Updates → *Update server* = `https://github.com/AO-Miko/roblox-manager.git`.
- Windows: the same field, `https://github.com/AO-Miko/roblox-manager` (set on first start).
- Android: built in as `https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/` (Info → Updates). The first APK is installed by hand.

The repository is public, so it contains only source, the signed APK and public keys, never cookies or secrets. Never commit anything from
`~/.config/roblox-manager-release/`.

## Where logins are kept

- Linux: in KDE Wallet / Secret Service (encrypted). Only if no wallet is available is a cookie kept in an owner-only file, and the app warns about it.
- Windows: encrypted with DPAPI (only your Windows user can decrypt), in `%APPDATA%\RobloxManager\vault`.
- Android: encrypted with an AES-256-GCM key inside the Android Keystore; app backup is switched off.

## Keys — back these up

`~/.config/roblox-manager-release/` holds
- `signing_key` (+ `.pub`): signs Linux commits and the Windows app packages. If lost, make a new key, update `tools/trust/allowed_signers` and reinstall the
  Linux and Windows apps once (they only trust the key they were installed with).
- `android-release.jks`, `android.pass`, `android-signing.properties`: sign the APK. **If lost, installed phones can never be updated** (Android rejects a different signing key); you would uninstall and reinstall.

## Version numbers

The version has five numbers, **R.B.S.F.D**:

| Number | Means | Example |
|---|---|---|
| R | complete rework | 1 -> 2 |
| B | big feature change | 1.7 -> 1.8 |
| S | small feature change | 1.8.0 -> 1.8.1 |
| F | bug fix | 1.8.1.0 -> 1.8.1.1 |
| D | design rework | 1.8.1.1.0 -> 1.8.1.1.1 |

Every update raises exactly **one** of them by 1. The numbers never go down; the only exception is a complete rework (R), which sets the other
four back to 0 (1.8.1.1.1 -> 2.0.0.0.0). Versions before this rule had three numbers: 1.7.0 counts as 1.7.0.0.0.

Publishing says which number to raise: `tools/release.sh big "notes" --push` (kinds: `rework`, `big`, `small`, `fix`, `design`); `tools/version.py` works out and checks the
number. The apps compare versions number by number.
