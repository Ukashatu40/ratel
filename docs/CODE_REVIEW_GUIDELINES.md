# Code review guidelines

## Who reviews

- One reviewer for most changes (including RatelVoice configuration).
- **Two reviewers** for RatelLink (keys) and RatelBSS: money. The `critical-review-gate` check enforces two distinct approvals on the latest commit. `.github/critical-reviewers.txt` names the project lead (@Ukashatu40) and the independent reviewer (@CaptRaven) as required approvers. When the lead is the author, @CaptRaven plus one more person, normally @capitanaserdel.
- Authors do not approve their own PRs. New pushes dismiss earlier approvals.
- Reviewer assignments for workstreams are in [OWNERSHIP_MATRIX.md](OWNERSHIP_MATRIX.md) and `.github/CODEOWNERS`. A junior or intern is never the only reviewer of a path.

## What reviewers evaluate

| Area | Questions |
| ---- | --------- |
| Correctness | Does it do what the issue and Build Plan say? What about empty, duplicate, out-of-order and failing inputs? |
| Maintainability | Could a teammate change this at 2am? Is it simpler than the alternatives? |
| Data integrity | State machine respected? Idempotent? Replay safe? Kobo ints? UTC? Constraints in the database? |
| Security | Secrets, authentication, authorization, input validation, injection, error leakage. |
| Privacy | What personal data is read, stored, logged or exposed? Could it be less? |
| Testing | Do tests prove the behavior, including failure paths? Would they fail if the code were wrong? |
| Performance (where relevant) | Hot paths: rating loop, agent intervals, list endpoints capped at 5,000. |
| API consistency | Matches `openapi.yaml`? Error shape, status codes, idempotency header? |
| Architecture | Dependency direction, boundaries, no new services or frameworks. |
| Error handling | Fails loudly and safely? No swallowed exceptions? No sensitive values in errors? |
| Observability | Structured log events for meaningful changes, no sensitive fields, health checks. |
| Operational safety | Config, restart, rollback, migration order, runbook. |

## Critical changes: verify the invariants explicitly

For RatelLink and RatelBSS: money, the reviewer writes in the review which invariants they checked:

- Ki/OPc: not logged, not returned, not sent to RatelBSS, encrypted at rest, key outside the database. No default or fallback key; startup fails closed without a valid key file outside `local`/`test`; no secret in any exception, repr or error response. ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md))
- API keys: only a hash is stored; one generic 401 for every failure; every `/v1` route requires a key (route-protection test green); 90-day ceiling holds; the key is never logged and audit entries cite `api_key_id` only. ([ADR 0007](adr/0007-api-key-verification-and-rotation.md))
- RatelLink is the only writer to RatelCore's subscriber database; documents come from the template.
- Every call is idempotent; activating an active line with the same settings changes nothing.
- Audit log entry written with the calling key id, and never contains Ki or OPc.
- Money is integer kobo; ledger append-only; wallet balance equals the sum of entries.
- Webhook: signature verified, provider re-queried, `provider_ref` unique, replay credits once.
- Voucher: PIN hashed, attempt limit enforced, redemption credits once.
- Rating marks records rated in the same transaction as the deduction.
- State changes only through the state machine; every transition not in the table is refused.

## How to review

- Read the issue and the PR description first. Check the diff against the acceptance criteria.
- Run it if you can. Ask for a lab run when the network is touched.
- Be specific and kind. Say what, why, and a suggested fix. Separate blockers from suggestions.
- Do not approve what you do not understand. Ask.
- Resolve conversations before merge; unresolved ones block it.

## Authors

Keep the PR small. Explain intent. Respond to every comment. Do not push unrelated changes after review.
Own the result: you can explain what changed, why, how it works, assumptions, what could fail and how it was tested.
