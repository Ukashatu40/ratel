# Docs: follow the setup guide on a clean machine and fix what is unclear
Labels: type:documentation, area:repository, priority:p2, risk:low, good first issue

**Week:** 2 | **Target date:** 2026-10-14 | **Owner:** @Arfaaah | **Reviewer:** @capitanaserdel (mentor: @capitanaserdel)
**Source:** docs/DEVELOPMENT_GUIDE.md; docs/TEAM_ONBOARDING.md. New people see problems the authors no longer notice.

## Objective
Someone with fresh eyes follows `docs/DEVELOPMENT_GUIDE.md` and `docs/TEAM_ONBOARDING.md` from the top, exactly as written, and fixes every step that is wrong, missing or unclear.

## Scope
- Do the setup on your own machine (a new virtual environment is fine): clone, `make install`, `make check`, run the app locally, run the mock.
- Keep a list of every place you got stuck or had to guess.
- Fix the documents in one pull request (or several small ones). Say what was confusing and why you changed it.
- Collect the same notes from @Abbalolo, @ml-lawarn and @capitanaserdel when they do their own onboarding, and fold them in.

## Out of scope
Changing how the project is set up (that is a proposal to the project lead). Changing code.

## Acceptance criteria
- A second person (@capitanaserdel or @ml-lawarn) follows the improved guide without help and reaches a green `make check`.
- The pull request shows before and after for each fix.
- `python scripts/ci/check_doc_links.py` passes.

## Security / privacy requirements
Never put a real key, a password or a real address in a document. Use placeholders.

## Testing requirements
The check is that the guide works for a person who did not write it.

## Suggested skill level
Careful reading and clear writing. No Python knowledge needed beyond running commands. A good first task and a real contribution.
