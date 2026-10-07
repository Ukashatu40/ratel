"""Synthetic fixtures only. Never put real customer data, keys, NINs or payment data in tests.

The sentinels below look like secrets on purpose. conftest.py fails the whole test run if either
value ever shows up in the captured test log (Build Plan: "a test searches every log file after a
full test run and finds no Ki or OPc value").
"""

SENTINEL_KI = "SENTINEL-KI-0123456789ABCDEF-DO-NOT-LOG"
SENTINEL_OPC = "SENTINEL-OPC-FEDCBA9876543210-DO-NOT-LOG"
SENTINELS = (SENTINEL_KI, SENTINEL_OPC)

# Invented values. IMSI example shape comes from the Build Plan's usage example.
SYNTHETIC_IMSI = "621000000000001"
SYNTHETIC_IMSI_2 = "621000000000002"
SYNTHETIC_MSISDN = "2340000000001"


def find_sentinels(text: str) -> list[str]:
    return [s for s in SENTINELS if s in text]
