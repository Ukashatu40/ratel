# Rehearsal 2026-11-23, run 2 (record)

Filled in by `scripts/demo/rehearse.sh`; the sheet and the rules are in [rehearsal-sheet.md](../runbooks/rehearsal-sheet.md). Last four digits only.

| | |
| --- | --- |
| Date | 2026-11-23 |
| Run number | 2 |
| People | Ukashatu40 |
| Commit demoed | cca4388 |
| Before the stopwatch | day-before table: y; fresh voucher batch: y |
| Releases | RatelLink `b561724` and the meter agent `1437beb` (no service code changed on `main` since); bss-app and the voice VM: TODO (not read on the day) |
| Lines | A …0455 (sold live; its keys were in RatelLink since 2026-11-19); B …0453; C …0455; D …0454 (put at zero with the rehearsal feed on 2026-11-18) |
| Phones | keypad …0452, telephone …0455, Android …0453, iPhone …0454 (its usual SIM …0451 taken out); …0019's phone off |

| # | Who | Step | What you must see | Budget | Actual (from the start) | ✓ / R / F | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | | **Sell a SIM** | | **2:30** | | | |
| 1.1 | Presenter | Sell SIM; pick the customer (KYC already approved) | the customer's card with a green KYC badge | 0:25 | 0:06 | ✓ |  |
| 1.2 | Presenter | Pick the SIM, the number and the plan | the plan's price and allowance | 0:25 | 0:54 | ✓ |  |
| 1.3 | Phones | The customer redeems a card on the RatelPay page for the line's number | "... added to your line" | 0:30 | 2:30 | ✓ |  |
| 1.4 | Presenter | Refresh balance, then Buy plan | the wallet drops by the plan's price | 0:25 | 3:01 | ✓ |  |
| 1.5 | Presenter | Activate line | the line is active | 0:20 | 4:22 | ✓ | activate count: 1  |
| 1.6 | Phones | Put the SIM in the phone; toggle airplane mode | the phone shows the network name | 0:25 | 6:08 | ✓ |  |
| **2** | | **Browse** | | **1:00** | | | |
| 2.1 | Operator | Start the window (phone idle until it prints) | three lines: the interface and the counting table | 0:15 | 13:30 | ✓ |  |
| 2.2 | Phones | Open a web page on line B's phone | the page loads | 0:20 | 17:08 | ✓ |  |
| 2.3 | Presenter | Line B's page, Usage tab | intervals with MB, newest first | 0:25 | 18:38 | ✓ |  |
| **3** | | **Call** | | **1:30** | | | |
| 3.1 | Phones | Call line C's number from the other phone, national form (0 and ten digits) | it rings and the caller's number shows | 0:20 | 20:06 | ✓ | the keypad (…0452) called the telephone (…0455) |
| 3.2 | Phones | Answer, talk about 20 seconds | audio both ways | 0:25 | 21:52 | ✓ |  |
| 3.3 | Phones | Hang up | the call ends on both | 0:10 | 22:58 | ✓ |  |
| 3.4 | Presenter | Line C's page, Calls tab (about 70 seconds after the hang-up) | the call: start, rang for, talk time, Answered | 0:35 | 25:29 | ✓ |  |
| **4** | | **Run out of data** | | **1:30** | | | |
| 4.1 | Presenter | Line D's page | state out of data; the history says allowance used up | 0:15 | 26:30 | ✓ |  |
| 4.2 | Operator | Start the rating job if the line was not out of data yet; read the journal | lines_out_of_data":1 | 0:20 | 27:10 | ✓ | already out of data (fed 2026-11-18); rating job not needed  |
| 4.3 | Phones | Toggle airplane mode on line D's data phone; run a speed test | about 1 Mbit/s | 0:30 | 35:47 | ✓ |  |
| 4.4 | Phones | Call from a line that is also out of data | it still rings with audio | 0:25 | 38:45 | ✓ | keypad called the iPhone (line at zero); received, not made  |
| **5** | | **Top up** | | **1:30** | | | |
| 5.1 | Phones | RatelPay: line D's number, a card, the PIN | "... added" and the new balance | 0:25 | 40:39 | ✓ |  |
| 5.2 | Operator | Start the rating job; read the journal | lines_renewed":1,"lines_restored":1 | 0:20 | 41:32 | ✓ |  |
| 5.3 | Presenter | Line D's page | state active; the history says allowance restored | 0:15 | 50:24 | ✓ |  |
| 5.4 | Phones | Toggle airplane mode; run a speed test | tens of Mbit/s | 0:30 | 51:12 | F | about 2.5 Mbit/s; a second toggle gave the same, and the Android (…0453, full speed and data left) gave 1 Mbit/s or less. Marked ✓ in the runner, corrected to F by hand |
| **6** | | **Prove the numbers** | | **1:30** | | | |
| 6.1 | Operator | End the window (phone idle 10 seconds before), then the report | the table of three counts and the commands for bss-app | 0:30 | 74:16 | ✓ |  |
| 6.2 | Operator | On bss-app paste the two commands the report printed | within 1%, exit 0 | 0:30 | 74:50 | ✓ | 0.14% off, within 1%, exit 0; stored = table to the byte (283685968)  |
| 6.3 | Operator | The calls query on the voice VM next to the Calls tab | the same start, rang for and talk time to the second | 0:30 | 75:56 | ✓ | rang 27 s, talk 128 s on both |

| Act | Name | Budget | Spent |
| --- | --- | --- | --- |
| 1 | Sell a SIM | 2:30 | 6:08 |
| 2 | Browse | 1:00 | 12:30 |
| 3 | Call | 1:30 | 6:51 |
| 4 | Run out of data | 1:30 | 13:16 |
| 5 | Top up | 1:30 | 12:27 |
| 6 | Prove the numbers | 1:30 | 24:44 |

| | |
| --- | --- |
| Total time | 75:56 (budget 9:30, plus about 30 seconds between acts) |
| Steps done | 24 of 24 |
| Steps marked R | 0 |
| Steps marked F | 1 (5.4, corrected by hand) |
| Counts towards the Week 8 gate | no (1 step failed; fewer than three people) |

**About the time.** 75:56 is a guided run with waits for the 5-minute marks; the Act 6 window ran 60 minutes. It is not the demo's pace.

## For each R and F: what, why, who fixes it by when

| Step | What | Why | Who, by when |
| --- | --- | --- | --- |
| 5.4 F | After the top-up, the line was active again (rating job: renewed 1, restored 1; Desk: active) but the iPhone measured about 2.5 Mbit/s, twice | Not the restore: RatelBSS asks RatelLink for the plan's speeds (Lab weekly, 20 Mbit/s down), and the Android on another full-speed line measured 1 Mbit/s or less at the same time. The network was slow that morning: radio or the site's internet link. TODO: the check on core-up after the run | the network team; before the demo |

## Other findings

1. **Run 1's only failure passed:** the keypad called the iPhone on the line at zero (4.4) and it rang with audio both ways.
2. **One call in the `calls` query has no talk time** (started 1795427100, rang 6 s, `talk_s` NULL): answered, with no BYE in the S-CSCF's rows. It
   was during act 4, before the call that passed. TODO (project lead): was it a dropped first attempt? The call agent keeps such a call open
   for up to 6 hours, then drops it and counts it (`open_calls_dropped`).
3. **Run 1's 5.4 was probably the same finding:** a first reading of 2.5 Mbit/s was noted there too.

## Evidence this run gives

- **#52 F, again:** one sale, one `line.activate` (step 1.5).
- **Act 6 over 60 minutes:** stored usage equals the counting table to the byte (283,685,968), 0.14% off the interface; the call's rang-for
  and talk time equal the S-CSCF's rows to the second (27 s and 128 s).
- **Calls at zero data shown on a smartphone** (the iPhone, received).
