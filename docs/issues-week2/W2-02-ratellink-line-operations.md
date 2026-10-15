# RatelLink: activate, data and deactivate write the Open5GS subscriber document
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** 2026-10-13 | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Source:** Build Plan, Contract 1; RatelLink spec; Week 1 RatelLink bullets; RatelVoice "Changes on RatelCore".

## Objective
`/activate`, `/data` and `/deactivate` write RatelCore's subscriber record correctly, including the calling settings, so a line created through the API attaches and registers for calls.

## Context
- `/activate`: writes the subscriber document: keys, MSISDN, internet APN at the given speeds, and the ims APN when `voice` is true.
- `/data` (`full`, `slow`, `off`): changes the internet APN only. Calling is untouched. Running out of data never stops calls.
- `/deactivate`: deletes the Open5GS subscriber document (keys stay in RatelLink's store); `/activate` rewrites it.
- Every line gets a fixed IPv4 address from `10.45.0.0/16` at activation; none activates without one; a released address is not reused for 24 hours.
- Until live changes land, every change takes effect at the next attach.

## The subscriber schema is now specified
The network team's Integration Guide (11 Oct 2026) gives the exact document, types, units and rules. Read [RATELCORE_INTEGRATION_FACTS.md](../RATELCORE_INTEGRATION_FACTS.md) before writing any code. The rules that matter most: update an existing document with `$set` on named paths only (never replace it), never write `security.sqn`, int32 for every integer, `internet` always at session index 0, `network_access_mode` 2, MSISDN as `["234" + 10 digits]`, Ki and OPc in upper case, speeds as `{value, unit}` whole numbers. Data `off` is a `$pull` of the internet session and data back `on` a `$push` at position 0.

## Delivered by the W2-02 pull request (`feature/ratellink-activate-and-data`): activate and data
`POST /v1/lines/{imsi}/activate` and `POST /v1/lines/{imsi}/data` (`link_activate_line`, `link_set_data_mode`) are built, in the contract, fuzzed by Schemathesis in CI, and tested on a real MongoDB. Pure document rules in `domain/subscriber.py`; writes to the core's `subscribers` collection in `repositories/mongo.py` as single targeted updates (never a replace); the services are `services/line_activation.py` and `services/data_mode.py`. `line_state` is now written, so `GET /v1/lines/{imsi}` and `GET /v1/assignments` return real data.

**Still open in this issue:** (1) `/deactivate`, which waits for the barring spike (W2-05) to decide bar or delete; (2) the **lab run**, which needs the network team's answers N1 (voice template), N2 (address range) and N3 (where RatelLink runs); (3) the acceptance criterion "matches the template field for field", which can only be checked against the real exported template. Until N1 exists, activation with `voice: true` is refused with 503 and `voice: false` works.

## Already delivered (W2-01 pull request): the address allocator
`IpAllocator` (`services/ip_allocation.py`) with its pure rules in `domain/ip_pool.py` and atomic MongoDB claims in the `ip_allocation` collection: the lowest free address from `RATEL_LINK_UE_POOL`, one address per line and one line per address, idempotent allocation, release, a 24-hour hold before another line can take a released address (the same line can take its own back), and a clear error when the pool is full. This issue only has to call `allocate` on activation and `release` on deactivation. The first host of the pool is the UPF gateway, so reserving it is correct (item 33 is resolved). **Before activation runs against the lab, the network team must say which part of `10.45.0.0/16` is outside the SMF's dynamic range (N2 in the facts file)**; point `RATEL_LINK_UE_POOL` at it. Item 34 is still open.

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
- **The `ims` session's voice `pcc_rule` entries must come from an exported working subscriber (N1 in the facts file); the guide's example is abbreviated on purpose.** **If the network team cannot supply the template in time, make it yourself on the lab:** in the Open5GS WebUI add one **test** subscriber with a **dummy** IMSI and **dummy** Ki/OPc (never a real SIM key) and the `internet` and `ims` APNs, then export that one document from the lab MongoDB (`db.subscribers.findOne({imsi: "<the test imsi>"})` in `mongosh` on core-cp) to a file **outside the repository**. That is a subscriber "Open5GS created itself", with the ims APN, which is what the Build Plan asks for. Replace the key values with placeholders before sharing the file with anyone, and keep it out of Git; only the field shape matters. Confirm with the network lead that the ims APN settings are the final ones.
- W2-01 (and the SIM key store, authentication and audit writer already delivered by the security PR). The Open5GS template and the ims APN/pool from the network team (TODO: obtain the template). Open5GS v2.8.0 on the lab core-cp.
- `TODO(contract)`: response bodies, `reason` values, whether speeds are required for `data` mode `off`. The stored number form is now known (`234` + 10 digits); the API form is N6 in the facts file.

## Acceptance criteria
- A document created through the API matches the template **field for field**, apart from its own values (automated comparison against the template).
- Activating a line whose document already exists changes only the fields RatelLink owns: `sqn`, `imeisv`, `mme_host`, `mm_realm`, `mme_timestamp` and `purge_flag` are untouched (test with a document that has them set). `security.sqn` is never written.
- Integers are written as int32, `internet` is at index 0, `network_access_mode` is 2, the MSISDN is a one-item array in `234` form, Ki and OPc are upper case.
- The `security` object never appears in any response, log line or audit entry.
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
