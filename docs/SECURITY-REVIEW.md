# Security review

The last full review was done on 2026-10-22 (code, build, dependencies, Android, GitHub). What was checked, what was found, and what was done. `tests/test_security.py`
keeps every fix in place.

## Checked and fine

- **Dependencies:** every direct and transitive library of the PC, Windows and Android apps was looked up on [osv.dev](https://osv.dev): no known vulnerabilities.
- **GitHub scanners:** CodeQL, Dependabot and secret scanning: no open alerts about the apps (3 warnings in a test file, fixed below).
- **Cookie handling:** stored encrypted (wallet, DPAPI, Android Keystore), sent only to roblox.com addresses, redirects are never followed with it, never written to a log
  (the log lines about it only say how long it is and where it is kept).
- **App debug log:** every event is passed through one hiding step before it is kept or written (cookie, token, password, code, e-mail, phone, IP address, folder names, the accounts in use, names/descriptions of people in answers). Answers are shortened, `debug.log` is readable by the user only, and nothing leaves the device. `tests/test_debug.py` and `DebugLogTest.kt` push cookies, e-mails, addresses, tokens and names through requests, tasks, logging, printed lines and crashes, then search the list, the export and the file for them.
- **Updates:** signed; archives are unpacked without links, outside paths or oversized files; an older version is never installed.
- **Dangerous calls:** no `shell=True`, `os.system`, `eval`, `pickle`, `verify=False` or `yaml.load` anywhere (a test scans for them).
- **Server locations:** the apps contact RoSeal's data service (data.roseal.live) or ipwho.is only when the person pressed Location and uptime and allowed that service (asked once; a switch for each in Settings; both off by default and never restored from a backup). RoSeal's list is one plain download (no cookie, nothing about the person or the server; 200 KB cap, checked entry by entry, kept 6 hours). ipwho.is gets one public IPv4 address of a Roblox server and nothing else (no cookie, no account, no redirects, 20 KB cap, answers checked and kept 30 days). Private and odd addresses are never sent, and the tickets in Roblox's join answer are never kept or logged (tests check all of this).
- **Game wiki links:** RoSeal's list of game links is downloaded only after the same agreement as the data centre list (400 KB cap, no redirects, kept 24 hours); every link is checked entry by entry (https only, a plain host name and a short safe path: no schemes, ports, logins, addresses or odd characters) before it can be opened. A test feeds it hostile links.
- **Android:** one exported component (the main screen), no backups, no plain http, only the internet, install and (for the friend alerts) notification permissions, no JavaScript bridge.

## Found and fixed

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | Android login web view | it could be navigated to any site, and could read files and other apps' content | only https links to Roblox are followed; file and content access off; no mixed content |
| 2 | PC, text from Roblox in rich-text labels (search results, friend profile, ban and unban questions, pending groups) | a name or description with HTML in it was read as HTML (layout spoofing) | `esc()` everywhere such a text is put into HTML; plain text where no formatting is needed; tested with hostile names |
| 3 | Play (PC and phone) | a join code from Roblox was put into the launcher link unchecked | a code must be letters, digits, `-` and `_` (64 at most), otherwise nothing is launched |
| 4 | Restart (Linux) | the launcher's path was put into shell text | the shell text is fixed and the path is an argument |
| 5 | Windows build | the two main libraries were pinned, what they need was not, and nothing was hashed | `tools/windows/requirements.lock`: every library with an exact version and SHA-256, installed with `--require-hashes` (a changed file is refused); `update_lock.py` renews it on purpose |
| 6 | PC folders | the folder with logs and saved names was readable by other users of the computer | private (`0700`) like the settings folder |
| 7 | PC, single-instance socket | any local user could ask the window to come to the front | the socket is for this user only |
| 8 | Tests | temporary files made with `mktemp` (CodeQL: insecure temporary file) | `mkstemp` |

## Known limits (by design)

- The ban, role and update-policy checks are in open-source code: they stop casual misuse, not someone who changes the program.
- The Windows program has no paid code-signing certificate (SmartScreen warns; the README shows how to check the download).
- Anyone who holds the release key can publish bans, roles and updates: the key stays with the owner (see [ADMIN.md](ADMIN.md)).
