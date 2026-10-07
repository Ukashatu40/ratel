"""RatelLink: provisioning API and the only writer to RatelCore's subscriber database.

Runs on core-cp. Reaches MongoDB on localhost only. Contract 1 in contracts/openapi.yaml.
The contract endpoints are not implemented yet (see contracts/not_implemented.txt). What exists:

- crypto.py, key_provider.py, sim_keys.py: Ki and OPc encrypted at rest (docs/adr/0006).
- auth.py: API-key authentication on every /v1 route, and key administration (docs/adr/0007).
- audit.py: the append-only audit log writer.
- admin_cli.py: init-db, key generate, api-key create|rotate|revoke|disable|list|check-expiry.
"""
