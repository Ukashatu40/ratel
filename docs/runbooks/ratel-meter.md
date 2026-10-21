# Runbook: RatelMeter Agent (core-up)

Keep it short. The person reading it is tired and the service is down. Never put a key, a token or
real customer data in a ticket, a chat message or this file. If you see one in a log, stop and tell
the project lead.

- **Last verified:** 2026-10-20 by @Ukashatu40 (verified in local test harness)
- **Owner:** @Ukashatu40 (RatelMeter owner)
- **Runs on:** core-up, as the systemd unit `ratel-meter.service` (files and install steps in `deploy/core-up/`)

## Service and purpose

The RatelMeter data agent reads per-line byte counters every 300 seconds on core-up's `ogstun`
interface, maps IP addresses to IMSIs via RatelLink, and posts usage batches to the RatelMeter API.

## Health checks

- Status check: `systemctl status ratel-meter.service` (active and running).
- Recent activity: check journal logs `journalctl -u ratel-meter.service -n 50 --no-pager`. Look for:
  - `meter.agent.started`: service loop initialized.
  - `meter.assignments.refreshed`: address-to-IMSI mappings successfully loaded from RatelLink.
  - `meter.poster.success`: batch acknowledged by RatelMeter API.
- Degraded / offline:
  - `meter.assignments.refresh_failed` or `meter.assignments.error`: RatelLink unreachable; raw readings spooled.
  - `meter.poster.rejected` or `meter.poster.error`: RatelMeter API unreachable; usage batches spooled to `/var/spool/ratel-meter`.

## Dependencies

- **RatelLink (`GET /v1/assignments`):** needed to map UE IP addresses to IMSIs. If down, agent spools raw readings without loss.
- **RatelMeter API (`POST /v1/usage`):** accepts usage batches. If down, batches spool to disk and replay automatically in chronological order once restored.
- **NTP / system clock:** must be synchronized (intervals are clock-aligned in UTC).
- **Spool directory (`/var/spool/ratel-meter`):** must be readable/writable by `ratelmeter` (mode 0700).

## Logs

JSON on stdout (`journalctl -u ratel-meter.service`). Key events:

| Event | What it tells you |
| ----- | ----------------- |
| `meter.agent.started` | Loop running with the configured interval. |
| `meter.counters.read` | Counters successfully gathered from the snapshot/interface. |
| `meter.assignments.refreshed` | Address mappings updated from RatelLink. |
| `meter.poster.success` | Usage batch acknowledged by RatelMeter API. |
| `meter.assignments.refresh_failed` | RatelLink returned non-200. Check RatelLink service on core-cp. |
| `meter.poster.rejected` | RatelMeter API rejected batch. Check API token and status. |
| `meter.spool.replayed` | Pending spooled files delivered to the API. |

Logs must never contain tokens, keys, IMSIs or UE IP addresses.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| `PermissionError: /var/spool/ratel-meter` | Incorrect directory owner or permissions | Run `sudo chown -R ratelmeter:ratelmeter /var/spool/ratel-meter && sudo chmod 0700 /var/spool/ratel-meter` |
| `meter.assignments.refresh_failed (401)` | Expired or incorrect `METER_AGENT_RATEL_LINK_API_KEY` | Generate new API key using RatelLink admin CLI and update `/etc/ratel-meter/ratel-meter.env` |
| `meter.poster.rejected (401)` | Invalid `METER_AGENT_API_KEY` | Update `/etc/ratel-meter/ratel-meter.env` with correct key |
| Spool files accumulating in `/var/spool/ratel-meter` | RatelMeter API is unreachable | Verify network connectivity to `METER_AGENT_METER_API_BASE_URL` |
| Service crash loops on start | Invalid snapshot format or missing environment file | Check `journalctl -u ratel-meter.service -e` and verify `/etc/ratel-meter/ratel-meter.env` exists |

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

1. RatelMeter owner: @Ukashatu40
2. Network team: core-up access and interface counters
3. Project lead
