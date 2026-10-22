# Security review

The last full review was done on 2026-10-22 (code, build, dependencies, Android, GitHub). What was checked, what was found, and what was done. `tests/test_security.py`
keeps every fix in place.

## Checked and fine

- **Dependencies:** every direct and transitive library of the PC, Windows and Android apps was looked up on [osv.dev](https://osv.dev): no known vulnerabilities.
- **GitHub scanners:** CodeQL, Dependabot and secret scanning: no open alerts about the apps (3 warnings in a test file, fixed below).
- **Cookie handling:** stored encrypted (wallet, DPAPI, Android Keystore), sent only to roblox.com addresses, redirects are never followed with it, never written to a log
  (the log lines about it only say how long it is and where it is kept).
- **Updates:** signed; archives are unpacked without links, outside paths or oversized files; an older version is never installed.
- **Dangerous calls:** no `shell=True`, `os.system`, `eval`, `pickle`, `verify=False` or `yaml.load` anywhere (a test scans for them).
- **Android:** one exported component (the main screen), no backups, no plain http, only the internet and install permissions, no JavaScript bridge.

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
