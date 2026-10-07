# Real-SIM path: first attach uses a line created through RatelLink (software-owned part)
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** Oct 9 | **Owner:** TODO | **Reviewers:** TODO + TODO (two required)
**Source:** Build Plan, Week 2 gate; RatelLink "Done when"; week one detail ("The first real-SIM attach ... must use a line created through this API, not by hand. That attach is RatelLink's acceptance test.").

## Objective
A real SIM, imported and activated **through RatelLink's API**, attaches through our radio, browses, and registers for calls. That is the Week 2 gate.

## Context
The software team owns: importing keys via `POST /v1/sims`, activating with `voice` true, checking with `GET /v1/lines/{imsi}`, and not breaking secrecy while doing it. The network team owns the radio, MongoDB authentication, the ims APN, RatelVoice and the attach itself.

## Scope
- A short written procedure (in `docs/runbooks/`) for creating a real line through the API, with no key ever in a ticket, chat, shell history that leaves the host, or log.
- Run it on the lab with the network team when SIM keys and the radio are ready.
- Record the result against the gate.

## Out of scope
Anything not needed for the gate. Importing existing customers. Live changes.

## Dependencies
- **Outside the software team:** SIM keys settled (they gate Week 2), the eNB joined to RatelCore (Friday), MongoDB authentication on, ims APN and P-CSCF address on RatelCore, a VoLTE phone that works.
- W2-01, W2-02, W2-03 working on the lab.

## Acceptance criteria
- The line was created through the API, not by hand in MongoDB (evidence: RatelLink audit log entries with the calling key id).
- The phone attaches, browses, and registers for calls. If it cannot, the blocker is written down with who owns it.
- The Open5GS document matches the template field for field.
- No Ki/OPc appears in any log, ticket, chat message or screenshot. The log search from W2-04 is green.
- If keys are not ready by Friday, the first attach is next week and this issue says so; do not substitute a hand-made line.

## Security / privacy requirements
Real keys are handled only on the lab hosts, by named people, outside Git, tickets and chat. Do not send them to AI tools.

## Suggested skill level
Careful and calm; Linux, API usage, comfortable working with the network team.
