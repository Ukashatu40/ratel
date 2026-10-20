# RatelCore integration facts (for RatelLink)

What the network team told the software team on 2026-10-11, and what it means for the code. This
is a summary of three documents that are **not in this repository** (it is public, and they carry
host addresses and operational detail): the *RatelLink Developer Integration Guide*, the *RatelLink
Development Documentation* and the *RatelCore Operations Runbook*, all dated 11 October 2026 and
kept next to the Build Plan (see [source/README.md](source/README.md)). Where this file and those
documents disagree, the documents win, and this file should be corrected.

Rules for this file: no host addresses, no credentials, no real IMSIs or numbers, nothing about how
the core is protected. Add only what a developer needs to write correct code.

## What this settles

The Open5GS subscriber document is now specified: field names, types, units, and the order of the
APN sessions. [W2-02](issues-week2/W2-02-ratellink-line-operations.md) no longer needs to guess the
schema. **One input is still missing**: the `ims` session's voice `pcc_rule` entries must be copied
from a template exported from the lab, not from the guide's abbreviated example (see N1 below).

## Rules for writing subscribers

1. RatelLink is the only writer of `subscribers`. Documents created by hand are deleted before the gate.
2. **Never replace a whole existing document.** The HSS writes `sqn`, `imeisv`, `mme_host`,
   `mm_realm`, `mme_timestamp` and `purge_flag` into it, and a replace wipes them. Use `$set` on
   named paths only.
3. **Exact BSON types.** Integers are int32. Keys and the MSISDN are strings. A double where an
   int32 is expected can be read as 0.
4. **Never write `security.sqn`.** Leave it out on create. Resetting it makes the SIM reject the
   network's challenge.
5. Every new SIM gets `network_access_mode` 2 (packet only). The network is LTE only.
6. Ki and OPc are stored as plaintext in this collection, because Open5GS needs them that way. They
   must never be logged, returned by the API, or leave the core host unencrypted. This is the
   place where RatelLink's encrypted store ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md))
   hands keys over, on the activation path only.

## The document

| Field | Type | Value |
| ----- | ---- | ----- |
| `imsi` | string | 15 digits |
| `msisdn` | array of string | `["234" + 10 digits]`, digits only, no plus sign. A line stored in any other form **cannot be called**: dialled numbers are rewritten to this form before the lookup |
| `schema_version` | int32 | 1 |
| `security.k` | string | Ki, 32 hex characters, **upper case** |
| `security.opc` | string | OPc, 32 hex characters. Putting OP here makes every attach fail with a MAC failure |
| `security.op` | string or null | null |
| `security.amf` | string | `"8000"` |
| `ambr` | object | `{downlink, uplink}`, each `{value, unit}` |
| `slice` | array | one slice holding the sessions |
| `subscriber_status` | int32 | 0 = service, 1 = barred (see N4) |
| `operator_determined_barring` | int32 | 0 |
| `access_restriction_data` | int32 | 32 |
| `network_access_mode` | int32 | 2 |
| `subscribed_rau_tau_timer` | int32 | 12 |
| HSS-owned: `imeisv`, `mme_host`, `mm_realm`, `purge_flag` | arrays | create as `[]`, never write again |

**Speeds** are `{value: int32, unit: int32}`, unit 0 bps, 1 Kbps, 2 Mbps, 3 Gbps, 4 Tbps. A plan of 10
Mbps is `{10, 2}`. A decimal plan becomes whole numbers in a smaller unit (1.5 Mbps is 1500 Kbps).
The contract carries `speed_*_mbps` as numbers, so RatelLink must do this conversion and refuse
(422) a speed that is not a whole number of Kbps.

**Sessions** (`slice[0].session`): `internet` (type 3, QCI 9, ARP priority 8, pre-emption 1 and 2,
ambr = the plan speeds, `pcc_rule` empty) and `ims` (type 1, QCI 5, ARP priority 1, with the voice
`pcc_rule` entries copied unchanged from the lab template). **`internet` must always be at index
0**: if `ims` comes first the phone gets no data. The `ims` session exists only when voice is on
for that line, and it never gets `ue.ipv4`.

## Operations

| RatelLink operation | Change in `subscribers` |
| ------------------- | ----------------------- |
| Add SIM (W2-01) | **None.** Keys only. A SIM with keys and no line cannot attach |
| Activate | Create from the template if absent. If present, `$set` only the fields RatelLink owns |
| Data `full` or `slow` | `$set` the internet session `ambr` (and the top-level `ambr`) |
| Data `off` | `$pull` the internet session. `ims` stays, so calls keep working. Turning data back on re-inserts `internet` with `$push` and `$position: 0` |
| Deactivate | **Not decided by the network team**: bar (`subscriber_status` 1) or delete the document (N4). Built as **delete** (Build Plan), swappable after the spike |
| Read line | `msisdn`, sessions, speeds, fixed address. **Never** the `security` object |

Changing one session without touching the other:
`update_one({"imsi": imsi}, {"$set": {"slice.0.session.$[s].ambr": new_ambr}}, array_filters=[{"s.name": "internet"}])`.

**Changes apply at the phone's next attach.** There is no live push yet (N5). Plan every demo step
that depends on a change (data off, slow down) around an airplane-mode toggle or a re-attach.

## Where this differs from what we already built or wrote

| Topic | Built or written | The network team's documents | Action |
| ----- | ---------------- | ---------------------------- | ------ |
| Address pool | The allocator hands out the lowest free address in the whole `10.45.0.0/16` | Fixed addresses must be allocated **outside the dynamic range** the SMF and UPF use, "agreed with the network team", or two phones can share an address and usage bills to the wrong line | **N2.** Until agreed, do not run activation against the lab. `RATEL_LINK_UE_POOL` can already point at a sub-range |
| Reserved first host | The allocator never gives out the first host (`.1`) | The first host of the pool is the UPF's own gateway address | **Confirmed correct.** Decision 33 is resolved |
| Ki and OPc case | Stored exactly as sent (either case) and compared without regard to case | `security.k` and `security.opc` are written in **upper case** | Activation converts to upper case when it writes. The contract's pattern already accepts both |
| `amf` | Not stored; open item 15 in [DECISIONS_PENDING.md](DECISIONS_PENDING.md) | Always `"8000"` | **Resolved:** a constant RatelLink writes, not a request field. Item 15 can be closed |
| MSISDN | Was: any non-empty string | Must be `234` + 10 digits | **Done in W2-02:** the API takes the stored form and the contract has the pattern `^234[0-9]{10}$` (N6 decided 2026-10-13) |
| Deactivate | W2-02 says "deletes the document" | Bar or delete is open, and delete makes the core reject the SIM with cause #8 | **Built as delete (2026-10-14).** Delete also loses the HSS-owned `security.sqn`, which rule 4 above warns about: the lab must show a re-activated SIM attaches again. Stays open until the W2-05 spike |
| Activation vs template | "Matches the template field for field" | Existing documents are never replaced, only `$set` | **Done in W2-02:** one atomic MongoDB update (`$set` for RatelLink's fields, `$setOnInsert` for the rest). Tested on a real MongoDB, including that `sqn` (int64) and the other HSS fields survive |

## Still missing, and who can supply it

| # | What | Why it blocks | From |
| - | ---- | ------------- | ---- |
| N1 | **A key-free export of one working subscriber that has the `ims` session** (for example `findOne` with the `security` field excluded, saved outside the repository) | The voice `pcc_rule` entries cannot be written from the guide's abbreviated example | Network team |
| N2 | **The static address range** for fixed IPs, outside the SMF's dynamic range | Without it, activation can hand out an address the core also hands out dynamically | Network team |
| N3 | **Who installs RatelLink on core-cp and with which MongoDB access.** Ready for them: `deploy/core-cp/` (install steps, systemd unit, and the least-privilege MongoDB user, tested). They must first enable MongoDB authentication (updating the HSS and PCRF settings) and run the user script. **Checked 2026-10-15 by the project lead on core-cp:** the unique `imsi` index exists; PyPI is reachable; MongoDB still accepted a command with no credentials, so authentication is not on yet. The documents say developers do not log in to the core hosts, and the project lead now has a login there: TODO(network team) confirm what it may be used for (read-only checks are assumed; the install stays with the network team) | W2-02's lab run and the Week 2 gate (a line created through the API attaches) | Network team and project lead |
| N4 | **Bar or delete** on deactivate. Whether the MME acts on `subscriber_status` 1 is untested. **Also: does a SIM attach again after delete and re-activate**, given the `sqn` is lost? | The choice only. `/deactivate` is built as delete | W2-05 spike |
| N5 | **Live changes.** They need a MongoDB replica set (change streams), which is not running | The demo's "runs out of data, then slowed or cut" happens only at next attach until this lands | W2-06 spike, then network team. **Source reading 2026-10-16 ([spike-live-changes.md](spike-live-changes.md)):** a replica set plus the HSS setting `use_mongodb_change_stream` lets RatelLink force one phone to detach and re-attach; a speed pushed into a live session is not in the source. Lab test pending |
| N6 | ~~API form of the number~~ **Decided 2026-10-13:** the API takes the stored form (`234` + 10 digits), so RatelLink never converts | | Done |
| N7 | **Where usage and call records come from.** The guide says they are not defined and the core produces counters and records in different places | RatelMeter (W2-08, W2-10) | Network team |
| N8 | The separate document the runbook mentions, *RatelLink Build Guide: Open5GS Subscriber Schema* (the Integration Guide may replace it) | Possibly more schema detail | Network team |
| N9 | **Python 3.12 on core-cp.** The host runs Ubuntu 22.04.5 with Python 3.10.12 (checked 2026-10-15). RatelLink needs 3.12 (see [deploy/core-cp/README.md](../deploy/core-cp/README.md)); it must be installed next to the system Python, not replace it | The install script stops with "needs Python 3.12 or newer" | Network team (adds software to a core host) |

## What this means for the demo

- **Use an Android VoLTE handset** for outgoing calls. Outgoing calls from iPhones fail today (a
  network-side fallback behaviour), though incoming calls to them work.
- **Calls to other networks do not work** and must not be promised in the demo.
- **Data limits take effect at the next attach** until live changes exist, so the "slowed or cut"
  step needs a re-attach unless N5 is solved.
- A line's SIM must have a **two-digit MNC** (PLMN 62100) or it does not belong to this network.
