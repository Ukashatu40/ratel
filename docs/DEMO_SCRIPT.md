# Demo script and cut list (draft)

The demo is **26 November 2026**. This is a draft for the project lead to change, written on
2026-10-14 from the Build Plan and the network team's documents. The PRD is not in this repository,
so every product detail it decides is marked `TODO(PRD)`. Where this page and the PRD disagree, the
PRD wins.

Nothing here is a promise. It is the shortest path that satisfies the Build Plan's finish line, so
that the team and management argue about the same sentence.

## The finish line (Build Plan, "The finish line")

> A customer can be sold a SIM in RatelDesk, browse through RatelCore, call another Ratelplus line
> through RatelVoice, run out of data and be slowed or cut off while calls still work, and top up
> on RatelPay, with every byte and every call matching the network's own records.

The demo is done when that runs, twice in rehearsal, **with no step repeated** (Week 8 gate).
Anything that does not serve that sentence can wait.

## The run (about ten minutes, six acts)

Each act names what is shown, what has to work behind it, who owns it, and what the fallback is.
Owners come from [OWNERSHIP_MATRIX.md](OWNERSHIP_MATRIX.md).

| # | Act (what the audience sees) | What must work behind it | Owner | Fallback if it fails live |
| - | ---------------------------- | ------------------------ | ----- | ------------------------- |
| 1 | **Sell a SIM.** In RatelDesk, create a customer, pick a free SIM and number, pick a plan, activate. The phone shows the network | RatelBSS lines, `POST /v1/lines/{imsi}/activate` with voice on, the SIM's keys already imported (`POST /v1/sims`), the phone attaching to RatelCore | @Abbalolo (BSS lines), @Ukashatu40 (RatelLink), network team (radio, core) | Activate the line from a prepared script and show the same screen. Keep one spare, already activated, line |
| 2 | **Browse.** Open a web page on the new line. Show the line page: data used so far | Attach with the fixed address from RatelLink, RatelMeter counting bytes, RatelBSS showing them | @ml-lawarn (RatelMeter), @Abbalolo | Show the counters from the network side next to the screen |
| 3 | **Call.** Call a second Ratelplus line. It rings, audio both ways, caller's number shown. Calls are free in the demo | RatelVoice, the `ims` session written by RatelLink, an **Android VoLTE** handset for the outgoing side | Network team (RatelVoice), @Ukashatu40 | Play the call from the other direction, or show a recorded registration. See "Phones" below |
| 4 | **Run out of data.** A line with a small allowance reaches zero. Data is slowed or cut. A call still works | Rating job, out-of-data trigger, `POST /v1/lines/{imsi}/data`, a re-attach so the change bites, voice untouched by the data change | @Ukashatu40 (money and RatelLink), @ml-lawarn | Use the line already at zero (see "Timing") and make the call from it |
| 5 | **Top up.** On RatelPay, redeem a voucher (or pay in the sandbox). Data returns | Vouchers, wallet credit exactly once, out-of-data reversed with `data` full, a re-attach | @Ukashatu40, @Arfaaah (RatelPay) | Voucher only; skip the gateway |
| 6 | **Prove the numbers.** Show the bytes and calls on the line page next to the network's own counters and records. They match (within 1% for data) | The accuracy check from the Week 3 gate, reconciliation, the RatelOps dashboard as the live screen | @ml-lawarn, network team (RatelOps), @Ukashatu40 | Show the stored 100-call and one-week pilot results |

`TODO(PRD)`: the plan name and allowance for the demo line, the voucher value, what the customer
sees on the line page, the exact words on the out-of-data screen, and what RatelPay shows after a
top-up.

## Things the audience must be told, not surprised by

These are true today and the Build Plan says they are acceptable for the demo, if said honestly.

- **Changes bite at the phone's next attach.** Data off, slowed, back on, and a deactivation reach
  the phone only after airplane mode is toggled (no live changes yet; they need a MongoDB replica
  set, N5). Rehearse the toggle as part of the act, with a sentence that explains it.
- **A line can use about five minutes of data past zero** before it is noticed, because the rating
  loop runs every 300 seconds.
- **Calls to other networks do not work**, and neither do SMS or emergency calls. Do not dial a
  mobile number outside Ratelplus in front of anyone.
- **Calls between Ratelplus lines are free** for the demo.

## Phones

- Outgoing calls from **iPhones fail today** (a network-side fallback behaviour). Incoming calls to
  them work. Use an Android VoLTE handset to place the call in act 3.
- A SIM must have a **two-digit MNC** (62100) or it does not belong to the network.
- **16 October** is the voice decision point. If no phone we could sell registers and calls
  reliably by then, management decides between showing calls on the phones that work and moving
  voice to a later date. Data does not wait for voice.
- Keep at least two phones per role on the table, charged, with the SIMs tested the day before.

## Timing (the part most likely to go wrong on stage)

Act 4 depends on a five-minute loop and a re-attach, and a live audience will not wait for either.
Two options, for the project lead to choose (this is a product call, not a technical one):

1. **Two lines.** Line A has been using data since before the demo and is already at zero and cut.
   Line B is used live, and its exhaustion is narrated while line A is shown. Needs no change to the
   300-second loop.
2. **A shorter loop for the demo only.** The Build Plan fixes 300 seconds and says to change it only
   when the delay costs measurable money; a demo-only change is a deviation to approve, not assume.

## The cut list

If the plan slips, cut from the top. Nothing above the line is ever cut, because it is the finish
line. The order is a proposal.

**Never cut**

1. RatelLink creating the line (this is the Week 2 gate: a real SIM, created through the API,
   attaches, browses and registers for calls).
2. Data browsing with the bytes counted and matching the network.
3. A call between two Ratelplus lines.
4. Out of data, with calls still working.
5. A top-up that restores data, credited exactly once.

**Cut in this order when behind**

| Order | Cut | What stays | Why it is safe |
| ----- | --- | ---------- | -------------- |
| 1 | The second payment path: the gateway in sandbox | Voucher top-up on RatelPay | The Build Plan says one gateway is enough to prove the flow, and a voucher proves the credit-once rule |
| 2 | Reports beyond one reconciliation view | The line page next to the network's counters | The finish line asks for matching numbers, not a report suite |
| 3 | Live changes | The airplane-mode toggle | Already planned out of the demo (Week 5 only "if the spike says they are small") |
| 4 | The RatelOps demo dashboard | Counters and records shown directly | It is the live screen but not part of the finish line |
| 5 | RatelPay polish (the 3-second-on-3G target, page weight) | A working, plain top-up page | Performance is a launch concern |
| 6 | Voice, only if the 16 October decision says so | Everything else; calls on the phones that work, or voice moved | Management's decision, not ours. Data does not wait for voice |

**Not before the demo (Build Plan, "What not to build yet")**: calls to other networks, SMS,
emergency calls, charging for calls, dealer hierarchy and wallets, USSD, a second payment gateway,
postpaid, real-time charging for data, self-care and dealer apps.

## Dates that matter

| Date | What | Source |
| ---- | ---- | ------ |
| 14 to 16 Oct | Week 2 gate: a real SIM created through RatelLink attaches, browses, registers for calls | Moved from 13 Oct by the project lead |
| 16 Oct | Voice decision point (phones) | Build Plan |
| 19 to 23 Oct | The full prepaid loop works in the lab, and a line sold in RatelDesk makes a call | Build Plan, Week 4 gate |
| 9 to 13 Nov | Pilot on staff SIMs; 98 of 100 test calls connect | Build Plan, Week 7 gate |
| 16 to 20 Nov | Demo runbook, customer care trained, **two full rehearsals with no step repeated** | Build Plan, Week 8 gate |
| 23 to 26 Nov | Freeze, on call, the demo | Build Plan |

## What exists today (2026-10-14)

| Act | State |
| --- | ----- |
| 1 Sell | RatelLink side built and tested: import keys, activate (with voice once the template arrives, N1), change data, deactivate, read a line, list addresses. **Not yet run against a real phone** (waits for N1, N2, N3, MongoDB authentication, SIM keys, radio). RatelBSS lines and RatelDesk: see issues W2-11 and W2-13 |
| 2 Browse | The address a line gets is allocated and listed for the meter. RatelMeter's agent and API: not assessed here, see W2-08 and W2-09 |
| 3 Call | The network team reports the first VoLTE call (their documents of 11 Oct). RatelLink writes the voice session from their template |
| 4 Out of data | RatelLink can set the speed and cut data without touching calls. The rating job and the trigger are Week 3 and 4 work |
| 5 Top up | Not assessed here: RatelBSS money lives in `services/app/bss_money`, and the Week 4 and 5 gates say what is due |
| 6 Numbers match | Not assessed here. It depends on the counter spike (W2-08) and on N7 (where usage and call records come from) |

## Rehearsal plan (draft)

1. **Walk-through on paper** with the owners above, this page in hand, by 23 Oct: each act, who
   presses what, what the fallback is.
2. **First dry run** after the Week 4 gate (23 Oct), with whatever works, to find the slow parts.
3. **Pilot** on staff SIMs from 9 Nov. Every failure in the pilot is a rehearsal for a demo failure.
4. **Two full rehearsals** 16 to 20 Nov, on the demo phones, in the demo room if possible, with
   someone reading this page aloud and someone else timing every act.
5. **Freeze** on 23 Nov. No change to the network or the software after it except a fix for a
   step that failed in a rehearsal.

## Open questions for the project lead

1. Which of the two timing options for act 4?
2. Which phones are the demo handsets, and who holds the spares?
3. Is the demo on the lab machines or on new ones (the Build Plan says decide before Week 7)?
4. Who presents, and who operates each screen? This page names owners of the parts, not of the
   stage.
5. What does management expect to see if voice moves to a later date?
