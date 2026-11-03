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

TODO: Network team to add the rest of the configuration here (P-CSCF, I-CSCF, rtpengine, IMS DNS), without credentials.
