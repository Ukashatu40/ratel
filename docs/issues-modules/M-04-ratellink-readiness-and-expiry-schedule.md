# RatelLink: readiness check and scheduled key-expiry check
Labels: type:feature, area:ratel-link, priority:p2, risk:critical

**Module:** RatelLink | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO (two required) | **Target:** TODO
**Ready:** yes
**Source:** `docs/runbooks/ratel-link.md` (TODO: readiness check; TODO(owner): who runs `check-expiry` and how it alerts).

## Objective
Someone can tell from outside whether RatelLink can actually work (MongoDB reachable, key readable), and expiring caller keys are logged on a schedule instead of only at start.

## Scope
- A readiness route outside `/v1` (like `/healthz`, not in the contract): ok only when MongoDB answers and the encryption key is loaded; otherwise 503 with no detail about why.
- A systemd timer and service for `admin_cli api-key check-expiry` in `deploy/core-cp/`. How it alerts: TODO(RatelOps), until then it logs `api_key.expiring`.
- Update the runbook table and remove the two TODOs.

## Out of scope
Alertmanager rules (network team, Week 5).

## Depends on
Nothing. Deployment file changes go through the project lead.

## Contract impact
None (operational routes are not in the contract). The route must be on the route-protection allowlist.

## Acceptance criteria
- [ ] Test: readiness is ok with a fake healthy store, 503 with MongoDB down, 503 with no key
- [ ] The response body never contains a path, host, key id or exception text
- [ ] `tests/ratel_link/api/test_route_protection.py` passes with the new route allowlisted
- [ ] `tests/tooling/test_deploy_files.py` passes with the new unit files
- [ ] `make check` is green

## Data, security and privacy
Unauthenticated route: it must reveal nothing. No new MongoDB privilege.

## Testing
Unit, deployment-file tests. Lab: confirm on core-cp during M-03.
