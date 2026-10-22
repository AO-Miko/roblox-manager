## What does this change, and why?

<!-- One thing per pull request, please. Link the issue if there is one: "Fixes #123". -->

## How was it tested?

<!-- The tests you ran or added, and what you tried by hand. -->

## Checklist

- [ ] The tests pass (CI runs them on Linux, Windows and Android; the Windows run uses wider fonts than most Linux setups)
- [ ] I added or updated tests for the change
- [ ] No secrets, cookies, passwords, personal data or generated files (builds, APKs) are included
- [ ] Texts still fit in a narrow window (`python tests/test_text_fit.py`)
- [ ] If it touches updates, signatures, sign-in or cookie handling: I explained the security reasoning above
- [ ] I did not change `linux/VERSION`, `android/version.properties`, `CHANGELOG.json` or anything in `dist/` (the maintainer does that at release time)
- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md); this pull request targets `main`, not `release` or `beta`
