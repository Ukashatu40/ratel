# RatelLink: install on core-cp and prove the runbook there
Labels: type:feature, area:ratel-link, area:deployment, priority:p0, risk:critical

**Module:** RatelLink | **Roadmap week:** 2 (gate) | **Owner:** TODO | **Reviewer:** TODO (two required) | **Target:** TODO
**Ready:** no, waits for N3 (MongoDB authentication on, who installs), N9 (Python 3.12 beside 3.10) from the network team
**Source:** Week 2 gate; `deploy/core-cp/README.md`; `docs/runbooks/ratel-link.md`; N2, N3, N9 in `docs/RATELCORE_INTEGRATION_FACTS.md`.

## Objective
RatelLink runs on core-cp as `ratel-link.service` from a release built from `main`, and the runbook has been followed there once, not only in a container.

## Scope
- Python 3.12 installed beside the system Python (not replacing it); release built from `main`; `install-release.sh <tarball> <python3.12>`.
- `admin_cli init-db`, key file created by the service user, caller keys created for `bss-app` and `meter-agent`, the roles file applied for the `ratel_link` MongoDB user.
- `RATEL_LINK_UE_POOL` set to the agreed range (N2); `RATEL_LINK_VOICE_TEMPLATE_FILE` set once the export exists (N1).
- Update "Last verified" in the runbook with the real date and what was run.

## Out of scope
Enabling MongoDB authentication (network team). The offline key backup (M-23). Real SIM keys.

## Depends on
N3, N9, N2, N1. M-23 before any real SIM key is imported.

## Contract impact
None.

## Acceptance criteria
- [ ] Startup log shows none of `key.provider.none`, `startup.indexes.missing`, `startup.checks.failed`, `startup.subscribers.index.missing`
- [ ] `GET /healthz` is ok and one authenticated call from a caller succeeds
- [ ] A release rollback was done once with the commands in `deploy/core-cp/README.md`
- [ ] The key file is owned by the service user, mode 0600, outside any Git checkout
- [ ] Runbook "Last verified" names core-cp and the date; any step that did not work is fixed in the runbook

## Data, security and privacy
No key, caller key or full IMSI in any ticket, chat message, shell history that leaves the host, or log.

## Testing
Lab. Part of lab session 1.
