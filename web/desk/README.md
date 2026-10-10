# RatelDesk

Staff web app. React and TypeScript. **Not started.**

- Owns the screens and nothing else. Every rule lives in RatelBSS; the screens call its API.
- Served only on the office network and the VPN.
- Every screen that changes data has a history tab (ACC-3).
- Show West Africa Time here; everything below the screen is UTC.
- Develop against a mock of the BSS API. TODO: where the BSS API contract lives (see docs/DECISIONS_PENDING.md).
- First screens are Week 4 in docs/ROADMAP.md.

## Planned structure (docs/adr/0008, for the frontend lead to confirm when scaffolding)

```
src/app/                 providers, routing, app shell
src/features/<feature>/  components/, hooks/, api/, types/   (customers, lines, stock, plans, ...)
src/shared/              UI primitives, API client, utilities
```

A feature does not import another feature. `shared` imports no feature. Screens call the API
client in `shared`; rules stay in RatelBSS.

When `package.json` appears here, CI runs install, lint, typecheck, test and build automatically
(`web` job in `.github/workflows/ci.yml`). Do not add a framework without the project lead's approval.
