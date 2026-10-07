# ADR 0002: Plain requirements files with a verified constraints file

- **Status:** Proposed (needs project lead approval)
- **Date:** 2026-10-06
- **Related:** Build Plan "Stack"; [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #2

## Context

Three Python deployables share one repository but need different dependencies (RatelLink needs the
MongoDB driver and no SQL stack; the agent needs almost nothing). The repository root is not one
installable package. The team is small and should not learn a new package manager mid-schedule.

## Decision

`requirements/{base,link,agent,app,dev}.txt` declare version ranges. `requirements/constraints.txt`
pins the exact versions that passed `make check` on Python 3.12 (generated with `pip freeze`).
CI and `make install` use `-c requirements/constraints.txt`. `pyproject.toml` holds tool
configuration only. Dependabot opens weekly PRs.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Poetry or uv with a lockfile | Better tooling, but another tool for six people to learn in week 2; easy to adopt later. |
| One `pyproject.toml` with extras | The root has several top-level directories; making it a package adds packaging problems we do not need. |
| Unpinned ranges only | Non-reproducible CI and deploys. |

## Consequences

No hashes in the constraints file (pip-audit warns about this). Upgrades are a deliberate
regenerate-and-test step documented in the development guide.

## Security implications

Pinned versions are audited in CI (`pip-audit`). Hash pinning is a possible later hardening step.

## Data implications

None.

## Operational implications

Deploy hosts install a deployable's own requirements file with the constraints file.
