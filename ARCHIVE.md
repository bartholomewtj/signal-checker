# What is on GitHub

The public tree is a run-kit plus the current tests. Clone it, install deps, run `just check`, `just test`, `just dash`.

Factory dirs (`adws/`, `specs/`, `requests/`) stay on this machine and are gitignored. Do not add them back.

Extra docs and old batteries were moved to `archive/` (gitignored). The full SSSF justfile is `archive/justfile.sssf`. The tracked justfile is app recipes only.

Do not restore extras to GitHub.
