# ADR 0013: Prepaid calls and SMS are authorised by bss-app, not by a Diameter charging server

- **Status:** Proposed (written 2026-11-26 for the project lead to accept or change)
- **Date:** 2026-11-26
- **Deciders:** the project lead
- **Related:** [catalogue.md](../catalogue.md), [customer-sms.md](../customer-sms.md), [ADR 0009](0009-ledger-append-only-in-the-database.md), [ADR 0012](0012-changes-to-one-line-take-turns.md)

## Context

Calls are charged from airtime after they end (`calls_cli`), so a call can run past zero: what
the wallet cannot cover is recorded as unpaid. SMS are free. Decided on 2026-11-26 for launch:

- a call stops when its airtime runs out, and a call from an empty wallet is refused;
- an SMS to another Ratelplus line costs N2 (VAT inclusive, like the call rates), charged before it
  is queued; a text the wallet cannot cover is not sent, and the sender gets an SMS from 555
  saying why; texts to 555 are free;
- texts to other networks are refused, not charged, with an SMS from 555 saying they are not
  available yet (there is no SMS interconnect; they were dropped after the SMSC's retries);
- emergency numbers (112, 199) and the customer care line are never refused or limited;
- when bss-app cannot be reached at call set-up, the call goes through limited to 2 minutes and is
  charged afterwards (an outage of one VM must not silence every phone).

The IMS way is online charging over Diameter Ro: the S-CSCF (Kamailio `ims_charging`) asks an
online charging system (OCS) for units during the call and tears it down when none are granted.

## Decision

bss-app authorises calls and SMS over HTTP, against the ledger it already keeps. No OCS.

**Calls.**
1. On a new outgoing call (initial INVITE from the phone), the P-CSCF asks bss-app, through the
   ussd container on the voice VM, for the call's limit: `POST /v1/pay/calls/authorize` with the
   SIP Call-ID, the caller's network-asserted number and the dialled number.
2. bss-app answers with one of: allowed with no limit (emergency and free numbers, call charging
   off, the caller not a Ratelplus line); allowed for N seconds; refused (line not in service, or
   less than 10 seconds of airtime). For a limit it **reserves** the money for N seconds at the
   call's rate (`call_reservation`), so two calls at once cannot spend the same naira:
   N = what the balance minus other open reservations buys at that rate, at most 3 hours.
3. The P-CSCF sets the call's maximum length to N (`ims_dialog` `timeout_avp`, already loaded)
   and refuses a refused call with `402 Payment Required`. When the limit is reached the dialog
   module ends the call for both sides.
4. When the call ends (BYE through the P-CSCF), it reports the end, and the reservation shrinks to
   the actual cost so the rest of the balance is free again at once. The actual charge still comes
   from the call record (`calls_cli`, every minute), which settles the reservation. A reservation
   nobody settled expires at its limit plus 15 minutes.
5. bss-app not answering within 2 seconds: the P-CSCF allows the call with a 2-minute limit.

**SMS.** The SMSC, before it queues a text from a phone, asks bss-app through the ussd container
(`POST /v1/pay/sms/charge`, keyed by the SMSC's message id, so a retry charges once). bss-app
answers send (charged, or free to 555), refused for balance, or refused as off-net. The price is a
catalogue setting (`sms_onnet_kobo`, default 200) an admin changes in RatelDesk. A text is charged
when accepted, not when delivered (the SMSC does not report delivery).

**Where.** bss-app: the authorisation, reservation and SMS charging rules and their API (voice VM
only, through nginx, payments key added by nginx as for 555). Voice VM: the ussd service forwards
the P-CSCF's and the SMSC's questions to bss-app over the TLS connection it already has, so
Kamailio needs no certificate and talks plain HTTP inside the `ratel_ims` network only.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Diameter Ro with an OCS (Kamailio `ims_charging` plus `ims_ocs`, CGRateS, or one we write) | A new service with its own copy of every balance, kept in step with the ledger; a Diameter stack to run and secure. Standard, and right at a larger scale; too much for launch. Can replace this later behind the same rules. |
| Keep charging after the call, allow debt | Rejected on 2026-11-26: calls must stop at zero. |
| Refuse calls when bss-app is down | Rejected on 2026-11-26: one VM's outage would stop every call. |
| Limit calls at the S-CSCF instead of the P-CSCF | The P-CSCF is where the phone's own requests enter, already loads `ims_dialog` with `timeout_avp` and `http_client`, and sees the network-asserted caller. |

## Consequences

- Calls stop at zero and SMS are charged, with one source of balance: the ledger.
- Call set-up gains one HTTP round trip on the LAN (bss-app answers from PostgreSQL; target under
  200 ms). A bss-app outage limits calls to 2 minutes instead of stopping them; up to 2 minutes per
  call can end up unpaid. Monitored: `calls.authorize_unreachable` alerts.
- The reservation shrinks at hang-up but is settled from the call record, so a call charged later
  than it ended is still charged once (the reference `call:<record>` is unique, as today).
- No announcements yet: a refused call shows the phone's own "call failed". The spoken
  announcements ("insufficient balance", "number not available", "1 minute left", English then
  Hausa) need an rtpengine able to encode AMR and AMR-WB (today it only decodes them; the phones
  offer nothing else) and an AMR-WB licensing answer. That is the next phase.
- A bundle bought from airtime during a call can take money the call has reserved; the call then
  ends with an unpaid remainder, as today. Rare; to close later by making purchases respect open
  reservations.
