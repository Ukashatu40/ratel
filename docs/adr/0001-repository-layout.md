# ADR 0001: Repository layout follows the Build Plan tree

- **Status:** Proposed (needs project lead approval)
- **Date:** 2026-10-06
- **Deciders:** TODO
- **Related:** Build Plan "Stack and repo layout"; [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #1

## Context

The setup request offered a starting layout with `services/{ratel_link, meter_agent, meter_api,
bss_lines, bss_money}` and allowed following the Build Plan's tree instead. The Build Plan says
there are three deployables, and that `app` runs "RatelBSS, RatelMeter's API, and the RatelDesk and
RatelPay front ends, as separate modules in one process". Its tree puts `bss_lines/`, `bss_money/`
and `meter_api/` under `services/app/`. Its tree is ambiguous about whether `ops/` sits under
`network/` or beside it.

## Decision

Follow the Build Plan tree: `services/app/{bss_lines,bss_money,meter_api}` as modules of one
Python package `app`, plus `services/ratel_link/` and `services/meter_agent/`. `web/desk`,
`web/pay`, `network/voice`, `ops/` (top level, as in the request's sketch), and `deploy/{core-cp,
core-up,voice,bss-app,ops}`. Python sources root is `services/` (`pythonpath` in `pyproject.toml`).

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Flat `services/bss_lines`, `services/meter_api`, ... as in the request's sketch | Reads as five services; the Build Plan says one process. Invites separate deployables. |
| One package per module with its own `pyproject.toml` | More tooling and release overhead than three deployables justify. |

## Consequences

Simple imports (`app.bss_lines`). Module boundaries inside `app` are conventions enforced by
tests in `tests/architecture/`, not by process boundaries. Splitting a module out later is
possible because dependency direction is already enforced.

## Security implications

None directly. Keeping RatelBSS out of `ratel_link` and the MongoDB driver is enforced by import tests.

## Data implications

One Alembic history for the `app` PostgreSQL database.

## Operational implications

One deployable for bss-app. Deployment files per host under `deploy/`.
