# RatelLink: activate, data and deactivate write the Open5GS subscriber document
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** 2026-10-13 | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Week:** 2 | **Target date:** TODO (by Oct 8) | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Source:** Build Plan, Contract 1; RatelLink spec; Week 1 RatelLink bullets; RatelVoice "Changes on RatelCore".

## Objective
`/activate`, `/data` and `/deactivate` write RatelCore's subscriber record correctly, including the calling settings, so a line created through the API attaches and registers for calls.

## Context
- `/activate`: writes the subscriber document: keys, MSISDN, internet APN at the given speeds, and the ims APN when `voice` is true.
- `/data` (`full`, `slow`, `off`): changes the internet APN only. Calling is untouched. Running out of data never stops calls.
- `/deactivate`: deletes the Open5GS subscriber document (keys stay in RatelLink's store); `/activate` rewrites it.
- Every line gets a fixed IPv4 address from `10.45.0.0/16` at activation; none activates without one; a released address is not reused for 24 hours.
- Until live changes land, every change takes effect at the next attach.

## Already delivered (W2-01 pull request): the address allocator
`IpAllocator` (`services/ip_allocation.py`) with its pure rules in `domain/ip_pool.py` and atomic MongoDB claims in the `ip_allocation` collection: the lowest free address from `RATEL_LINK_UE_POOL`, one address per line and one line per address, idempotent allocation, release, a 24-hour hold before another line can take a released address (the same line can take its own back), and a clear error when the pool is full. This issue only has to call `allocate` on activation and `release` on deactivation. Open questions are items 33 and 34 in DECISIONS_PENDING.md.

## Scope
- Build documents from a **template taken from a subscriber Open5GS created itself**, one that already has the ims APN. Never handwrite the schema.
- Static IP assignment and the 24-hour hold. Confirm the fixed-address rule with the network team on day one (Build Plan).
- `line_state` updates (`status`, `msisdn`, `apns`, `ue_ip`, speeds, `data_mode`, `updated_at`).
- Idempotency: activating an active line with the same settings succeeds and changes nothing.
- Routes go on `new_v1_router()` so they require `Authorization: Bearer <key>` by default (ADR 0007).
- Remove `link_activate_line`, `link_set_data_mode`, `link_deactivate_line` from `contracts/not_implemented.txt`.

## Out of scope
Live changes (throttle or detach mid-session). Switching deactivation to `subscriber_status` barring (decide after W2-05). Reading lines (W2-03).

## Dependencies
- W2-01 (and the SIM key store, authentication and audit writer already delivered by the security PR). The Open5GS template and the ims APN/pool from the network team (TODO: obtain the template). Open5GS v2.8.0 on the lab core-cp.
- `TODO(contract)`: response bodies, `reason` values, whether speeds are required for `data` mode `off`, number formats.

## Acceptance criteria
- A document written through the API matches the template **field for field**, apart from its own values (automated comparison against the template).
- Activate twice with the same settings: one document, no change on the second call.
- `data` with `off` removes only the internet APN; the ims APN remains.
- `deactivate` removes the document; a later `activate` restores it from stored keys.
- No two active lines share an address; a released address is not handed out again within 24 hours (test with an injected clock).
- Lab run recorded in the PR (required): a line created this way is present in the lab MongoDB as expected.

## Data / integrity requirements
Idempotent. State only through these operations. Unique `imsi` and unique active address. UTC timestamps.

## Security / privacy requirements
Keys are decrypted **only on the activation path, through `SimKeyStore.get_keys`**, only to write the document, and never logged, returned, put in an audit entry or kept longer than the call (`SimKeys` has a redacted repr and no serialisation path; do not unpack it into logs or dicts). `/data` and `/deactivate` do not need the keys. Every write adds an audit entry with the calling system's `api_key_id` (from the `ApiPrincipal`), through `AuditLog.append`, whose guard rejects `ki`, `opc` and similar fields. RatelLink is the only writer of the `open5gs` subscribers collection; only subscriber documents are touched there.

## Testing requirements
Unit (document builder, IP allocator), integration (local MongoDB), **lab** (required).

## Operational requirements
Runbook update. Rollback: deactivate and re-activate restores a line.

## Suggested skill level
Careful, security-minded; Python/FastAPI, MongoDB, comfortable with Open5GS data and Linux on the lab host.
