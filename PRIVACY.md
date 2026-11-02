# Privacy policy

_Last updated: 2 November 2026. This policy covers the Roblox Manager apps for Linux, Windows and Android, and this repository._

**The short version:** everything the apps keep stays on your own device. There is no server of mine, no account with me, no analytics, no telemetry, no crash
reporting and no ads. The apps only talk to Roblox, to GitHub (for updates and the signed lists described below) and, **only if you allow it**, to two small
public services for server locations.

## Who I am

Roblox Manager is a free, open-source hobby project (GPL-3.0) made and maintained by one person, Miko ([@AO-Miko](https://github.com/AO-Miko)). It is not a company and
it is **not made by, affiliated with or endorsed by Roblox Corporation**. "Roblox" is a trademark of its owner.

Because the apps send nothing to me, I do not receive or hold your personal data. The only personal data I publish is described under
[Public lists in this repository](#public-lists-in-this-repository).

## What stays on your device

Nothing in this list is ever uploaded:

- **Your password and 2-step codes** are sent only to Roblox, to sign in. They are never stored, never written to a log and are dropped from memory when the sign-in ends.
- **Roblox's sign-in cookie** (`.ROBLOSECURITY`), which works like a key to your account, is stored **encrypted**: in the system wallet on Linux (KDE Wallet / GNOME
  Keyring), with Windows data protection (DPAPI) on Windows, and with an AES-256-GCM key inside the Android Keystore on Android. It is sent only to `roblox.com`
  addresses. Android app backup is turned off.
- **Your saved accounts** (user id and name) and **the app's settings** (including the look you chose and which notifications you have read).
- **A cache** of names and profile pictures the app has shown, so it does not ask Roblox again.
- **A request log** (address, answer code and timing of what the app asked Roblox) and an **app debug log**. Cookies, tokens, passwords, codes, e-mail addresses, phone
  numbers, IP addresses, folder names, your account names and ids, and the names and descriptions of people in Roblox's answers are replaced by a mark before anything is kept.
- On Linux, small records of bulk actions you ran, so you can look back at what happened.

You can switch the logs off and clear them, clear the caches, and remove an account (which deletes its saved sign-in) in the app's settings. Uninstalling the app, or
deleting its folders, removes everything. Where the files are is described in the [README](README.md#how-your-data-is-handled).

## What goes over the network

| To | What | When |
|---|---|---|
| **Roblox** (`roblox.com` addresses such as `auth`, `users`, `friends`, `groups`, `games`, `economy`, `apis`, `thumbnails`, `presence`) | Your sign-in, and the requests for the features you use (friends, groups, VIP servers, Robux ...), with your cookie | When you use the app |
| **Roblox image servers** | Downloads of pictures, without any cookie | When pictures are shown |
| **Roblox, for the Staff List** | The public profile, picture and counts of the staff (pages anyone can open), without your cookie | When you open the Staff List |
| **GitHub** (`github.com`, `api.github.com`, `raw.githubusercontent.com`) | Downloads of the update, and of the signed lists: bans, staff roles, the update policy and notifications | At start and about every ten minutes |
| **ipwho.is** | The public address of a game server, to show where it is | **Only if you turn it on** in Settings (server locations) |
| **RoSeal** (`data.roseal.live`) | Download of public data files (data centres, game wiki links); nothing about you is sent | **Only if you turn it on** in Settings |

GitHub, Roblox and these services can of course see your IP address, as with any download or web request, and they handle it under their own policies
([GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement), [Roblox](https://www.roblox.com/info/privacy)). The apps send no
account data to GitHub. Nothing else leaves the device: **no third-party analytics, advertising or crash-reporting service is used.**

## Android permissions

- **Internet**: to talk to Roblox and GitHub.
- **Install packages**: only so the app can install its own verified updates. Android always asks you to confirm.
- **Notifications**: only for friend alerts and the app's notifications, if you allow it.

The app does not use your location, contacts, camera, microphone, photos, advertising id or any other personal data on the phone.

## Public lists in this repository

Four small files in this repository are public, signed with the release key, and downloaded by the apps. Nothing about you is sent when they are downloaded.

- **Ban list** (`dist/bans.json`): a banned Roblox **user id**, the **reason**, **who** banned them and **when**. See [docs/ADMIN.md](docs/ADMIN.md) and the [Terms](TERMS.md).
- **Staff roles** (`dist/roles.json`): the Roblox user ids of the staff and their role.
- **Update policy** (`dist/policy.json`) and **notifications** (`dist/notifications.json`): version numbers and public messages. They contain no personal data.

These are personal data about the people listed, and they are public on purpose: the apps must be able to read them. Past versions stay in the repository's history.
A ban is kept for as long as it is in force. If you are on the list and want to ask for a correction or removal, or you are a staff member who wants to be removed, see
[Your rights and contact](#your-rights-and-contact).

## Children

Roblox has its own age rules and parental controls, and you must follow them. The apps collect nothing from anyone, children included, because nothing is sent to me.

## Security

Cookies are stored encrypted as described above, updates are verified (Linux only installs commits signed with the release key, Windows only an update package signed
with it, Android only an APK with a matching checksum and the same signing key as the installed app), and the signed lists are only believed with a valid signature.
Details are in [SECURITY.md](SECURITY.md), [docs/UPDATES.md](docs/UPDATES.md) and the [README](README.md#how-your-data-is-handled). If you lose a device, use
"sign out" on roblox.com to invalidate its cookie.

## Your rights and contact

Depending on where you live (for example under the EU/UK GDPR), you may have the right to access, correct or delete personal data, and to object to its use. As I hold no
data about you apart from the public lists above, these requests are only about those lists. To ask for something:

- open an issue at <https://github.com/AO-Miko/roblox-manager/issues> (it is public, so do not put anything private in it), or
- for something private, use GitHub's private report: <https://github.com/AO-Miko/roblox-manager/security/advisories/new>.

This is a one-person project, so replies are best effort: expect an answer within about a week.

## Changes

If the apps start to handle data differently, this policy changes **before** that version is released. The history of every change is in this repository, and a test
checks that every outside address the apps use is named in this policy. The version of this policy that applies is the one in the version of the app you run.
