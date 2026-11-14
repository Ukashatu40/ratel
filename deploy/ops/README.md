# deploy/ops

The monitoring host and the scripts that build it. RatelOps configuration (dashboards, scrape
config) is in [ops/](../../ops/).

**The host exists.** An Ubuntu 22.04 VM on pve, 2 cores, 4 GB, 32 GB, `onboot` set because pve has
restarted guests unannounced. Its address is in `/etc/ratel-fw/addresses.nft` on each host as `ops`,
not here, because this repository is public.

Deployment is systemd, not Docker Compose. Prometheus and node_exporter come from the upstream
release with their SHA-256 checked against the release's own sums file; Grafana comes from its own
apt repository. Ubuntu's packages for all three are years behind.

| File | What it does | Runs on |
| ---- | ------------ | ------- |
| `install-monitoring.sh` | Prometheus and node_exporter, both on `127.0.0.1` | the ops VM |
| `install-grafana.sh` | Grafana on `127.0.0.1:3000`, with the Prometheus datasource provisioned | the ops VM |
| `install-node-exporter.sh` | node_exporter bound to the host's own address. Takes a binary path, so a core host never needs to reach the internet | core-cp, core-up, bss-app, and the voice VM once it has a firewall |
| `install-dashboards.sh` | the dashboards in `ops/grafana/dashboards/` | the ops VM |

All four are safe to run again.

## Nothing listens on a public address

These hosts are on public addresses. Prometheus, Grafana and the ops VM's own node_exporter listen
on `127.0.0.1` only, and Grafana is reached by a tunnel from your own machine:

```
ssh -N -L 3000:127.0.0.1:3000 <the ops host>      # then http://127.0.0.1:3000
```

The exporters on the other hosts have to be reachable by the ops VM, so they bind to the host's own
address and the host's firewall admits that one source. The rule is in each host's file in
[deploy/firewall/](../firewall/), reviewed like anything else. Install the exporter first and open
the port second, and no unprotected port is ever exposed.

## What is still missing

- **Alertmanager.** Not installed. `ops/README.md` has an open question about which channel alerts
  go to, and an alert daemon with nowhere to send alerts is theatre. The first alert worth writing
  is an eNB going away: `.39` dropped at 02:01 on 2026-11-14 and nothing said so for nineteen hours.
- **The voice VM.** It has no inbound firewall at all, so it has no exporter either. Its ruleset is
  written and waiting in `deploy/firewall/voice.nft`. Deploy that first, in daylight, with the
  handsets in reach, because it is the host carrying every SIP registration.
- **Call records on a dashboard.** They are in `call_record` on bss-app and want a Postgres
  datasource with a read-only user, which means a password, which means its own provisioning file
  and an environment file on the host.
- **A runbook**, in `docs/runbooks/`, once a rebuild of the ops VM has actually been rehearsed.

Rules: secrets live in owner-only environment files on the host, never here. Production changes go
through reviewed commits. Nobody edits production by hand. A bad deploy here must never be able to
take RatelCore down, which is why business, voice and ops each have their own VM.

Owner: Network team.
