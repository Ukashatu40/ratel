# Environments and configuration

| Environment | Purpose | Data | Secrets | Network access |
| ----------- | ------- | ---- | ------- | -------------- |
| **local** | A developer's machine. | Synthetic only. | Throwaway values in an untracked `.env`. | `compose.dev.yaml` services on 127.0.0.1. RatelLink calls go to the mock (`make mock`). |
| **test** | CI and automated tests. | Synthetic only. | Test-only placeholder keys. | None. No lab, no production. |
| **lab** | Today's core-cp and core-up (and the radio when it joins). | Test SIMs and synthetic customers. | Env files on the lab hosts, owner-only. | Lab network. This is where "touches the network" tests run. |
| **staging / pilot** | Pilot on staff SIMs (Week 7). TODO: decide before week 7 whether the pilot runs on the lab machines or new ones. | Staff lines only. | Env files on the hosts, owner-only. | VPN. |
| **production** | Customer service. | Real customers. | Env files on the hosts, owner-only, **outside Git**. | VPN only, except RatelPay and the payment webhook. |

## Rules

- Production secrets live **outside Git**, in environment files with owner-only permissions on each host. [Build Plan]
- `.env.example` has placeholders only, and documents every variable. Copy it to `.env` for local use. `.env` and friends are git-ignored; CI runs a secret scan.
- You can run everything locally without production credentials. If you cannot, that is a bug.
- `RATEL_ENV` is one of `local`, `test`, `lab`, `staging`, `production`. Code may use it for safety checks (refusing dangerous defaults), never for different business behavior.
- No developer has write access to production databases. [Build Plan]
- Lab and production credentials are never shared in chat, tickets or AI tools.
- Lab host addresses: core-cp `102.214.241.42`, core-up `102.214.241.43`, voice `102.214.241.44`. `bss-app` and `ops` addresses are not yet confirmed. TODO: production host details, deployment credentials handling, network-team contact.

## Variables

See `.env.example`. By component:

| Component | Variables |
| --------- | --------- |
| all | `RATEL_ENV`, `LOG_LEVEL` |
| app | `DATABASE_URL`, `REDIS_URL`, `RATEL_LINK_BASE_URL`, `RATEL_LINK_API_KEY` |
| ratel-link | `MONGO_URI` (localhost only), `OPEN5GS_DB_NAME`, `RATEL_LINK_DB_NAME`, `RATEL_LINK_KEY_FILE`, `RATEL_LINK_KEY_ID`, `RATEL_LINK_UE_POOL`, `RATEL_LINK_API_KEY_MAX_AGE_DAYS`, `RATEL_LINK_API_KEY_ROTATION_OVERLAP_DAYS`, `RATEL_LINK_API_KEY_EXPIRY_WARN_DAYS` |
| meter-agent | `METER_AGENT_MODE`, `METER_API_BASE_URL`, `METER_API_KEY`, `METER_SPOOL_DIR`, `METER_AGENT_RATEL_LINK_API_KEY` |
| local containers | `POSTGRES_*`, `REDIS_PASSWORD`, `MONGO_ROOT_*` |

### RatelLink security settings

Decisions: [ADR 0006](adr/0006-ki-opc-encryption-at-rest.md) (encryption) and
[ADR 0007](adr/0007-api-key-verification-and-rotation.md) (API keys).

| Variable | Default | Rule |
| -------- | ------- | ---- |
| `RATEL_LINK_KEY_FILE` | none | Path to a file holding base64 of 32 random bytes. Required outside `local` and `test`; without a usable file RatelLink does not start. Must be a regular file owned by the service user with no group or other permissions. The key itself is never in an environment variable or in Git. |
| `RATEL_LINK_KEY_ID` | `1` | Id stored in each encrypted record, so a later key can be told apart. 1 to 32 characters: lowercase letters, digits, `.`, `_`, `-`. |
| `RATEL_LINK_UE_POOL` | `10.45.0.0/16` | The pool of fixed IPv4 addresses given to lines at activation (Build Plan). A private IPv4 network of at least 4 addresses. The network and broadcast addresses and the first host are never given out. TODO(network team): confirm which addresses in the lab pool are already taken. |
| `RATEL_LINK_API_KEY_MAX_AGE_DAYS` | `90` | Lifetime of each API key. 1 to 90. Values above 90 are rejected (Build Plan: rotated every 90 days). |
| `RATEL_LINK_API_KEY_ROTATION_OVERLAP_DAYS` | `7` | How long the old key keeps working after `rotate`. 1 to 30, and not longer than the key lifetime. |
| `RATEL_LINK_API_KEY_EXPIRY_WARN_DAYS` | `14` | `api_key.expiring` is logged for keys this close to expiry. 1 to 90. |

Callers present their key as `Authorization: Bearer <key>`. The env vars `RATEL_LINK_API_KEY`
(RatelBSS) and `METER_AGENT_RATEL_LINK_API_KEY` (the RatelMeter agent, which calls
`GET /v1/assignments`) hold the bare key value, `rlk_<api_key_id>.<secret>`. Each calling system has
its own key. The overlap and warning defaults are proposals for the project lead to confirm.

Settings classes (`services/*/config.py`) read the process environment. They do not read `.env`
files themselves; load `.env` with your shell or process manager.
