# ADR 0008: Code organisation inside each component

- **Status:** Proposed (requested by the project lead; needs the lead's approval and review by the two RatelLink reviewers, because it moves RatelLink's code)
- **Date:** 2026-10-08
- **Deciders:** Project lead
- **Related:** [ADR 0001](0001-repository-layout.md) (what sits where in the repository); [DEPENDENCIES.md](../DEPENDENCIES.md); [ARCHITECTURE.md](../ARCHITECTURE.md); `tests/architecture/test_layers.py`

## Context

[ADR 0001](0001-repository-layout.md) decided the folders between components. It said nothing about the
inside of a component, and the first real code ended up as twelve files in one folder
(`services/ratel_link/`): HTTP, crypto, MongoDB, business rules and a command line tool side by side.
That works for a week and then costs time at every change: nobody can tell where a new endpoint, a
new rule or a new query belongs, and a reviewer cannot tell from the file list what is safe to touch.

The project lead wants each component organised with a pattern that fits its type and size, the way
they organise their own backend projects. Four of the six people have little or no experience of
working in a shared codebase, so the pattern must also be easy to learn and checked by tools, not
only by reviewers.

## Decision

**One vocabulary of layers for the whole repository. Each component uses the layers it needs, and
each layer has an import rule that a test enforces.**

| Layer | Holds | May import | Must not import |
| ----- | ----- | ---------- | --------------- |
| `api` | HTTP: routes, request and response bodies, the authentication dependency | `services`, `domain` | repositories, database drivers |
| `services` | Use cases: combine rules, security primitives and storage to do one thing | `domain`, `security`, repository **ports**, `config` | `api`, MongoDB or SQL code, FastAPI |
| `domain` | Plain data and business rules. No I/O, no clock, no logging | standard library, pydantic | every other layer, FastAPI, drivers, crypto library, `config` |
| `repositories` | Storage. `ports` says what the services need (interfaces); `mongo` (or SQL) implements it | `domain` (and `config` for connections) | `api`, `services`, `security` |
| `security` | Encryption, key provider, API key format and hashing | `domain`, `config` | `api`, `services`, `repositories` |
| entry points | `main.py`, `admin_cli.py`: build the app or run a command, wiring everything together | anything | (nothing) |

`common` and the standard library may be imported anywhere. Imports flow inward:
`api -> services -> domain`. There are no import cycles.

### Where each component stands

| Component | Pattern | Why |
| --------- | ------- | --- |
| **RatelLink** (`services/ratel_link/`) | Full layering, as above. **Built in this change.** | Small but critical: it holds the keys. Storage and key handling must be replaceable (a KMS later) and testable without a database. |
| **`app` modules** (`bss_lines`, `bss_money`, `meter_api`) | Same layer names, lighter. `api`, `services`, `domain`, `repositories`, plus `models` for the SQLAlchemy tables (used only by repositories and Alembic). Start with one file per layer (`api.py`, `services.py`, ...) and turn a file into a package of the same name when it passes about 300 lines or holds two unrelated concerns. Do not create empty layers. | CRUD plus business rules on PostgreSQL. Pure rules (the line state machine, the rating function) go in `domain` so they are unit tested with no database, as the Build Plan asks. `bss_money -> bss_lines`, `meter_api` only, as in [DEPENDENCIES.md](../DEPENDENCIES.md). |
| **`meter_agent`** | A pipeline: `sources/` (read counters, read call records), `domain/` (interval alignment, counter delta and reset, joining call start and end), `spool/` (disk spool and ordered replay), `client/` (post to the RatelMeter API, read RatelLink assignments), `runners/` (the data-mode and call-mode loops), `main.py`, `config.py`. `domain` imports nothing. `runners` may import all. | It is a loop that collects and ships, not an API. The rules the Build Plan cares most about (no lost interval, no double count, counter resets) are pure logic and must be testable alone. |
| **`common`** | Flat, on purpose. A few cross-cutting primitives. No sub-packages. | Both deployables share it, so every file is a coupling point. Add a file only when two deployables need it. |
| **`web/desk`** (React and TypeScript) | By feature: `src/app/` (providers, routing), `src/features/<feature>/{components,hooks,api,types}`, `src/shared/` (UI primitives, API client, utilities). A feature does not import another feature. `shared` imports no feature. | Screens map to features and teams. **Proposal for the frontend lead to confirm when scaffolding.** |
| **`web/pay`** (plain HTML, CSS, JS) | `index.html`, `css/`, `js/` with one module per concern, no build step, and a written page-weight budget. | The 3G rule favours the smallest possible page. **Proposal for the frontend lead to confirm.** |
| **Tests** | Mirror the source tree: `tests/<component>/<layer>/test_<module>.py`. In-memory fakes in `tests/<component>/fakes.py`. Architecture rules in `tests/architecture/`. | A reviewer finds the tests for a file without searching. |

### RatelLink layout (implemented)

```
services/ratel_link/
  main.py              entry point: builds the FastAPI app, startup checks
  admin_cli.py         entry point: init-db, key generate, api-key ...
  config.py            settings
  api/                 dependencies.py (require_api_key, AuthFirstRoute), router.py (new_v1_router),
                       schemas.py (request bodies)
  services/            authentication.py, api_key_admin.py, audit_log.py, sim_keys.py
  domain/              identifiers.py, sim_keys.py, api_keys.py, audit.py
  repositories/        ports.py (interfaces), mongo.py (MongoDB)
  security/            crypto.py, key_provider.py, api_key_tokens.py
```

### Rules for putting code somewhere

1. Ask in this order. Does it speak HTTP? `api`. Does it touch the database or a driver?
   `repositories`. Is it a decision about the business with no I/O? `domain`. Does it combine steps
   or call storage? `services`. Is it cryptography, a key, or a credential format? `security`.
2. The package root holds entry points and settings only. A new file there fails the build.
3. No `utils.py`, `helpers.py`, `misc.py` or `common.py` inside a component. A file is named for
   what it holds (`api_key_tokens.py`), so a dumping ground cannot form.
4. Every package has an `__init__.py` whose docstring says what the layer is for and what it may
   import. A test checks it.
5. A route is added to `api/router.new_v1_router()`, validated with a schema from `api/schemas.py`,
   and calls a service. It contains no business rule and no query.
6. A service receives its dependencies as arguments (a repository port, a key provider, a clock). It
   never creates a database client.

### How it is enforced

`tests/architecture/test_layers.py` reads the source with `ast` and fails on: a layer importing a
layer it may not, a framework or driver in a layer that must not have it, a file at the package
root that is not an entry point or settings, a package without an explanatory docstring, and any
import cycle. Each rule is proven able to fail on a small fake tree. Another component adds a
`Layering` entry when it gets its first layered code.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Keep flat modules | It is what we had. Fine for five files, not for the endpoints coming in W2-01 to W2-03. |
| Package by feature (one folder per endpoint group, each with its own rules and queries) | Good when features are independent. RatelLink's features all share the same security core and the same two stores, so the layers are the real boundary. Features can still become files inside `api/` and `services/`. |
| Full domain-driven design (aggregates, use-case classes, a mediator) | More ceremony than a six-person team with a deadline needs. The four layers are enough to keep rules testable and storage replaceable. |
| A different pattern per component | Harder to learn. One vocabulary means someone who has learned RatelLink can read `bss_lines`. |
| Rules in the review guide only | Four of six people are new to reviews. A failing test teaches faster than a comment. |

## Consequences

- More files and a few more import lines per change. In return a new endpoint, rule or query has an
  obvious place, and a reviewer sees from the path what kind of change it is.
- RatelLink's security-sensitive code is now in `security/` and `services/sim_keys.py`, so it is
  quick to find and review, and `domain` cannot import the crypto library or the database.
- The move changed no behavior. The set of test names is identical before and after (one test was
  renamed because it reads a different file). The module paths in ADR 0006 and 0007 changed; those
  documents are updated, their decisions are not.
- Entry points are unchanged: `ratel_link.main:create_app` for uvicorn and
  `python -m ratel_link.admin_cli` for administration.
- The layer vocabulary has to be taught. The onboarding guide for new developers covers it.
- The `app` and `meter_agent` structures are written down but not yet enforced, because they have
  no code. Their rules are added to `test_layers.py` with their first layered code.

## Security implications

Smaller review surface per change, and the rule that the domain cannot reach the crypto library or
the database makes some mistakes (secrets in domain objects, queries built from request data in a
rule) impossible to merge. No change to secrets handling, access or attack surface.

## Data implications

None. No collection, field, index or migration changes.

## Operational implications

None for deployment. Developers must use the new module paths in imports and in
`monkeypatch` targets.
