# Product rules (the product requirements of record)

**Status:** DRAFT, awaiting review. Written by the project lead (@Ukashatu40) on 2026-10-23.
**Why this exists:** the Ratel Plus Subscriber Platform PRD that the Build Plan cites was never
found: not in the repo, not in the project, not with the Build Plan's author. Nobody can produce
it, so this page takes its place. When it is approved it is the document that CLAUDE.md and the
source README mean by "the PRD". If the original PRD turns up, compare it with this page in a pull
request and change whichever is wrong.
**Starting text:** the Build Plan of 28 Sep 2026 and the extract the network lead (@CaptRaven)
wrote on 2026-10-22 ("Ratelplus Product Rules (Build Plan extract)", kept outside Git), which he
drafted with AI assistance from the Build Plan. Nothing here is new product behaviour except the
rows marked **Decided**, each with its date and who decided it.
**Review 2026-10-23:** @CaptRaven checked the page row by row against the Build Plan. The lifecycle
table, the plan, wallet and rating rules, vouchers, payments and the call and usage record fields
match it. He asked for six changes, all made in this revision. His approval is still pending.
**To approve:** @CaptRaven (author of the Build Plan) and @capitanaserdel (frontend lead). Review
each row against the Build Plan, which is the source for everything not marked Decided.

## How to read this page

| Word | Meaning |
| ---- | ------- |
| **Rule** | Stated by the Build Plan. Code and tests follow it. |
| **Decided** | Not in the Build Plan. Chosen by the project lead on the date given. Changing it needs a pull request that edits this page. |
| **Demo value** | A stand-in so the demo can run. Not a compliance or finance answer. Replace it before a real customer. |
| **Open** | Nobody has decided. Code marks it `TODO(PRD)` and does not guess. |

Where this page and `contracts/openapi.yaml` disagree, the contract wins for the shape of an API
call, and this page wins for product behaviour. Fix the one that is wrong in the same pull request.

## Requirement ids the Build Plan cites

The Build Plan names these ids but not the original wording. The right column is only what the
Build Plan says about each.

| Id | What the Build Plan says | Where |
| -- | ------------------------ | ----- |
| CHG-6 | Live changes: a line that runs out of data or is suspended is slowed or cut without waiting for a reattach. Priority P1. Target: slowed within 60 seconds; a suspended line loses internet and calls within 60 seconds; otherwise the fallback (changes at next attach) is written down. Result of the spike: [spike-live-changes.md](spike-live-changes.md) | RatelLink |
| VOI-1 to VOI-4 | Done when: two phone models we would sell register and show VoLTE; 20 test calls of 3 minutes all connect with two-way audio and none drops; the called phone shows the caller's number; a deactivated line cannot call or be called after its next attach. Which sentence is which id is not stated | RatelVoice |
| VOI-7 | Charging for minutes. Not built for the demo: calls are not rated, their records show on the line page | RatelBSS money |
| TOP-2 | RatelPay shows nothing personal about a line's owner | RatelPay |
| TOP-3 | RatelPay loads in under 3 seconds on 3G: a small page, no heavy framework bundle | RatelPay |
| ACC-3 | Every screen that changes data has a history tab | RatelDesk, RatelPay |
| OPS-1, OPS-2 | Done-when for RatelOps, wording not given. The component spec says Prometheus, Grafana and Alertmanager, alerts by email and one chat channel, a radio counts as up when the MME sees it connected | RatelOps |

Ids never named anywhere (CHG-1 to CHG-5, VOI-5, VOI-6, TOP-1, ACC-1, ACC-2) are unknown. Do not
invent them.

## Line lifecycle

Six states: `awaiting_activation`, `active`, `out_of_data`, `expired`, `suspended`, `terminated`.
`out_of_data` is the state in which internet stops or slows but calls carry on. A suspended line
returns to whichever of `active` or `out_of_data` it was in (stored as `state_before_suspension`).
**Every transition not in this table is refused.**

| From | To | When | RatelBSS calls RatelLink |
| ---- | -- | ---- | ------------------------ |
| awaiting_activation | active | First plan paid for and KYC verified | `/activate` with the plan's speeds, voice true |
| active | out_of_data | Allowance used up before the plan expires | `/data` mode slow with the plan's slow speeds, or mode off, per the plan's `on_exhaustion` |
| out_of_data | active | Customer buys a bundle or a new plan | `/data` mode full with the plan's speeds |
| active or out_of_data | expired | Plan validity ends without renewal | `/deactivate` |
| expired | active | Customer buys a plan | `/activate` |
| active or out_of_data | suspended | Customer care action, with a reason | `/deactivate` |
| suspended | the state it had before | Customer care action, with a reason | `/activate`, then `/data` if it was `out_of_data` |
| any other state | terminated | Care action or end of contract | `/deactivate`; SIM retired, number quarantined |

Rules:

- State changes happen only through the state machine. Each writes an audit entry saying who made it and why. No code updates a state column directly.
- No line activates until the customer's KYC is verified.
- A transition not in the table is refused, and tests prove it.
- Until live changes (CHG-6) land, a slowed or cut line may keep its old service until its phone next reattaches.
- A number taken back from a terminated line is quarantined for a period compliance sets. **No value is decided**, so none is written here and code must not default one (decision 4). Any value used to run the demo is a setting labelled demo only, never a built-in default.
- **Decided 2026-10-23, reasons:** every care action (suspend, reinstate, terminate) carries a reason from a short fixed list plus free text. Starting list: `fraud`, `non_payment`, `customer_request`, `lost_sim`, `other`. @capitanaserdel and @ml-lawarn edit the list before RatelDesk is built.
- **Decided 2026-10-23, failure in the middle of a transition:** if RatelLink fails, the line's state does not change, the call is retried with the same `Idempotency-Key`, and an alert fires after repeated failure. The retry count is set when W2-11 is built (decision 16 in [DECISIONS_PENDING.md](DECISIONS_PENDING.md)).

## Plans, bundles, wallet and ledger

Money is whole kobo, never a decimal. Time is stored and sent as UTC, epoch seconds on the wire.
Both are engineering rules ([ENGINEERING_RULES.md](ENGINEERING_RULES.md)); the Build Plan itself
says only that usage intervals align to UTC.

- A **plan** has `plan_id`, name, `price_kobo`, `validity_days`, `data_bytes`, upload and download speeds, channels, `on_exhaustion` (`slow` or `stop`) and slow upload and download speeds. States: `on_sale`, `retired`.
- A **bundle** has `bundle_id`, name, `price_kobo`, `validity_days`, `data_bytes` and channels. States: `on_sale`, `retired`.
- Each plan period or bundle bought creates one **allowance bucket** with total bytes, used bytes, `valid_from` and `valid_to`. Data left in an expired bucket is lost. **There is no rollover in the first release.**
- The **wallet** holds `line_id` and `balance_kobo`: cash the customer can spend on plans and bundles.
- The **ledger** is append-only. A wallet's balance always equals the sum of its entries. A nightly job checks that and alerts on any mismatch ([ADR 0009](adr/0009-ledger-append-only-in-the-database.md)).
- **VAT** is recorded as its own ledger entry so reports can separate it. Rate: 7.5% at the time of the Build Plan, to be confirmed by finance (decision 7). Demo value: 7.5%.
- The kinds of ledger entry are not specified. Code marks them `TODO(PRD)`.

## Rating loop

- Every 300 seconds it takes usage records not yet rated and deducts each from the line's buckets, soonest expiry first.
- It marks each record rated in the same database transaction as the deduction, so a crash never rates a record twice.
- When the last bucket runs out the line moves to `out_of_data` through the state machine. When validity ends without renewal it moves to `expired` the same way.
- A line can use up to about five minutes of data past zero before it is noticed. Accepted for the demo.
- Calls are not rated for the demo (VOI-7).

## Vouchers

- A card has a 20 digit number and a 13 digit PIN plus one Luhn check digit. The PIN is stored hashed, never in plain text.
- States: `requested`, `approved`, `sent_to_printer`, `in_stock`, `on_sale`, `used`, `expired`, and `locked` for lost or stolen cards.
- At most 5 failed redemption attempts per card number per hour.
- A voucher redeemed twice credits exactly once.

## Payments

- One gateway for the first release. Which one is open (decision 6; candidates and the sandbox requirement are in [DECISIONS_PENDING.md](DECISIONS_PENDING.md) item 11).
- Credit a payment only after verifying the webhook's signature and re-querying the transaction with the provider.
- `provider_ref` is unique, so a webhook delivered twice credits once.
- One payment row per provider transaction, with provider, `amount_kobo`, status and `line_id`.

## Customers and KYC

| Field | Notes |
| ----- | ----- |
| `customer_id` | Key |
| `name` | |
| `phone` | Contact number, separate from the line's MSISDN |
| `email` | |
| `id_type` | Type of identity document. Allowed values open (decision 3). **Demo value:** `NIN` only |
| `id_number` | The Build Plan says to capture the customer's NIN at registration |
| `address` | Format open (decision 3). **Demo value:** free text |
| `kyc_status` | `pending`, `verified` or `rejected` |
| `blocked` | A separate flag, not a `kyc_status` value |

- No line activates until `kyc_status` is `verified`.
- The verification rules (which documents, who verifies, what a rejection means) are compliance's. The Build Plan says to confirm the current NCC SIM registration requirements with them before the pilot. Open (decision 2).
- RatelPay shows none of these fields (TOP-2). RatelDesk is served only on the office network and the VPN.
- **Decided (engineering rule, [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)):** the NIN and every field above are personal data. They never appear in logs, tests or the repository. The Build Plan text does not state this.

## Staff access (RatelDesk)

**Decided 2026-10-23, demo only:** two roles, `agent` and `admin`. Every change is audited. Accounts
and sessions follow decision 13 in [DECISIONS_PENDING.md](DECISIONS_PENDING.md). The real roles are
reviewed before the pilot.

**Decided 2026-10-27 (project lead), first release, M-26:** staff sign in with an email and a
password; the server keeps the session and sets an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
A session lasts 8 hours at most and ends after 30 minutes without use. Five wrong passwords in a
row lock the account for 15 minutes. A password is at least 12 characters. There is no sign-up: an
admin makes accounts with `staff_cli` on bss-app. An `agent` sells and looks after lines (register a
customer, sell a SIM, activate, suspend, reinstate). Only an `admin` registers a customer as already
`verified` or terminates a line. TODO(PRD): the permission split, the lockout and the session
lengths are the project lead's choices for the first release, to be confirmed with the product
owner and compliance before the pilot.

## SIMs

**Decided 2026-10-10 (DECISIONS_PENDING.md item 4):** importing a SIM for an IMSI that already exists
with the same keys changes nothing (200). With different keys it is refused with 409 and the keys are
never overwritten. Changing a SIM's keys becomes a deliberate admin action later.

## Addresses and sessions

- **Rule:** RatelLink gives every line a fixed IPv4 address on the internet APN at activation, from `10.45.0.0/16`, and no line is activated without one. The IMS APN uses its own pool, set by the network team. The meter relies on this to map addresses to IMSIs.
- **Decided 2026-10-22 (network lead):** the internet session is IPv4 only (Open5GS session type 1), because the meter counts IPv4 addresses and IPv6 would pass uncounted. The live core was changed on 2026-10-22 (SMF pool, UPF pool, `ogstun`, and both lab subscribers) and RatelLink writes the internet session as type 1 in the subscriber template, so a new line does not come up IPv4v6 again. A live phone attach to confirm it is still pending.

## Call and usage records

Fields as the Build Plan lists them; the agreement with the network team is in
[call-record-agreement.md](call-record-agreement.md).

**call_record** (PostgreSQL, one row per call): `call_id` (unique; the API upserts on it, so a replay
overwrites instead of adding), `from_msisdn`, `to_msisdn`, `started_at`, `answered_at`, `ended_at`,
`end_reason`. The allowed `end_reason` values, and what from and to mean, are open (decision 8).

**usage_record** (PostgreSQL, one row per line per 300 second interval): `imsi` plus `period_start`
(unique), `period_end`, `ue_ip`, `apn`, `bytes_up`, `bytes_down`, `source`, `record_id`. Packets from
the phone's address count as upload, packets to it as download.

How they are produced:

- The S-CSCF writes a record when each call starts and ends (Kamailio `acc` and `dialog` modules, into RatelVoice's MySQL). Every 60 seconds the agent joins each call's start and end into one record and posts it to the RatelMeter API. The lab does not do this yet: see the lab finding in the call record agreement.
- Every 300 seconds the data agent reads per-address counters on the `ogstun` interface, subtracts the previous reading, maps each address to an IMSI with `GET /v1/assignments`, and posts the batch. The internet session is IPv4 only so that every byte is counted (see Addresses and sessions).
- Intervals align to the clock in UTC (00:00, 00:05, 00:10 and so on), so a replayed interval always lands on the same key. Intervals with zero bytes are skipped.
- A reading lower than the last one means the UPF or its host restarted, so the new reading counts from zero.
- If the API is unreachable the agent spools to disk and replays in order. Nothing is lost and nothing is counted twice.
- Clocks on core-up and the voice VM stay synchronised over NTP, because every record's key and every call's duration depend on them.
- A released IP address is not given to another line for 24 hours, so a late counter reading is never charged to the wrong person. This is **enforced by RatelLink's allocator** (it records release times in `ip_allocation.released_at`), not by Open5GS and not by the assignments endpoint. `GET /v1/assignments` lists current addresses and those still on hold ([DECISIONS_PENDING.md](DECISIONS_PENDING.md) item 52). A phone that is attached without a fixed address can be given a recently released one from the SMF's own pool, so the fixed addresses must be outside the SMF's dynamic range (N2 in [RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md), still open).

## Out of scope for the demo

Charging for minutes (VOI-7), rollover of unused data, and everything in the Build Plan's "What not
to build yet" list. **Decided 2026-10-23:** charging for minutes and rollover are not wanted for the
demo, and are revisited after it.

## Demo journeys

**Decided 2026-10-23 as a draft** for the team to confirm against what can be finished by the code
freeze on 2026-11-23. The Build Plan says RatelDesk and RatelPay are done when "the four journeys in
the PRD" run through the screens without anyone touching the API by hand, but does not list them.

1. Buy and activate a line (pay, KYC verified, line becomes `active`, phone has data).
2. Top up with a voucher or a payment.
3. Run out of data and be slowed or cut (`out_of_data`), then buy a bundle and be restored.
4. Suspend a line with a reason and reinstate it.

## Open decisions

"Owner" is who can answer. A row is closed when its **Status** says so, with a date.

| # | Decision | Owner | Status |
| - | -------- | ----- | ------ |
| 1 | Does the original PRD exist? | Project lead | **Closed 2026-10-23 by the project lead: it does not exist.** It is not in the repo, in the project or with the Build Plan's author. This page replaces it |
| 2 | Current NCC SIM registration and KYC verification rules | Compliance | Open. Asked: TODO date |
| 3 | Allowed `id_type` values and the address format | Compliance, RatelBSS developers | Open. Demo values above |
| 4 | Number quarantine period after termination | Compliance | Open. No value set; code must not default one |
| 5 | Data retention for customer, usage and call records | Compliance | Open |
| 6 | Payment provider | Project lead, finance | Open |
| 7 | VAT rate | Finance | Open. Demo value above |
| 8 | `end_reason` values and the meaning of from and to in a call record | Network team, RatelMeter developers | Open |
| 9 | Reason values for care actions | Customer care, RatelBSS developers | **Decided 2026-10-23** (starting list above) |
| 10 | What happens when RatelLink fails mid-transition | Project lead, RatelLink developers | **Decided 2026-10-23** (above); retry count at W2-11 |
| 11 | Staff roles for RatelDesk | Project lead | **Decided 2026-10-23, demo only** |
| 12 | SIM re-import with different keys | Project lead, network team | **Decided 2026-10-10**: 409, never overwrite |
| 13 | Charging for minutes and rollover after the demo | Product owner | **Decided 2026-10-23**: not for the demo |
| 14 | The four journeys | Product owner | **Decided 2026-10-23 as a draft**, team to confirm |

## Change log

| Date | Change |
| ---- | ------ |
| 2026-10-23 | First draft by the project lead from the Build Plan and the network lead's extract. |
| 2026-10-23 | Review by @CaptRaven against the Build Plan: addresses and sessions rule added, released-address rule corrected, quarantine demo value removed, UTC and NIN rules marked as engineering rules, extract authorship corrected. |
