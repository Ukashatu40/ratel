"""bss_money module. Build Plan component specs apply.

Layers (docs/adr/0008): api, services, domain, repositories, models.
The rating function and ledger rules are pure: they go in `domain`. Money is whole kobo.

Built so far (M-15): the wallet, the append-only ledger and the allowance bucket tables, posting
money (`services.post_entry`) and the nightly wallet-versus-ledger check (`check_cli`).
Not built yet: plans and the rating function (M-16), the rating job (M-17), vouchers (M-18), the
payment gateway (M-19), and the API.
"""
