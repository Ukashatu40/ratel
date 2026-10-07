# RatelVoice configuration

Owned by the **Network team**. Configuration, not application code: Kamailio P-CSCF, I-CSCF and
S-CSCF, rtpengine, IMS DNS and MySQL on the `voice` VM, on the same LAN as core-cp with no NAT
between them.

The configuration lives here so every change is reviewed (one reviewer) and can be rolled back.
Reference starting point per the Build Plan: the `docker_open5gs` project's Kamailio, rtpengine and
DNS configuration (not its Open5GS). IMS domain: `ims.mnc000.mcc621.3gppnetwork.org`.

No secrets in this directory. TODO: Network team to add configuration here, and agree the call
record fields with the RatelMeter owner (Week 2).
