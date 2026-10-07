# scripts/github

Helpers that configure GitHub from the files in `.github/`. They need the GitHub CLI (`gh`)
authenticated as a repository admin. **None of these were run by the setup author** (no GitHub
credentials were available). They were syntax-checked and shellchecked only. Run them yourself, in
this order, and read `docs/GITHUB_SETUP.md` first.

| Order | Script | Does |
| ----- | ------ | ---- |
| 1 | `setup_labels.sh` | Creates or updates the labels in `.github/labels.yml` |
| 2 | `apply_ruleset.sh` | Creates or updates the `main-protection` ruleset |
| 3 | `create_project.sh` | Creates the GitHub Project and its fields (views are manual) |
| 4 | `create_issues.sh` | Creates the Week 2 issues from `docs/issues-week2/` |

All scripts accept `OWNER/REPO` as the first argument and default to the repo of the current
directory.
