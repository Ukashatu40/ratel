# RatelMeter agent: the real counter reader for core-up
Labels: type:feature, area:ratel-meter, priority:p1, risk:high

**Module:** RatelMeter agent | **Roadmap week:** 2 to 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** partly. The reader and its tests against recorded snapshots can start now. Picking the mechanism needs lab session 1, section D.
**Source:** Build Plan, RatelMeter spec "How data works"; #24 and #25 (now in lab session 1); `services/meter_agent/counters/__init__.py` (the `CounterReader` protocol, a stub).

## Objective
A real implementation of `CounterReader.read()` returns cumulative `bytes_up_total` and `bytes_down_total` for every address on core-up's `ogstun`, with the mechanism measured to lose no bytes.

## Scope
- Implement `CounterReader` for the chosen mechanism (nftables per-element counters, per-line accounting rules, or conntrack accounting; the lab decides).
- Packets from a phone's address count as upload, to it as download.
- Until the lab decides, the parsing part works on recorded snapshots (synthetic, no real addresses) and has its tests.

## Out of scope
The loop and the posting (M-08, M-09). Call mode (M-10).

## Depends on
Lab session 1 section D for the final mechanism. Network team provides read access to the counters on core-up.

## Contract impact
None.

## Acceptance criteria
- [ ] `read()` returns integers keyed by address; a malformed snapshot raises a clear error and is never counted as zero
- [ ] Tests cover many short flows, one long transfer and an empty table (recorded snapshots)
- [ ] On the lab, totals are within 1% of the interface's own byte counters (record in lab session 1)
- [ ] `tests/architecture` rules for the agent still pass (no MongoDB or SQL driver in the agent)

## Data, security and privacy
Addresses and counters are personal data once joined to an IMSI: no address in operational logs.

## Testing
Unit; the accuracy check is a lab run.
