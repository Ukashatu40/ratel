"""The printable sheet of a voucher batch: an A4 PDF, 24 cards a page, with the Ratel logo.

Written by hand (PDF 1.4: the standard Helvetica and Courier fonts, one embedded image, lines and
fills) so the app needs no PDF library and the PINs pass through no code we did not write. The
naira sign is not in the standard fonts, so it is drawn: an N with two strokes across it.

Each card shows, like other networks' printed e-PINs: the logo, the value, the PIN in groups of
four, the card number (needed with the PIN to load it), how to load it, and the card's place in
its batch. Cut along the dashed lines.

The bytes this returns hold live PINs. They are sent once, to the person who printed the batch,
and never stored or logged.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

LOGO = Path(__file__).resolve().parent.parent / "assets" / "ratel_logo.png"

MM = 72 / 25.4
PAGE_W, PAGE_H = 210 * MM, 297 * MM
COLUMNS, ROWS = 3, 8
CARDS_PER_PAGE = COLUMNS * ROWS
MARGIN_X, TOP, BOTTOM = 10 * MM, 16 * MM, 10 * MM
CARD_W = (PAGE_W - 2 * MARGIN_X) / COLUMNS
CARD_H = (PAGE_H - TOP - BOTTOM) / ROWS

Rgb = tuple[float, float, float]
NAVY: Rgb = (0.0, 0.2, 0.553)  # #00338d, RatelDesk's navy
INK = (0.059, 0.125, 0.22)  # #0f2038
MUTED = (0.392, 0.455, 0.545)  # #64748b
LINE = (0.78, 0.82, 0.88)
GREEN, YELLOW, RED = (0.0, 0.529, 0.318), (1.0, 0.8, 0.0), (0.894, 0.0, 0.169)  # the logo's arc

# Advance widths of printable ASCII (32 to 126), per 1000 units of font size, from the standard
# Helvetica AFM metrics. Courier is 600 for every character.
_ASCII = "".join(chr(c) for c in range(32, 127))
_WIDTHS = {
    "H": dict(
        zip(
            _ASCII,
            (
                278,
                278,
                355,
                556,
                556,
                889,
                667,
                191,
                333,
                333,
                389,
                584,
                278,
                333,
                278,
                278,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                278,
                278,
                584,
                584,
                584,
                556,
                1015,
                667,
                667,
                722,
                722,
                667,
                611,
                778,
                722,
                278,
                500,
                667,
                556,
                833,
                722,
                778,
                667,
                778,
                722,
                667,
                611,
                722,
                667,
                944,
                667,
                667,
                611,
                278,
                278,
                278,
                469,
                556,
                333,
                556,
                556,
                500,
                556,
                556,
                278,
                556,
                556,
                222,
                222,
                500,
                222,
                833,
                556,
                556,
                556,
                556,
                333,
                500,
                278,
                556,
                500,
                722,
                500,
                500,
                500,
                334,
                260,
                334,
                584,
            ),
            strict=True,
        )
    ),
    "HB": dict(
        zip(
            _ASCII,
            (
                278,
                333,
                474,
                556,
                556,
                889,
                722,
                238,
                333,
                333,
                389,
                584,
                278,
                333,
                278,
                278,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                556,
                333,
                333,
                584,
                584,
                584,
                611,
                975,
                722,
                722,
                722,
                722,
                667,
                611,
                778,
                722,
                278,
                556,
                722,
                611,
                833,
                722,
                778,
                667,
                778,
                722,
                667,
                611,
                722,
                667,
                944,
                667,
                667,
                611,
                333,
                278,
                333,
                584,
                556,
                333,
                556,
                611,
                556,
                611,
                556,
                333,
                611,
                611,
                278,
                278,
                556,
                278,
                889,
                611,
                611,
                611,
                611,
                389,
                556,
                333,
                611,
                556,
                778,
                556,
                556,
                500,
                389,
                280,
                389,
                584,
            ),
            strict=True,
        )
    ),
}


def width(text: str, font: str, size: float, char_space: float = 0) -> float:
    """The width of `text` in points, in one of the sheet's fonts."""
    if font in ("C", "CB"):
        units = 600 * len(text)
    else:
        units = sum(_WIDTHS[font].get(c, 556) for c in text)
    return units * size / 1000 + char_space * max(len(text) - 1, 0)


@dataclass(frozen=True)
class SheetCard:
    serial: int  # 1-based place in the batch
    card_number: str  # 20 digits
    pin: str  # 14 digits


@dataclass(frozen=True)
class SheetBatch:
    name: str
    face_value_kobo: int
    card_count: int
    printed_at: datetime
    printed_by: str


def groups(digits: str, size: int = 4) -> str:
    return " ".join(digits[i : i + size] for i in range(0, len(digits), size))


def naira_amount(kobo: int) -> str:
    """12345600 kobo as '123,456' (whole naira), or '123,456.50'."""
    whole, part = divmod(kobo, 100)
    return f"{whole:,}" if part == 0 else f"{whole:,}.{part:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    """The content stream of one page, in points from the bottom left."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(
        self,
        x: float,
        y: float,
        s: str,
        font: str,
        size: float,
        rgb: Rgb = INK,
        char_space: float = 0,
    ) -> None:
        r, g, b = rgb
        # Tc is part of the graphics state and outlives ET, so it is set every time.
        self.ops.append(
            f"BT /{font} {size:.2f} Tf {char_space:.2f} Tc {r:.3f} {g:.3f} {b:.3f} rg "
            f"{x:.2f} {y:.2f} Td ({_escape(s)}) Tj ET"
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: Rgb | None = None,
        stroke: Rgb | None = None,
        width: float = 0.5,
        dash: str = "",
    ) -> None:
        parts = ["q", dash] if dash else ["q"]
        if fill:
            parts.append("{:.3f} {:.3f} {:.3f} rg".format(*fill))
        if stroke:
            parts.append("{:.3f} {:.3f} {:.3f} RG {:.2f} w".format(*stroke, width))
        parts.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        parts.append("B" if fill and stroke else ("f" if fill else "S"))
        parts.append("Q")
        self.ops.append(" ".join(parts))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        rgb: Rgb = LINE,
        width: float = 0.5,
        dash: str = "",
    ) -> None:
        r, g, b = rgb
        self.ops.append(
            f"q {r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {dash} "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q"
        )

    def image(self, name: str, x: float, y: float, w: float, h: float) -> None:
        self.ops.append(f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def _amount_width(amount: str, size: float) -> float:
    return width("N" + amount, "HB", size)


def _naira(page: _Page, x: float, y: float, amount: str, size: float, rgb: Rgb = NAVY) -> None:
    """'N' with two strokes, then the amount, in Helvetica-Bold, from (x, y)."""
    page.text(x, y, "N" + amount, "HB", size, rgb)
    n_width = 722 * size / 1000
    for level in (0.33, 0.55):  # the two bars of the naira sign, across the N
        yy = y + size * 0.72 * level
        page.line(x - size * 0.06, yy, x + n_width + size * 0.02, yy, rgb, width=size * 0.07)


def _card(
    page: _Page, x: float, y: float, card: SheetCard, batch: SheetBatch, logo_ratio: float
) -> None:
    """One card with its bottom-left corner at (x, y). Heights are from the card's bottom edge."""
    pad = 3 * MM
    left, right = x + pad, x + CARD_W - pad
    top = y + CARD_H - pad
    # the cut line, shared with the neighbours
    page.rect(x, y, CARD_W, CARD_H, stroke=LINE, width=0.5, dash="[2.5 2] 0 d")
    # logo, top left; value and "AIRTIME", top right
    logo_h = 7 * MM
    page.image("Logo", left, top - logo_h, logo_h * logo_ratio, logo_h)
    amount, size = naira_amount(batch.face_value_kobo), 17.0
    _naira(page, right - _amount_width(amount, size), top - size * 0.72, amount, size)
    page.text(
        right - width("AIRTIME", "HB", 5.5, 0.8), y + 21.0 * MM, "AIRTIME", "HB", 5.5, MUTED, 0.8
    )
    # PIN, then the card number
    page.text(left, y + 20.4 * MM, "PIN", "HB", 5.5, MUTED, 0.8)
    page.text(left, y + 16.0 * MM, groups(card.pin), "CB", 12.5, NAVY)
    page.text(left, y + 13.4 * MM, "CARD NO.", "HB", 5.5, MUTED, 0.8)
    page.text(left, y + 10.5 * MM, groups(card.card_number), "C", 8.6, INK)
    # how to load it
    page.line(left, y + 9.0 * MM, right, y + 9.0 * MM, LINE, 0.4)
    page.text(left, y + 6.6 * MM, "Text CARD, the card no. and PIN to 555", "H", 5.8, INK)
    page.text(left, y + 4.3 * MM, "or dial *123*card no.*PIN#", "H", 5.8, INK)
    page.text(left, y + 1.9 * MM, f"{batch.name}   No. {card.serial:04d}", "H", 5.0, MUTED)
    site = "ratelplus.net.ng"
    page.text(right - width(site, "HB", 5.0), y + 1.9 * MM, site, "HB", 5.0, NAVY)
    # the logo's colours, along the bottom edge
    third = CARD_W / 3
    for i, colour in enumerate((GREEN, YELLOW, RED)):
        page.rect(x + i * third, y, third, 1.0 * MM, fill=colour)


def _header(page: _Page, batch: SheetBatch, number: int, pages: int) -> None:
    y = PAGE_H - 9 * MM
    page.text(MARGIN_X, y, "Ratelplus airtime vouchers", "HB", 10, NAVY)
    amount = naira_amount(batch.face_value_kobo)
    summary = f"Batch {batch.name}   {batch.card_count:,} cards of"
    page.text(MARGIN_X + 52 * MM, y, summary, "H", 8.5, INK)
    _naira(page, MARGIN_X + 52 * MM + width(summary, "H", 8.5) + 3, y, amount, 8.5, INK)
    label = f"Page {number} of {pages}"
    page.text(PAGE_W - MARGIN_X - width(label, "H", 8.5), y, label, "H", 8.5, MUTED)
    page.text(
        MARGIN_X,
        y - 4.6 * MM,
        "CONFIDENTIAL: live PINs. Keep this sheet locked away and cut along the dashed lines. "
        "Cards load only after the batch is put on sale.",
        "H",
        6.5,
        RED,
    )
    stamp = batch.printed_at.strftime("%d %b %Y %H:%M %Z").strip()
    page.text(MARGIN_X, 5 * MM, f"Printed {stamp} by {batch.printed_by}", "H", 6.5, MUTED)


@cache
def _logo() -> tuple[int, int, bytes]:
    """(width, height, zlib data) of the RGB PNG logo, embedded as is (PNG predictors)."""
    data = LOGO.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("the logo is not a PNG")
    pos, idat = 8, b""
    width = height = 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if (depth, colour, interlace) != (8, 2, 0):
                raise ValueError("the logo must be an 8-bit RGB PNG, not interlaced")
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    zlib.decompressobj().decompress(idat[:64])  # fails early on a broken file
    return width, height, idat


def render(batch: SheetBatch, cards: Sequence[SheetCard]) -> bytes:
    """The PDF for `cards`, in order, 24 a page."""
    if not cards:
        raise ValueError("no cards to print")
    logo_w, logo_h, logo_data = _logo()
    pages: list[_Page] = []
    total = (len(cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    for start in range(0, len(cards), CARDS_PER_PAGE):
        page = _Page()
        _header(page, batch, len(pages) + 1, total)
        for i, card in enumerate(cards[start : start + CARDS_PER_PAGE]):
            col, row = i % COLUMNS, i // COLUMNS
            x = MARGIN_X + col * CARD_W
            y = PAGE_H - TOP - (row + 1) * CARD_H
            _card(page, x, y, card, batch, logo_w / logo_h)
        pages.append(page)

    objects: list[bytes] = []  # object n is objects[n - 1]

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    fonts = {
        "H": "Helvetica",
        "HB": "Helvetica-Bold",
        "C": "Courier",
        "CB": "Courier-Bold",
    }
    font_ids = {
        key: add(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} "
            "/Encoding /WinAnsiEncoding >>".encode()
        )
        for key, name in fonts.items()
    }
    logo_id = add(
        f"<< /Type /XObject /Subtype /Image /Width {logo_w} /Height {logo_h} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
        f"/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {logo_w} >> "
        f"/Length {len(logo_data)} >>\nstream\n".encode()
        + logo_data
        + b"\nendstream"
    )
    resources = (
        "<< /Font << "
        + " ".join(f"/{k} {v} 0 R" for k, v in font_ids.items())
        + f" >> /XObject << /Logo {logo_id} 0 R >> >>"
    )
    pages_id = len(objects) + 1 + 2 * len(pages)  # after every page and its content
    page_ids = []
    for page in pages:
        content = zlib.compress(page.stream(), 9)
        content_id = add(
            f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )
        page_ids.append(
            add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W:.2f} "
                f"{PAGE_H:.2f}] /Resources {resources} /Contents {content_id} 0 R >>".encode()
            )
        )
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    assert add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()) == pages_id
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info_id = add(
        f"<< /Title (Ratelplus vouchers {_escape(batch.name)}) /Producer (RatelBSS) >>".encode()
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)
