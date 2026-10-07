"""app: RatelBSS (lines, money), RatelMeter API, and the RatelDesk/RatelPay back end.

One process on bss-app. bss_lines, bss_money and meter_api are modules, not services.
This process never talks to the network directly. It uses RatelLink and RatelMeter contracts only.
"""
