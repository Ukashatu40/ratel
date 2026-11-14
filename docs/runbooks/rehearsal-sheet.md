# Rehearsal sheet: the six acts, timed

Print this page, or copy it to `docs/records/rehearsal-YYYY-MM-DD.md` and fill it in on screen. One sheet per run. Never write a
PIN, a key or a full IMSI on it: last four digits only.

The Week 8 gate is **two full runs in a row with no step repeated**. A step is **R** (repeated) if anything had to be done again
because it did not work the first time; **F** (failed) if it could not be done and a fallback was used. A fallback that was planned
(the checklist says "if it fails") is written down but is still an **F**. A run with any R or F does not count towards the gate.
What the steps are and why: [DEMO_SCRIPT.md](../DEMO_SCRIPT.md). What must be true before: [demo-day-checklist.md](demo-day-checklist.md).

## The run

| | |
| --- | --- |
| Date, start time (WAT) | |
| Commit demoed, and the release on each host (`bss-app`, `core-up`, `voice`, `core-cp`) | |
| Run number (1 or 2 of the gate) | |
| Where | |

**People.** One person has one job. Write the names, and use people who can act on the day: the repository's collaborators
(@Ukashatu40, @capitanaserdel, @CaptRaven, @Abbalolo, @ml-lawarn, @Arfaaah). A suggestion from the ownership matrix, with a backup each:
Operator @Ukashatu40 (backup @capitanaserdel, who owns the meter); Presenter @ml-lawarn (backup @Abbalolo, who owns the lines);
Phones @Arfaaah (backup @Abbalolo); Reader @Abbalolo (backup @Arfaaah); Timer @capitanaserdel (backup @ml-lawarn); @CaptRaven for the
voice and network questions of act 3, by phone if he cannot come.

**If not everyone can come, this is the least that still counts.** Only the Phones person must be in the room with the phones. The
Reader and the Timer can join by a video call or a phone call with the sheet in front of them, and the Presenter's screen can be
shared. Three people is the minimum: the Operator, one person for the phones and the Presenter's clicks, and one for the Reader and
Timer jobs together. With fewer than three, still do the run and fill in the sheet, and write "run with N people" in the header: it
finds the failures, but it does not count towards the gate, which asks for someone else reading and timing.

| Role | What they do | Name |
| --- | --- | --- |
| Presenter | the RatelDesk and RatelPay screens, says the words | |
| Phones | the SIMs, the airplane toggles, the calls and the speed tests | |
| Operator | the terminals on `core-up`, `bss-app` and the voice VM | |
| Reader | reads [DEMO_SCRIPT.md](../DEMO_SCRIPT.md) aloud, one step at a time | |
| Timer | this sheet, a stopwatch, every cell below | |

**What is in each hand before you start** (from the checklist; last four digits of the IMSI only):

| Line | For | IMSI ends | SIM is in | Phone does |
| --- | --- | --- | --- | --- |
| A | Act 1, sold live | | | |
| B | Acts 2 and 6 | | | browses |
| C | Act 3 | | | calls |
| D | Acts 4 and 5 | | | |

Before the stopwatch starts, the Operator confirms the day-before table of the checklist was run (tick: ☐) and a fresh voucher
batch is on sale (☐).

## The steps

Start the stopwatch at 1.1. Write the **actual** time you finished each step as minutes and seconds from the start. The budget
is a target, not a limit: a step that takes longer is a finding, not a failure. Mark each step **✓**, **R** or **F**.

| # | Who | Step | What you must see | Budget | Actual | ✓ / R / F | Notes (fallback used, what went wrong) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | | **Sell a SIM** | | **2:30** | | | |
| 1.1 | Presenter | Sell SIM; pick the customer (KYC already approved) | the customer's card with a green KYC badge | | | | |
| 1.2 | Presenter | Pick the SIM, the number and the plan | the plan's price and allowance | | | | |
| 1.3 | Phones | The customer redeems a card on the RatelPay page for the line's number | "₦… added to your line" | | | | |
| 1.4 | Presenter | Refresh balance, then **Buy plan** | the wallet drops by the plan's price | | | | |
| 1.5 | Presenter | **Activate line** | the line is **active** | | | | |
| 1.6 | Phones | Put the SIM in the phone; toggle airplane mode | the phone shows the network name | | | | |
| **2** | | **Browse** | | **1:00** | | | |
| 2.1 | Operator | **Start snapshot** on `core-up` (the loop, then the snapshot); phone idle until it prints | three numbers printed; write the first (`T0`) here: | | | | |
| 2.2 | Phones | Open a web page on line B's phone | the page loads | | | | |
| 2.3 | Presenter | Line B's page, **Usage** tab | intervals with MB, newest first | | | | |
| **3** | | **Call** | | **1:30** | | | |
| 3.1 | Phones | Call line C's number from the other phone, in the national form (`0` and ten digits) | it rings and the caller's number shows | | | | |
| 3.2 | Phones | Answer, talk about 20 seconds | audio both ways | | | | |
| 3.3 | Phones | Hang up | the call ends on both | | | | |
| 3.4 | Presenter | Line C's page, **Calls** tab (about 70 seconds after the hang-up) | the call: start, rang for, talk time, result Answered | | | | |
| **4** | | **Run out of data** | | **1:30** | | | |
| 4.1 | Presenter | Line D's page | state **out of data**, the history says allowance used up | | | | |
| 4.2 | Operator | `sudo systemctl start ratel-rating.service` if the line was not yet out of data; read the journal | `lines_out_of_data":1` | | | | |
| 4.3 | Phones | Toggle airplane mode on line D's data phone; run a speed test | about 1 Mbit/s | | | | |
| 4.4 | Phones | Call from a line that is also out of data | it still rings with audio | | | | |
| **5** | | **Top up** | | **1:30** | | | |
| 5.1 | Phones | RatelPay: line D's number, a card, the PIN | "₦… added", the new balance | | | | |
| 5.2 | Operator | `sudo systemctl start ratel-rating.service`; read the journal | `lines_renewed":1,"lines_restored":1` | | | | |
| 5.3 | Presenter | Line D's page | state **active**, the history says allowance restored | | | | |
| 5.4 | Phones | Toggle airplane mode; run a speed test | tens of Mbit/s | | | | |
| **6** | | **Prove the numbers** | | **1:30** | | | |
| 6.1 | Operator | **End snapshot** on `core-up` (phone idle 10 seconds before); then `delta`; write the first number (`T1`) and the bytes (`N`): | | | | | |
| 6.2 | Operator | `reconcile_cli --from $((T0/300*300)) --to $((T1/300*300)) --network-total $N` on `bss-app` | **`within 1%`**, exit 0; write the line: | | | | |
| 6.3 | Operator | The `calls` query on the voice VM for one call, next to the Calls tab | the same start, rang for and talk time to the second | | | | |

Total budget: **9:30**, plus about 30 seconds between acts. Write the total actual time: ________

## What happened

| | |
| --- | --- |
| Total time, start to finish | |
| Steps marked R | |
| Steps marked F (and which fallback) | |
| Did this run count towards the gate? (no R and no F) | yes / no |
| The three slowest steps | |
| Anything the audience would have noticed | |
| What we could not show, and why | |

## After the run (within the hour, while it is fresh)

1. Copy this sheet to `docs/records/rehearsal-YYYY-MM-DD.md` with the cells filled in and the commit demoed.
2. For every R and F, write one line: what, why, and who fixes it by when. A fix goes through the normal pull request; **nothing is
   changed on a host between two rehearsals except a fix for a step that failed** (the freeze rule from 23 Nov).
3. Run the **After** list of the checklist: shred the voucher files, remove the snapshot files, disable any caller key made for the
   day.
4. Tick the evidence into the issues: #52 (the lab session), #57 to #63 (the modules) and #65 (the dry runs and rehearsals).
