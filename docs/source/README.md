# Source documents

| Document | In this repo? | Notes |
| -------- | ------------- | ----- |
| `Ratelplus_Build_Plan.pdf` | **No, on purpose** | Primary technical source of truth. 27 pages, dated Sep 28, 2026. Contains the lab's internal addresses and company plans. |
| Ratel Plus Subscriber Platform PRD | No | Wins over the Build Plan on product behavior. **Where it lives is not recorded.** The Build Plan's first page links to it by name, but the PDF export dropped the link (the PDF was printed from a web page; its header says "Sep 28, 2026, @Muhammad"). Ask the Build Plan's author for it, then record the location here. The Build Plan cites PRD ids such as CHG-6, VOI-1 to VOI-7, TOP-2, TOP-3, ACC-3, OPS-1, OPS-2. |

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

## What the PRD must contain (inferred from the Build Plan, to check against the real one)

The Build Plan cites these requirement ids, so the PRD defines at least: **CHG-6** (live changes, P1),
**VOI-1 to VOI-7** (voice, including charging for minutes in VOI-7), **TOP-2** (RatelPay shows nothing
personal about a line's owner), **TOP-3** (RatelPay loads in under 3 seconds on 3G), **ACC-3** (every
screen that changes data has a history tab), **OPS-1 and OPS-2** (monitoring), and "the four
journeys" that RatelDesk and RatelPay must run end to end. Work that depends on the PRD: the RatelDesk
screens and the BSS API behind them (DECISIONS_PENDING.md #4), the customer and KYC fields, and the
exact product rules around plans, bundles and vouchers.
