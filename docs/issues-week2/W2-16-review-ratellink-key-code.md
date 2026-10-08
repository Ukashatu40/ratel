# Independent review of the merged RatelLink key code (PR #10)
Labels: type:security, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** 2026-10-12 (first pass 2026-10-09; must be done before any real SIM key is imported) | **Owner:** @CaptRaven | **Reviewers:** @capitanaserdel (first pass) + @Ukashatu40 (reads the findings) (two required)
**Source:** Build Plan "Review" rule (two reviewers for RatelLink); docs/CODE_REVIEW_GUIDELINES.md "Critical changes: verify the invariants explicitly"; docs/DECISIONS_PENDING.md #26.

## Objective
Someone other than the author and the two reviewers who approved PR #10 reads the code that encrypts and stores Ki/OPc and authenticates callers, and writes down what they checked and what they found.

## Context
PR #10 was merged on 2026-10-07 with approvals from @capitanaserdel and @Abbalolo. The independent reviewer had not yet been named in `.github/critical-reviewers.txt`, so did not review it. Files have been reorganised by the code organisation PR (ADR 0008). If that PR is not merged yet, the flat names apply.

| Flat name (PR #10) | Where it lives after ADR 0008 |
| ------------------ | ----------------------------- |
| `crypto.py` | `security/crypto.py` |
| `key_provider.py` | `security/key_provider.py` |
| `auth.py` | `security/api_key_tokens.py`, `services/authentication.py`, `services/api_key_admin.py`, `api/dependencies.py` |
| `sim_keys.py` | `services/sim_keys.py` |
| `models.py` | `domain/*.py`, `api/schemas.py` |
| `audit.py` | `domain/audit.py`, `services/audit_log.py` |
| `repositories.py` | `repositories/ports.py`, `repositories/mongo.py` |
| `main.py` | `main.py`, `api/router.py` |

Read ADR 0006 and 0007 first: they say what the code is meant to do and what it admits it does not do.

## Scope
Review against the checklists, and write the result in a comment on this issue:
- The invariants in `docs/CODE_REVIEW_GUIDELINES.md`: Ki/OPc not logged, not returned, not sent to RatelBSS, encrypted at rest with the key outside the database; no default or fallback key; every `/v1` route requires a key; one generic 401; keys hashed; audit entries cite `api_key_id` and never a key.
- `docs/SECURITY_REVIEW_CHECKLIST.md`, part A (source-supported) in full.
- The assumptions listed in DECISIONS_PENDING.md (#12 to #25): confirm or challenge each.
- Try to break it: send a request with no key, a wrong key, a malformed body; read the logs after a test run for any key-shaped value.

## Out of scope
Fixing what is found (each finding becomes its own issue, labelled by risk). The Week 6 full security review.

## Acceptance criteria
- A written review on this issue that names the invariants checked and the files read.
- Every finding is an issue with a risk label, or an explicit "no change, because ...".
- The project lead has read the findings before the first real SIM key is imported.

## Security / privacy requirements
Do not paste a key, a token or any real value into the review. Describe findings by file and line, without exploit detail in a public issue; for anything serious use the private channel in SECURITY.md.

## Testing requirements
Run `make check` and the integration tests (`make up`, then `make test-integration`) on your machine.

## Suggested skill level
Security-minded reader of Python and web APIs. The first pass is also the way to learn the code that @capitanaserdel will approve changes to.
