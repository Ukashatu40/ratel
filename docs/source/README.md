# Source documents

| Document | In this repo? | Notes |
| -------- | ------------- | ----- |
| `Ratelplus_Build_Plan.pdf` | **No, on purpose** | Primary technical source of truth. 27 pages, dated Sep 28, 2026. Contains the lab's internal addresses and company plans. |
| Ratel Plus Subscriber Platform PRD | No | Wins over the Build Plan on product behavior. TODO: add the link or say where it lives. The Build Plan cites PRD ids such as CHG-6, VOI-1 to VOI-7, TOP-2, TOP-3, ACC-3, OPS-1, OPS-2. |

## Getting the Build Plan

Ask the project lead. Save your copy as `docs/source/Ratelplus_Build_Plan.pdf` on your machine.
`.gitignore` keeps `docs/source/*.pdf` out of Git, so it cannot be committed by accident. Do not
upload it to issues, pull requests, chat rooms outside the team, or AI tools that are not approved
for it.

## Why it is not here

The repository is public (a free GitHub account only enforces branch rules on public repositories,
see [../GITHUB_SETUP.md](../GITHUB_SETUP.md)). The Build Plan holds internal LAN addresses and
business plans, so it was removed from the working tree on 2026-10-08.

**It is still in the Git history** (the first commits contain it) and may have been read or copied
since it was pushed on 2026-10-07. Treat its contents as exposed. Removing it from history means
rewriting `main` and force pushing, which the branch rules forbid and which the project lead decides
(see [../DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #7). If the repository becomes private
(GitHub Pro or an organization plan), the PDF can be shared through the repository again.
