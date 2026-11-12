# Runbook: demo act 6, "Prove the numbers"

Nothing here is a real customer's: use the lab phones. No number, key, PIN or password goes into this page, a ticket or a chat.

- **Last verified:** data half 2026-11-09 on the lab: 39,213,826 bytes stored against 39,217,060 on the interface, 0.01% off, `within 1%`, exit 0 (three intervals, one phone browsing, release `ratel-meter-f992f8e`). The calls half: timings spot-checked against the S-CSCF's rows on 2026-11-05 (the Calls tab against the query below still to be compared side by side)
- **Owner:** the project lead (reconciliation: @capitanaserdel; the voice VM: the network team)
- **Runs on:** core-up (the kernel's byte counters), bss-app (the comparison) and the voice VM (the S-CSCF's call records), with RatelDesk open in a browser

The finish line says every byte and every call matches the network's own records. This act shows it **from the command line,
next to RatelDesk**: there is no reconciliation screen (decided; it is not on the build list). The audience sees two sources that
do not know each other agree: what the platform stored, and what the network itself counted.

## What is compared with what

| | The platform's number | The network's own number | Agreement |
| --- | --- | --- | --- |
| **Data** | The line page's **Usage** tab: 5-minute intervals the meter agent counted with nftables and RatelBSS stored | The kernel's byte counters on `ogstun`, read by `ratel-interface-totals.sh` (the agent never touches them) | Within **1%** (`reconcile_cli` says `within` or `OUTSIDE`) |
| **Calls** | The line page's **Calls** tab: one row per call, from the call agent | The S-CSCF's `acc` table on the voice VM (the call agent only reads it) | The same calls, and the same talk time to the second |

## Before the demo (once, in the rehearsal)

| Check | How | Ready? |
| --- | --- | --- |
| The data agent posts every 5 minutes | On core-up `sudo journalctl -u ratel-meter.service -n 5 --no-pager` shows `meter.poster.success`; the Usage tab has intervals | TODO |
| The call agent posts every minute | On the voice VM `sudo journalctl -u ratel-meter-calls.service -n 5 --no-pager` ([deploy/voice/README.md](../../deploy/voice/README.md)); the Calls tab has the rehearsal call | **Not installed** (waits for Python 3.12 on the voice VM) |
| `ogstun` carries only the internet traffic | Take two snapshots around a **call** with no browsing: the bytes must be near zero. If a call moves `ogstun`, the data check must be done without a call in the window | TODO(lab) |
| Clocks agree | `chronyc tracking` on core-up and bss-app: system time within a second | TODO |
| One phone browses | Put the other phone's mobile data off during the check, so the story is simple (the check also holds with two phones: both sides count all of them) | |

Rehearse the whole act **twice** with the stopwatch (the Week 8 gate). The data half needs about 12 minutes of waiting, so it is
**started during act 2 and read in act 6** (below).

## The data half

**Start (during act 2, "Browse"; the phone is attached and about to browse).** On core-up. The loop waits for 1 to 3 seconds
past a 5-minute boundary (:00, :05, :10 ...) and then takes the snapshot, so the window starts on an interval boundary. Keep the
phone idle until it prints:

```bash
while :; do s=$(( $(date +%s) % 300 )); [ $s -ge 1 ] && [ $s -le 3 ] && break; sleep 1; done; ./ratel-interface-totals.sh snapshot | tee /tmp/act6-start.txt      # prints: <epoch> <rx bytes> <tx bytes>
```

**End (just before act 6; at least 5 minutes after the start).** Stop the phone about 10 seconds before a boundary (or keep it
streaming as steadily as at the start), then:

```bash
while :; do s=$(( $(date +%s) % 300 )); [ $s -ge 1 ] && [ $s -le 3 ] && break; sleep 1; done; ./ratel-interface-totals.sh snapshot | tee /tmp/act6-end.txt
./ratel-interface-totals.sh delta /tmp/act6-start.txt /tmp/act6-end.txt     # prints the bytes between the two (the window on stderr)
```

Wait about a minute: the agent posts the interval that just ended at the boundary, and the last one must be stored before comparing.

**On stage, on bss-app** (`bss` helper from [demo-setup.md](demo-setup.md)). The window is each snapshot's epoch rounded **down** to
300 s, so it contains whole intervals only:

```bash
T0=<first number of act6-start.txt>; T1=<first number of act6-end.txt>; N=<the delta's bytes>
bss app.meter_api.reconcile_cli --from $((T0 / 300 * 300)) --to $((T1 / 300 * 300)) --network-total $N; echo "exit $?"
```

The audience sees one line, for example `ours 41234567, network 41300112: 0.16% off, within 1%`, and `exit 0`. Then show the same
window on the line page's Usage tab (the rows between those times add up to the same bytes).

Say: "The first number is what the platform billed from; the second is the Linux kernel's own count on the interface. The
platform does not read it."

## The calls half

**Mark (during act 3, "Call"; on the voice VM, before the call).** Paste once per session:

```bash
mark(){ A=$(docker exec mysql mysql -uroot -N scscf -e "SELECT COALESCE(MAX(id),0) FROM acc"); echo "marked acc>$A"; }
calls(){ docker exec mysql mysql -uroot scscf -e "SELECT started_epoch, answered_epoch - started_epoch AS rang_s, ended_epoch - answered_epoch AS talk_s FROM (SELECT MIN(IF(method='INVITE',start_ts,NULL)) started_epoch, MIN(IF(method='INVITE',UNIX_TIMESTAMP(time),NULL)) answered_epoch, MIN(IF(method='BYE',UNIX_TIMESTAMP(time),NULL)) ended_epoch FROM acc WHERE id>$A GROUP BY callid) x ORDER BY started_epoch"; }
mark
```

**After the call (act 6).** Wait 70 seconds after the hang-up (the call agent looks every minute and holds rows 10 seconds), then:

```bash
calls
```

It prints one line per call since the mark: when it started (epoch), how long it rang, and the talk time in seconds, with **no number
and no Call-ID**. On RatelDesk's Calls tab for the caller's line, the same call shows "Rang for" and "Talk time" as `m ss`. They
match to the second; the start is shown in WAT (one hour ahead of UTC), the epoch minus the time of day tells them apart.

Say: "The right-hand screen is built from the S-CSCF's own accounting rows. This table is those rows."

## What the first runs taught (2026-11-09)

- **The first comparison was 32% off, and the agent was right.** It labelled each record with the interval it was *read* in, so
  what it counted from 10:35 to 10:40 was stored as 10:40. Fixed in `ratel-meter-f992f8e`. After the fix the same method gave
  0.01%. Records stored before the fix are one interval late: never compare windows over them.
- **Take both snapshots with the waiting loop**, 1 to 3 seconds after a boundary (the commands above). Until 2026-11-12 the
  loop waited 5 to 25 seconds, and a window of 10 minutes with the phone streaming at the start and idle at the end was 1.11% off
  (ours 19,064,606 against 18,854,389 on the interface): the 5 to 25 seconds of traffic at one edge. Keep the phone
  idle, or streaming steadily, for 10 seconds around both snapshots. Snapshots taken by hand
  at an arbitrary second give a window that does not match the interval boundaries.
- **Restarting `ratel-meter.service` before 2026-11-10 lost the traffic since the last tick,** because the previous reading
  was kept in memory only. From the release that saves the readings (`ratel-meter-dedb131`) until the fix of 2026-11-11, a restart in the
  middle of an interval was worse than it looked: the tick the agent made at once overwrote the interval before it. The lab
  test on 2026-11-11 showed it (9.95% off). Since the fix the agent waits for the next boundary after a restart
  (`meter.agent.waiting_for_boundary`) and loses nothing. Still, do not restart it in or near the window.
- **Only RatelLink-provisioned SIMs count.** An address without an assignment (a SIM that attached with a dynamic address) is
  in the interface total but not in our store; the agent logs it as `meter.agent.unmapped_usage` (counts only). On 2026-11-09
  one such address carried a few hundred bytes per interval, which is below the tolerance, but a lab phone that streams
  would break the comparison: switch other devices off for the demo.
- **Both counters agree to the byte when they see the same window:** a direct comparison of the counting table with the
  interface (no agent) gave 141,112 bytes against 141,112 up and 539,864 against 539,968 down.

## If the numbers do not match

| What you see | Likely cause | What to do |
| --- | --- | --- |
| `OUTSIDE 1%`, ours **lower** | The last interval is not stored yet, or the agent missed an interval | Wait a minute, run the comparison again. `journalctl -u ratel-meter.service` on core-up for `poster` errors |
| `OUTSIDE 1%`, ours **higher** | The window starts or ends mid-interval | The snapshots were not just after a boundary. Redo with a 10-minute window; show the earlier one if rehearsed |
| `network 0` | The snapshot files are swapped or the interface name is wrong | `IFACE=ogstun` is the default; check `ip -s link show ogstun` |
| Exit 2 | The window or the database | Read the one-line message: it names the problem, never a value |
| The Calls tab is empty, `calls` prints a row | The call agent is not running or cannot post | The voice README's table; `curl` the `/v1/calls` check from the voice VM (401 means nginx admits it) |
| The call is listed with another reason (Declined, Not answered) | The call was not answered | Not an error; make an answered call |

**Fallback if it fails live** ([DEMO_SCRIPT.md](../DEMO_SCRIPT.md)): show the stored 100-call and one-week pilot results.
TODO: those results do not exist yet; keep the output of the two rehearsals (counts and totals only, no number) in a file for this.
