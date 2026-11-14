# RatelMeter agent: byte accuracy against the interface, every run (record)

Each row compares what RatelBSS stored for a window of whole 5-minute intervals with the kernel's own byte counters on `ogstun`
(`docs/runbooks/demo-act-6.md`). Lab, core-up and bss-app, one or two phones. "Off" is (stored - interface) / interface. Totals are
bytes; no IMSI or number appears here.

| Date (UTC) | Window | What was special | Stored | Interface | Off | What it showed |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-09 | 15 min | steady streaming | 39,213,826 | 39,217,060 | **0.01%** | the method works |
| 2026-11-09 | 10 min | first comparison, the agent labelled each record one interval late | 43,692,638 | 64,521,213 | 32.28% | a labelling bug (`f992f8e`): the record's `period_start` was the interval the agent read in, not the one it counted. Fixed, and the same method then gave 0.01% |
| 2026-11-11 | 15 min | one restart mid-interval, the first release that saved its readings | 47,116,261 | 52,323,267 | 9.95% | the tick the agent made at once after the restart overwrote an interval already posted. Fixed (`9e171a5`): a resumed agent waits for the next boundary |
| 2026-11-12 | 10 min | two restarts mid-interval, the fixed release | 19,064,606 | 18,854,389 | 1.11% | no interval lost; the excess is traffic at one snapshot edge (phone streaming at the start, idle at the end). The loop now waits 1 to 3 seconds past the boundary |
| 2026-11-12 | 60 min | `ratel-app` stopped for the whole window; 12 batches spooled | 181,524,763 | 187,332,115 | 3.10% | delivery exact: 12 intervals with 2 records each, no gap, no duplicate, spool emptied. **2.5% of the interface (4,752,189 bytes) is unexplained** after 1,055,163 bytes the agent logged as unmapped; the counting table was 0.17% below the interface over its whole life |
| 2026-11-13 | 40 min | steady streaming, `ratel-window.sh` (three counts together) | 93,007,320 | 93,009,976 | **0.00%** | stored equals the counting table to the byte; unmapped 0 |
| 2026-11-13 | 25 min | `ratel-app` stopped for the whole window, restarted after it | 68,252,553 | 68,257,101 | **0.01%** | stored equals the counting table less the unmapped bytes to the byte; spool emptied within 7 minutes |

## What this supports

- In steady running, and with the API down for a whole window, every byte the counting table sees is stored once, to the byte. The
  table itself is within 0.01% of the interface in both clean runs and 0.17% over its whole life (2.2 GB).
- Two real bugs were found and fixed by this method (the interval label, the tick after a restart), both by comparing with a counter
  the agent does not use.

## What it does not explain

- The 2.5% of 2026-11-12 (60 minutes). It was not reproduced in two clean runs on 2026-11-13, one of them with the same outage.
  That window had other devices on the interface (the network team's test phones, 14 addresses in the agent's readings) and 5
  ticks with unmapped traffic. If it recurs, take the three counts with `ratel-window.sh`: the table's line says whether the rule or
  the agent is short.
- Traffic from an address RatelLink has not assigned to a line is on the interface and not in our store, by design; the agent logs
  it as `meter.agent.unmapped_usage` (counts only). Switch other devices off for the demo.

## For the issues

#58 and #59: the lab accuracy and the restart and outage criteria (rows 2026-11-12 restart, 2026-11-13 both).
