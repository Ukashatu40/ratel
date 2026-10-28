# ADR 0010: Frontend stack for RatelDesk and RatelPay

- **Status:** Proposed (drafted for the project lead; the frontend lead and the two frontend developers should correct it before it is accepted)
- **Date:** 2026-10-23
- **Deciders:** Project lead
- **Related:** Build Plan (RatelDesk, RatelPay); [ARCHITECTURE.md](../ARCHITECTURE.md); `web/desk/`, `web/pay/README.md`; [PRODUCT_RULES.md](../PRODUCT_RULES.md) (TOP-2, TOP-3, ACC-3); issues #62 and #63; [DEPENDENCIES.md](../DEPENDENCIES.md)

## Context

CLAUDE.md says no new framework enters the repository without an ADR the project lead approves. Two
front ends exist and have different needs:

- **RatelDesk** (staff) is served only on the office network and the VPN. [ARCHITECTURE.md](../ARCHITECTURE.md) already says React and TypeScript, from the Build Plan. A scaffold is on `main` (PR #70, the sell wizard) and uses more than that: Vite, Tailwind CSS 4, React Router, TanStack Query, oxlint and a self-hosted Inter font. Those additions were never approved in an ADR.
- **RatelPay** (customers) is the only public page. PRODUCT_RULES TOP-3 requires it to load in under 3 seconds on 3G, "a small page without a heavy framework bundle". `web/pay/README.md` says no build step and no framework, with a page-weight budget of one request and 30 KB, and leaves one point open: the planned separate `css/` and `js/` files cannot meet that budget on the 3G preset.

Both talk only to RatelBSS's own API (M-02, not specified yet), coded first against a mock. Neither may talk to the network, RatelLink or MongoDB.

## Decision

**RatelDesk:** React 19 and TypeScript, built with Vite, styled with Tailwind CSS, routed with React Router, with server data held by TanStack Query, linted with oxlint, as in `web/desk/package.json` today. Versions are pinned by the committed `package-lock.json`. No other UI library, CSS framework or state library is added without a new ADR.

**RatelPay:** no framework and no build step. One file, `index.html`, with its CSS and JavaScript inline, 30 KB or less transferred, one request (option 1 in the RatelPay README). The weaker option (separate files, measured on "Slow 4G") would not meet TOP-3 and is rejected unless the project lead decides to relax the requirement. The frontend lead confirms this.

**Both:** no third-party scripts, analytics, CDNs or web fonts loaded from another site. Fonts are self-hosted in RatelDesk and absent from RatelPay. Money is received as whole kobo integers and formatted for display only; times arrive as UTC epoch seconds and are shown in West Africa Time, in these two applications only.

## Alternatives considered

| Option | Why not (or why it came second) |
| ------ | ------------------------------- |
| One framework for both front ends | A React bundle cannot fit RatelPay's 30 KB budget, so TOP-3 would fail |
| Plain HTML for both | Possible, but RatelDesk has forms, tables, routing and a history tab on every screen (ACC-3). The Build Plan already names React, and the scaffold exists |
| Next.js or another server-rendering framework for RatelDesk | Adds a Node server to operate on bss-app for no stated need. Not in the Build Plan |
| Separate CSS and JS files for RatelPay | Each extra request adds about 2 seconds on the 3G preset (README). Cannot meet TOP-3 |

## Consequences

- Easier: the developers keep working in what they already started, and RatelPay stays small enough to read in one sitting.
- Harder: RatelPay's single file needs discipline (clear sections, a measured page weight in every PR that changes it). RatelDesk's dependency list is long for a demo and each package is something we must keep patched.
- To maintain: the Node dependency audit in CI (it runs once a lockfile exists, and `web/desk` now has one).

## Security implications

- RatelDesk shows personal data (name, phone, KYC status). No third-party code runs in the page. TODO(project lead): staff sign-in is a mock today. The real design (server-side sessions as in DECISIONS_PENDING item 13, and no token in `localStorage`) is a separate decision before any real customer data is shown.
- RatelPay shows nothing personal about a line's owner (TOP-2) and handles a voucher code once, at submit. The code never goes in a URL, a log or the page source. The page sends no API key: the reverse proxy adds it on each exact public path (today only `/v1/pay/vouchers/redeem`) and replaces anything the browser sent (#116). Rate limiting and webhook signature checks are RatelBSS's job.
- Each npm package widens the supply chain. The lockfile is committed and the audit job must stay green.

## Data implications

Neither front end stores business data. Money and time handling follow the rules above. TODO(frontend lead): test tooling for `web/` (there is no test script yet) and the Node version to pin.

## Operational implications

Nothing runs from Node on bss-app. RatelDesk is built on a developer machine or in CI, and its static files are served by the reverse proxy to the VPN only. RatelPay's single file is served by RatelBSS on the public path. `deploy/bss-app/` now holds the reverse proxy template, which adds RatelPay's key (#116). TODO(frontend lead and project lead): confirm how the RatelPay page itself is served (nothing serves it yet) and where RatelDesk's build happens.
