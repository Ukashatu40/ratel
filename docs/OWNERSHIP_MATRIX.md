# Ownership matrix

Workstreams are the Build Plan's. **Assigned by the project lead on 2026-10-08** (roster and
reasoning in [TEAM_STRUCTURE.md](TEAM_STRUCTURE.md)). Keep `.github/CODEOWNERS` and the owner
fields of the Week 2 issues in step with this file when owners change.

| Workstream | Primary Owner | Backup | Reviewer | Risk | Current Status | Notes |
| ---------- | ------------- | ------ | -------- | ---- | -------------- | ----- |
| Contracts (`contracts/openapi.yaml`, mock) | @Ukashatu40 | @CaptRaven | @CaptRaven (controlled) | High | Week 2: reconcile with merged contract, close TODOs | Build Plan gate Week 1: `openapi.yaml` merged. Change lands on both sides in one commit. |
| RatelLink | @Ukashatu40 | none yet (R-08) | @CaptRaven + @capitanaserdel (two required) | Critical | Week 2: complete against the lab | Build Plan: owner should be the most careful developer, not the fastest. Holds every line's keys. Encryption and API-key authentication are built (ADR 0006, 0007). |
| RatelMeter: agent (core-up data mode, voice call mode) | TODO (suggested: @ml-lawarn paired with @CaptRaven) | @CaptRaven | @CaptRaven + @Ukashatu40 | High | Week 2: data agent running on core-up | Linux, packet counters. Call mode starts once the network team agrees the call record fields. |
| RatelMeter: API (`/v1/usage`, `/v1/calls`, record store) | @ml-lawarn | @Abbalolo | @Ukashatu40 | High | Week 3: records every 300 seconds, `/v1/usage` | Upserts on `imsi + period_start` and `call_id`. |
| RatelBSS: lines (and its screens) | @Abbalolo | @ml-lawarn | @Ukashatu40 | High | Week 2: line flow calling the real RatelLink | Calls the network only through RatelLink. |
| RatelBSS: money | @Ukashatu40 | none yet (R-08) | @CaptRaven + @capitanaserdel (two required) | Critical | Vouchers and gateway sandbox now; rating once the plan model settles | Wallets, ledger, vouchers, payments, rating job. |
| RatelDesk | @capitanaserdel | @Abbalolo | @Ukashatu40 | Medium | Not started; needs a frontend developer from week two | Against a mock of the BSS API. First screens Week 4. |
| RatelPay | @Arfaaah (supervised) | @capitanaserdel | @capitanaserdel | Medium | Not started; Week 5 | Under 3 seconds on 3G; nothing personal shown. |
| Repository, CI and GitHub governance | @Ukashatu40 | @capitanaserdel | @capitanaserdel, and @CaptRaven for the review-gate files | High | Foundation created (this scaffold) | See [GITHUB_SETUP.md](GITHUB_SETUP.md) for what is applied. |
| RatelVoice | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Week 2: first phone registers for calls | Network team owns. Touches software only via RatelLink and RatelMeter. Configuration in `network/voice/`. |
| RatelOps | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Starts week 4 | Configuration in `ops/`. |
| RatelCore and radio | Network team (TODO name; confirm whether @CaptRaven) | TODO | Network team | Network | Week 2: settle SIM keys; first real-SIM attach | Network team owns. |
