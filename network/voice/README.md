# RatelVoice configuration

Owned by the **Network team**. Configuration, not application code: Kamailio P-CSCF, I-CSCF and
S-CSCF, rtpengine, IMS DNS and MySQL on the `voice` VM, on the same LAN as core-cp with no NAT
between them.

The configuration lives here so every change is reviewed (one reviewer) and can be rolled back.
Reference starting point per the Build Plan: the `docker_open5gs` project's Kamailio, rtpengine and
DNS configuration (not its Open5GS). IMS domain: `ims.mnc000.mcc621.3gppnetwork.org`.

No secrets in this directory.

## What is here

| Path | What |
| ---- | ---- |
| `scscf-acc/` | The S-CSCF's **call records** for RatelMeter's call agent: `acc` writing finished calls to MySQL, with the numbers and the request's arrival time. `acc-columns.sql` (the three extra columns), `scscf-acc.cfg.snippets` (the four fragments to place in `kamailio_scscf.cfg`), `check-acc.sh` (a read-only check that prints no row). Tested on the lab on 2026-10-30 and 2026-11-02; the agreement with the RatelMeter owner is [docs/call-record-agreement.md](../../docs/call-record-agreement.md) (draft, waiting for sign-off) |
| `pcscf-transport/` | The P-CSCF's **transport choice for phones that register over UDP**. One line disabled so the P-CSCF stops opening its own TCP connection to such a phone. That connection held the address pair the handset needed for its own, which stopped iPhones placing calls at all and stopped them sending a BYE when they ended a call they had received. Applied and verified on the lab on 2026-11-12 |
| `scscf-numbering/` | The S-CSCF's **number normalisation on the originating side**: national `0XXXXXXXXXX` to `234XXXXXXXXXX` (2026-10-11), and the international form of our own IMS block, `+234206473XXXX` to `234206473XXXX` (2026-11-12). A dialled number in any other form is not a known public identity, and the I-CSCF answers `500 Forbidden - HSS responded with unknown Experimental Result` |
| `smsc-numbering/` | The SMSC's **destination rewrite** for the national form, plus the delivery worker's interval and retry count. Without the rewrite a message addressed `0XXXXXXXXXX` is dropped after its retries, because no phone is registered under that form. Applied and verified on 2026-11-11 and 2026-11-12 |
| `stack/` | **The whole configuration as deployed** on the voice VM, mirroring `~/docker_open5gs`: P-CSCF (with `route/` and `sems`), S-CSCF, I-CSCF, SMSC, IMS DNS, rtpengine, the `ratel-ims.yaml` compose file, and `env.example` with placeholder values only. The directories above remain the record of why each change was made and how to roll it back. See [stack/README.md](stack/README.md), including what is deliberately excluded |

## Facts worth knowing before changing any of this

- A line's IMS public identities are derived by the Open5GS HSS from the subscriber record's
  `msisdn` field, as `sip:<msisdn>@<ims domain>` and `tel:<msisdn>`, with no plus sign. The
  subscriber document holds no IMS fields, so there is nothing to provision per line and no IMS
  entry to add when a line is sold. PyHSS runs on the voice VM but is not in the Cx path: the Cx
  peer is the Open5GS HSS on core-cp, confirmed by its own `cx_rx_lir` and `cx_rx_uar` counters.
- Restarting the `scscf` container drops every registration, and the S-CSCF reads a subscriber's
  profile, including the SMS trigger, only on a fresh registration. Re-register the phones after any
  S-CSCF restart or the SMS path will look broken.
- Restarting the `smsc` container empties its message store.
- Two IMS domains are in play. A handset registers under `ims.mnc000.mcc621.3gppnetwork.org`, which
  is the correct form for PLMN 621-00, while this stack's components use `ims.mnc002...`. It works
  because a second DNS zone was added for `mnc000`. Explained in full, with the consequences, in
  [stack/CHANGES-FROM-UPSTREAM.md](stack/CHANGES-FROM-UPSTREAM.md).
- Diameter points at the Open5GS core on core-cp, not at the PyHSS container this stack ships with.
  Six files carry that change. A redeploy from plain upstream would silently use PyHSS and nothing
  would register. Also in [stack/CHANGES-FROM-UPSTREAM.md](stack/CHANGES-FROM-UPSTREAM.md).
- The `scscf` container has produced no script log output since 2026-10-18, cause not established,
  so `xlog` and `xnotice` lines in its configuration run silently. Confirm S-CSCF changes by
  behaviour or by capturing SIP between the components, not by looking for a log line.

TODO: Network team to rehearse a rebuild of the voice VM from `stack/` on a spare host and write the
runbook in `docs/runbooks/`. The configuration is now here, but a recovery that has never been
performed is not a recovery plan.
