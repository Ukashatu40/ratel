# The voice stack configuration as deployed

Owned by the **Network team**. This is the Kamailio IMS configuration running on the `voice` VM, from
the `docker_open5gs` project, with the Ratelplus changes applied. It mirrors `~/docker_open5gs` on
that host, so a file here sits at the same path there.

It exists so the call path is not held in one place. Before this, every Ratelplus change lived only
on the VM, and losing the VM meant losing the demo's voice path with it.

**[CHANGES-FROM-UPSTREAM.md](CHANGES-FROM-UPSTREAM.md) is the page to read first.** It lists every
difference from upstream, which of them are ours, and which are only version drift. Established by
checksum on 2026-11-13, before the password redaction described below: 38 of the 51 comparable files
were byte-identical to upstream, twelve differed, and one is new.

## Why whole files, when `scscf-acc/` uses fragments

The fragment approach was chosen because these files hold the database URL, and that was right about
the URL but only half right about the reason. The addresses in them are placeholders (`PCSCF_IP`,
`SCSCF_IP`, `MYSQL_IP`, `MCC`, `MNC`, `NETWORKNAME` and the rest), substituted from `.env` by each
container's `*_init.sh` at start-up into `/etc/kamailio_*` inside the container. The **password in
those URLs is not a placeholder.** Nothing substitutes it. See the next section.

Whole files are kept here anyway, with that one string redacted, because the alternative is holding
the call path in fragments that cannot be diffed against upstream.

## The one redaction: `KAMAILIO_DB_PASSWORD`

Eight files carry the Kamailio database password as a literal, in eighteen places: the four `*.cfg`
files that build the `DB_URL`, and the four `*_init.sh` scripts that create the MySQL users with it.
Upstream ships a well-known default there and the voice VM still uses it. **In this tree every one of
those eighteen places reads `KAMAILIO_DB_PASSWORD` instead.** So these eight files are byte-identical
to the VM and to upstream apart from that string, and nothing in this directory is a working
credential.

Two consequences, both deliberate:

- A rebuild from this tree must put a real password in all eighteen places, in both the `*.cfg` and
  the matching `*_init.sh`, because the two sides must agree or Kamailio cannot open its database.
  No variable substitution exists for it today.
- The checksums in [CHANGES-FROM-UPSTREAM.md](CHANGES-FROM-UPSTREAM.md) were taken before the
  redaction, so those eight files no longer match the hashes recorded there. Everything else does.

**This is a finding, not just a packaging detail.** The four Kamailio databases on the voice VM are
protected by a password published in the upstream project. MySQL publishes no host port in
`ratel-ims.yaml`, so reaching it means a shell on the voice VM or another container on the
`ratel_ims` bridge, which is why this is not an emergency. Rotating it means editing the `DB_URL` in
four files, changing four MySQL users and restarting the containers, which drops every registration.
That is post-demo work, not pre-freeze work.

TODO: Network team to rotate the Kamailio database password after 26 Nov, and to wire it to a
variable in `.env` at the same time so this redaction is no longer needed.

The sibling directories stay, and they are the more useful half: they carry why each change was made,
how to roll it back, and what was verified when. Read them before editing anything here.

| Directory | Change recorded |
| --------- | --------------- |
| [`../scscf-acc/`](../scscf-acc/) | Call records to MySQL |
| [`../pcscf-transport/`](../pcscf-transport/) | Transport choice for phones registered over UDP |
| [`../scscf-numbering/`](../scscf-numbering/) | Originating number normalisation |
| [`../smsc-numbering/`](../smsc-numbering/) | SMS destination rewrite and delivery timing |

The Diameter peering, the second DNS zone and the SMS over IMS routing have no directory of their
own. They are described in [CHANGES-FROM-UPSTREAM.md](CHANGES-FROM-UPSTREAM.md).

## What is here

| Path | Container, and what it holds |
| ---- | ---------------------------- |
| `pcscf/` | `pcscf`: the main config, `route/` (`mo`, `mt`, `register`, `rtp`, `websocket`, `xmlrpc`), the Diameter Rx config, `tls.cfg`, and the `sems` profiles |
| `scscf/` | `scscf`: the main config, the Diameter Cx config, and the `CxDataType_Rel*.xsd` schemas the config loads |
| `icscf/` | `icscf`: the main config and its Diameter Cx config |
| `smsc/` | `smsc`: the main config and `smsc-create.sql` |
| `dns/` | `dns`: `named.conf` and the zone files, including `ims_zone_mnc000`, which is ours |
| `rtpengine/` | `rtpengine`: its start-up script |
| `ratel-ims.yaml` | the compose file: which containers run, on which addresses, on the `ratel_ims` bridge |
| `env.example` | every variable the stack reads, with placeholder values only |

## What is deliberately not here

- **`.env`.** It holds the real addresses and credentials, and `UE1_KI` and `UE1_OP`, which are SIM
  key material. It never leaves the host. Use `env.example` for the variable names.
- **TLS private keys.** `pcscf/tls.cfg` names a path to one. The key itself stays on the host.
- **The upstream deploy files for stacks we do not run**, such as the 5G, srsLTE and OAI compose
  files that ship with `docker_open5gs`.
- **Container images.** They come from the `docker_open5gs` build, not from here.

## Rebuilding from this

**Not yet a tested procedure.** These are the files, not a rehearsed recovery. Writing and rehearsing
the rebuild is the remaining work, and it belongs in `docs/runbooks/` once it has actually been done
on a spare host. Until then, treat this as the configuration of record and nothing more.

Outline, to be proved rather than trusted: install Docker and the `docker_open5gs` images, place this
tree at `~/docker_open5gs`, write a real `.env` from `env.example`, apply the MySQL schema including
[`../scscf-acc/acc-columns.sql`](../scscf-acc/acc-columns.sql), bring up the containers named in
`ratel-ims.yaml`, then re-register the phones. Note that `ratel-ims.yaml` does not start `pyhss`,
which is running on the live VM, so the running stack and this file do not match.

TODO: Network team to rehearse this on a spare host and write the runbook. Until that happens, the
honest answer to "could we rebuild the voice VM today" is no, only faster than before.
