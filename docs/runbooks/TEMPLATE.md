# Runbook: <service name>

Keep it short. The person reading it is tired and the service is down. The Build Plan requires a
short runbook note for every component that runs in production: how to tell it is healthy and what
to do when it is not. Never put secrets, keys or real customer data in a runbook.

- **Last verified:** YYYY-MM-DD by TODO (someone actually followed these steps)
- **Owner:** TODO
- **Runs on:** host (core-cp, core-up, voice, bss-app, ops) and how (systemd unit or Docker Compose service)

## Service and purpose

One sentence: what it does and who depends on it.

## Health checks

- How to tell it is healthy (command, URL, expected output, metric in RatelOps).
- What "slow" or "degraded" looks like.

## Dependencies

What it needs to run (other services, databases, files, clocks), and what breaks if it is down.

## Logs

Where they are, how to read them (`journalctl -u ...`, `docker compose logs ...`), the events that matter. Reminder: logs must not contain keys or personal data; if you see any, report it as a security issue.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| | | |

## Recovery

Ordered steps to restore service. Include restart order if several services are involved.

## Rollback

How to return to the previous version or configuration, and how to tell it worked. Link the deployment procedure.

## Escalation

Who to call next, in what order, and when. TODO: network-team contact, project lead.
