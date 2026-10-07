# ADR 0003: A small shared `common` library

- **Status:** Proposed (needs project lead approval)
- **Date:** 2026-10-06
- **Related:** Build Plan "Engineering rules" (logs, time, money); [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #3

## Context

`ratel-link` and `app` deploy to different hosts but must share: the standard error shape, JSON
logging that never leaks Ki/OPc/PINs, UTC and 300-second interval helpers, and the strict kobo
type. Duplicating them risks the two copies drifting on exactly the rules the Build Plan calls
non-negotiable.

## Decision

`services/common/` holds only those four things (errors, logging and HTTP request context, time,
money). It imports nothing from the deployables or from database drivers (tested). It ships with
each deployable that imports it.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Duplicate the code in each service | Silent drift on security-relevant behavior. |
| Publish `common` as a separate package | Release overhead for ~200 lines. |
| Put it inside `app` and import from `ratel_link` | Breaks the rule that `ratel_link` does not import `app`. |

## Consequences

One more directory to keep small. It must not grow business logic. A PR that adds anything else
to `common` needs the project lead's review.

## Security implications

Positive: redaction and error behavior are tested once. A bug there affects both services.

## Data implications

Kobo and UTC rules are defined once.

## Operational implications

Deploy bundles for core-cp and bss-app include `services/common/`.
