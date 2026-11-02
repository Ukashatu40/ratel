"""Reading a file of SIMs or numbers to put into stock, and refusing what is wrong with it.

Pure: no database, no file access. An error names the line and the column, never the value on it
(an ICCID, an IMSI and a number are identifiers that stay out of logs and chat;
docs/SECURITY_AND_PRIVACY.md).

SIM file: a header `iccid,imsi,batch`, then one SIM per line. Nothing else. A column for a key (ki,
opc, anything else) is refused: BSS never holds key material, and a file that carries it should not
be sitting on this host.
Number file: one number per line in the stored form (digits, international, no plus), an optional
`msisdn` header, blank lines and lines starting with # ignored.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

SIM_COLUMNS = ("iccid", "imsi", "batch")
_ICCID = re.compile(r"^[0-9]{18,20}$")
_IMSI = re.compile(r"^[0-9]{15}$")
_MSISDN = re.compile(r"^234[0-9]{10}$")
_BATCH_MAX = 40
MAX_ROWS = 10_000


@dataclass(frozen=True)
class SimEntry:
    iccid: str
    imsi: str
    batch: str


def parse_sims(text: str) -> list[SimEntry]:
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise ValueError("the file is empty")
    header = tuple(cell.strip().lower() for cell in rows[0])
    if header != SIM_COLUMNS:
        extra = sorted(set(header) - set(SIM_COLUMNS))
        if extra:
            raise ValueError(
                f"unexpected column(s) {', '.join(extra)}: only iccid, imsi, batch are allowed"
            )
        raise ValueError("the header must be exactly: iccid,imsi,batch")
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ValueError(f"more than {MAX_ROWS} SIMs in one file")
    entries: list[SimEntry] = []
    seen_iccid: set[str] = set()
    seen_imsi: set[str] = set()
    for number, row in enumerate(body, start=2):  # line 1 is the header
        if len(row) != len(SIM_COLUMNS):
            raise ValueError(f"line {number}: expected 3 columns")
        iccid, imsi, batch = (cell.strip() for cell in row)
        if not _ICCID.match(iccid):
            raise ValueError(f"line {number}: the ICCID must be 18 to 20 digits")
        if not _IMSI.match(imsi):
            raise ValueError(f"line {number}: the IMSI must be 15 digits")
        if not batch or len(batch) > _BATCH_MAX or not batch.isprintable():
            raise ValueError(
                f"line {number}: the batch must be 1 to {_BATCH_MAX} printable characters"
            )
        if iccid in seen_iccid or imsi in seen_imsi:
            raise ValueError(f"line {number}: an ICCID or IMSI appears twice in the file")
        seen_iccid.add(iccid)
        seen_imsi.add(imsi)
        entries.append(SimEntry(iccid, imsi, batch))
    if not entries:
        raise ValueError("the file has a header and no SIMs")
    return entries


def parse_numbers(text: str) -> list[str]:
    numbers: list[str] = []
    seen: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or (number == 1 and line.lower() == "msisdn"):
            continue
        if not _MSISDN.match(line):
            raise ValueError(
                f"line {number}: a number is 234 and ten digits, no plus sign or spaces"
            )
        if line in seen:
            raise ValueError(f"line {number}: a number appears twice in the file")
        seen.add(line)
        numbers.append(line)
    if not numbers:
        raise ValueError("the file has no numbers")
    if len(numbers) > MAX_ROWS:
        raise ValueError(f"more than {MAX_ROWS} numbers in one file")
    return numbers
