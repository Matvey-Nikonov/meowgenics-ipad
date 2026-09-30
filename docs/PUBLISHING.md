# Publishing this source repository

The local publication branch is **`agent/github-ready`**. It starts with fresh
history so private artwork from development commits cannot travel with it.
The older `agent/ipad-foundation` branch is retained locally for recovery and
must not be pushed. No remote repository or push is created automatically.

Enable the included push check in each clone:

```sh
git config --local core.hooksPath .githooks
```

Before publishing, verify the exact branch and all of its reachable history:

```sh
git switch agent/github-ready
python3 Scripts/audit-publication.py HEAD
git status --short
```

Create an **empty** repository in your own GitHub account, then, when ready,
replace the example remote and push only the audited branch:

```sh
git remote add origin git@github.com:YOUR_ACCOUNT/meowgenics-ipad.git
git push -u origin agent/github-ready:main
```

Do not use `--all`, `--mirror`, `--follow-tags` or bypass the pre-push hook. The
hook audits every outgoing ref, including its full history. Deleting a game
asset in the latest commit is insufficient if an earlier commit still has it.

This project intentionally publishes text source, source patches, documentation,
license notices and configuration examples only. Keep all game files, custom
icons, logs, screenshots, saves, pairing records, signing material, dependency
downloads and build products in ignored/private locations. The script checks
file paths and blob contents, but manual review is still necessary for personal
information written into ordinary text. Review any logs before quoting them.

The original local icon is retained privately for local builds through
`MEWGENICS_APP_ICON`. A fresh clone generates a neutral placeholder instead.
GitHub Actions runs the same history audit and lightweight host tests; it does
not download the game, provision an iPad, sign an app or publish binaries.
