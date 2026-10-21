# meter_api (RatelMeter API)

Part of the BSS application (`services/app`). Ingests 300-second data usage records from the meter agent and serves paginated query requests from RatelBSS.

## Endpoints

- `POST /v1/usage`: Ingests a batch of usage records (up to 5,000 records). Keyed on `(imsi, period_start)`. Replaying an interval overwrites the existing row, preventing duplicates.
- `GET /v1/usage`: Queries usage records within a time range `[from, to]` and optional `imsi` filter. Returns up to 5,000 records per page with an opaque `next_cursor` for keyset pagination.

## Layer Structure (ADR 0008)

```
meter_api/
  domain.py                 Pure business invariants (no I/O, no DB drivers)
  models.py                 SQLAlchemy UsageRecordModel and table constraints
  api/                      HTTP routing, Pydantic schemas, dependencies
  repositories/             Ports and SqlUsageRepository (PostgreSQL/SQLite upsert)
  services/                 IngestService and QueryService
```

## Privacy & Security

- Usage records are personal data.
- Operational logs strictly omit sensitive identifiers (`imsi`, phone numbers).
- Authenticated via Bearer token (`meter_api_key`).
  There is no built-in key. If `METER_API_KEY` is unset, empty or `CHANGE_ME`, every request gets 401, and
  outside `local` and `test` the app refuses to start.
