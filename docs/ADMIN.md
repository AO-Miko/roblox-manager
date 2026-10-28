# Staff, roles and bans

## Roles

Five roles, one above the other:

| Rank | Role | Staff List | Admin page / can ban |
|---|---|---|---|
| 5 | Owner | yes | yes |
| 4 | Co-owner | yes | yes |
| 3 | Senior admin | yes | yes |
| 2 | Admin | yes | yes |
| 1 | Trusted friend | yes | no (listed as a thank-you, no powers) |

Everybody else has no role.

**The hierarchy:** a higher role may act on lower roles and on people without a role. Nobody acts on themselves, and nobody on someone of the
same or a higher role. An unban needs at least the role of whoever placed the ban (an admin cannot lift a co-owner's ban).

## The role list

`dist/roles.json`, signed with the release key (`dist/roles.json.sig`, namespace `roblox-manager-roles`):

```json
{ "serial": 3, "roles": { "239345228": "owner", "1234567": "senior-admin", "7654321": "trusted-friend" } }
```

Role names: `owner`, `co-owner`, `senior-admin`, `admin`, `trusted-friend` ("Senior Admin" and `senior_admin` are read too).
Change it on the PC that has the release key, which signs it and publishes it:

```
tools/roles.sh set 1234567 senior-admin --push
tools/roles.sh remove 1234567 --push
tools/roles.sh list
```

The apps download it at every start and every ten minutes, like the ban list. It is only believed with a valid signature, a newer `serial` replaces an
older one, and the last good list is kept for offline use.

## Staff List page (everybody, PC and phone)

Every user sees the **Staff List** page (on the phone it is under **More**): the staff in hierarchy order with their public Roblox profile (display name, username, joined date,
followers, following, friends, description) and a **Go to profile** button. It needs no sign-in and no role.

## Admin page (admin and up)

On the phone (under **More**) it shows what is in force: who is banned, by whom and with which role, and the staff. Bans and unbans themselves are published from a PC (below).

On the PC it appears only when the signed-in account's user id has a role of admin or higher; for everybody else it is hidden and Ctrl+number skips it.
It bans and unbans by user id or username. **A ban needs a reason.** Before anything is banned the page shows the person's Roblox profile (picture, display name, username,
user id, joined date, followers, following, friends, description) together with the reason and asks **"Are you sure you want to ban this user?"**; only **Yes, ban** publishes it,
**Cancel** (the default button) changes nothing. **Unban** works the same way: press **Unban...** with someone selected in the list, or type their id or username (the reason box is then an optional note). The page shows their
profile and what the ban says (when, by whom with which role, and why) and asks **"Are you sure you want to unban this user?"**; only **Yes, unban** lets them back in (the apps notice
within about ten minutes), **Cancel** changes nothing. A ban can only be lifted by someone with at least the role of whoever placed it, and nobody unbans themselves. An account that no
longer exists on Roblox can still be unbanned. The page also shows who is banned, by whom and with which role.
The rules above are checked in the page, and again in `tools/ban.sh` (so they hold however a ban is started).

**Publishing needs the release key.** A ban is only valid when signed with the release key, so the page publishes by running `tools/ban.sh` in your
checkout of the repository (branch `release`) on a PC that has the key, `git`, `bash` and `ssh-keygen`; the page tells you what is missing and lets you
pick the repository folder. Other people with a role can see the Admin page, but they can only publish from a PC that holds that key.
(Giving the key to someone also lets them bypass the rules by hand, so the key stays with the owner.)

`tools/ban.sh` can also be used directly:

```
tools/ban.sh ban 12345678 "reason" --by 239345228 --push     # --by: the user id acting; without it the key holder acts as owner
tools/ban.sh unban 12345678 "why, optional" --by 239345228 --push
tools/ban.sh list
```

## What this protects

Like the rest of the app this is client-side: it keeps honest users honest and cannot stop someone who edits the program. The signature stops
anybody else from changing the lists.

## Notifications

The maintainer can send a message to everybody who uses the app (Linux, Windows and Android). It appears on the **Notifications** page; a red number in the
side bar (the bell on the phone) says how many are unread, and a new one also pops up. The list is `dist/notifications.json`, signed with the release key
(`dist/notifications.json.sig`, namespace `roblox-manager-notifications`). The apps fetch it at every start and every ten minutes, believe it only with a valid
signature, never accept a lower `serial` than the one they have, show everything as plain text, and keep a link only if it starts with `https://`. Nothing about the
person is sent. Which ones were read is kept only on their device.

```
tools/notify.sh send "Title" "Text of the message" [--level info|important|warning] [--link https://...] [--channel all|beta|stable] [--expires YYYY-MM-DD] [--id NAME] --push
tools/notify.sh remove ID --push
tools/notify.sh list
```

Run it on the `release` branch. No new app version is needed (GitHub's cache can delay a change by a few minutes). Title: at most 80 characters; text: at most 1000;
the newest 50 are kept. `--channel beta` sends it only to people on the Beta channel. The same id sent again replaces the old message (people who read it see it
as read; use a new id to make it unread again).
