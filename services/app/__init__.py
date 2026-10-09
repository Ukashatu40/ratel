"""app: RatelBSS (lines, money), RatelMeter API, and the RatelDesk/RatelPay back end.

One process on bss-app. bss_lines, bss_money and meter_api are modules, not services.
This process never talks to the network directly. It uses RatelLink and RatelMeter contracts only.

Inside each module (docs/adr/0008): api, services, domain, repositories, and models for the
SQLAlchemy tables. Start with one file per layer (api.py, services.py, domain.py, repositories.py,
models.py) and make a file into a package of the same name when it passes about 300 lines or holds
two unrelated concerns. Do not create empty layers. Module direction (docs/DEPENDENCIES.md):
bss_money -> bss_lines and meter_api; those two import neither money nor each other.
"""
