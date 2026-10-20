# Module ratel_link: RatelLink is demo-ready and tested
Labels: type:feature, area:ratel-link, area:deployment, priority:p1, risk:critical

**Module:** ratel_link (`services/ratel_link`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-03 RatelLink: install on core-cp and prove the runbook there
- [ ] M-04 RatelLink: readiness check and scheduled key-expiry check
- [ ] M-05 RatelLink: apply the lab answer on deactivate (bar or delete) and on re-activation
- [ ] M-06 RatelLink: apply data changes without waiting for the next attach (detach and re-attach)

## The module is done when
- [ ] A line created only through the API attaches, browses and registers for calls on the lab (lab session 1, A), recorded
- [ ] The service runs on core-cp from a release, the runbook was followed there, and a rollback was done once
- [ ] Deactivate and re-activate behave as the lab proved, and the decision is written in DECISIONS_PENDING
- [ ] No Ki, OPc or caller key in any log, ticket or screenshot (the automated search and the lab search are both clean)
- [ ] The service survives a restart and a MongoDB restart without losing or duplicating a write (test, then once on the lab)
- [ ] A caller key was rotated once with the documented steps
- [ ] Every route still requires a key (the route-protection test passes)
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
Network team (N1, N2, N3, N9, SIM keys, radio). The key-file backup owner (M-23). Two real reviewers.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-03 RatelLink: install on core-cp and prove the runbook there

**Ready:** no, waits for N3 (MongoDB authentication on, who installs), N9 (Python 3.12 beside 3.10) from the network team
**Source:** Week 2 gate; `deploy/core-cp/README.md`; `docs/runbooks/ratel-link.md`; N2, N3, N9 in `docs/RATELCORE_INTEGRATION_FACTS.md`.

#### Objective
RatelLink runs on core-cp as `ratel-link.service` from a release built from `main`, and the runbook has been followed there once, not only in a container.

#### Scope
- Python 3.12 installed beside the system Python (not replacing it); release built from `main`; `install-release.sh <tarball> <python3.12>`.
- `admin_cli init-db`, key file created by the service user, caller keys created for `bss-app` and `meter-agent`, the roles file applied for the `ratel_link` MongoDB user.
- `RATEL_LINK_UE_POOL` set to the agreed range (N2); `RATEL_LINK_VOICE_TEMPLATE_FILE` set once the export exists (N1).
- Update "Last verified" in the runbook with the real date and what was run.

#### Out of scope
Enabling MongoDB authentication (network team). The offline key backup (M-23). Real SIM keys.

#### Depends on
N3, N9, N2, N1. M-23 before any real SIM key is imported.

#### Contract impact
None.

#### Acceptance criteria
- [ ] Startup log shows none of `key.provider.none`, `startup.indexes.missing`, `startup.checks.failed`, `startup.subscribers.index.missing`
- [ ] `GET /healthz` is ok and one authenticated call from a caller succeeds
- [ ] A release rollback was done once with the commands in `deploy/core-cp/README.md`
- [ ] The key file is owned by the service user, mode 0600, outside any Git checkout
- [ ] Runbook "Last verified" names core-cp and the date; any step that did not work is fixed in the runbook

#### Data, security and privacy
No key, caller key or full IMSI in any ticket, chat message, shell history that leaves the host, or log.

#### Testing
Lab. Part of lab session 1.

### M-04 RatelLink: readiness check and scheduled key-expiry check

**Ready:** yes
**Source:** `docs/runbooks/ratel-link.md` (TODO: readiness check; TODO(owner): who runs `check-expiry` and how it alerts).

#### Objective
Someone can tell from outside whether RatelLink can actually work (MongoDB reachable, key readable), and expiring caller keys are logged on a schedule instead of only at start.

#### Scope
- A readiness route outside `/v1` (like `/healthz`, not in the contract): ok only when MongoDB answers and the encryption key is loaded; otherwise 503 with no detail about why.
- A systemd timer and service for `admin_cli api-key check-expiry` in `deploy/core-cp/`. How it alerts: TODO(RatelOps), until then it logs `api_key.expiring`.
- Update the runbook table and remove the two TODOs.

#### Out of scope
Alertmanager rules (network team, Week 5).

#### Depends on
Nothing. Deployment file changes go through the project lead.

#### Contract impact
None (operational routes are not in the contract). The route must be on the route-protection allowlist.

#### Acceptance criteria
- [ ] Test: readiness is ok with a fake healthy store, 503 with MongoDB down, 503 with no key
- [ ] The response body never contains a path, host, key id or exception text
- [ ] `tests/ratel_link/api/test_route_protection.py` passes with the new route allowlisted
- [ ] `tests/tooling/test_deploy_files.py` passes with the new unit files
- [ ] `make check` is green

#### Data, security and privacy
Unauthenticated route: it must reveal nothing. No new MongoDB privilege.

#### Testing
Unit, deployment-file tests. Lab: confirm on core-cp during M-03.

### M-05 RatelLink: apply the lab answer on deactivate (bar or delete) and on re-activation

**Ready:** no, waits for lab session 1, sections B (barring, re-activation after delete)
**Source:** DECISIONS_PENDING items 51 and 52; N4; `docs/issues-week2/W2-05-spike-subscriber-status-barring.md`.

#### Objective
Deactivate and re-activate behave as the lab proved, and the decision is written down.

#### Scope
Decided by the lab answer, one of:
- **Delete stays** (the source reading says the MME seems to ignore barring): only if re-activation attaches again. If it does not (lost `security.sqn`), RatelLink must not write a fresh `sqn` blindly: propose a way to the project lead and the network team first.
- **Bar:** only if the lab shows the MME rejects a barred line and calls are cut too. Then deactivate sets `subscriber_status` instead of deleting.

#### Out of scope
Live changes (M-06).

#### Depends on
Lab session 1, section B.

#### Contract impact
Probably none; if the response or the `line_state` meaning of `barred` changes, `openapi.yaml` in the same commit.

#### Acceptance criteria
- [ ] The decision is recorded in DECISIONS_PENDING with the lab record that supports it
- [ ] Behaviour matches the lab result, with tests for both deactivate and re-activate
- [ ] `docs/runbooks/ratel-link-lab-acceptance.md` step 4.8 updated to what actually happens
- [ ] `make check` is green

#### Data, security and privacy
A deactivated line must stop working. No key is logged. The SIM's stored keys are kept.

#### Testing
Unit plus the lab.

### M-06 RatelLink: apply data changes without waiting for the next attach (detach and re-attach)

**Ready:** no. Do not start. The Build Plan forbids live-change code before the spike answers; waits for lab session 1 section C and decision 57.
**Source:** `docs/spike-live-changes.md`; N5; PRD CHG-6 (live changes, P1, to read once the PRD is in hand); DECISIONS_PENDING item 57.

#### Objective
After a data change, the phone is detached and re-attaches within 60 seconds with its new record.

#### Scope
After the existing `$set`, set and then clear the boolean `request_cancel_location` on that one subscriber document. The replica set and the HSS setting `use_mongodb_change_stream` are done by the network team first.

#### Out of scope
Pushing a new speed into a running session (needs new C code in the PCRF; not recommended).

#### Depends on
Lab session 1 section C passes; network team agrees the field outside the integration guide's list and the `schema_version` change; replica set running.

#### Contract impact
None expected. Whether the response says "applied now" is a product call (PRD).

#### Acceptance criteria
- [ ] The field is a BSON boolean and is never left `true`
- [ ] Nothing else in the document changes; HSS-owned fields survive
- [ ] A failure to detach does not undo the data change
- [ ] On the lab, a data change reaches the phone within 60 seconds without airplane mode
- [ ] If the lab test fails, this issue is closed and the airplane-mode fallback stays

#### Data, security and privacy
No new privilege. No value logged.

#### Testing
Unit, MongoDB integration, lab.
