# Network team: what the demo needs from RatelCore, RatelVoice and RatelOps
Labels: type:feature, area:network, area:ops, priority:p0, risk:high

**Module:** Network team | **Owner:** TODO (network lead names the person for each line) | **Reviewer:** TODO | **Target:** TODO per line
**Source:** Roadmap "Network team tracks"; `docs/RATELCORE_INTEGRATION_FACTS.md` (N1 to N9); `docs/DEMO_SCRIPT.md`; #26.
The software team cannot finish its modules without these. Track each as a checkbox; one line may become its own issue.

## RatelCore and radio
- [ ] MongoDB authentication on, HSS and PCRF updated, one test call after (N3)
- [ ] Python 3.12 beside 3.10 on core-cp (N9); RatelLink installed (M-03)
- [ ] Voice template export without keys (N1); static address range (N2)
- [ ] SIM keys settled for the test SIMs (two-digit MNC); eNB joined; ims APN and P-CSCF address
- [ ] Hand-made subscribers removed before the gate
- [ ] NTP on every host (core-up first)
- [ ] Production security settings, including ciphering
- [ ] Per-line byte counter measured and handed over (#24 via lab session 1)
- [ ] Optional: replica set and `use_mongodb_change_stream` for the live-changes test (N5)
- [ ] Backups of MongoDB, PostgreSQL and MySQL, and a real restore rehearsal. No backup of the `open5gs` database leaves core-cp unencrypted

## RatelVoice
- [ ] Call record source: accounting enabled writing to MySQL in UTC, `CREATE TABLE` sent, #26 signed
- [ ] First call between two Ratelplus phones with the QCI 1 voice bearer through Rx
- [ ] At least six test phone models collected, including the brands our customers carry; ask the SIM supplier whether our SIMs support VoLTE
- [ ] Phone test list final; an Android handset for outgoing calls (iPhone outgoing calls fail today)
- [ ] VOI-1 to VOI-4 in the PRD pass: two sellable phone models register and show VoLTE; 20 test calls of 3 minutes all connect with two-way audio and none drops; the called phone shows the caller's number; a deactivated line can't call or be called after its next attach
- [ ] 20 calls at once; restart tests; the 100-call test in the pilot
- [ ] Kamailio configuration in `network/voice/` (without credentials) so it is not only on the VM

## RatelOps
- [ ] Ops VM, Prometheus and Grafana; Kamailio metrics
- [ ] Alertmanager alarms to the network team by email and one messaging channel the team picks: they fire when a radio, RatelCore or RatelVoice is switched off (OPS-1, OPS-2)
- [ ] The demo dashboard

## Demo
- [ ] Pilot on staff SIMs, capacity tests for attach bursts
- [ ] Demo runbook; plan for moving existing customers
- [ ] The bss-app VM and the VPN (M-27)

## Done when
Each box is ticked with the date, or has a named owner and a date. Anything not done by the freeze (23 November) is cut with the project lead's agreement, using the cut list in `docs/DEMO_SCRIPT.md`.
