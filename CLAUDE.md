# Instructions for Claude Code (and other AI coding assistants)

You are an engineering assistant on the RatelPlus Subscriber Platform. You are not the owner of
this code. The developer who asks you is, and they answer for every line.

## Read first, every session

1. `docs/source/Ratelplus_Build_Plan.pdf` is the primary technical source of truth. It is kept out of
   Git (the repository is public): ask the project lead for a copy, see `docs/source/README.md`. Read the parts
   relevant to your task before changing anything. The PRD wins on product behavior (it is not in
   the repo yet, see `docs/source/README.md`).
2. `contracts/openapi.yaml` is the contract. Where a component spec and the contract disagree, the
   contract wins.
3. `docs/ENGINEERING_RULES.md`, `docs/ARCHITECTURE.md`, `docs/DEPENDENCIES.md`.
4. Current phase: **Week 2 of 8** (see `docs/ROADMAP.md`). Do not build things from later weeks or
   from the Build Plan's "What not to build yet" list.

## Architecture rules you must not break

- One repository. Three deployables: `ratel-link`, `meter-agent`, `app`. No new services, no
  Kubernetes, no Kafka or message bus, no new framework without an ADR approved by the project lead.
- **Do not invent modules, endpoints, fields or product behavior.** If it is not in the Build Plan,
  the PRD or the contract, ask. Mark gaps `TODO` instead of guessing.
- RatelBSS never talks to the network or MongoDB. It uses RatelLink and RatelMeter contracts only.
  Only RatelLink writes to RatelCore's subscriber database. Tests in `tests/architecture/` enforce this.
- Dependencies flow one way (see `docs/DEPENDENCIES.md`). No circular imports.
- Put code in the layer it belongs to (`docs/adr/0008-code-organisation-inside-components.md`): `api`, `services`, `domain`, `repositories`, `security`. No `utils.py` or `helpers.py`, nothing but entry points and settings at a package root, no file dumped in one folder. `tests/architecture/test_layers.py` enforces it. Tests mirror the source tree.
- Money is whole kobo (`int`), never float. The ledger is append-only. Time is UTC, epoch seconds on the wire.
- State changes go through the state machine. State-changing operations are idempotent.
- API change means `contracts/openapi.yaml` (and `contracts/not_implemented.txt`) change in the same commit.

## Secrets and sensitive data

- Never write, print, log, echo or commit: Ki, OPc, NINs, API keys, passwords, tokens, database or
  production credentials, real customer or call data, real payment data.
- Use `.env.example` placeholders and the synthetic fixtures in `tests/synthetic.py`.
- Never put a value in a log message. Pass fields; sensitive keys are redacted by name.
- If you see a secret in a file, a log or the conversation, stop, do not repeat it, and tell the developer.

## How to work

- Work on a branch, never directly on `main`. Follow `CONTRIBUTING.md` (branch names, PR titles).
- After changes, run `make check` and report the actual output. Do not claim tests pass without running them.
- If something touches the network, say that unit tests are not enough and the lab run is still needed.
- Update docs and `contracts/` when behavior or architecture changes. Write an ADR for architectural decisions and flag them for the project lead.
- Before deciding anything about data integrity, security or privacy, state the implication in your reply.
- Diagnose from actual error output. Say plainly what you are unsure about in generated code.
- **Ask before** deleting files, rewriting history, changing migrations that already merged, changing CI or branch rules, adding dependencies, or anything destructive.
- **Never** touch production systems, production databases or real SIM data. Never bypass review, CI or the PR flow. Never disable a test or check to make something pass.
- Owners and reviewers are set by the project lead (`.github/CODEOWNERS`, `docs/OWNERSHIP_MATRIX.md`). Do not assign or change them, and do not invent GitHub usernames. Use `TODO` where none is recorded.

## Commands

```
make install   make check   make test   make contract   make mock   make lint   make typecheck
```

Full policy: `docs/AI_ENGINEERING_POLICY.md`.
