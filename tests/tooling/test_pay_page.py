"""RatelPay's page: one file within its weight budget, calling only our public paths."""

from __future__ import annotations

import gzip
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/pay/index.html"
CONTRACT = ROOT / "contracts/openapi.yaml"
BUDGET_BYTES = 30 * 1024  # web/pay/README.md: 30 KB transferred, one request


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_page_fits_the_budget_with_and_without_compression() -> None:
    raw = PAGE.read_bytes()
    assert len(raw) <= BUDGET_BYTES, f"{len(raw)} bytes"
    assert len(gzip.compress(raw)) <= BUDGET_BYTES


def test_the_page_makes_no_second_request_to_load() -> None:
    text = _text()
    assert not re.search(r"<script[^>]*\bsrc=", text), "no separate script file"
    assert not re.search(r"<link[^>]*rel=[\"']?stylesheet", text), "no separate stylesheet"
    assert not re.search(r"<(img|iframe|video|audio|source|embed|object)\b", text)
    assert "@import" not in text and "@font-face" not in text
    assert not re.search(r"url\((?!data:)", text), "no file loaded from the stylesheet"
    assert not re.search(r"https?://", text), "no address of any other site in the page"
    assert '<link rel="icon" href="data:,">' in text  # no separate favicon request


def test_the_page_calls_only_public_pay_paths_that_the_contract_defines() -> None:
    text = _text()
    api = re.search(r'var API = "([^"]+)";', text)
    assert api is not None
    suffixes = set(re.findall(r'API \+ "([^"]+)"', text))
    assert suffixes == {"/vouchers/redeem", "/payments", "/payments/"}
    contract_paths = set(re.findall(r"^  (/v1/[^\n:]+):", CONTRACT.read_text(), re.M))
    for suffix in suffixes:
        path = api.group(1) + suffix
        if suffix.endswith("/"):
            path += "{payment_id}"
        assert path in contract_paths, path


def test_the_page_keeps_nothing_about_a_card_a_line_or_a_person() -> None:
    text = _text()
    script = re.search(r"<script>(.*?)</script>", text, re.S)
    assert script is not None
    code = script.group(1)
    assert "localStorage" not in code and "document.cookie" not in code and "indexedDB" not in code
    assert "console." not in code, "nothing is logged, not even in a browser"
    assert 'credentials: "omit"' in code and 'cache: "no-store"' in code
    # The only thing stored is a payment id, in sessionStorage, under one key.
    stored = re.findall(r"sessionStorage\.setItem\(([^,]+),", code)
    assert stored == ["STORE"]
    assert 'autocomplete="off"' in text
    assert not re.search(r"<input[^>]+\b(name|value)=", text), "no input is named or pre-filled"


def test_the_page_is_in_english_zoomable_and_labelled() -> None:
    text = _text()
    assert '<html lang="en">' in text
    assert "user-scalable" not in text and "maximum-scale" not in text
    for field in ("phone", "card", "pin", "amount"):
        assert f'<label for="{field}"' in text or f'for="{field}"' in text, field


def test_the_logic_tests_pass() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; CI has it")  # the check still runs in CI
    result = subprocess.run(  # noqa: S603  (fixed arguments, our own test file)
        [node, "--test", "web/pay/tests/logic.test.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]
