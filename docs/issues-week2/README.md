# Week 2 issues (Oct 5 to Oct 9)

Seeded strictly from the Build Plan's Week 2 software objectives:

- RatelLink complete against the lab, writing calling settings
- RatelMeter's data agent running on core-up
- RatelBSS's line flow calling the real RatelLink
- Live-changes spike written up
- The real-SIM path usable (software-owned part)
- Contract and mock integration

**Week 2 gate:** a real SIM, created through RatelLink, attaches, browses and registers for calls.

Owners and reviewers were assigned by the project lead on 2026-10-08 (see
[../OWNERSHIP_MATRIX.md](../OWNERSHIP_MATRIX.md)). "Suggested skill level" describes the kind of work.
W2-09 still has no named owner. Items that depend on Week 1 work say "TODO confirm" because the
status of Week 1 was not visible when these were written. Several target dates (Oct 7 and Oct 8)
have already passed: re-plan against the Week 2 gate on Oct 9.

The Ki/OPc encryption ([ADR 0006](../adr/0006-ki-opc-encryption-at-rest.md)) and API-key authentication
([ADR 0007](../adr/0007-api-key-verification-and-rotation.md)) are decided and built in the security PR,
so W2-01 to W2-03 build on them instead of waiting for those decisions.

`scripts/github/create_issues.sh` turns each `W2-*.md` file into a GitHub issue (title from the
first line, labels from the `Labels:` line, assignee from `**Owner:** @login` when there is one, the
rest as the body). Review them first. Run it once: running it again creates duplicates.

| File | Workstream | Risk | Reviewers |
| ---- | ---------- | ---- | --------- |
| W2-01 | RatelLink: `POST /v1/sims` on the encrypted key store (store delivered by the security PR) | Critical | 2 |
| W2-02 | RatelLink: activate, data, deactivate write the subscriber document | Critical | 2 |
| W2-03 | RatelLink: line status, assignments, audit entries on writes (API-key auth delivered by the security PR; CI auth seeding for Schemathesis) | Critical | 2 |
| W2-04 | RatelLink: acceptance tests | Critical | 2 |
| W2-05 | Spike: `subscriber_status` barring | High | 1 |
| W2-06 | Spike: live-changes write-up | High | 1 |
| W2-07 | Real-SIM path (software-owned part) | Critical | 2 |
| W2-08 | Spike: counter mechanism on core-up | High | 1 |
| W2-09 | RatelMeter data agent on core-up | High | 1 |
| W2-10 | Call record fields agreed with the network team | High | 1 |
| W2-11 | RatelBSS lines: line flow against the real RatelLink | High | 1 |
| W2-12 | Contracts: reconcile, close TODOs, keep the mock current | High | 1 (controlled) |
| W2-13 | RatelBSS lines: the line state machine (pure, with tests). First task for @Abbalolo | High | 1 |
| W2-14 | RatelMeter agent: interval and counter delta logic (pure). First task for @ml-lawarn | High | 1 |
| W2-15 | RatelMeter agent: disk spool and ordered replay | High | 1 |
| W2-16 | Independent review of the merged RatelLink key code (PR #10) | Critical | 2 (review task) |
| W2-17 | Docs: follow the setup guide on a clean machine and fix what is unclear. First task for @Arfaaah | Low | 1 |

## Re-plan, 2026-10-08

Written on Thursday evening, one day before the gate. **Dates changed; the Nov 26 demo date did not.**

### Where we are

- Built and merged (PR #10): the encrypted SIM key store, API-key authentication on `/v1`, the audit log writer, the admin CLI. Everything W2-01 to W2-03 builds on.
- Not built: the six Contract 1 endpoints, the Open5GS document builder, IP allocation. None of W2-01 to W2-04 had started, and all were due Oct 8 or 9.
- One strong backend developer (the project lead) owns all of RatelLink and cannot approve their own PRs. Four of the other five people are new to a shared, reviewed codebase.

### The honest answer on the Week 2 gate

"A real SIM, created through RatelLink, attaches, browses and registers for calls" **cannot pass on Oct 9.** Software needs `POST /v1/sims` (W2-01), `activate` with the Open5GS template (W2-02), and an address from the pool. The network side needs SIM keys, the radio, the ims APN and MongoDB authentication, and we do not know their state. The Build Plan allows for this: "this Friday if SIM keys are ready and **next week if not**" (and W2-07 says the same). Recommendation: tell management on Oct 9 that the gate moves to Wed Oct 14 to Fri Oct 16, with the reason and the new date. Do not substitute a hand-made line.

### The critical path

```
Oct 9    W2-01 POST /v1/sims  ──┐                      (lead)
Oct 9    template + MongoDB auth + SIM key status  ──►  (CaptRaven: blocks W2-02)
Oct 13   W2-02 activate / data / deactivate  ───────────┤  (lead)
Oct 14   W2-03 GET line, assignments, audit  ───────────┤  (lead)
Oct 15   W2-04 acceptance tests                          │
Oct 14+  W2-07 first real-SIM attach  ◄── SIM keys, radio, ims APN (network)
```

Everything not on this path runs **in parallel** and must not need the lead:

| Person | Now to Oct 9 | Oct 12 to 16 |
| ------ | ------------ | ------------ |
| **@Ukashatu40** | W2-01. Close the contract items W2-01 and W2-02 need (W2-12). Run the onboarding Session 1. Create the issues and the Project. | W2-02, W2-03, W2-04. Review windows twice a day. |
| **@CaptRaven** | 1) hand over the Open5GS subscriber template, say whether MongoDB authentication is on, and what state the SIM keys are in (these block the lead). 2) Review PR #11. | W2-16 (final), W2-08 counter spike, W2-05, W2-06 write-up, W2-10 answers, pair on W2-09. |
| **@capitanaserdel** | Onboarding. W2-16 first pass (the code he will approve changes to). Read the PRD and tell the lead what RatelDesk needs from a BSS API. | Standing second approver. Mentor @Arfaaah. RatelDesk groundwork once the BSS API shape is agreed (Week 4 screens). |
| **@Abbalolo** | Onboarding and practice PR (Oct 9). | W2-13 (state machine), then W2-11 against the mock. |
| **@ml-lawarn** | Onboarding and practice PR (Oct 9). | W2-14, W2-15, then W2-09 with @CaptRaven. W2-10 draft. |
| **@Arfaaah** | Onboarding and practice PR (Oct 9). | W2-17, then RatelPay groundwork when RatelDesk and the BSS API exist. |

### What moved, and why

| Issue | Was | Now | Reason |
| ----- | --- | --- | ------ |
| W2-01 | Oct 8 | Oct 9 | Everything it needs exists. First on the lead's list |
| W2-02 | Oct 8 | Oct 13 | Needs the template from the network team |
| W2-03, W2-04 | Oct 8, 9 | Oct 14, 15 | After W2-02 |
| W2-05 | Oct 7 | Oct 12 | The first attach works without it (delete and rewrite) |
| W2-06 | Oct 9 | Oct 13 | Its only consumer is the Week 5 decision. **Lead decides** whether to keep Oct 9 |
| W2-07 | Oct 9 | Oct 14 (software) | Waits for network inputs |
| W2-08 | Oct 7 | Oct 12 | Needed for real counters, not for W2-14 or W2-15 |
| W2-09 | one big issue | epic over W2-14, W2-15, W2-08, W2-03 | Too big for one issue, and can start without the lab |
| W2-11 | Oct 9 | Oct 16 | Needs the state machine (W2-13) first, then the real RatelLink |

### What the lead must do

1. **Tonight or first thing:** ask @CaptRaven the four questions that block W2-02 and W2-07: is the Open5GS subscriber template (with the ims APN) available, is MongoDB authentication on and bound to 127.0.0.1, what is the state of the SIM keys, and when does the radio join.
2. **Share the Build Plan and the PRD** with the team privately (neither is in the repository). The PRD is also what @capitanaserdel needs to design RatelDesk.
3. **GitHub, once, by you:** `scripts/github/setup_labels.sh` (adds the new labels), `gh auth refresh -s project` then `scripts/github/create_project.sh Ukashatu40`, finish the Status options and views by hand (GITHUB_SETUP.md), then `scripts/github/create_issues.sh` **once** after you have read the issue files (it now assigns owners). Create four Onboarding issues from the issue form.
4. **Decide:** keep or move the W2-06 date; tell management about the gate.
5. **Plan Week 3 this weekend.** The Week 3 software items are RatelMeter writing records and `/v1/usage`, plans and bundles, and the rating logic on synthetic records. The lead is on RatelLink until about Oct 15. The rating function (pure, with tests, Build Plan "BSS: money") is a candidate for @capitanaserdel to write: it is money, so the lead and @CaptRaven both review it, and the gate enforces that. Decide by Oct 12.

### Risks this plan accepts

- The lead is still a single point of failure for RatelLink until a second person can read and change it (R-08). The plan reduces what else the lead has to do, not that.
- Review capacity: two required reviewers on every RatelLink PR, one of them also on the network team (R-10). Agree two review windows a day.
- Juniors' first tasks are small pure-logic issues on purpose. They are the lowest-risk way to learn the flow, and they do not move the gate. If W2-13 to W2-15 slip by a few days, nothing critical slips.
