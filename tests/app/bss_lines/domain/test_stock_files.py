"""Reading a SIM or number file: what is accepted, and what is refused without echoing a value."""

from __future__ import annotations

import pytest

from app.bss_lines.domain.stock import SimEntry, parse_numbers, parse_sims

ICCID_A, IMSI_A = "8923400000000012345", "621000000000150"
ICCID_B, IMSI_B = "8923400000000012346", "621000000000151"
HEADER = "iccid,imsi,batch\n"


def test_a_sim_file_is_read() -> None:
    entries = parse_sims(f"{HEADER}{ICCID_A},{IMSI_A},LAB-1\n{ICCID_B}, {IMSI_B} ,LAB-1\n\n")
    assert entries == [SimEntry(ICCID_A, IMSI_A, "LAB-1"), SimEntry(ICCID_B, IMSI_B, "LAB-1")]


def test_the_header_may_be_in_any_case() -> None:
    assert len(parse_sims(f"ICCID,IMSI,Batch\n{ICCID_A},{IMSI_A},LAB-1\n")) == 1


@pytest.mark.parametrize(
    "columns", ["iccid,imsi,ki,opc,batch", "iccid,imsi,batch,ki", "iccid,imsi,batch,notes"]
)
def test_a_file_with_any_extra_column_is_refused_and_names_the_column(columns: str) -> None:
    with pytest.raises(ValueError, match="unexpected column") as caught:
        parse_sims(f"{columns}\n{ICCID_A},{IMSI_A},LAB-1,x,y\n")
    assert ICCID_A not in str(caught.value) and IMSI_A not in str(caught.value)


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("", "empty"),
        (HEADER, "no SIMs"),
        ("iccid,batch,imsi\n", "header must be exactly"),
        (f"{HEADER}123,{IMSI_A},LAB-1\n", "ICCID must be 18 to 20 digits"),
        (f"{HEADER}{ICCID_A},12345,LAB-1\n", "IMSI must be 15 digits"),
        (f"{HEADER}{ICCID_A},{IMSI_A},\n", "batch must be"),
        (f"{HEADER}{ICCID_A},{IMSI_A},{'x' * 41}\n", "batch must be"),
        (f"{HEADER}{ICCID_A},{IMSI_A}\n", "expected 3 columns"),
        (f"{HEADER}{ICCID_A},{IMSI_A},LAB-1\n{ICCID_A},{IMSI_B},LAB-1\n", "appears twice"),
        (f"{HEADER}{ICCID_A},{IMSI_A},LAB-1\n{ICCID_B},{IMSI_A},LAB-1\n", "appears twice"),
    ],
)
def test_a_bad_sim_file_is_refused_without_echoing_any_identifier(
    body: str, complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint) as caught:
        parse_sims(body)
    for value in (ICCID_A, ICCID_B, IMSI_A, IMSI_B):
        assert value not in str(caught.value)


def test_the_line_is_named_in_the_complaint() -> None:
    with pytest.raises(ValueError, match="line 3"):
        parse_sims(f"{HEADER}{ICCID_A},{IMSI_A},LAB-1\n{ICCID_B},nope,LAB-1\n")


def test_a_number_file_is_read_with_comments_blank_lines_and_a_header() -> None:
    assert parse_numbers("msisdn\n# lab numbers\n2347000000150\n\n2347000000151\n") == [
        "2347000000150",
        "2347000000151",
    ]


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("", "no numbers"),
        ("# nothing\n", "no numbers"),
        ("+2347000000150\n", "234 and ten digits"),
        ("07000000150\n", "234 and ten digits"),
        ("234 700 000 0150\n", "234 and ten digits"),
        ("2347000000150\n2347000000150\n", "appears twice"),
    ],
)
def test_a_bad_number_file_is_refused_without_echoing_a_number(body: str, complaint: str) -> None:
    with pytest.raises(ValueError, match=complaint) as caught:
        parse_numbers(body)
    assert "7000000150" not in str(caught.value)
