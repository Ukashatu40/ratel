# Host firewall for core-cp and core-up

Until this existed, neither host filtered inbound traffic: SSH, the radios' S1 port, PFCP and GTP-U were
open to any address that could reach them (R-16). The firewall was also never saved to disk, and the
servers lose power every night, so anything loaded by hand was gone each morning.

Read **Apply** in full before you start. A wrong rule can cut your SSH session off from the host.

## What it does

| Host | Let in | Everything else |
|---|---|---|
| core-cp | SSH (key-only, 10 new connections a minute per address), S1 (SCTP 36412) from the radios, PFCP (UDP 8805 and 8806) from core-up, HTTPS (443) from core-up and bss-app for RatelLink's proxy | dropped |
| core-up | SSH (as above), GTP-U (UDP 2152) from the radios, PFCP (UDP 8805 and 8806) from core-cp | dropped |

Replies to what the host started, loopback and ping are always let in. Only traffic addressed to the host
is filtered. The phones' internet traffic is forwarded through core-up and is not touched, and neither
are the NAT table or the RatelMeter counting table. The firewall is its own table, `inet ratel_fw`.

The files hold no addresses (the repository is public). The addresses live on each host in
`/etc/ratel-fw/addresses.nft`, copied from `addresses.nft.example`.

| File | Goes to |
|---|---|
| `core-cp.nft` or `core-up.nft` | `/etc/ratel-fw/ratel-fw.nft` (the one for that host) |
| `addresses.nft.example` | `/etc/ratel-fw/addresses.nft`, with the real addresses |
| `ratel-fw.service` | `/etc/systemd/system/ratel-fw.service` |

Do **not** use `/etc/nftables.conf` or `nftables.service` for this. The stock file starts with
`flush ruleset`, which would delete the NAT table the phones' internet depends on.

## Apply (one host at a time, core-cp first)

1. **Copy the files** from your machine, then install them on the host:
   ```
   scp deploy/firewall/core-cp.nft deploy/firewall/ratel-fw.service ratelplus-core-cp:/tmp/
   ```
   ```
   sudo install -d -m 0755 /etc/ratel-fw
   sudo install -m 0644 /tmp/core-cp.nft /etc/ratel-fw/ratel-fw.nft
   sudo install -m 0644 /tmp/ratel-fw.service /etc/systemd/system/ratel-fw.service
   ```
2. **Write the addresses** (on core-cp this now includes `bss_app`; the rules name it, and a name that is
   not defined makes the load fail, which leaves the host with no firewall) (real ones, typed on the host; copy the names from `addresses.nft.example`):
   ```
   sudoedit /etc/ratel-fw/addresses.nft
   ```
   `radios` must list every radio. S1 and GTP-U from a radio that is missing are dropped.
3. **Check the syntax**, which applies nothing:
   ```
   sudo nft -c -f /etc/ratel-fw/ratel-fw.nft && echo syntax ok
   ```
4. **Arm the rollback**, then load the rules. If anything goes wrong, the timer removes the firewall
   after ten minutes by itself (typing an SSH passphrase for the test takes minutes, and a shorter
   timer has already expired under the person doing this once):
   ```
   sudo systemd-run --on-active=600 --unit=ratel-fw-rollback /usr/sbin/nft delete table inet ratel_fw
   sudo nft -f /etc/ratel-fw/ratel-fw.nft
   ```
5. **Test with a new SSH connection from a second terminal.** Your current session survives the rules
   whether or not they are right, so it proves nothing. First check the firewall is still loaded, then
   try the new connection. If it connects, cancel the rollback:
   ```
   sudo nft list tables | grep ratel_fw
   sudo systemctl stop ratel-fw-rollback.timer
   ```
   If `ratel_fw` is missing from the list, or the timer is "not loaded", the rollback has already
   run and the firewall is **off**: your test proved nothing. Load it again (step 4) and redo the test
   faster. If the new connection does not connect, do nothing: the rollback runs within ten minutes.
6. **Check the core still works:**
   ```
   sudo ss --sctp -n | head -8
   sudo nft list chain inet ratel_fw input | tail -3
   ```
   On core-cp every radio is still `ESTAB`. The last line is the drop counter. It rises when something
   unlisted knocks, and a rising count right after loading is normal on a host exposed to the internet.
7. **Make it permanent:**
   ```
   sudo systemctl daemon-reload
   sudo systemctl enable --now ratel-fw.service
   systemctl is-active ratel-fw.service
   ```

Repeat on core-up with `core-up.nft`. When both are done, check that a phone can still attach (lab
session) and that core-up's `sudo nft list tables` shows `ratel_fw` next to the NAT table.

## After a power cut

Check `systemctl is-active ratel-fw.service` on both hosts. If `addresses.nft` is missing or has a typo,
the unit fails and the host comes up **without** a firewall (it fails open, so a mistake cannot lock the
team out). `sudo journalctl -u ratel-fw.service` says what is wrong.

## Undo

```
sudo systemctl disable --now ratel-fw.service
```

## What this does not cover

- The voice VM and the bss-app VM have their own rules to write. The voice VM is unchecked.
- SSH is open to any address, key-only and rate limited. Restricting it to a VPN or fixed addresses is
  the next step, once there is one.
- The S1 rule is tested only for syntax in a container; the lab run (a radio attaching through it) is
  still needed. PFCP, SSH, the rate limit and the other tables were exercised in two network
  namespaces on nftables 1.0.2, the version on core-up.
