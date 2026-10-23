# deploy/core-up

RatelCore user plane host. Runs the **meter_agent** in data mode, and the small nftables table
that counts bytes per phone address for it.

**Status (2026-10-23).** The counting table was loaded on core-up and rolled back by hand on 2026-10-22.
The kernel accepted it, `ratel-meter-nft.service` started and stopped it cleanly, and the real
`nft -j list table` output (empty sets, and one element) is the fixture the tests parse. On 2026-10-23
the agent was installed from a release with `install-release.sh`, the table was loaded by its unit, and
one run of the agent as `ratelmeter` (step 7) read the table and exited 0. That run logged
`meter.assignments.error` because nothing on core-up can reach RatelLink yet. **Not done:** the
service is neither started nor enabled; the path from core-up to RatelLink on core-cp does not exist;
the RatelMeter API is not deployed; and no real phone traffic has been counted on `ogstun` (needs a
phone, lab session #52). The counting rules were also proven exactly in a throwaway
namespace test on 2026-10-20 (100 packets of 1028 bytes counted as 102800 bytes each way). The first
full install is the first real test of the rest: write down any difference from these steps.

**IPv6 is not counted.** The table matches IPv4 addresses only, so the internet session must stay IPv4
only. The core was changed to IPv4 only on 2026-10-22 (SMF, UPF, `ogstun`, both lab subscribers) and RatelLink
writes session type 1. Kernel IPv6 forwarding is off too. If IPv6 is ever turned back on, its traffic would pass
unmetered until it is counted. A check on a real phone is still pending.

## What is here

| File | Purpose |
| ---- | ------- |
| `install-release.sh` | Installs a release into its own folder with its own virtualenv and points `current` at it. Never restarts anything |
| `ratel-meter.nft` | The counting table: one set per direction, an element counter per address. Counts only, never drops or changes a packet |
| `ratel-meter-nft.service` | Loads that table at boot and removes it on stop (runs as root, does only that) |
| `ratel-meter.service` | The agent. Runs as the unprivileged user `ratelmeter` with one capability, `CAP_NET_ADMIN`, so it can read the table |
| `ratel-meter.env.example` | The agent's settings, with placeholders |

## Layout on core-up

```
/opt/ratel-meter/releases/<release>/   code and its own virtualenv (owned by root, read-only)
/opt/ratel-meter/current               a link to the active release (the unit runs from here)
/etc/ratel-meter/ratel-meter.env       settings and the two API keys (mode 0600)
/etc/ratel-meter/ratel-meter.nft       the counting table
/var/spool/ratel-meter/                usage waiting to be sent (service user only, mode 0700)
```

## Installation

1. **Python 3.12 must exist on core-up** at `/opt/python-3.12/bin/python3.12`. Ubuntu 22.04 ships 3.10, so
   it is built from the python.org source with `make altinstall` and does not touch the system Python:
   [docs/runbooks/python-3.12-on-ubuntu-22.04.md](../../docs/runbooks/python-3.12-on-ubuntu-22.04.md).
   Installed on core-up on 2026-10-22 (3.12.15).

2. **Build the release on your machine, from a reviewed commit on `main`** (never from a working
   tree), and copy it over with the script and the unit files. The release carries its own
   dependencies as prebuilt Linux wheels (about 3 MB), so installing it needs no internet on core-up:
   ```bash
   git switch main && git pull
   scripts/release/build-meter-release.sh HEAD /tmp     # prints the tarball name and its SHA-256
   REL=ratel-meter-$(git rev-parse --short HEAD)
   scp /tmp/$REL.tar.gz deploy/core-up/install-release.sh deploy/core-up/ratel-meter.nft \
     deploy/core-up/ratel-meter-nft.service deploy/core-up/ratel-meter.service \
     deploy/core-up/ratel-meter.env.example <core-up>:/tmp/
   ```
   The builder refuses a commit that is not on `origin/main`, and builds for Python 3.12 on x86_64
   Linux. On core-up, compare `sha256sum /tmp/$REL.tar.gz` with the value it printed.

3. **Install the release** (creates the user `ratelmeter` and the folders, installs the
   dependencies from `requirements/constraints.txt`, checks the service user can import it):
   ```bash
   cd /tmp && sudo ./install-release.sh $REL.tar.gz /opt/python-3.12/bin/python3.12
   ```
   If it fails, the half-made release is removed and nothing else changes. Run it again after fixing.
   The install downloads packages, so core-up needs working DNS. On 2026-10-23 it failed once with
   `Temporary failure in name resolution` during a site uplink outage; `getent hosts pypi.org` answered
   again later and the same command then succeeded.

4. **Install the counting table, and check it before loading** (a dry run, nothing is applied):
   ```bash
   sudo cp /tmp/ratel-meter.nft /etc/ratel-meter/ratel-meter.nft
   sudo nft -c -f /etc/ratel-meter/ratel-meter.nft && echo "syntax accepted"
   ```

5. **Install the settings.** Put the two real keys in without displaying them in a ticket or chat:
   ```bash
   sudo install -m 0600 -o ratelmeter -g ratelmeter /tmp/ratel-meter.env.example /etc/ratel-meter/ratel-meter.env
   sudo -e /etc/ratel-meter/ratel-meter.env
   ```
   Until the real keys exist, any non-empty placeholder lets the agent start and read its own
   counters, but it cannot reach RatelLink or the usage API.

6. **Install the units and check them with the host's own systemd:**
   ```bash
   sudo cp /tmp/ratel-meter-nft.service /tmp/ratel-meter.service /etc/systemd/system/
   sudo systemctl daemon-reload
   systemd-analyze verify /etc/systemd/system/ratel-meter-nft.service /etc/systemd/system/ratel-meter.service
   ```
   `systemd-analyze verify` must print nothing about these two files. Run it with `sudo`: without it, it prints
   a permission error about `netplan-ovs-cleanup.service`. A line about `RestartMode` in `snapd.service`
   also appears on Ubuntu 22.04 and is not about our files (seen 2026-10-23).

7. **Load the counting table, then run the agent once by hand before starting the service:**
   ```bash
   sudo systemctl start ratel-meter-nft.service
   sudo nft list table inet ratel_meter          # the table and its two empty sets
   sudo systemd-run --wait --pipe -p User=ratelmeter -p EnvironmentFile=/etc/ratel-meter/ratel-meter.env \
     -p AmbientCapabilities=CAP_NET_ADMIN -p CapabilityBoundingSet=CAP_NET_ADMIN \
     -p Environment=PYTHONPATH=/opt/ratel-meter/current/services \
     /opt/ratel-meter/current/venv/bin/python -m meter_agent.main --once
   echo "exit status: $?"
   ```
   Exit status 0 means it read the counters. An error line with `error_type` and status 1 says why not.
   Until RatelLink is reachable, a `meter.assignments.error` line with `ConnectError` and status 0 is the
   expected result (seen 2026-10-23): the counters were read, and any usage is kept in the spool.

8. **Start the agent, and enable both at boot only when you are happy:**
   ```bash
   sudo systemctl start ratel-meter.service
   sudo systemctl enable ratel-meter-nft.service ratel-meter.service
   ```

## Upgrade and rollback

Upgrade: build a new release (step 2), run `install-release.sh` (step 3), then
`sudo systemctl restart ratel-meter.service`. Rollback: point `/opt/ratel-meter/current` at the
previous release in `/opt/ratel-meter/releases/` (`sudo ln -sfn <old release> /opt/ratel-meter/current`)
and restart. Old releases are never deleted by the script.

## Verification

```bash
sudo systemctl status ratel-meter-nft.service ratel-meter.service
sudo journalctl -u ratel-meter.service -f
# The agent can read the table as its own user (this is what it runs):
sudo -u ratelmeter env -i /usr/sbin/nft -j list table inet ratel_meter | head -c 300; echo
```
The last command needs the capability the unit grants, so run under the unit, not as a plain shell, if it
reports "Operation not permitted". `journalctl` must not show `meter.counters.nft_failed`.

Refer to [docs/runbooks/ratel-meter.md](../../docs/runbooks/ratel-meter.md) for diagnostics and troubleshooting.
