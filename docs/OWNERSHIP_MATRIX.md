# Ownership matrix

Workstreams are the Build Plan's. **Assigned by the project lead on 2026-10-08 and revised on
2026-10-18** (roster and reasoning in [TEAM_STRUCTURE.md](TEAM_STRUCTURE.md); the revision is
decision 58 in [DECISIONS_PENDING.md](DECISIONS_PENDING.md)). Keep `.github/CODEOWNERS` and the owner
fields of the module issues in step with this file when owners change.

One module issue has one owner. It is not split between people: an owner who is stuck asks the
project lead.

| Workstream | Primary Owner | Backup | Reviewer | Risk | Current Status | Notes |
| ---------- | ------------- | ------ | -------- | ---- | -------------- | ----- |
| Contracts (`contracts/openapi.yaml`, mock) | @Ukashatu40 | @CaptRaven | @CaptRaven (controlled) | High | Week 2: reconcile with merged contract, close TODOs | Build Plan gate Week 1: `openapi.yaml` merged. Change lands on both sides in one commit. |
| RatelLink | @Ukashatu40 | @capitanaserdel (decision 6; risk R-08 stays open until they can change it) | @CaptRaven + @capitanaserdel (two required) | Critical | Week 2: complete against the lab | Build Plan: owner should be the most careful developer, not the fastest. Holds every line's keys. Encryption and API-key authentication are built (ADR 0006, 0007). |
| RatelMeter: agent (core-up data mode, voice call mode) | @capitanaserdel | @Abbalolo | @Ukashatu40, and @CaptRaven for the counters | High | Week 2: data agent running on core-up | Linux, packet counters, read with @CaptRaven. Call mode starts once the network team agrees the call record fields. One owner for the agent and the API, so the ingest call between them has one author. |
| RatelMeter: API (`/v1/usage`, `/v1/calls`, record store) | @capitanaserdel | @Abbalolo | @Ukashatu40 (the owner cannot approve their own code) | High | Week 3: records every 300 seconds, `/v1/usage` | Upserts on `imsi + period_start` and `call_id`. |
| RatelBSS: lines | @Abbalolo | @capitanaserdel | @Ukashatu40 | High | Week 2: line flow calling the real RatelLink | Calls the network only through RatelLink. Its screens are RatelDesk, a separate row. |
| RatelBSS: money | @Ukashatu40 | @capitanaserdel (decision 6; risk R-08 stays open until they can change it) | @CaptRaven + @capitanaserdel (two required) | Critical | Vouchers and gateway sandbox now; rating once the plan model settles | Wallets, ledger, vouchers, payments, rating job. One owner for the whole module. |
| RatelDesk | @ml-lawarn | @capitanaserdel | @capitanaserdel | Medium | Not started | Against a mock of the BSS API. First screens Week 4. Frontend only: no backend work (decision 58). |
| RatelPay | @Arfaaah (supervised) | @ml-lawarn | @capitanaserdel | Medium | Not started; Week 5 | Under 3 seconds on 3G; nothing personal shown. |
| Repository, CI and GitHub governance | @Ukashatu40 | @capitanaserdel | @capitanaserdel, and @CaptRaven for the review-gate files | High | Foundation created (this scaffold) | See [GITHUB_SETUP.md](GITHUB_SETUP.md) for what is applied. |
| RatelVoice | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Week 2: first phone registers for calls | Network team owns. Touches software only via RatelLink and RatelMeter. Configuration in `network/voice/`. |
| RatelOps | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Starts week 4 | Configuration in `ops/`. |
| RatelCore and radio | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Week 2: settle SIM keys; first real-SIM attach | Network team owns. |
