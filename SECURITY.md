# Security policy

This repository handles SIM keys, customer identity data, call records and money. Treat every
security question as important.

## Reporting a vulnerability or a leaked secret

**Do not open a public GitHub issue, pull request, discussion or chat message.**

1. Preferred: use GitHub private vulnerability reporting for this repository (Security tab,
   "Report a vulnerability"). TODO: project lead to enable it, see docs/GITHUB_SETUP.md.
2. Otherwise contact the project lead directly. TODO: add the private contact channel here.

Include what you found, where, and how to reproduce it **with synthetic data only**. Do not include
real keys, NINs, customer data or production logs in the report.

If a secret was committed, pasted or sent anywhere it should not be: tell the project lead
immediately. The secret is treated as compromised and rotated. Removing it from Git history is
not a substitute for rotation.

## What is in scope

RatelLink, the app (RatelBSS, RatelMeter API), RatelDesk, RatelPay, the meter agent, the CI and
deployment files in this repository, and the contracts. RatelCore, RatelVoice and RatelOps are
network-team systems; report issues about them the same way and they will be routed.

## Handling

Acknowledgement target and fix timelines are not defined yet. TODO: project lead to set them.

## For developers

Rules live in [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md) and
[docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md). Review checklist:
[docs/SECURITY_REVIEW_CHECKLIST.md](docs/SECURITY_REVIEW_CHECKLIST.md).
