# Week 2 issues (Oct 5 to Oct 9)

Seeded strictly from the Build Plan's Week 2 software objectives:

- RatelLink complete against the lab, writing calling settings
- RatelMeter's data agent running on core-up
- RatelBSS's line flow calling the real RatelLink
- Live-changes spike written up
- The real-SIM path usable (software-owned part)
- Contract and mock integration

**Week 2 gate:** a real SIM, created through RatelLink, attaches, browses and registers for calls.

Owners and reviewers are **TODO**: the project lead assigns them after assessments. "Suggested skill
level" describes the kind of work, not a person. Items that depend on Week 1 work say
"TODO confirm" because the status of Week 1 was not visible when these were written.

`scripts/github/create_issues.sh` turns each `W2-*.md` file into a GitHub issue (title from the
first line, labels from the `Labels:` line, the rest as the body). Review them first.

| File | Workstream | Risk | Reviewers |
| ---- | ---------- | ---- | --------- |
| W2-01 | RatelLink: key store and `POST /v1/sims` | Critical | 2 |
| W2-02 | RatelLink: activate, data, deactivate write the subscriber document | Critical | 2 |
| W2-03 | RatelLink: line status, assignments, audit log, API-key auth | Critical | 2 |
| W2-04 | RatelLink: acceptance tests | Critical | 2 |
| W2-05 | Spike: `subscriber_status` barring | High | 1 |
| W2-06 | Spike: live-changes write-up | High | 1 |
| W2-07 | Real-SIM path (software-owned part) | Critical | 2 |
| W2-08 | Spike: counter mechanism on core-up | High | 1 |
| W2-09 | RatelMeter data agent on core-up | High | 1 |
| W2-10 | Call record fields agreed with the network team | High | 1 |
| W2-11 | RatelBSS lines: line flow against the real RatelLink | High | 1 |
| W2-12 | Contracts: reconcile, close TODOs, keep the mock current | High | 1 (controlled) |
