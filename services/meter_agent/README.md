# meter_agent (RatelMeter agent)

Runs in two modes from one program:

- **data** on core-up: every 300 seconds reads per-address byte counters on `ogstun`,
  subtracts the previous reading, maps address to IMSI using RatelLink's `GET /v1/assignments`,
  posts the batch to the RatelMeter API.
- **call** on voice: every 60 seconds reads new Kamailio call records from MySQL, joins start and
  end, posts to the RatelMeter API.

Rules from the Build Plan (do not weaken): clock-aligned UTC intervals, never lose an interval,
never double count (API upserts on `imsi + period_start` and `call_id`), handle counter resets,
skip zero-byte intervals, spool to disk when the API is unreachable and replay in order.

Nothing is implemented yet. Week 2 issues: `docs/issues-week2/`.
