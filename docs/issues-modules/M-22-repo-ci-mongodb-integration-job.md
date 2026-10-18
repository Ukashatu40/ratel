# Repository: run the MongoDB integration tests in CI
Labels: type:infrastructure, area:repository, priority:p2, risk:high

**Module:** Repository, CI and docs | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** yes, but changing CI is the project lead's decision before work starts
**Source:** `docs/TESTING_STRATEGY.md` (TODO: a MongoDB service container job); the integration and fuzz tests are skipped locally and in CI today.

## Objective
Tests marked `integration` (RatelLink repositories, the process and database acceptance tests, Schemathesis fuzz) run in CI against a real MongoDB.

## Scope
A service container for MongoDB in the workflow; set `RATEL_TEST_MONGO_URI`; keep the job required only after it is stable. Consider PostgreSQL too once M-11 exists.

## Out of scope
Changing branch rules or the review gate.

## Depends on
The project lead approving the workflow change.

## Contract impact
None.

## Acceptance criteria
- [ ] The integration job runs and passes on a PR
- [ ] Breaking a repository test on purpose makes it fail (shown once, then reverted)
- [ ] No credential in the workflow file

## Data, security and privacy
Synthetic data only.

## Testing
The workflow itself.
