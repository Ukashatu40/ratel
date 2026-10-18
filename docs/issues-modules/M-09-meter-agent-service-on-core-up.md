# RatelMeter agent: entry point, settings, systemd unit and runbook for core-up
Labels: type:feature, area:ratel-meter, area:deployment, priority:p1, risk:high

**Module:** RatelMeter agent | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, waits for M-07 and M-08
**Source:** Build Plan, RatelMeter "Done when"; #25; `services/meter_agent/README.md` (planned structure: `main.py`, `config.py`, `runners/`).

## Objective
The data agent runs on core-up as a service that survives a restart, with a runbook page next to RatelLink's.

## Scope
- `main.py` and settings for the data mode; wire reader, cache, poster and spool into the loop in `agent.py`.
- A systemd unit (hardened like RatelLink's), an owner-only settings file template, a README for the host under `deploy/`.
- Runbook: `docs/runbooks/ratel-meter.md` (symptoms, what to check, who to call).
- NTP must be on core-up (network team, Week 3): the intervals depend on the clock.

## Out of scope
Call mode on the voice VM (M-10).

## Depends on
M-07, M-08, M-01. Network team for the user account and permissions on core-up.

## Contract impact
None.

## Acceptance criteria
- [ ] Stopping the agent mid-interval and restarting loses nothing and counts nothing twice (test and lab)
- [ ] With the API offline for an hour then back, every spooled interval arrives in order (test with a fake poster; lab once)
- [ ] The unit starts at boot and restarts on failure
- [ ] Deployment-file tests (no secret, no host address in committed files) pass
- [ ] The runbook was followed on core-up once and "Last verified" says so

## Data, security and privacy
Spool directory is owner-only (see PR for #31). No IMSI in operational logs.

## Testing
Unit, failure-path, lab (lab session 1 section E).
