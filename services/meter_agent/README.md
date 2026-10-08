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

## Planned structure (docs/adr/0008)

```
meter_agent/
  main.py, config.py   entry point (mode data|call) and settings
  sources/             read from the outside: byte counters on ogstun, call records from MySQL
  domain/              pure logic: interval alignment, counter delta and reset, join call start/end
  spool/               disk spool and replay in order
  client/              post batches to the RatelMeter API, read RatelLink assignments
  runners/             data_mode.py and call_mode.py: the loops that tie the above together
```

`domain` imports nothing from the other folders. `runners` may import all of them. No database
driver for MongoDB or SQL (tested). Add the rules to `tests/architecture/test_layers.py` with the first code.

Nothing is implemented yet. Week 2 issues: `docs/issues-week2/`.
