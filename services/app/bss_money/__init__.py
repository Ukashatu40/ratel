"""bss_money module. Build Plan component specs apply.

Layers (docs/adr/0008, enforced by tests/architecture/test_layers.py):
  domain/        pure rules: ledger entries, plans and bundles, allowance buckets, rating
  services/      use cases: post an entry, check the wallets. They use the repository port only
  repositories/  ports.py (what the services need) and sql.py (PostgreSQL)
  models/        the SQLAlchemy tables, used by the repositories and by Alembic
  check_cli.py   entry point: the nightly wallet-versus-ledger check
Money is whole kobo. Time is UTC.

Built so far: the wallet, the append-only ledger and the allowance bucket tables, posting money
(M-15), and the plan, bundle and rating rules as a pure function (M-16).
Not built yet: the rating job that runs it (M-17), vouchers (M-18), the payment gateway (M-19)
and the API. The actual plans, prices and speeds are TODO(PRD).
"""
