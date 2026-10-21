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

The server is the public GitHub repository `AO-Miko/roblox-manager`, branch `release` (`origin`). The old local bare repository is kept as the
`local` remote.

- Linux: Settings → Updates → *Repository* = `https://github.com/AO-Miko/roblox-manager.git`.
- Android: built in as `https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/` (Settings → Updates). The first APK is installed by hand
  from `dist/roblox-manager.apk`.

The repository is public, so it contains only source, the signed APK and public keys, never cookies or secrets. Never commit anything from
`~/.config/roblox-manager-release/`.

## Where logins are kept

- Linux: in KDE Wallet / Secret Service (encrypted). Only if no wallet is available is a cookie kept in an owner-only file, and the app warns about it.
- Android: encrypted with an AES-256-GCM key inside the Android Keystore; app backup is switched off.

## Keys — back these up

`~/.config/roblox-manager-release/` holds
- `signing_key` (+ `.pub`): signs Linux releases. If lost, make a new key, update `tools/trust/allowed_signers` and reinstall the Linux app once.
- `android-release.jks`, `android.pass`, `android-signing.properties`: sign the APK. **If lost, installed phones can never be updated** (Android rejects a different signing key); you would uninstall and reinstall.
