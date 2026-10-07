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
- Hostnames and addresses beyond the lab's `core-cp` and `core-up` are not recorded in this repo until confirmed. TODO: production host details, deployment credentials handling, network-team contact.

## Variables

See `.env.example`. By component:

| Component | Variables |
| --------- | --------- |
| all | `RATEL_ENV`, `LOG_LEVEL` |
| app | `DATABASE_URL`, `REDIS_URL`, `RATEL_LINK_BASE_URL`, `RATEL_LINK_API_KEY` |
| ratel-link | `MONGO_URI` (localhost only), `OPEN5GS_DB_NAME`, `RATEL_LINK_DB_NAME`, `RATEL_LINK_KEY_FILE` |
| meter-agent | `METER_AGENT_MODE`, `METER_API_BASE_URL`, `METER_API_KEY`, `METER_SPOOL_DIR` |
| local containers | `POSTGRES_*`, `REDIS_PASSWORD`, `MONGO_ROOT_*` |

Settings classes (`services/*/config.py`) read the process environment. They do not read `.env`
files themselves; load `.env` with your shell or process manager.
