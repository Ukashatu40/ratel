# Lab session 1: a line created through RatelLink attaches, browses, calls and is counted (Week 2 gate)
Labels: type:investigation, area:ratel-link, area:network, priority:p0, risk:high

**Owner:** TODO (project lead) | **Network team present:** TODO (name) | **Date:** TODO (set when the prerequisites below are all ticked)
**Source:** Build Plan Week 2 gate; `docs/runbooks/ratel-link-lab-acceptance.md`; `docs/spike-live-changes.md`; `docs/DEMO_SCRIPT.md`
**Absorbs:** #21, #22 (lab part), #23, #24, #25 (lab part), #27 (lab part). Each is closed with a link to this issue. #26 is not absorbed: it waits on a network-team decision and has its own owner.

## Objective
One real SIM, created only through RatelLink's API, attaches through our radio, browses, registers for calls and places a call. The same session answers the open lab questions (barring, re-activation, live changes, byte counter) and records the numbers.

## Before the session (all must be ticked, otherwise it is not scheduled)
- [ ] RatelLink installed on core-cp from `deploy/core-cp/` with Python 3.12 beside 3.10 (N9) (M-03)
- [ ] MongoDB authentication on; HSS and PCRF updated; one test call made after (N3), owner: network team
- [ ] Voice template exported without keys (N1) and `RATEL_LINK_VOICE_TEMPLATE_FILE` set; template comparison clean (runbook step 1)
- [ ] Static address range agreed and `RATEL_LINK_UE_POOL` set (N2), owner: network team
- [ ] Encryption key file exists and its offline backup has a named owner (R-14, M-23)
- [ ] Caller key created for `bss-app`, never written down
- [ ] Test SIM keys issued by the lab, two-digit MNC (62100); radio joined to the core; a VoLTE Android phone plus a second phone
- [ ] Hand-made subscribers removed from the lab database (Integration Guide, section 7)

## Steps and what to record
Follow `docs/runbooks/ratel-link-lab-acceptance.md` and fill its record table. Pass or fail, with the SIM's last four digits only.

### A. The gate (was #23)
- [ ] Line created through the API (audit entries show the calling system); the document matches the template
- [ ] Attach within about a minute; browse works on the fixed address
- [ ] IMS registration seen in the S-CSCF log; a call between the two phones rings with two-way audio
- [ ] Data off: no data, calls still work. Data on: back (airplane-mode toggle each time)
- [ ] Log search for the SIM's keys returns 0; no key in any ticket, chat or screenshot

### B. Barring and re-activation (was #21)
- [ ] Deactivate (delete): the phone is rejected with cause #8
- [ ] Re-activate with the same body: does the SIM attach again (the lost `sqn`)? Record exactly what the phone shows
- [ ] On a lab test subscriber, set `subscriber_status` to barred: does the MME reject the attach? Does a barred line keep calls?
- [ ] Written answer in `docs/`; decision on bar versus delete (DECISIONS_PENDING 52); M-05 updated

### C. Live changes (was #22 lab part, `docs/spike-live-changes.md`)
- [ ] Only if the network team agrees to a single-node replica set and `use_mongodb_change_stream`: run the test sequence in the doc
- [ ] Record: does the phone re-attach by itself, how many seconds (target 60), do calls register again
- [ ] Deactivate race (flag first, then delete): is the CLR sent?
- [ ] Result written into the spike doc; decision 57 confirmed or rejected; M-06 started or closed

### D. Byte counter (was #24)
- [ ] Many short flows plus one long transfer; each candidate mechanism's totals against the interface's own counters
- [ ] Chosen mechanism, numbers, within 1%; R-03 updated; M-07 unblocked

### E. Data agent on core-up (was #25 lab part)
- [ ] The agent runs as a service on core-up with a runbook note (M-09)
- [ ] Over the real session from A, totals match the interface counters within 1%
- [ ] Stop and restart mid-interval: nothing lost, nothing counted twice

### F. RatelBSS flow (was #27 lab part)
- [ ] Sell-to-activate from RatelBSS produces exactly one `/activate` call on the lab RatelLink (M-14)
- [ ] RatelBSS's `GET /v1/lines/{imsi}` view matches the network's

## Out of scope
Importing customers, live changes beyond test C, call accounting (#26), anything from Week 3 onward.

## Done when
Sections A to F each say pass, or fail with a named blocker and owner. A fail is a finding, not a reason to keep this issue open; the fix gets its own issue. Never substitute a hand-made line.

## Security
Real keys are handled on the lab hosts by named people only. No keys, caller keys or full IMSIs in this issue, its comments or screenshots. Open5GS keeps plaintext Ki/OPc: no database backup leaves core-cp unencrypted.
