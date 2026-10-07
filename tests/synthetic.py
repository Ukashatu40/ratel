"""Synthetic fixtures only. Never put real customer data, keys, NINs or payment data in tests.

The sentinels below look like secrets on purpose. conftest.py fails the whole test run if any
value ever shows up in the captured test log (Build Plan: "a test searches every log file after a
full test run and finds no Ki or OPc value"). An API key reaching the log fails the run too.
"""

SENTINEL_KI = "SENTINEL-KI-0123456789ABCDEF-DO-NOT-LOG"
SENTINEL_OPC = "SENTINEL-OPC-FEDCBA9876543210-DO-NOT-LOG"

# A syntactically valid but obviously fake RatelLink API key: rlk_<api_key_id>.<43-char secret>.
# Built from parts on purpose: the whole token never appears as one literal in the repository, so
# the gitleaks rule for `rlk_` keys needs no allowlist.
SENTINEL_API_KEY_ID = "bss-app"
SENTINEL_API_SECRET = "SENTINEL-API-SECRET-DO-NOT-LOG-0123456789AB"  # 43 characters
SENTINEL_API_KEY = "rlk_" + SENTINEL_API_KEY_ID + "." + SENTINEL_API_SECRET

SENTINELS = (SENTINEL_KI, SENTINEL_OPC, SENTINEL_API_KEY, SENTINEL_API_SECRET)

# Valid-format (32 hex characters) but obviously invented keys, for tests that need a key the
# store will accept. Sequential patterns, not real Ki or OPc.
SYNTHETIC_KI_HEX = "00112233445566778899aabbccddeeff"
SYNTHETIC_OPC_HEX = "ffeeddccbbaa99887766554433221100"

# Invented values. IMSI example shape comes from the Build Plan's usage example.
SYNTHETIC_IMSI = "621000000000001"
SYNTHETIC_IMSI_2 = "621000000000002"
SYNTHETIC_MSISDN = "2340000000001"


def find_sentinels(text: str) -> list[str]:
    return [s for s in SENTINELS if s in text]
