# Rehearsal 2026-11-17, run 1 (record)

Filled in by `scripts/demo/rehearse.sh`; the sheet and the rules are in [rehearsal-sheet.md](../runbooks/rehearsal-sheet.md). Last four digits only.

| | |
| --- | --- |
| Date | 2026-11-17 |
| Run number | 1 |
| People | Ukashatu40, CaptRaven |
| Commit demoed | 67548ce (the runner's branch; the same content as `aa4c67c` on `main`) |
| Before the stopwatch | day-before table: y; fresh voucher batch: y |
| Releases | core-up meter agent `1437beb`; bss-app, core-cp and the voice VM: TODO (not read on the day) |
| Lines | A …0454 (new, sold live, keys imported on 2026-11-16); B …0453 (the iPhone with …0451 left mid-run, see 2.2); C …0454 (the call, see 3.1); D …0453 |
| Phones | keypad …0452, telephone …0454 (its usual SIM …0240 taken out), Android …0453, iPhone …0451 until it left |
| Network that morning (2026-11-16) | the site's internet link was down from the morning until the network team restored it; no root cause recorded |

| # | Who | Step | What you must see | Budget | Actual (from the start) | ✓ / R / F | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | | **Sell a SIM** | | **2:30** | | | |
| 1.1 | Presenter | Sell SIM; pick the customer (KYC already approved) | the customer's card with a green KYC badge | 0:25 | 0:18 | ✓ |  |
| 1.2 | Presenter | Pick the SIM, the number and the plan | the plan's price and allowance | 0:25 | 0:23 | ✓ |  |
| 1.3 | Phones | The customer redeems a card on the RatelPay page for the line's number | "... added to your line" | 0:30 | 0:49 | ✓ |  |
| 1.4 | Presenter | Refresh balance, then Buy plan | the wallet drops by the plan's price | 0:25 | 0:56 | ✓ |  |
| 1.5 | Presenter | Activate line | the line is active | 0:20 | 3:02 | ✓ | activate count: 1  |
| 1.6 | Phones | Put the SIM in the phone; toggle airplane mode | the phone shows the network name | 0:25 | 11:02 | ✓ |  |
| **2** | | **Browse** | | **1:00** | | | |
| 2.1 | Operator | Start the window (phone idle until it prints) | three lines: the interface and the counting table | 0:15 | 41:58 | ✓ |  |
| 2.2 | Phones | Open a web page on line B's phone | the page loads | 0:20 | 43:47 | ✓ | iPhone gone; browsed on the Android (line 0453, slowed)  |
| 2.3 | Presenter | Line B's page, Usage tab | intervals with MB, newest first | 0:25 | 46:12 | ✓ |  |
| **3** | | **Call** | | **1:30** | | | |
| 3.1 | Phones | Call line C's number from the other phone, national form (0 and ten digits) | it rings and the caller's number shows | 0:20 | 57:07 | ✓ | the keypad (…0452) called the telephone (…0454); the only direction that works today |
| 3.2 | Phones | Answer, talk about 20 seconds | audio both ways | 0:25 | 59:28 | ✓ | Time: 15:56  |
| 3.3 | Phones | Hang up | the call ends on both | 0:10 | 60:29 | ✓ |  |
| 3.4 | Presenter | Line C's page, Calls tab (about 70 seconds after the hang-up) | the call: start, rang for, talk time, Answered | 0:35 | 62:16 | ✓ |  |
| **4** | | **Run out of data** | | **1:30** | | | |
| 4.1 | Presenter | Line D's page | state out of data; the history says allowance used up | 0:15 | 63:27 | ✓ |  |
| 4.2 | Operator | Start the rating job if the line was not out of data yet; read the journal | lines_out_of_data":1 | 0:20 | 64:44 | ✓ | already out of data; rating job not needed  |
| 4.3 | Phones | Toggle airplane mode on line D's data phone; run a speed test | about 1 Mbit/s | 0:30 | 66:20 | ✓ |  |
| 4.4 | Phones | Call from a line that is also out of data | it still rings with audio | 0:25 | 68:31 | F | keypad to Android did not ring; called the telephone  |
| **5** | | **Top up** | | **1:30** | | | |
| 5.1 | Phones | RatelPay: line D's number, a card, the PIN | "... added" and the new balance | 0:25 | 71:35 | ✓ |  |
| 5.2 | Operator | Start the rating job; read the journal | lines_renewed":1,"lines_restored":1 | 0:20 | 72:34 | ✓ |  |
| 5.3 | Presenter | Line D's page | state active; the history says allowance restored | 0:15 | 74:16 | ✓ |  |
| 5.4 | Phones | Toggle airplane mode; run a speed test | tens of Mbit/s | 0:30 | 78:36 | ✓ |  |
| **6** | | **Prove the numbers** | | **1:30** | | | |
| 6.1 | Operator | End the window (phone idle 10 seconds before), then the report | the table of three counts and the commands for bss-app | 0:30 | 84:33 | ✓ |  |
| 6.2 | Operator | On bss-app paste the two commands the report printed | within 1%, exit 0 | 0:30 | 85:58 | ✓ | window 14:05 to 14:55 UTC: interface 142,496,980 bytes, stored 142,318,952 = the counting table less unmapped (0) to the byte; 0.12% off, within 1%, exit 0 |
| 6.3 | Operator | The calls query on the voice VM next to the Calls tab | the same start, rang for and talk time to the second | 0:30 | 87:28 | ✓ | rang 48 s, talk 35 s on both |

| Act | Name | Budget | Spent |
| --- | --- | --- | --- |
| 1 | Sell a SIM | 2:30 | 11:02 |
| 2 | Browse | 1:00 | 35:10 |
| 3 | Call | 1:30 | 16:04 |
| 4 | Run out of data | 1:30 | 6:15 |
| 5 | Top up | 1:30 | 10:05 |
| 6 | Prove the numbers | 1:30 | 8:52 |

| | |
| --- | --- |
| Total time | 87:28 (budget 9:30, plus about 30 seconds between acts) |
| Steps done | 24 of 24 |
| Steps marked R | 0 |
| Steps marked F | 1 |
| Counts towards the Week 8 gate | no (1 step(s) failed; fewer than three people) |

**About the time.** 87:28 is not the demo's pace: the run was guided one step at a time in a chat, and Act 2 includes a break
before the window was started. The pace is measured in rehearsal 2.

## For each R and F: what, why, who fixes it by when

| Step | What | Why | Who, by when |
| --- | --- | --- | --- |
| 4.4 F | The keypad called the Android (…0453, out of data) and it did not ring; the keypad then called the telephone, which rang | Smartphones cannot make or receive calls (IPsec through the P-CSCF), known since 2026-11-05 | @CaptRaven; the phone set for the demo is decided on 2026-11-18 evening |
| 5.4 | TODO (project lead): confirm whether the first speed test read 2.5 Mbit/s and needed a second airplane toggle. If so, the step is R | | |

## Other findings (not R or F, but they would hurt on the day)

1. **A phone left in the middle of the run** (the iPhone with …0451, at act 2). On the day the demo phones stay on the table, and a spare
   is ready for each role.
2. **Calls work in one direction only:** the keypad calls the telephone; the telephone cannot call the keypad, and neither smartphone takes
   part. The network team knows.
3. **There was no spare phone for line A.** The telephone's own SIM (…0240) was taken out for …0454.
4. **The site's internet link was down in the morning of 2026-11-16** (core-up and bss-app both). The network team restored it; the cause
   is not recorded. The day-before table caught it, which is what it is for.
5. **The key leak check for …0454 was not done:** the shell that held its keys was closed before the check (`docs/runbooks/ratel-link-lab-acceptance.md`, step 5).
   The caller key `lab-import-8` was disabled on 2026-11-18.
6. **The backup call of step 4.4 is not in the `calls` query**, which lists answered calls only. TODO (project lead): if it was not
   answered, it is in `missed_calls` and nothing is wrong.

## Evidence this run gives

- **#52 F:** one sale in RatelDesk produced exactly one `line.activate` in RatelLink's journal (step 1.5).
- **Act 6:** the stored usage equals the counting table to the byte over 50 minutes, 0.12% off the interface; the call's rang-for and
  talk time equal the S-CSCF's rows to the second.
- **Acts 1, 4 and 5 on the real system:** a live sale through activation, a line at zero slowed to about 1 Mbit/s, a voucher top-up renewed
  and restored by the rating job, and tens of Mbit/s again.
