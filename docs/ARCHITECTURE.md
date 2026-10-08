# Architecture

Source: Build Plan ("The components", "How the network works", "Workstreams", "Component
specifications", "Stack and repo layout"). Terminology below is the Build Plan's. This document
adds no architecture of its own. Where it records a choice the Build Plan left open, it says so and
links an ADR.

## Principles

1. Nothing we build can be switched off from outside. No licence files, no subscriber caps, no vendor remote access.
2. Data and voice both ship for the demo, on separate tracks. They meet at one point: RatelLink writes a line's calling settings when it activates the line.
3. SIM keys and money get the most care.
4. The simplest thing that works on 26 November. No Kubernetes, no message bus, no microservices beyond what the network forces.

## Components

| Name | What it is | Built on | Runs on | Owner |
| ---- | ---------- | -------- | ------- | ----- |
| RatelCore | LTE core: MME, HSS, SMF, PCRF, SGW-U, UPF | Open5GS v2.8.0 | core-cp, core-up | Network team |
| RatelVoice | VoLTE core: P-CSCF, I-CSCF, S-CSCF, media relay, IMS DNS | Kamailio IMS, rtpengine | voice (new VM) | Network team |
| RatelOps | Monitoring, alarms, live dashboard | Prometheus, Grafana, Alertmanager | ops (new VM) | Network team |
| RatelLink | Provisioning API; the only writer to RatelCore's subscriber database | Python, FastAPI, MongoDB driver | core-cp | Software team |
| RatelMeter | Data usage and call records for billing | Python | Agents on core-up and voice; API on bss-app | Software team |
| RatelBSS | Customers, stock, plans, lines, charging, wallets, vouchers, payments, reports | Python, FastAPI, PostgreSQL, Redis | bss-app | Software team |
| RatelDesk | Staff web app | React, TypeScript | bss-app | Software team |
| RatelPay | Customer top-up page, light enough for 3G | Small page served by RatelBSS | bss-app, public through a reverse proxy | Software team |

Lab machines (Build Plan; addresses are in the Build Plan, not in this public repository): core-cp
(MME, HSS, SMF, PCRF, MongoDB; RatelLink), core-up (SGW-U, UPF; RatelMeter agent in data mode). `voice`, `bss-app` and `ops`
are not created yet. TODO: confirm production host details.

## The two touch points

The business software touches the network at exactly two points.

```
Phone+SIM -> eNB -> RatelCore (core-cp: MME HSS SMF PCRF MongoDB | core-up: SGW-U UPF) -> Internet
                          ^ writes line records          | byte counters      | call records (RatelVoice)
                      RatelLink  <----- Contract 1 ----  RatelBSS  <---- Contract 2 ---- RatelMeter
                      (core-cp)                          (bss-app)                       (agents + API)
```

- **RatelLink** is how anything tells the network that a line exists, whether it may make calls, and how fast its internet may go. It is the **only** writer to RatelCore's subscriber database.
- **RatelMeter** is how the network tells the business what each line used. It only **reads** byte counters and call records.
- Everything else (customers, plans, vouchers, payments, reports) lives purely in software and never touches the network directly.

## Boundaries

**Network/software boundary.** RatelBSS does not access RatelCore. It interacts with the network
only through RatelLink and RatelMeter, according to `contracts/openapi.yaml`. No helper code may
bypass this. Enforced by `tests/architecture/test_boundaries.py`: `app` cannot import the MongoDB
driver, `ratel_link` or `meter_agent`.

**Data boundaries.**

| Data | Lives only in | Never in |
| ---- | ------------- | -------- |
| Ki, OPc | RatelLink's store (AES-256-GCM encrypted at rest, key in a file outside the database, [ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)) and Open5GS's MongoDB (plaintext there: see [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md), Backups) | PostgreSQL, logs, tickets, chat, test fixtures, AI tools, unencrypted backups leaving core-cp |
| Customer, KYC, NIN | RatelBSS PostgreSQL | RatelPay pages, logs, RatelLink |
| Usage and call records | RatelMeter's PostgreSQL tables on bss-app | Logs (call records are personal data) |
| Money (wallets, ledger, vouchers, payments) | RatelBSS PostgreSQL | Floating point anywhere |
| Open5GS subscriber documents | `open5gs` database in MongoDB, written by RatelLink only | Written by anything else |
| RatelLink's own state | `ratel_link` database in the same MongoDB, own user | Read by anything else |

**Deployment boundaries.** `bss-app`, `voice` and `ops` get their own VMs. A bad deploy must never
be able to take RatelCore down. Only RatelLink touches MongoDB, over `127.0.0.1`
(config validation in `services/ratel_link/config.py` rejects any other host). Access rules: every
API and RatelDesk is reachable only over the WireGuard VPN. Public by design: RatelPay and the
payment gateway's webhook. Expose only those paths, verify every webhook signature, rate-limit both.

## Deployables and repository layout

| Deployable | Contains | Runs on | Talks to |
| ---------- | -------- | ------- | -------- |
| `ratel-link` (`services/ratel_link/`) | RatelLink | core-cp | MongoDB on 127.0.0.1 only |
| `meter-agent` (`services/meter_agent/`) | RatelMeter agent: data mode on core-up, call mode on voice | core-up, voice | Pushes records to the app; spools to local disk when unreachable |
| `app` (`services/app/`) | RatelBSS, RatelMeter API, RatelDesk and RatelPay back ends, as modules in one process | bss-app | PostgreSQL and Redis on the same VM, RatelLink over the LAN |

`services/common/` is a small shared library (error shape, JSON logging with redaction, UTC time,
kobo type). It is a library, not a service. See [ADR 0003](adr/0003-shared-common-package.md).
Repository layout: [README](../README.md). Why it differs slightly from the example tree: [ADR 0001](adr/0001-repository-layout.md).

## Component responsibilities

**RatelLink.** Owns the SIM key store and every write to the `subscribers` collection in the
`open5gs` database, including the ims APN and MSISDN RatelVoice depends on. Collections in its own
`ratel_link` database: `sim_key` (`imsi`, and `ki` and `opc` each as an encrypted envelope
`{v, alg, kid, nonce, ct}`, plus `created_at`), `api_key` (one document per calling system, with its
key generations and only their hashes, [ADR 0007](adr/0007-api-key-verification-and-rotation.md)),
`line_state`, `audit_log` (append-only, never contains Ki, OPc or keys). Status: `provisioned`, `active`, `barred`. Data mode:
`full`, `slow`, `off`. Every line gets a fixed IPv4 address from `10.45.0.0/16` at activation;
released addresses are not reused for 24 hours. Every call is idempotent. Every `/v1` call requires a valid API key (`Authorization: Bearer <key>`),
and `audit_log` entries carry the calling system's `api_key_id`. Subscriber documents are
built from a template taken from a subscriber Open5GS created itself, never handwritten.
Until live changes land, every change takes effect at the line's next attach.

**RatelMeter.** Agent in data mode reads per-address byte counters on `ogstun` every 300 seconds,
subtracts the previous reading, maps address to IMSI via RatelLink's `GET /v1/assignments`, and
posts the batch. Agent in call mode reads Kamailio call records from RatelVoice's MySQL every 60
seconds and joins start and end. The API stores `usage_record` (unique on `imsi + period_start`)
and `call_record` (unique on `call_id`) in PostgreSQL and serves `/v1/usage` and `/v1/calls`.

**RatelBSS: lines.** Staff accounts, customers, SIM and number stock, plans, bundles, lines.
Line state machine: `awaiting_activation`, `active`, `out_of_data`, `expired`, `suspended`,
`terminated`. Every transition calls RatelLink and writes an audit entry. No code updates a state
column directly. No line activates until KYC is verified.

**RatelBSS: money.** Allowance buckets, wallets, ledger, vouchers, payments, and the rating job.
Every 300 seconds it rates unrated usage records against buckets (soonest expiry first), marking
each record rated in the same transaction as the deduction. When the last bucket runs out, it moves
the line to `out_of_data` through the state machine. Calls are not rated for the demo.

**RatelDesk and RatelPay.** The screens and nothing else. Every rule lives in RatelBSS. RatelDesk is
served only on the office network and the VPN. RatelPay shows nothing personal about a line's owner,
loads in under 3 seconds on 3G, and is a small page without a heavy framework bundle.

**RatelVoice, RatelOps (network team).** Configuration, not application code. RatelVoice
configuration lives in `network/voice/`, RatelOps in `ops/`. They touch our software only through
RatelLink (calling settings) and RatelMeter (call records).

## Major data flows

1. **Sell and activate.** RatelDesk -> RatelBSS (customer, SIM, number, plan, KYC verified) -> line state machine -> `POST /v1/lines/{imsi}/activate` -> RatelLink writes the Open5GS subscriber document (keys, MSISDN, internet APN at plan speeds, ims APN when voice) -> takes effect at the phone's next attach.
2. **Attach.** Phone -> eNB -> MME -> HSS reads the record from MongoDB (the only moments RatelCore reads a line's record) -> session with the line's fixed IP and AMBR -> UPF counts bytes.
3. **Usage.** UPF counters -> RatelMeter agent (core-up) -> RatelMeter API -> `usage_record` -> RatelBSS rating job -> buckets -> `out_of_data` -> `POST /v1/lines/{imsi}/data` (slow or off).
4. **Calls.** S-CSCF writes call records to RatelVoice MySQL -> RatelMeter agent (voice) -> RatelMeter API -> `call_record` -> shown on the line page (not rated for the demo).
5. **Top-up.** Customer -> RatelPay -> payment gateway -> webhook -> RatelBSS verifies signature and re-queries the provider -> credits once (`provider_ref` unique) -> ledger entry. Or voucher redemption, at most 5 failed attempts per number per hour.

Running out of data never touches calling: `/data` changes only the internet APN. Only
`/deactivate` stops calls.
