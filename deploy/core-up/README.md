# deploy/core-up

RatelCore user plane host. Runs the **meter_agent** in data mode, and the small nftables table
that counts bytes per phone address for it.

**Status: not yet installed on core-up.** The counting rules were proven there on 2026-10-20 (the
kernel accepted them, and 100 test packets counted exactly 102800 bytes each way), but the agent has
never run on the host. The first install is the first real test: write down any difference from
these steps in the PR that fixes the files.

## What is here

| File | Purpose |
| ---- | ------- |
| `ratel-meter.nft` | The counting table: one set per direction, an element counter per address. Counts only, never drops or changes a packet |
| `ratel-meter-nft.service` | Loads that table at boot and removes it on stop (runs as root, does only that) |
| `ratel-meter.service` | The agent. Runs as the unprivileged user `ratelmeter` with one capability, `CAP_NET_ADMIN`, so it can read the table |
| `ratel-meter.env.example` | The agent's settings, with placeholders |

## Installation

1. Create the system user and group:
   ```bash
   sudo useradd -r -s /usr/sbin/nologin ratelmeter
   ```

2. Create the directories with restricted permissions:
   ```bash
   sudo mkdir -p /opt/ratel-meter/current /etc/ratel-meter /var/spool/ratel-meter
   sudo chown -R ratelmeter:ratelmeter /opt/ratel-meter /var/spool/ratel-meter
   sudo chown root:ratelmeter /etc/ratel-meter && sudo chmod 0750 /etc/ratel-meter
   sudo chmod 0700 /var/spool/ratel-meter
   ```

3. Deploy code and dependencies into `/opt/ratel-meter/current` with a Python 3.12 venv.

4. Install the counting table and **check it before loading it** (a dry run, nothing is applied):
   ```bash
   sudo cp deploy/core-up/ratel-meter.nft /etc/ratel-meter/ratel-meter.nft
   sudo nft -c -f /etc/ratel-meter/ratel-meter.nft && echo "syntax accepted"
   ```

5. Install the settings:
   ```bash
   sudo cp deploy/core-up/ratel-meter.env.example /etc/ratel-meter/ratel-meter.env
   sudo chmod 0600 /etc/ratel-meter/ratel-meter.env
   sudo chown ratelmeter:ratelmeter /etc/ratel-meter/ratel-meter.env
   # Edit it: put the two real keys in. Never paste a key into a ticket or chat.
   ```

6. Install the units and check them with the host's own systemd:
   ```bash
   sudo cp deploy/core-up/ratel-meter-nft.service deploy/core-up/ratel-meter.service /etc/systemd/system/
   sudo systemctl daemon-reload
   systemd-analyze verify /etc/systemd/system/ratel-meter-nft.service /etc/systemd/system/ratel-meter.service
   ```
   `systemd-analyze verify` must print nothing about these two files.

7. Load the counting table, then check it counts nothing wrong before starting the agent:
   ```bash
   sudo systemctl enable --now ratel-meter-nft.service
   sudo nft list table inet ratel_meter          # the table and its two empty sets
   ```

8. Start the agent:
   ```bash
   sudo systemctl enable --now ratel-meter.service
   ```

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
