# Call record agreement: RatelVoice → RatelMeter

**Status:** DRAFT — awaiting sign-off. Section 11 (added 2026-11-01) answers the questions from the lab results of 2026-10-30 and asks the network lead to decide the open points in it
**Drafted by:** @ml-lawarn
**To be signed off by:** @CaptRaven (network lead) and @capitanaserdel (RatelMeter owner since 2026-10-18)
**Reviewers:** @Ukashatu40, @CaptRaven
**Source:** Build Plan, RatelMeter spec "How calls work"; week two RatelVoice
column ("call record fields agreed with RatelMeter"); ticket "Agree the call
record fields with the network team".
**Related:** `contracts/openapi.yaml` (`CallRecord`, `end_reason` TODO),
DECISIONS_PENDING.md, W2-10 (call mode), W2-12 (ingest call).

## Lab finding, 2026-10-16: no finished-call record exists on RatelVoice yet

> **Superseded on 2026-10-30.** `acc` was switched on in the S-CSCF and now writes call records to MySQL. What it writes,
> and what it does not, is in section 11. The text below is the finding as it was on 2026-10-16.

Read-only checks on the voice VM by @Ukashatu40 (names and counts only, no rows, no credentials):

- No `acc`, `missed_calls` or CDR table exists in any database (`icscf`, `pcscf`, `scscf`,
  `ims_hss_db`).
- The S-CSCF and P-CSCF configurations load `ims_dialog.so`, and the S-CSCF also loads
  `ims_charging.so`. **Neither loads the `acc` module**, and no `acc_log_flag` or `acc_db_flag`
  is set. The IMS dialog tables (`dialog_in`, `dialog_out`, `dialog_vars`) and `ro_session` exist.
- A count of those tables read outside a call returned 0. **That does not show what they hold
  during or after a call**: it was not read while a call was up. TODO(network team): read them
  during a call and after it ends. The read-only steps are in
  [runbooks/voice-call-record-checks.md](runbooks/voice-call-record-checks.md).
- The configurations were edited by hand (backup copies sit beside them) and are not in Git.

What this means: sections 3 and 10 assume `acc` and `dialog` write one record per call. On the lab
as it stands, nothing is known to keep a call after it ends. The call-mode agent has nothing to
read until the network team decides where call records come from (enable `acc` writing to MySQL
in UTC, or another source such as the charging session) and sends the table definition.
Sections 3 to 10 stay as the *proposal* for that source, not as a description of what exists.
Related: N7 in [RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md).

## 1. Purpose

This document records, in writing, exactly what RatelVoice (Kamailio) writes
to its MySQL database, what the RatelMeter call-mode agent reads, and what
`GET /v1/calls` returns. It exists so call mode can start: the agent is built
against this agreement, and the network team configures Kamailio to produce it.

Where this document and `contracts/openapi.yaml` disagree, the contract wins
and this document is corrected. Where this document and the Build Plan
disagree about what the product does, the PRD wins.

Sign-off by the network lead is required before any call-mode code is written.

**Note on scope:** the data-mode agent (W2-14, W2-15, W2-09) is built
independently of this agreement. This document governs call mode only.

## 2. The shape the API must return

`GET /v1/calls` returns `CallRecord` objects. Frozen fields (from the
contract):

| Field        | Type              | Notes |
|--------------|-------------------|-------|
| `call_id`    | string            | Stable, unique per call. Key for upsert. |
| `from_msisdn`| string            | Caller's number, E.164. |
| `to_msisdn`  | string            | Callee's number, E.164. |
| `started_at` | integer           | UTC epoch seconds. |
| `answered_at`| integer or null   | UTC epoch seconds; `null` if never answered. |
| `ended_at`   | integer           | UTC epoch seconds. |
| `end_reason` | string (enum)     | See §6. **TODO in the contract today.** |

Times are Unix epoch seconds in UTC, sent as integers. Both `/v1/calls` and
`/v1/usage` return at most 5,000 records per response, with `next_cursor` for
the rest. Calls are keyed on `call_id`; a replay must overwrite, never
duplicate.

## 3. What Kamailio writes (to be confirmed by @CaptRaven)

RatelVoice's S-CSCF writes call accounting via Kamailio's `acc` and `dialog`
modules into RatelVoice's MySQL. The network team owns this configuration.

The agent reads whatever Kamailio produces; it does not modify it. The
following must be confirmed by the network lead before this agreement is
signed:

- **Table names and columns.** Exact `acc` and `dialog` table names and the
  columns the agent will read. (Question Q1.)
- **One row or two per call.** Whether Kamailio writes a single row per call
  or separate start and end rows, and which column links them. The Build Plan
  says the agent "joins each call's start and end into one record," which
  implies two rows — confirm. (Question Q2.)
- **Restart safety.** Whether a Kamailio restart mid-call can lose the end
  row. If it can, the agent cannot guarantee `ended_at` and must decide how to
  represent the call. (Question Q7.)

## 4. `call_id`: how it is produced, and why it is stable and unique

The API upserts on `call_id`, so `call_id` must be stable (the same call
produces the same `call_id` on replay) and unique (two different calls never
collide).

**Proposed:** the SIP `Call-ID` header, as recorded by Kamailio's `acc`
module. It is globally unique per call, is generated by the originating
phone, and appears on both the start and end accounting rows, which makes the
join trivial.

**Risk:** a phone can reuse or spoof a `Call-ID`. If Kamailio cannot
guarantee uniqueness, the fallback is a composite of the `Call-ID` plus
`from_tag` plus `started_at`, or a Kamailio-generated `dialog_id`. The
network lead picks. (Question Q3.)

Whatever is chosen, state it here and in the contract, and add a test that
replays a batch and asserts the row count does not change.

## 5. Time zone and format

- **Store UTC.** All timestamps written by Kamailio must be UTC.
- **Wire format:** epoch seconds as integers, matching `/v1/usage`.
- **Kamailio's MySQL timestamps are the risk.** If Kamailio writes `DATETIME`
  in server-local time, the agent must convert to UTC explicitly, and that
  conversion must be tested. Confirm the column type and the server's time
  zone. (Question Q5.)
- NTP must be running on the voice VM and on core-up, because every record's
  key and every call's duration depend on synchronized clocks. (Network team,
  Week 3, but it matters from now.)

## 6. `end_reason` values

The contract has a `TODO` for `end_reason`. Proposed closed set; the network
lead confirms Kamailio can emit each, and maps SIP response codes to them.
(Question Q4.)

| `end_reason`  | Meaning | Typical SIP cause |
|---------------|---------|-------------------|
| `completed`   | Call answered, then ended normally by either party. | BYE after 200 OK |
| `cancelled`   | Caller hung up before the callee answered. | CANCEL |
| `busy`        | Callee was busy. | 486, 600 |
| `no_answer`   | Callee never answered; timeout. | No final response, timer expiry |
| `unavailable` | Callee not registered / not reachable. | 404, 480 |
| `failed`      | Any other SIP failure. | Other 4xx/5xx/6xx |
| `error`       | Network-side failure with no SIP final response. | Internal error |

Keep the set closed and small. Billing and reporting need to distinguish
answered from not, and normal from abnormal; they do not need every SIP code.
If finer detail is wanted later, add a separate `sip_status` field rather than
widening this enum.

**Unanswered calls.** A call that was never answered has `answered_at` set to
`null`. The `end_reason` is one of `cancelled`, `no_answer`, `busy`, or
`unavailable` — never `completed`. Confirm how Kamailio represents the
absence of an answer, and whether an end row exists at all for an unanswered
call. (Question Q6.)

## 7. The agent's behavior (for context; call mode is a later ticket)

Every 60 seconds the agent reads new records from Kamailio's MySQL, joins
each call's start and end into one `CallRecord`, and posts the batch to the
RatelMeter API. Records are keyed on `call_id`, so a replay overwrites.

This document does not authorize building call mode. Call mode starts once
this agreement is signed and W2-10 is scheduled.

## 8. Personal data

Call records are personal data. Who called whom, and when, is sensitive.

- Access to `/v1/calls` follows the same rules as customer records: VPN only,
  one API key per calling system, rotated every 90 days.
- Operational logs **never** contain `from_msisdn` or `to_msisdn`. Log
  `call_id` only. If a number must be inspected for debugging, mask it to its
  last four digits.
- Call records are never exported without a logged reason.
- The agent's logs follow the same rule: no IMSI, no MSISDN.

## 9. Contract change

Resolve the `end_reason` TODO in `contracts/openapi.yaml` in the **same
commit** as the signed document (not in the commit that only adds section 11). Add the enum from §6 to the `CallRecord` schema,
and remove the `TODO(contract)` marker. CI's Schemathesis run must still pass.

## 10. Questions for the network lead (@CaptRaven)

Please answer inline. These block sign-off.

1. **Schema.** Which exact tables and columns will Kamailio's `acc` and
   `dialog` modules write? Please paste the `CREATE TABLE` or the column
   list.
2. **Rows.** Is there one row per call or two (start and end)? Which column
   links them?
3. **Key.** What is the stable unique key — SIP `Call-ID`, `dialog_id`, or a
   composite? Can it be relied on across a Kamailio restart?
4. **`end_reason`.** Can Kamailio emit each value in §6? Which SIP response
   codes map to which value? Is there a value we are missing?
5. **Time.** Are the MySQL timestamps UTC or server-local? What column type?
   What time zone is the voice VM in?
6. **Unanswered.** For an unanswered call, is there an end row? What does it
   contain? How is `answered_at` known?
7. **Restart.** If Kamailio restarts mid-call, is the end row lost? If so,
   how should the agent represent that call?
8. **Volume.** Roughly how many accounting rows per call, and expected peak
   calls per second at the demo, so the agent's 60-second poll can be sized.

## 11. Answers from the lab, 2026-10-30 and 2026-11-02 (for the network lead to confirm)

Source: `acc` switched on in the S-CSCF on 2026-10-30, a `start_ts` column added on 2026-11-02, and the call cases
tried on both days between two of our own phones, read as counts, times and codes only (no number or Call-ID left the
VM). The procedure and the raw results are in [runbooks/voice-call-record-checks.md](runbooks/voice-call-record-checks.md),
section 3. The configuration is on the voice VM; its changes are kept in Git as snippets and SQL in
[../network/voice/](../network/voice/README.md) (no credentials).

### Answers to the questions in section 10

1. **Schema.** `scscf.acc` (answered INVITE, and BYE) and `scscf.missed_calls` (an INVITE that failed), from the
   container's own `acc-create.sql`, plus two columns we added to both: `from_user` and `to_user` (`VARCHAR(64)`),
   filled from the From and To user parts, and a third, `start_ts` (`INT UNSIGNED`, epoch seconds), filled with the
   arrival time of the INVITE (see `started_at` below). The agent reads `id`, `method`, `callid`, `from_tag`, `sip_code`,
   `sip_reason`, `time`, `from_user`, `to_user`, `start_ts`. TODO(network lead): add the `SHOW CREATE TABLE` output of both
   tables (column names and types, no rows) to the pull request; it also gives the type of `time`.
2. **Rows.** There is no start row and no end row. An answered call leaves `acc` rows for the INVITE (code 200) and
   for the BYE; a call that failed leaves `missed_calls` rows. **Each event is written twice** for a call between two
   of our own phones (one row per leg). A hang-up leaves **two** BYE rows when one phone hangs up (seen on 2026-11-02,
   both directions); four appeared once on 2026-10-30, most likely because both phones pressed hang up. `callid` links
   them all.
3. **Key.** The SIP Call-ID, and **both legs of a call share it** (seen). The agent groups by `callid`, so the number
   of rows per call does not matter. Not tested: a Kamailio restart (see 7). Not decided: a phone's Call-ID can
   embed the phone's address; whether `call_id` is stored as is or hashed is TODO(network lead, RatelMeter owner),
   and logs must follow section 8 either way.
4. **`end_reason`.** The codes seen are in the table below. A decline came back as 486 on 2026-10-30 and as 603 on
   2026-11-02, and a ring-out as 486 (after about 78 s) and as a 487 after the caller cancelled at 180 s, so the code
   alone does **not** separate busy from declined from ringing out. The set in section 6 cannot be emitted as written.
   A proposal follows the table.
5. **Time.** UTC. The VM is `Etc/UTC` and synchronised, MySQL's system time zone is UTC and `NOW()` equals
   `UTC_TIMESTAMP()`. The agent still converts explicitly, with a test.
6. **Unanswered.** There is no end row, only a `missed_calls` row written when the final reply passed the S-CSCF.
   `answered_at` is null. Its code is in the table.
7. **Restart.** Not tested. `acc` writes each row when the reply passes, so rows already written survive a restart,
   but a restart drops registrations and the S-CSCF keeps its dialogs in memory only (`ims_dialog` `db_mode` 0).
   TODO(lab): restart the S-CSCF during a call, hang up, and see whether a BYE row appears. Also unexplained: one
   answered call (2026-10-30 13:25 UTC) has no BYE row at all.
8. **Volume.** A failed call leaves 2 rows; an answered call leaves 2 INVITE rows and 2 to 4 BYE rows. At a handful of
   calls a second that is hundreds of rows a minute at most, so a 60-second poll is no concern.

### What each case looks like

| Case | Rows seen |
| ---- | --------- |
| Answered, then a hang-up | `acc` INVITE 200, then BYE 200 |
| Cancelled by the caller | `missed_calls` INVITE 487 |
| Busy | `missed_calls` INVITE 486 Busy Here |
| Declined by the callee | `missed_calls` INVITE **486 Busy Here** on 2026-10-30; **603 Decline** after 11 s on 2026-11-02 (the phone decides) |
| Rang out, nobody answered | `missed_calls` INVITE **486 Busy Here** about 78 s after the call was made (2026-10-30); **487** at 180 s when the caller finally cancelled (2026-11-02): the network sent no no-answer code in 3 minutes |
| Callee not reachable (airplane mode, or off) | `missed_calls` INVITE **408 Request Timeout** and **500** ("Server error on LIR select next S-CSCF") in the same second, 3 s after the call was made |

### Proposal for `end_reason` (the values are PRD decision 8, still open; the network lead and the project lead decide)

| `end_reason` | When |
| ------------ | ---- |
| `completed` | the callid has an `acc` INVITE 200 |
| `cancelled` | no 200 and a `missed_calls` 487 |
| `declined` | no 200 and a 603 (a phone may send 486 instead, which then reads as `not_answered`) |
| `not_answered` | no 200 and a 486 or 600: busy, ringing out and some declines look the same |
| `unavailable` | no 200 and a 408, 500, 404 or 480 (480 is "temporarily unavailable": the callee cannot be reached) |
| `failed` | any other `missed_calls` code |

This replaces `busy`, `no_answer` and `error` from section 6: the first two could never be told apart, and no row exists for
`error`. Take the rule in this order, because the two rows of one failed call can carry different codes. Caution: a 500
from the HSS lookup is also what a fault on our own HSS would produce, so `unavailable` can hide a network fault.
A phone decides how it declines (603 or 486), so busy and declined cannot be separated for every phone. The ring time of
any failed call is `time - start_ts`, so the product can tell a quick refusal from a long unanswered ring if it needs to
(for example, a 487 after 180 s is a caller who gave up on an unanswered call). PRD decision 8.

### Building one `CallRecord` from the rows

- `call_id`: the Call-ID. `from_msisdn`, `to_msisdn`: see the next point.
- **Number format.** `from_user` came as `234` and ten digits; `to_user` came as dialled, `0` and ten digits. The
  stored form of a line's number is digits only, international, no plus sign (`contracts/openapi.yaml`, voucher
  redeem). The agent turns `0XXXXXXXXXX` into `234XXXXXXXXXX` (built: [deploy/voice](../deploy/voice/README.md)). TODO(network lead): other forms a phone may send
  (`+234…`, `234…`), and what to do with a number that matches no rule (post it as it is, never drop the call).
  This also means section 2's "E.164" should read "digits only, international, no plus sign", to match the lines.
- `answered_at`: the `time` of the INVITE 200, as epoch seconds in UTC; null when there is none.
- `ended_at`: the `time` of the **lowest-`id` BYE** of the callid (the first hang-up). For a call that never connected,
  the `time` of its `missed_calls` row.
- **`started_at`: verified on 2026-11-02 (option a).** `acc` records only the time the *final reply* passed the S-CSCF,
  so the S-CSCF now stores the arrival time of each INVITE in `start_ts` (a variable set when the request arrives,
  written with the row). Every case tried gave a plausible, non-zero value: an answered call's INVITE row showed the ring
  time (6 s and 4 s), a decline 11 s, an unreachable callee 3 s, an unanswered call cancelled by the caller 180 s. Both
  legs of one call carried the same `start_ts`. A BYE row's `start_ts` is the BYE's own arrival. `started_at` is the
  smallest `start_ts` of the callid's INVITE rows (`acc` and `missed_calls`). Nothing here depends on option (b).
- A call with an INVITE 200 and **no BYE** is not posted until a BYE appears. TODO(network lead, RatelMeter owner):
  after how long such a call is reported to operations instead (the contract has no open-ended call).

### Tested in the lab, and what is left

Done on 2026-11-02: the `started_at` change for an answered, a declined, an unanswered and an unreachable call (and a
call cancelled by the caller); the caller-hangs-up case. For the first two answered calls the direction check
(`from_tag` of the BYE against the INVITE's) gave 0 for the callee hanging up (two rows) and 1 for the caller hanging up
(two rows), so the lowest-`id` BYE rule holds.

Still to test before signing:

1. Restart the S-CSCF during a call, hang up, and see whether a BYE row appears (question 7). It drops registrations,
   so do it last.
2. Whether a call to a phone that is registered but has no data connection behaves like the unreachable case.
3. One answered call (2026-10-30 13:25 UTC) has no BYE row at all: hang up and ask again whether that can recur.

## 12. Sign-off

- [ ] @CaptRaven (network lead) — Kamailio side confirmed; questions answered.
- [ ] @capitanaserdel (RatelMeter owner) — agent side confirmed; contract updated.
- [ ] `contracts/openapi.yaml` `end_reason` TODO resolved in the same commit.

Signed: ______________________ (network lead)   Date: __________

Signed: ______________________ (RatelMeter owner) Date: __________