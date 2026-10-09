"""RatelLink: provisioning API and the only writer to RatelCore's subscriber database.

Runs on core-cp. Reaches MongoDB on localhost only. Contract 1 in contracts/openapi.yaml.
The contract endpoints are not implemented yet (see contracts/not_implemented.txt).

Layout (docs/adr/0008): entry points and settings at the root, layers in sub-packages.

    main.py, admin_cli.py   entry points: build the app / run the admin commands
    config.py               settings (environment variables)
    api/                    HTTP: routes, request bodies, authentication dependency
    services/               use cases (business logic)
    domain/                 plain data and rules, no I/O
    repositories/           storage ports and their MongoDB implementation
    security/               encryption, key provider, API key format and hashing

Imports flow inward only: api -> services -> (domain, security, repositories.ports).
tests/architecture/test_layers.py enforces it.
"""
