# What differs from upstream, and why

Established on 2026-11-13 by checksumming every file in this tree against
[`herlesupreeth/docker_open5gs`](https://github.com/herlesupreeth/docker_open5gs) and diffing the
ones that did not match. **38 of the 51 comparable files were byte-identical to upstream.** Twelve
differ and one does not exist upstream.

One change was made after that comparison, so eight files no longer match the hashes it produced:
the Kamailio database password is redacted to `KAMAILIO_DB_PASSWORD` in `pcscf/pcscf.cfg`,
`pcscf/pcscf_init.sh`, `scscf/scscf.cfg`, `scscf/scscf_init.sh`, `icscf/icscf.cfg`,
`icscf/icscf_init.sh`, `smsc/smsc.cfg` and `smsc/smsc_init.sh`. Those eight are otherwise unchanged
from the VM and from upstream. [README.md](README.md) explains why, and what a rebuild has to do
about it.

Keep this page accurate when the stack changes. It is the only record of what a plain upstream
deployment would get wrong.

## Baseline

This tree was taken from upstream around **2026-09-05** (nearest upstream commit before the files'
2026-10-08 date: `1f3bcf7`). Upstream HEAD at the time of comparison was `39029be`, 2026-10-31.

## Ratelplus changes

| File | Change | Recorded in |
| ---- | ------ | ----------- |
| `icscf/icscf.xml` | Diameter `Peer` and `DefaultRoute` set to `hss.localdomain`, realm `localdomain`, port 3868, replacing the `IMS_DOMAIN` and `PYHSS_BIND_PORT` placeholders | this page |
| `scscf/scscf.xml` | the same | this page |
| `pcscf/pcscf.xml` | `Peer` and `DefaultRoute` set to `pcrf.localdomain`, realm `localdomain`, port 3868 | this page |
| `icscf/kamailio_icscf.cfg` | `ims_icscf` `cxdx_dest_realm` set to `"localdomain"` instead of `NETWORKNAME` | this page |
| `scscf/kamailio_scscf.cfg` | `ims_auth` and `ims_registrar_scscf` `cxdx_dest_realm` set to `"localdomain"` | this page |
| `pcscf/pcscf.cfg` | the `PCRF_REALM` substitution set to `localdomain` instead of `EPC_DOMAIN` | this page |
| `dns/named.conf` plus the new `dns/ims_zone_mnc000` | a second IMS zone, for `ims.mnc000.mcc621.3gppnetwork.org` | this page |
| `scscf/kamailio_scscf.cfg` | `acc` writing call records to MySQL | [`../scscf-acc/`](../scscf-acc/) |
| `scscf/kamailio_scscf.cfg` | SMS over IMS routing: the terminating test gained `!is_method("MESSAGE")`, and `route[FINAL_ORIG]` passes `INVITE|MESSAGE` into `PSTN_handling` instead of `INVITE` alone | this page |
| `scscf/kamailio_scscf.cfg` | originating number normalisation, national and international | [`../scscf-numbering/`](../scscf-numbering/) |
| `pcscf/kamailio_pcscf.cfg` | `udp_mtu_try_proto` commented out | [`../pcscf-transport/`](../pcscf-transport/) |
| `smsc/kamailio_smsc.cfg` | SMS destination rewrite, worker interval, retry count | [`../smsc-numbering/`](../smsc-numbering/) |
| `ratel-ims.yaml`, `env.example` | ours, no upstream equivalent | [README.md](README.md) |

## The Diameter change is the one that matters most

Six of the files above exist to point Diameter at the **Open5GS core on core-cp** rather than at the
PyHSS container this stack ships with. Cx goes to `hss.localdomain` and Rx to `pcrf.localdomain`,
both on port 3868, in realm `localdomain`, which is Open5GS's own realm.

This is why a line needs no IMS provisioning: the Open5GS HSS derives a subscriber's public
identities from the `msisdn` field of its subscriber record. PyHSS keeps its own `ims_hss_db`, which
holds 2 rows and is not consulted.

**Anyone redeploying from plain upstream gets PyHSS instead, and nothing registers.** The failure
looks like a handset problem, not a configuration one. That is the trap this page exists to prevent.

TODO: Network team to decide whether to stop the PyHSS container, since it is running and unused.

## The two IMS domains, explained

3GPP TS 23.003 builds the home network domain from the PLMN with the MNC padded to three digits. For
PLMN 621-00 that is **`ims.mnc000.mcc621.3gppnetwork.org`**, and that is what a handset derives from
the SIM and uses when it registers.

This stack's `IMS_DOMAIN` resolves to `ims.mnc002...` instead, which is where the P-CSCF's `Path`,
the S-CSCF's `Service-Route` and the identities the HSS returns all live. A `.env.bak-before-mnc002`
file on the VM suggests `MNC` was changed deliberately at some point to produce it.

Registration works anyway because `dns/ims_zone_mnc000` was added so the handset can resolve the
P-CSCF under the domain it asks for, and because matching happens on the identity derived from the
IMSI rather than on the domain. The handset then accepts identities under `mnc002`.

So a handset registers under one domain and is told its own identity lives under another. It works
today. It is still wrong, and it is the kind of mismatch that surfaces later as something
unrelated-looking.

TODO: Network team to decide whether to move `IMS_DOMAIN` to `mnc000` and retire the extra zone. Not
before the demo: the identities, the SMSC rules and the numbering rules all assume the current form.

**Note on `dns/ims_zone_mnc000`:** unlike `dns/ims_zone`, it hardcodes container addresses
(`172.22.0.15`, `.19`, `.20`, `.21`, `.18`, `.33`, `.140`) rather than using the `DNS_IP`,
`PCSCF_IP` placeholders that the init script substitutes. If the compose network addressing changes,
this zone goes stale silently and handsets stop resolving the P-CSCF. Worth converting to
placeholders.

## Differences that are upstream drift, not ours

`pcscf/route/mo.cfg`, `pcscf/route/mt.cfg` and `pcscf/route/register.cfg` differ only because this
tree predates upstream changes made on 2026-10-21. Do not treat these as Ratelplus configuration:

| Upstream commit | What it did | Effect of not having it |
| --------------- | ----------- | ----------------------- |
| `73cba73` | Remove `qosReference` from `MediaComponent` | our files still send `"qosReference": "qosVoNR"` in the policy request |
| `cfac922` | Fix the UE IP used in N5 policy authorization | we have the older behaviour, and some MO/MT log labels are the wrong way round in `mo.cfg` |

TODO: Network team to decide whether to adopt these. They touch the policy path that the dedicated
voice bearer depends on, so this is a lab change with a call test, not a merge.

## Known gap in `ratel-ims.yaml`

It defines `dns`, `mysql`, `rtpengine`, `icscf`, `scscf`, `pcscf` and `smsc`. The `pyhss` container
is **running on the voice VM but is not in this file**, so something else started it. The compose
file alone does not reproduce the running stack.

TODO: Network team to establish what starts `pyhss` and either add it here or stop it.
