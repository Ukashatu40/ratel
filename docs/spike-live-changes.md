# Spike: live changes (W2-06), written from the Open5GS source

**Status:** DRAFT for the network lead and the project lead. Written 2026-10-16 from reading the
Open5GS v2.8.0 source (the `v2.8.0` tag on GitHub). **Nothing here was measured on the lab.** The
lab runs a patched HSS build (a `2.8.0` source with a fix applied), so every answer below must be
checked against the build that is actually installed. Each claim says how to check it.

Question owner: [W2-06](issues-week2/W2-06-spike-live-changes.md). Risk: R-05 in
[RISK_REGISTER.md](RISK_REGISTER.md). Facts the network team gave:
[RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md), item N5.

## The short answer

1. **A live change can be forced, but not by pushing a new speed.** The HSS can tell the MME about
   a changed document, and can make the MME **detach one phone**, which then attaches again and
   picks up its new record. A new speed pushed into a *running* session is not in the source.
2. The route is: MongoDB as a **replica set** (even a single node), the HSS setting
   `use_mongodb_change_stream` turned on, and RatelLink setting one boolean field on the
   subscriber document. The RatelLink side is small. The risk is on the core host.
3. **Recommendation (for the network lead and project lead to confirm or reject):** plan Week 5
   as *"detach and re-attach"*, conditional on a lab test of the sequence below passing within
   the 60 second target. If the test fails, the fallback stays as it is today: changes apply at the
   phone's next attach.

## Q1. Does the HSS tell the MME when a subscriber document changes?

**Yes, in the source, when change streams are on.** `src/hss/hss-context.c`:

- `hss_db_poll_change_stream()` reads a MongoDB change stream. The config key is
  `use_mongodb_change_stream` under `hss`. The code does not set a default, so it is **off** unless
  written, and it is forced off if the MongoDB C driver is older than 1.9.0.
- `hss_handle_change_event()` looks at the changed field names:
  - a change under `ambr`, `slice`, `subscriber_status`, `operator_determined_barring`,
    `network_access_mode`, `access_restriction_data` or `subscribed_rau_tau_timer` sends an
    **Insert-Subscriber-Data-Request** (IDR) to the MME (`hss_s6a_send_idr`). The changed value
    is not examined.
  - the boolean field **`request_cancel_location`** set to `true` sends a **Cancel-Location-Request**
    (CLR, `hss_s6a_send_clr`, type subscription withdrawal). If both are in one change, only the
    CLR is sent.
- Change streams need MongoDB to run as a **replica set**. A single-node replica set is enough in
  principle. That is what the integration guide means by "needs a replica set, not running".

**What the MME does with an IDR** (`src/mme/mme-s6a-handler.c`, `mme_s6a_handle_idr`): it copies
the new AMBR and rebuilds the session list *inside its own record of the phone*. The handler
sends no S1AP, GTP or NAS message. So an IDR alone does **not** change a running data session.
Open point: it calls `mme_session_remove_all()`, whose effect on an attached phone we have not
read. Test it before relying on IDR for anything.

Check on the lab: set `use_mongodb_change_stream` in the HSS config of the installed build, change
`ambr` of a test line, and read the HSS and MME logs for an IDR.

## Q2. Can the PCRF push a lower speed to a live session over Gx?

**Not from a database change.** `src/pcrf/pcrf-gx-path.c`:

- `pcrf_gx_send_rar()` sends a Re-Auth-Request only when an **Rx** request arrives (media rules
  installed or removed). It carries per-rule QoS, not the session AMBR.
- The PCRF reads the subscriber's data only when a Gx Credit-Control-Request arrives (a new
  session). Nothing watches the database.

So pushing a new speed into a live session means **new code in the PCRF** (watch the change, send
a RAR with QoS information), in a patched C build that the network team would have to maintain. It
is not small, and the Build Plan says guessing means writing it twice. **Not recommended.**

## Q3. Can one IMSI be detached so the phone re-attaches with its new record?

**Yes, in the source.** Setting `request_cancel_location` to `true` on that subscriber document
makes the HSS send a CLR with *subscription withdrawal*. In `mme_s6a_handle_clr` the MME then:

- for a phone that is connected: sends a **NAS Detach Request** (`nas_eps_send_detach_request`);
- for an idle phone: pages it first (`s1ap_send_paging`), then detaches;
- stores whether the CLR asked for "re-attach required".

When the phone attaches again, the PCRF reads the new document, so the new speed (or the missing
data session) applies. A detach also ends the phone's registration for calls; a normal phone
registers again by itself after it attaches.

Not answered by the source, to measure: whether the phone re-attaches **by itself** or stays
detached until the user acts (this depends on the "re-attach required" flag in the CLR the HSS
builds and on the phone), and how many seconds the whole sequence takes. The target is 60 seconds.

## The sequence to test (needs the lab and one phone)

| Step | Who | Check |
| ---- | --- | ----- |
| 1 | Network team: MongoDB as a single-node replica set; `use_mongodb_change_stream` on in the HSS config; restart both | HSS log shows the change stream started |
| 2 | RatelLink (or a one-off test by hand on a **test** line): `$set` the new `ambr`, then `$set` `request_cancel_location` to `true` | MME log shows a Detach Request for that IMSI |
| 3 | Phone | Re-attaches within 60 seconds, without a person touching it |
| 4 | Phone | New speed in force; calls register again |
| 5 | RatelLink | Sets `request_cancel_location` back so that the next `true` is a *change* (setting a field to the value it already has produces no change event) |

Two sequences need their own test, because a deleted document produces no useful change event:

- **Slow or cut data:** change the document first, then set the flag (above).
- **Deactivate:** if the document is deleted, the HSS may have nothing to read when the event
  arrives, so the CLR may never be sent. Try "set the flag, wait until the MME logs the detach,
  then delete". The race matters, so this is a lab test, not a guess.

## What it would mean for RatelLink (Week 5, if the lab test passes)

- **Small:** after the existing `$set` on `ambr` / `slice`, set and later clear
  `request_cancel_location`. RatelLink already has update rights on `subscribers` (no new
  privilege). Tests: the field is a BSON boolean, it is never left `true`, nothing else in the
  document changes, and a failure to detach does not undo the data change.
- **Needs the network team first:** the field is outside the integration guide's list, and the
  guide says schema changes are agreed with them and versioned through `schema_version`. The
  replica set and the HSS setting are changes on the core host. Neither is a developer change.
- **Contract:** no new field is needed in `openapi.yaml`: callers already ask for the data change.
  Whether the response should say "applied now" or "applies at next attach" is a product call.

## Related finding for the barring spike (W2-05)

In `mme_s6a_handle_ula` and `mme_s6a_handle_idr` the MME does not read `subscriber_status` or the
barring data. The HSS puts them in its answer, so a barred line is *reported* but the MME seems to
ignore it. That agrees with the integration guide ("the MME may not act on it"). If the lab
confirms it, **barring does not work as a deactivate**, and deletion stays as built. The
re-activation question (the lost `security.sqn`) is separate and still needs the lab.

## Wording for customer care until live changes exist

"Changes to your data apply the next time your phone reconnects to the network. Switching
airplane mode on and off applies them at once."

## What was and was not checked

- **Read:** `hss-s6a-path.c`, `hss-context.c`, `pcrf-gx-path.c`, `mme-s6a-handler.c` at tag
  `v2.8.0`, summarised by a tool, not compiled or run.
- **Not read:** `mme_session_remove_all`, `nas_eps_send_detach_request` (to see how the re-attach
  flag is encoded), the `ogs_dbi_*` library, and the patched HSS build the lab runs.
- **Not measured:** everything in the table above.
