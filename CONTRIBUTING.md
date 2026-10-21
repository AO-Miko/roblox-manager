# Contributing

Thanks for wanting to help! This is a hobby project and I'm not sure how long I'll keep working on it, so please keep expectations modest. Bug reports,
ideas and pull requests are welcome.

## How it works

- Everyone contributes through **pull requests from a fork**. Nobody else has write access, and **only the maintainer merges**.
- Pull requests go to the **`main`** branch. `release` is the branch the apps update from: it only receives signed release commits made by the maintainer,
  so please never target it.
- Checks must pass before a pull request can be merged (the tests on Linux, Windows and Android), and the maintainer reviews every change.
- Releases (and the signing keys) are the maintainer's alone. A merged pull request is not released automatically; it ships with the next release.

## Before you start

- For anything bigger than a small fix, open an issue first so we don't waste your time.
- Changes to the **update code, signature checks, trusted keys, sign-in or cookie handling** (`linux/updater.py`, `linux/sshsig.py`, `linux/vault.py`,
  `linux/auth.py`, `linux/rbx.py`, `tools/trust/`, `android/.../core/AppUpdate.kt`, `Accounts.kt`, `PasswordLogin.kt`, the workflows and the release scripts) get
  extra scrutiny and are slower to review. Explain the security reasoning in the pull request.
- Security problems: don't open a public issue, see [SECURITY.md](SECURITY.md).

## The project

- `linux/` is the desktop app (Python and Qt/PySide6), used for **both Linux and Windows**. System differences are isolated in `linux/plat.py`,
  `linux/vault.py` and `linux/updater.py`.
- `android/` is the Android app (Kotlin, Jetpack Compose). `tools/` holds the build and release scripts, `tests/` the tests, `docs/UPDATES.md` explains updates.

## Running the tests

Desktop (needs Python 3.12 or newer, `pip install -r tools/windows/requirements.txt`, and `git` and `ssh-keygen` on the path):

```sh
export QT_QPA_PLATFORM=offscreen          # PowerShell: $env:QT_QPA_PLATFORM = "offscreen"
python tests/test_sshsig.py
python tests/test_updater.py
python tests/test_updater_release.py
python tests/test_windows_native.py
python tests/test_info_tab.py
python tests/test_nav.py                  # side bar, search, shortcuts
python tests/test_admin.py                # roles, staff list, admin page (needs git, bash, ssh-keygen)
python tests/test_versions.py             # the five-number version R.B.S.F.D
python tests/test_settings_updates.py
python tests/test_text_fit.py             # no cut-off text on any tab
python tests/test_gui_full.py             # the whole app against a fake Roblox
python linux/launcher.py --selftest
```

Android: `cd android && ./gradlew :app:testDebugUnitTest` (JDK 21; the build needs the Android SDK, see `tools/android-env.sh`).

Tests never talk to the real Roblox: the desktop tests use a fake server, the Android tests use MockWebServer. Please keep it that way, and never put real cookies,
passwords or account details in a test, a log or a pull request.

## Pull request checklist

- The change does one thing, and the pull request says what and why.
- Tests were added or updated, and they pass (the CI runs them on Linux, Windows and Android).
- No secrets, personal data, or generated files (builds, APKs, caches) are included.
- Texts fit in a narrow window and with wider fonts (`tests/test_text_fit.py` checks this).
- Anything that changes an account (unfriend, leave a group, switch a server on ...) keeps asking first and keeps following Roblox's rate limits.
- User-visible changes are described in the pull request so the maintainer can add them to the update log (`CHANGELOG.json` is written at release time; please
  don't edit it).

By contributing you agree that your contribution can be distributed under the same terms as the rest of the project.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
