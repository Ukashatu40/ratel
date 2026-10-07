# ADR NNNN: Title

- **Status:** Proposed | Accepted | Superseded by ADR NNNN | Rejected
- **Date:** YYYY-MM-DD
- **Deciders:** TODO (the project lead decides architecture)
- **Related:** Build Plan section, issues, other ADRs

Use an ADR for meaningful architectural decisions: anything that changes component boundaries,
data ownership, the contract, security posture, the deployables, or adds a dependency or service.
Do not write one for ordinary implementation choices. Number them in order; never edit an
accepted ADR's decision, supersede it with a new one.

## Context

What is the situation? What does the Build Plan or PRD say, and where is it silent? What forces
are in play (deadline, team size, risk)?

## Decision

What we will do, in one or two paragraphs. Plain words.

## Alternatives considered

| Option | Why not (or why it came second) |
| ------ | ------------------------------- |
| | |

## Consequences

What gets easier, what gets harder, what we now have to maintain.

## Security implications

Effect on secrets (Ki, OPc, keys, credentials), access, attack surface, auditability. "None" is an answer, say why.

## Data implications

Effect on data ownership, integrity (idempotency, state machine, kobo, UTC), privacy, retention, migrations.

## Operational implications

Deployment, configuration, monitoring, runbooks, rollback, cost to the Network team.
