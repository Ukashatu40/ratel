# Contributing

## The flow

```
Issue -> Branch -> Implementation -> Tests -> Pull Request -> Review -> CI -> QA/Integration -> Merge
```

- Every change starts from an issue that meets [docs/DEFINITION_OF_READY.md](docs/DEFINITION_OF_READY.md).
- `main` is protected: no direct pushes, no force pushes, pull request required, CI must pass,
  review required, conversations resolved. Merging is **squash only**, so history stays one commit
  per PR. There is no `develop` branch.
- Done means [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md), not "it merged".

## Branch names

`<type>/<short-description>`, lowercase, hyphens, concise.

| Prefix | Use |
| ------ | --- |
| `feature/` | new capability |
| `fix/` | bug fix |
| `refactor/` | no behavior change |
| `chore/` | tooling, dependencies, housekeeping |
| `docs/` | documentation, runbooks, ADRs |
| `security/` | hardening and security reviews |

Examples: `feature/line-state-machine`, `fix/usage-replay-double-count`. CI rejects other names.

## Commit and PR title style

`<type>: <what changed>` in the imperative, under about 72 characters. Optional scope:
`feat(ratel-link): store keys encrypted at rest`.

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`, `infra`. Use `!` for a
breaking contract change (`feat!: ...`). Because merges are squashed, **the PR title becomes the
commit on `main`**, and CI checks it. Commits inside your branch can be rough; keep them
secret-free anyway, because history is permanent.

## Pull requests

- Fill in the whole template. Say what you did **not** change.
- Keep PRs small enough to review properly. Split by deliverable, not by file.
- You own the PR. You must be able to explain what changed, why, how it works, what you assumed,
  what could fail, and how you tested it. AI-generated code gets no discount.
- Reviewers: one for most changes. **Two for RatelLink and RatelBSS: money** (enforced by the
  `critical-review-gate` check). Review standard: [docs/CODE_REVIEW_GUIDELINES.md](docs/CODE_REVIEW_GUIDELINES.md).
- Touching the network? Show it working against the lab and say so in the PR.
- Changing API behavior? Update `contracts/openapi.yaml` (and `contracts/not_implemented.txt`) in the same PR.

## Before you push

```
make check
```

## Never commit

Secrets, API keys, passwords, Ki, OPc, SIM data, NINs, real customer or call data, production
logs, database dumps. Use synthetic fixtures (`tests/synthetic.py`). If you commit a secret by
accident, tell the project lead immediately; deleting the commit is not enough, the secret must be
rotated.

More: [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md), [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md).
