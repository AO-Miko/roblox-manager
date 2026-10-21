# How updates work

One git repository is the update server for both apps. Everything is published on the `release` branch.

| | Linux app | Android app |
|---|---|---|
| Reads | the `linux/` folder of the newest commit | `dist/update.json` and `dist/roblox-manager.apk` |
| When | every launch (`roblox-manager` launcher runs `updater.py --boot`) | every start of the app |
| Trust | the commit must be SSH-signed by the key in `tools/trust/allowed_signers`, and must descend from the installed one (no rollbacks) | APK SHA-256 must match `update.json`; Android only installs it if it is signed with the same key as the installed app |
| Install | automatic, previous version kept for rollback (Settings → Updates → Go back) | Android always asks the user to confirm the install (one-time "allow installs from this app") |

## Publishing a release

```
tools/release.sh 1.2.0 "what changed" --push
```

It bumps the versions, runs the Android unit tests, builds the signed APK, writes `dist/update.json`, makes a signed commit and tag, and pushes.

## Hosting

Right now the remote is a local bare repository (`/home/miko/git-server/roblox-manager.git`), which serves the Linux app on this PC.
A phone cannot reach that, so for the Android app (and a second PC) host the repository somewhere reachable:

1. Create a repository on GitHub / Codeberg / your own server (a private one works for Linux with an SSH key; for the phone use a public one, or any
   https address that serves `dist/` without a login).
2. `git remote set-url origin <url>` and `git push origin release`.
3. Linux: Settings → Updates → *Repository* = the git URL.
4. Android: Settings → Updates → *Update server address* = the raw address of `dist/`, for GitHub
   `https://raw.githubusercontent.com/USER/REPO/release/dist/`. The first APK is installed by hand from `dist/roblox-manager.apk`.

The APK and manifest contain no secrets. Never commit anything from `~/.config/roblox-manager-release/`.

## Keys — back these up

`~/.config/roblox-manager-release/` holds
- `signing_key` (+ `.pub`): signs Linux releases. If lost, make a new key, update `tools/trust/allowed_signers` and reinstall the Linux app once.
- `android-release.jks`, `android.pass`, `android-signing.properties`: sign the APK. **If lost, installed phones can never be updated** (Android rejects a different signing key); you would uninstall and reinstall.
