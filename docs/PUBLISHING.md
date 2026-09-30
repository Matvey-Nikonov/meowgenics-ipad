# Publishing this source repository

The public repository is
[Matvey-Nikonov/meowgenics-ipad](https://github.com/Matvey-Nikonov/meowgenics-ipad),
with default branch **`main`**. Its initial source snapshot has fresh history so
private artwork from development commits cannot travel with it.

The maintainer's local publication branch is `agent/github-ready`, tracking
`origin/main`. The older `agent/ipad-foundation` branch is retained locally for
recovery and must not be pushed. A normal clone contains the clean public history.

Enable the included push check in each clone:

```sh
git config --local core.hooksPath .githooks
```

Before publishing, verify the exact branch and all of its reachable history:

```sh
python3 Scripts/audit-publication.py HEAD
git status --short
```

For the maintainer's existing checkout, push only the audited publication branch:

```sh
git push -u origin agent/github-ready:main
```

For contributions, fork the public repository, create a branch from its `main`,
run the checks, push that branch to your fork and open a pull request. Keep the
existing license and upstream notices with modifications.

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
