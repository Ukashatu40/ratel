# Team structure

**No permanent assignments yet.** The project lead has not completed individual technical
capability assessments and will assign people after assessing each one. Job titles are not a proxy
for ability. Do not infer ownership of RatelLink, RatelMeter, BSS lines, BSS money, security or
frontend from a title. Everything below is a template with `TODO`.

## Current team composition

| Group | Size | Notes |
| ----- | ---- | ----- |
| Software team: developers | 5 | Most have experience with React, Next.js, Python and Node.js. Capabilities not yet assessed. |
| Software team: additional reviewer | 1 | The "independent reviewer" for critical changes. TODO: name and confirm. |
| Software project lead | 1 | Owns the software implementation. Assigns work after assessments. |
| Network team | separate | Owns RatelCore, RatelVoice, RatelOps, radio and network infrastructure. Most senior relevant person: Senior Network/Software Engineer (network lead). |

The software team owns the business and software side. The Network team owns the network side.
Respect that boundary. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Known role categories (not assignments)

- **Project lead:** priorities, assignments, final say on architecture decisions and contract changes.
- **Independent reviewer:** second reviewer on critical changes (RatelLink, RatelBSS: money).
- **Workstream owner:** accountable for a workstream's delivery. TODO.
- **Backup:** can take over a workstream. TODO.
- **Network lead:** Network team counterpart for RatelLink, RatelMeter and RatelVoice touchpoints.
- **Frontend lead:** ultimately owns RatelDesk and RatelPay review routing. TODO: confirm after assessments.

## Proposed workstream categories

Taken from the Build Plan: Contracts, RatelLink, RatelMeter (agent and API), RatelBSS: lines,
RatelBSS: money, RatelDesk and RatelPay, plus repository/CI/GitHub governance. RatelVoice, RatelOps
and RatelCore belong to the Network team. The Build Plan's guidance for the split: one careful
developer owns RatelLink (it holds every line's keys), the network-facing work (Linux, MongoDB,
packet counters) and the application work (pure application code) are different skills, and
RatelDesk and RatelPay need a frontend developer from week two. With fewer than four backend
developers, whoever owns BSS lines builds its screens too.

## Technical skill assessment matrix

Filled in by the project lead. Suggested scale: `0` none, `1` basic, `2` working, `3` strong, `?` not assessed.

| Person | Role | React | Next.js | TypeScript | Python | FastAPI | Node.js | SQL | PostgreSQL | MongoDB | Docker | Linux | Testing | Git/GitHub | Security | Backend | Frontend | Notes |
| ------ | ---- | ----- | ------- | ---------- | ------ | ------- | ------- | --- | ---------- | ------- | ------ | ----- | ------- | ---------- | -------- | ------- | -------- | ----- |
| TODO dev 1 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |
| TODO dev 2 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |
| TODO dev 3 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |
| TODO dev 4 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |
| TODO dev 5 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |
| TODO reviewer | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | |

## Ownership matrix

See [OWNERSHIP_MATRIX.md](OWNERSHIP_MATRIX.md).

## Reviewer matrix

| Area | Reviewers required | Who |
| ---- | ------------------ | --- |
| RatelLink (`services/ratel_link/`) | **2** | TODO: project lead + independent reviewer |
| RatelBSS: money (`services/app/bss_money/`) | **2** | TODO: project lead + independent reviewer |
| Contracts (`contracts/`) | 1, controlled | TODO: project lead, network lead consulted |
| RatelBSS: lines, RatelMeter | 1 | TODO |
| RatelDesk, RatelPay | 1 | TODO: frontend lead |
| RatelVoice and RatelOps configuration | 1 | TODO: network lead |
| CI, GitHub governance, security docs | 1, controlled | TODO: project lead |

The author never reviews their own PR. Avoid making one person the reviewer for everything.

## Escalation path

1. **Blocked on a technical question:** ask in the issue; if unresolved within half a day, the workstream owner, then the project lead.
2. **Needs the network team** (RatelCore, RatelVoice, lab access, SIM keys, call record fields): the network lead. TODO: confirm contact.
3. **Product behavior unclear or Build Plan and PRD seem to disagree:** the project lead. The PRD wins.
4. **Architecture or contract decision:** the project lead, via an ADR. Do not decide silently.
5. **Security concern or leaked secret:** the private channel in [../SECURITY.md](../SECURITY.md), never a public issue or chat.
6. **Weekly gate at risk:** the project lead, as soon as it is visible. Risks go in [RISK_REGISTER.md](RISK_REGISTER.md).
7. **Voice decision (Oct 16) and scope changes:** management decides, via the project lead.
