# Project lead: CI, key backup, reviews, bss-app deployment and demo readiness
Labels: type:infrastructure, area:repository, area:deployment, priority:p1, risk:high

**Owner:** TODO (project lead) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Say so in this issue.**
**Source:** `docs/DEMO_SCRIPT.md`; Build Plan "Definition of done", "Environments" and the weekly gates; `docs/issues-modules/README.md`.

## What this issue is for
The work no software module owns but the demo needs: CI, the key backup, the independent reviews, the bss-app VM, and the rehearsals.

## Deliverables
- [ ] M-22 Repository: run the MongoDB integration tests in CI
- [ ] M-23 Repository: decide the offline backup of the RatelLink key file and name its owner (R-14)
- [ ] M-24 Repository: independent review of the RatelLink key code before customer keys
- [ ] M-27 Repository: deploy RatelBSS on the bss-app VM
- [ ] M-30 Repository: security review of RatelLink and RatelBSS money
- [ ] M-31 Demo readiness: end-to-end dry runs, pilot, runbook, care training, rehearsals

## Done when
- [ ] Every deliverable below is ticked, with the date and the evidence (PR, record or review)
- [ ] The two reviews (M-24, M-30) were done by a person who did not write the code, or the risk is recorded as accepted with the project lead's name (R-17, decision 56)
- [ ] Two full rehearsals ran with no step repeated (M-31)

## Deliverable details

### M-22 Repository: run the MongoDB integration tests in CI

**Ready:** yes, but changing CI is the project lead's decision before work starts
**Source:** `docs/TESTING_STRATEGY.md` (TODO: a MongoDB service container job); the integration and fuzz tests are skipped locally and in CI today.

#### Objective
Tests marked `integration` (RatelLink repositories, the process and database acceptance tests, Schemathesis fuzz) run in CI against a real MongoDB.

#### Scope
A service container for MongoDB in the workflow; set `RATEL_TEST_MONGO_URI`; keep the job required only after it is stable. Consider PostgreSQL too once M-11 exists.

#### Out of scope
Changing branch rules or the review gate.

#### Depends on
The project lead approving the workflow change.

#### Contract impact
None.

#### Acceptance criteria
- [ ] The integration job runs and passes on a PR
- [ ] Breaking a repository test on purpose makes it fail (shown once, then reverted)
- [ ] No credential in the workflow file

#### Data, security and privacy
Synthetic data only.

#### Testing
The workflow itself.

### M-23 Repository: decide the offline backup of the RatelLink key file and name its owner (R-14)

**Ready:** yes
**Source:** `docs/RISK_REGISTER.md` R-14; `docs/runbooks/ratel-link.md` ("Backup: TODO(owner)").

#### Objective
Losing `ratel_link.key` cannot lose every stored Ki and OPc, and one named person is responsible for the copy.

#### Scope
Choose where the copy lives (offline, apart from database backups), who holds it, and how a restore is tested. Write it in the runbook. No key value in the issue.

#### Out of scope
Re-encryption tooling, a second key.

#### Depends on
The project lead's decision.

#### Contract impact
None.

#### Acceptance criteria
- [ ] The runbook names the owner and the procedure (no value)
- [ ] A restore was rehearsed once with a throwaway key, not the real one
- [ ] R-14 is updated

#### Data, security and privacy
The copy is never stored with database backups and never travels in a ticket or chat.

#### Testing
A restore rehearsal.

### M-24 Repository: independent review of the RatelLink key code before customer keys

**Ready:** no, scheduled for Week 6; must be done before any customer key, and not before the Week 6 security review
**Source:** `docs/DECISIONS_PENDING.md` item 56 (proposed); `docs/RISK_REGISTER.md` R-17; closed #32.

#### Objective
Someone who did not write or approve PR #10 reads the key code and its tests and reports what they checked.

#### Scope
`services/ratel_link/security/` (crypto, key provider, authentication), the Ki/OPc store, ADR 0006 and 0007. An AI-assisted pass may be added but does not count as the independent human review.

#### Out of scope
Rewriting the code. Findings become their own issues.

#### Depends on
A reviewer who is not the author and not CaptRaven's approval-only habit. Named by the project lead.

#### Contract impact
None.

#### Acceptance criteria
- [ ] A written review lists what was read and what was not
- [ ] Each finding is a labelled issue or marked as accepted with the project lead's name
- [ ] R-17 is closed or re-rated

#### Data, security and privacy
Review with synthetic keys only. Do not paste real keys anywhere.

#### Testing
n/a

### M-27 Repository: deploy RatelBSS on the bss-app VM

**Ready:** no. Host details for bss-app are unconfirmed (`docs/ARCHITECTURE.md`: TODO) and the network team owns the VM.
**Source:** `deploy/bss-app/README.md` (the only file there); `deploy/core-cp/` as the model; `docs/ARCHITECTURE.md`.

#### Objective
The app (RatelBSS, RatelMeter API, RatelDesk and RatelPay files) runs on bss-app from a release built from `main`, restarts by itself, and is reachable as the architecture says.

#### Scope
PostgreSQL and Redis, a systemd unit with the same hardening as RatelLink's, an owner-only settings template, the reverse proxy (RatelDesk and API over the VPN only, RatelPay and the webhook public), an install and rollback script, a runbook. No host address or secret in committed files.

#### Out of scope
Backups and the restore rehearsal (network team, Week 6, N-01).

#### Depends on
The bss-app VM and VPN from the network team (N-01). M-22 if CI changes are needed.

#### Contract impact
None.

#### Acceptance criteria
- [ ] The install and a rollback were run once on bss-app
- [ ] The deployment-file tests (no secret, no address) pass
- [ ] RatelDesk and the API are not reachable from outside the VPN (checked, recorded)
- [ ] The service restarts after a reboot and after a crash

#### Data, security and privacy
No credential in Git. Database users follow least privilege like `deploy/core-cp/mongo/`.

#### Testing
Deployment-file tests; the install is a lab run.

### M-30 Repository: security review of RatelLink and RatelBSS money

**Ready:** no, scheduled once M-15 to M-19 exist; related to M-24
**Source:** Roadmap Week 6 ("security review of RatelLink and RatelBSS: money"); `docs/AI_ENGINEERING_POLICY.md`.

#### Objective
A human reviewer who did not write the code has checked authorisation, idempotency, the ledger rules and secret handling in RatelLink and RatelBSS money, and the findings are tracked.

#### Scope
Authentication and authorisation on every route, the append-only ledger, voucher and webhook replay, logging of secrets, dependency audit. An AI-assisted pass may help but does not count as the review.

#### Out of scope
Rewriting. Penetration testing by outsiders.

#### Depends on
M-15 to M-19, M-24, a named reviewer.

#### Contract impact
None.

#### Acceptance criteria
- [ ] A written review lists what was read and what was not
- [ ] Every finding is an issue or an accepted risk with the project lead's name
- [ ] The secret scan, dependency audit and log search are green

#### Data, security and privacy
Synthetic data only.

#### Testing
n/a

### M-31 Demo readiness: end-to-end dry runs, pilot, runbook, care training, rehearsals

**Ready:** the first dry run is not ready until the loop works once in the lab
**Source:** `docs/DEMO_SCRIPT.md`; Roadmap Weeks 7 and 8.

#### Objective
The demo script runs twice in rehearsal with no step repeated, on the demo phones, and customer care can use RatelDesk.

#### Scope
- An end-to-end dry run as soon as the pieces exist, and again after every module is demo-ready.
- Pilot on staff SIMs (network team leads); the 100-call test.
- The demo runbook and the decisions in `docs/DEMO_SCRIPT.md` (timing option for act 4, handsets and spares, who presents).
- Customer care training on RatelDesk.
- Decide before Week 7 whether the pilot runs on today's lab machines or new ones (Build Plan, Environments).
- Freeze on 23 November.

#### Out of scope
Anything on the "not before the demo" list.

#### Depends on
All module issues, N-01.

#### Contract impact
None.

#### Acceptance criteria
- [ ] Two full rehearsals with no step repeated, timed, in the demo setting
- [ ] 98 of 100 test calls connect in the pilot
- [ ] A full pilot week of usage matches the network's counters within 1%
- [ ] Every failure in a rehearsal has an issue or a documented fallback

#### Data, security and privacy
Staff SIMs only. No customer data in the demo.

#### Testing
The rehearsals are the test.
