# Roadmap

Source: Build Plan, "The eight-week plan". Dates and gates are the Build Plan's. **The deadline is
not modified here.** A week is not finished until its gate passes, and the next week's work assumes
it has. Three tracks run side by side: RatelCore and the radio, RatelVoice (both network team), and
the software (this repository).

**Active phase: Week 2. Re-planned on 2026-10-08: the Week 2 gate carries into the week of Oct 12 (see [issues-week2/README.md](issues-week2/README.md)). The Nov 26 demo date is unchanged.**

| Week | Dates | Software work | Gate |
| ---- | ----- | ------------- | ---- |
| 1 | Sep 28 to Oct 2 | Contracts merged on day one, then the week one tasks | The eNB registers with our MME, and `openapi.yaml` is merged |
| **2 (active)** | **Oct 5 to Oct 9** | RatelLink complete against the lab, writing calling settings; RatelMeter's data agent running on core-up; RatelBSS's line flow calling the real RatelLink; live-changes spike written up | **A real SIM, created through RatelLink, attaches, browses and registers for calls** |
| 3 | Oct 12 to Oct 16 | RatelMeter writes records every 300 seconds and serves `/v1/usage`; plans and bundles; rating logic tested on synthetic records | Usage for a real session matches the interface counters within 1%, and two phones hold a call |
| 4 | Oct 19 to Oct 23 | Rating job live, with `out_of_data` triggered at zero; vouchers redeem; first RatelDesk screens | The full prepaid loop works in the lab, and a line sold in RatelDesk makes a call |
| 5 | Oct 26 to Oct 30 | Live changes, if the spike says they are small; the payment gateway end to end in sandbox; first reports; RatelPay | Alarms fire when a radio, RatelCore or RatelVoice is switched off |
| 6 | Nov 2 to Nov 6 | Hardening: restart, replay and idempotency tests; security review of RatelLink and RatelBSS: money | Restarts and replays lose nothing and count nothing twice; a restore has actually been done |
| 7 | Nov 9 to Nov 13 | Daily fixes from the pilot; reconciliation reports | A full week of pilot usage matches the network's counters, and 98 of 100 test calls connect |
| 8 | Nov 16 to Nov 20 | Customer care trained on RatelDesk; final fixes; two full demo rehearsals | The demo script runs twice with no step repeated |
| Demo | Nov 23 to Nov 26 | Freeze, on call | The demo on 26 November |

## Network team tracks (context, not software-team work)

| Week | RatelCore and radio | RatelVoice |
| ---- | ------------------- | ---------- |
| 1 | Turn on MongoDB authentication; create the bss-app and voice VMs; cable the radio and bring it up on RatelCore | Kamailio P-CSCF, I-CSCF, S-CSCF, rtpengine and IMS DNS installed; ims APN and P-CSCF address on RatelCore; test phones collected |
| 2 | Settle SIM keys; first real-SIM attach | First phone registers for calls on a real SIM; phone test list started; call record fields agreed with RatelMeter |
| 3 | Production security settings on the core, including ciphering; NTP on every host | First call between two Ratelplus phones, with the QCI 1 voice bearer set up through Rx. Voice decision point on 16 October |
| 4 | Create the ops VM; Prometheus and Grafana on RatelCore | Call records flowing to RatelMeter's call agent; Kamailio metrics in Prometheus |
| 5 | Alertmanager alarms; the RatelOps demo dashboard; any core changes the spike calls for | Phone test list final; IPsec and codec fixes for the phones that need them |
| 6 | Backups of MongoDB, PostgreSQL and MySQL, and a real restore rehearsal | 20 calls at once; restart tests |
| 7 | Pilot on staff SIMs; capacity tests for attach bursts | Pilot: staff use their lines for calls; the 100-call test |
| 8 | Demo runbook; plan for moving existing customers | Fixes from the pilot |

## Things outside the software team that can move the whole plan

- **SIM keys gate Week 2.** Until the core holds Ki and OPc for real SIMs, no real phone can attach.
- **Phones gate voice.** If by **16 October** no phone we could sell registers and calls reliably, management decides whether the demo shows calls on the phones that do work, or whether voice moves to a later date. Data does not wait for voice.
- **Network team load.** It carries RatelCore, RatelVoice, RatelOps and the radio. RatelVoice needs its own engineer.

## Week 2 software issues

Seeded in [issues-week2/](issues-week2/). Work backward from the gate: nothing here is "extra".

## Finish line

A customer can be sold a SIM in RatelDesk, browse through RatelCore, call another Ratelplus line
through RatelVoice, run out of data and be slowed or cut off while calls still work, and top up on
RatelPay, with every byte and every call matching the network's own records.

## Not before the demo

Calls to other networks, SMS and emergency calls; charging for calls; live-change code before the
spike answers its questions; dealer hierarchy and wallets; USSD; a second payment gateway; postpaid
and credit limits; real-time online charging for data; self-care and dealer apps.
