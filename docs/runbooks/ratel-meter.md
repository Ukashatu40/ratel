# Runbook: RatelMeter Agent (core-up)

Keep it short. The person reading it is tired and the service is down. Never put a key, a token or
real customer data in a ticket, a chat message or this file. If you see one in a log, stop and tell
the project lead.

- **Last verified:** 2026-10-23 (partly). By hand on core-up: the counting table loads and rolls back, the unit
  works, the real `nft -j list table` output parses, and the agent (release installed with
  `install-release.sh`) ran once as `ratelmeter` with only `CAP_NET_ADMIN`, read the table and exited 0.
  TODO: the agent has not run as a service, it cannot reach RatelLink or the usage API yet, and nothing has
  counted real phone traffic. Do not claim more until that is done.
- **Owner:** @capitanaserdel (RatelMeter owner)
- **Runs on:** core-up, as the systemd unit `ratel-meter.service`, with the counting table loaded by
  `ratel-meter-nft.service` (files and install steps in `deploy/core-up/`)

## Service and purpose

The RatelMeter data agent reads per-line byte counters every 300 seconds on core-up's `ogstun`
interface, maps IP addresses to IMSIs via RatelLink, and posts usage batches to the RatelMeter API.

The counters come from an nftables table, `inet ratel_meter`, with one set for upload (by source address)
and one for download (by destination address). The agent runs `nft -j list table inet ratel_meter` itself,
as the unprivileged user `ratelmeter` with one capability (`CAP_NET_ADMIN`). If it cannot read the table
it fails that interval and logs it. It never reports "no usage" for a failure.

## Health checks

- Status check: `systemctl status ratel-meter-nft.service ratel-meter.service` (both active).
- The table exists and is counting: `sudo nft list table inet ratel_meter` (an element appears for each address with traffic).
- Recent activity: check journal logs `journalctl -u ratel-meter.service -n 50 --no-pager`. Look for:
  - `meter.agent.started`: service loop initialized.
  - `meter.assignments.refreshed`: address-to-IMSI mappings successfully loaded from RatelLink.
  - `meter.poster.success`: batch acknowledged by RatelMeter API.
- Degraded / offline:
  - `meter.assignments.refresh_failed` or `meter.assignments.error`: RatelLink unreachable. The raw readings are kept in the spool (files starting `raw-`) and are attributed to lines, then sent, once a refresh works.
  - `meter.poster.rejected` or `meter.poster.error`: RatelMeter API unreachable; usage batches spooled to `/var/spool/ratel-meter`.

## What the meter does not count

- **IPv6.** The counters match IPv4 addresses only, so the internet session must stay IPv4 only. The core was
  changed on 2026-10-22 (SMF, UPF, `ogstun`, and both lab subscribers), and RatelLink writes the internet session
  as type 1. Kernel IPv6 forwarding is also off on core-up (checked 2026-10-22). TODO: confirm on a real phone
  that it attaches IPv4 only (the network lead will confirm when a SIM reattaches). Before anyone re-enables
  IPv6, count it first.
- **Voice and SMS.** The ims APN uses another interface (`ogstun2`) and is not counted here.
- **Traffic on other interfaces**, and anything that does not pass the forward hook.

## Dependencies

- **RatelLink (`GET /v1/assignments`):** needed to map UE IP addresses to IMSIs. If down, agent spools raw readings without loss.
- **RatelMeter API (`POST /v1/usage`):** accepts usage batches. If down, batches spool to disk and replay automatically in chronological order once restored.
- **NTP / system clock:** must be synchronized (intervals are clock-aligned in UTC).
- **Spool directory (`/var/spool/ratel-meter`):** must be readable/writable by `ratelmeter` (mode 0700).
- **The counting table (`ratel-meter-nft.service`):** if it is not loaded the agent has nothing to read.

## Logs

JSON on stdout (`journalctl -u ratel-meter.service`). Key events:

| Event | What it tells you |
| ----- | ----------------- |
| `meter.agent.started` | Loop running with the configured interval. |
| `meter.counters.read` | Counters read from the table (the number of addresses only, never an address). |
| `meter.counters.nft_failed` | `nft` exited with an error (usually the table is not loaded). That interval is skipped. |
| `meter.agent.tick_error` | One interval failed (`error_type` says why). Nothing was posted for it. |
| `meter.assignments.refreshed` | Address mappings updated from RatelLink. |
| `meter.poster.success` | Usage batch acknowledged by RatelMeter API. |
| `meter.assignments.refresh_failed` | RatelLink returned non-200. Check RatelLink service on core-cp. |
| `meter.poster.rejected` | RatelMeter API rejected batch. Check API token and status. |
| `meter.agent.unmapped_usage` | Bytes were counted for addresses that no line owns (`addresses`, `bytes_up`, `bytes_down`; never the addresses). Those bytes are not sent and cannot be recovered. TODO(lab): learn from the lab session how often this happens. A steady stream means the assignments from RatelLink are missing a line. |
| `meter.spool.replayed` | Pending spooled files delivered to the API. |

Logs must never contain tokens, keys, IMSIs or UE IP addresses.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| `PermissionError: /var/spool/ratel-meter` | Incorrect directory owner or permissions | Run `sudo chown -R ratelmeter:ratelmeter /var/spool/ratel-meter && sudo chmod 0700 /var/spool/ratel-meter` |
| `meter.assignments.refresh_failed (401)` | Expired or incorrect `METER_AGENT_RATEL_LINK_API_KEY` | Generate new API key using RatelLink admin CLI and update `/etc/ratel-meter/ratel-meter.env` |
| `raw-*.json` files accumulating in `/var/spool/ratel-meter` | RatelLink is unreachable or rejecting the key, so usage cannot be attributed yet | Fix the cause of `meter.assignments.*` in the journal; the files are sent in order on the next good refresh |
| `meter.poster.rejected (401)` | Invalid `METER_AGENT_API_KEY` | Update `/etc/ratel-meter/ratel-meter.env` with correct key |
| Spool files accumulating in `/var/spool/ratel-meter` | RatelMeter API is unreachable | Verify network connectivity to `METER_AGENT_METER_API_BASE_URL` |
| Service crash loops on start | Missing environment file, or a missing key (the agent has no default keys) | Check `journalctl -u ratel-meter.service -e` and verify `/etc/ratel-meter/ratel-meter.env` exists and holds both keys |
| `meter.counters.nft_failed` on every interval | The counting table is not loaded, or the agent may not read it | `systemctl status ratel-meter-nft.service`; `sudo nft list table inet ratel_meter`; check `CAP_NET_ADMIN` in the unit |
| `meter.agent.tick_error` with `MalformedSnapshotError` | `nft` answered but the output is not what the reader expects (a set is missing, or an element has no counter) | Compare `sudo nft -j list table inet ratel_meter` with `deploy/core-up/ratel-meter.nft`. Do not edit the table by hand |

## Reconciling with the network's counters (M-28, demo act 6)

Our stored bytes against what the network itself counted, per SIM, for a window. It changes nothing.

1. The network team writes what the network counted per IMSI in the window, as `imsi,bytes` lines (a header
   line and `#` comments are fine). Where they read it from is theirs (N7); this takes the file.
2. Pick a window on 300-second boundaries, in Unix epoch seconds: `[from, to)`. Records are whole intervals, so
   a window that cuts one in half will not match.
3. On bss-app, as the service user with the app's settings loaded (see `docs/runbooks/demo-setup.md` for the
   `bss` helper):

   ```bash
   bss app.meter_api.reconcile_cli --from 1793620800 --to 1793624400 --network-totals /tmp/network.csv
   ```

   Exit 0: every SIM is within 1% (`--tolerance-bps 100`). Exit 1: at least one differs, or is on one side
   only; each is listed with the IMSI masked to its last four digits. Exit 2: it could not run (bad file, bad
   window, database). Delete the file afterwards: it holds IMSIs.
4. A difference is for a person to look at. Nothing is corrected or billed from here.

## Recovery

1. Check configuration and permissions:
   ```bash
   sudo systemctl status ratel-meter.service
   ls -la /etc/ratel-meter/ratel-meter.env
   ls -la /var/spool/ratel-meter
   ```
2. Restart service:
   ```bash
   sudo systemctl restart ratel-meter.service
   ```
3. Watch log stream:
   ```bash
   sudo journalctl -u ratel-meter.service -f
   ```

## Rollback

To roll back to a previous version:
1. Stop service: `sudo systemctl stop ratel-meter.service`
2. Point `/opt/ratel-meter/current` symlink to previous release.
3. Start service: `sudo systemctl start ratel-meter.service`

## Escalation

1. RatelMeter owner: @capitanaserdel
2. Network team: core-up access and interface counters
3. Project lead
