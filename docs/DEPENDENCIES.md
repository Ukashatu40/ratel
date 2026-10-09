# Dependencies

Runtime and code dependencies between components. The graph is a DAG. Do not add an edge that
closes a cycle.

```
RatelLink      -> RatelCore (writes subscriber documents in MongoDB on core-cp)

RatelMeter     -> RatelCore  (reads UPF byte counters on core-up)
               -> RatelVoice (reads call records from MySQL on voice)
               -> RatelLink  (reads GET /v1/assignments)
               -> BSS        (agent pushes records to the RatelMeter API on bss-app)

BSS Lines      -> RatelLink  (Contract 1)

BSS Money      -> RatelMeter (Contract 2: usage records)
               -> BSS Lines  (line state machine, plans)
               -> RatelLink  (indirectly, through BSS Lines)

RatelDesk      -> BSS API
RatelPay       -> BSS API
```

Notes:

- "RatelMeter -> BSS" is a runtime push from the agent to the RatelMeter API, which lives in the
  `app` process. It does not mean `meter_api` imports BSS code. `meter_api` imports nothing from
  `bss_lines` or `bss_money`.
- BSS never reaches RatelCore or MongoDB. Only RatelLink does.
- RatelVoice depends on RatelLink having written each line's calling settings. That is the single
  point where the data and voice tracks meet.
- RatelOps reads every machine, read-only, and nothing depends on it.

## Python import rules (enforced in `tests/architecture/`)

| Package | May import | Must not import |
| ------- | ---------- | --------------- |
| `common` | stdlib, FastAPI, Pydantic | `app`, `ratel_link`, `meter_agent`, database drivers |
| `ratel_link` | `common`, `pymongo`, `cryptography` | `app`, `meter_agent`, SQLAlchemy, Alembic, psycopg, redis |
| `meter_agent` | `common`, `httpx` | `app`, `ratel_link`, MongoDB drivers, SQLAlchemy |
| `app` | `common`, SQLAlchemy, Redis, httpx | `ratel_link`, `meter_agent`, MongoDB drivers |
| `app.bss_lines` | `app.db`, `common` | `app.bss_money`, `app.meter_api` |
| `app.meter_api` | `app.db`, `common` | `app.bss_lines`, `app.bss_money` |
| `app.bss_money` | `app.bss_lines`, `app.meter_api`, `common` | (nothing above it) |

TODO (see [DECISIONS_PENDING.md](DECISIONS_PENDING.md)): whether BSS Money reads RatelMeter data
through the HTTP contract or an in-process interface, since both live in one process on bss-app.

Inside a component the direction is one way too, by layer ([ADR 0008](adr/0008-code-organisation-inside-components.md)).
For `ratel_link`: `api -> services -> (domain, security, repositories.ports)`, `repositories.mongo -> domain`,
`security -> domain`, and `main` / `admin_cli` wire everything. `domain` imports no other layer,
no framework, no driver. Services never import `repositories.mongo`. No import cycles anywhere.
Production code never imports `tests/`. All of this is tested (`tests/architecture/`).

## Third-party dependencies

Pinned in `requirements/constraints.txt`, declared in `requirements/*.txt`. Adding one needs a
reason in the PR. `cryptography` (RatelLink only) provides AES-256-GCM for Ki and OPc ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)). Prefer the standard library and what the Build Plan already names. No Kafka, no
Kubernetes, no extra frameworks.
