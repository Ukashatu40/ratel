"""API key format, generation and hashing."""

import hashlib
import re

from ratel_link.security.api_key_tokens import generate_token, hash_secret
from tests.synthetic import SENTINEL_API_SECRET


def test_token_format_and_entropy() -> None:
    pattern = re.compile(r"^rlk_bss-app\.[A-Za-z0-9_-]{43}$")
    tokens = [generate_token("bss-app") for _ in range(2000)]
    assert all(pattern.match(t) for t, _ in tokens)
    assert len({t for t, _ in tokens}) == 2000  # no repeats
    assert len({t.split(".")[1] for t, _ in tokens}) == 2000
    # 43 url-safe characters is 256 bits. Every character class shows up, so it is not a stub.
    alphabet = set("".join(t.split(".")[1] for t, _ in tokens))
    assert len(alphabet) > 60


def test_hash_is_sha256_hex_of_the_secret_with_a_domain_prefix() -> None:
    h = hash_secret(SENTINEL_API_SECRET)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == hash_secret(SENTINEL_API_SECRET)
    assert h != hash_secret(SENTINEL_API_SECRET + "x")
    assert h != hashlib.sha256(SENTINEL_API_SECRET.encode()).hexdigest()  # domain separated
