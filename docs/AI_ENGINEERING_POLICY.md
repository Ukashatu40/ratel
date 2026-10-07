# AI engineering policy

**AI is an engineering assistant, not the owner of the code.** The developer who commits it owns it.

## Developer responsibilities

When you use an AI coding assistant, you remain responsible for:

- **Understanding** the generated code. If you cannot explain it, do not merge it.
- **Validating** it against the Build Plan, the contract and the PRD. AI tools invent endpoints, fields and behavior. Check.
- **Testing** it. Run `make check` yourself and read the output. Add tests for failure paths.
- **Reviewing** it before asking a human to. AI-generated code gets exactly the same review standard as hand-written code.
- **Protecting sensitive information** (below).
- **Following the architecture** and the engineering rules. AI suggestions that add services, frameworks or shortcuts around the boundaries are declined.
- **Following security rules.** AI output does not get an exemption.

In a PR you must be able to explain what changed, why, how it works, what you assumed, what could
fail and how it was tested. "The AI wrote it" is not an explanation.

## Never send to an AI tool

- Ki, OPc, or any SIM key material
- NINs or any identity data of real customers
- Real customer records, real call records, real usage tied to a person
- Payment secrets, real card data, voucher PINs
- API keys, tokens, passwords, database credentials, production credentials
- Private infrastructure secrets (keys, VPN configs, host passwords)
- Sensitive production logs (redact first, or do not share)

Use synthetic data (`tests/synthetic.py`). If you pasted something sensitive by accident, tell the
project lead; treat it as leaked and rotate it.

## Rules for assistants working in this repository

Written in [CLAUDE.md](../CLAUDE.md). In short: read the Build Plan first, respect the architecture,
do not invent modules or behavior, do not expose secrets, run tests, update docs, ask before
destructive changes, never touch production, never bypass the workflow.

## What AI may be used for

Drafting boilerplate, tests, documentation, refactors, explanations, reviews as a second pair of
eyes. What it may not do: decide architecture, approve a PR, assign owners, hold credentials, or
run anything against production.

## Review of AI-assisted work

Reviewers do not need to know whether AI was used, and do not lower the bar if it was. If a
reviewer asks the author to explain a section and the author cannot, the PR goes back.
Critical areas (RatelLink, RatelBSS: money) get the two-reviewer rule regardless of how the code was written.

## Agent tool permissions

Assistants run with the developer's local permissions, on a branch, against local or test
resources only. They are never given production credentials, lab write credentials without the
developer present, or the ability to merge.
