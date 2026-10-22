# Security policy

Roblox Manager handles something sensitive: the sign-in cookie of a Roblox account. Security reports are taken seriously, even though this is a
hobby project run by one person.

## Reporting a vulnerability

**Please do not open a public issue.** Use GitHub's private reporting instead:
[Security → Report a vulnerability](https://github.com/AO-Miko/roblox-manager/security/advisories/new).
Only the maintainer can see it. Please include what you found, how to reproduce it, and which version and system (Linux, Windows or Android).

This is a one-person project, so replies are best effort: expect an answer within about a week, and a fix as soon as it can be made and released.
You will be credited in the advisory if you want to be.

## Supported versions

Only the **latest stable release** gets fixes. All three apps update themselves, so most people are on it within a day. Beta releases (pre-releases on the `beta` branch) are early
access: they get fixes by a newer beta, and security fixes go out to both channels.

## What counts

Especially welcome:

- anything that can leak or misuse a sign-in cookie, password or 2-step code (logs, files, network, other apps on the same device);
- anything that lets someone other than the maintainer get code onto a user's device through an update (the signature checks, the downloaded packages,
  the update server addresses, unpacking of archives);
- a way to make the app spend Robux, or change an account, without the user asking for it;
- a way around the signed ban list, role list or update policy (`dist/bans.json`, `dist/roles.json`, `dist/policy.json`), for example to ban someone without the release key, or to get the Admin page without a role.

Not in scope: Roblox's own website or API, problems that need an attacker who already controls the device or the user's operating-system account, and the
fact that the Windows program has no paid code-signing certificate (SmartScreen warns about it; the README explains how to check the download).

## How the project protects users (for reviewers)

- **Cookies** are stored encrypted: KDE Wallet / Secret Service on Linux, DPAPI on Windows, the Android Keystore on Android. They are only sent to `roblox.com`.
  Nothing is sent to any server of the maintainer; there is none. See "How your data is handled" in the README.
- **Updates are signed.** The Linux app only installs git commits, and the Windows app only installs packages, that are signed (SSH Ed25519) with the
  release key it was installed with, and only newer versions. The Android app only installs an APK whose SHA-256 matches and that is signed with the same key
  as the installed app (Android enforces this itself). So write access to this repository, or to the download links, is not enough to run code on a user's
  device; the private keys live only on the maintainer's computer and are never in GitHub, CI or this repository.
- **Staff roles and bans are signed too.** `dist/roles.json` and `dist/bans.json` are only believed with a valid signature of the release key; the role hierarchy is enforced in the Admin
  page and again in `tools/ban.sh`. See [docs/ADMIN.md](docs/ADMIN.md).
- **The repository** requires pull requests and passing checks on `main`, has no collaborators with write access, blocks force-pushes and deletions (also on the `release` and `beta` branches, which only receive signed release commits), protects
  release tags, and runs secret scanning with push protection, Dependabot and CodeQL. Workflows run with read-only tokens and only GitHub's own actions,
  pinned to exact commits. Workflows from first-time contributors need the maintainer's approval before they run.

If the release key were ever lost or leaked, the maintainer would publish a notice here, make a new key and ask users to reinstall once; the apps only trust
the key they were installed with, by design.
