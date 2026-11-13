import io

import pytest
from PIL import Image

from app.medical.extract import MAX_SIDE, extract_text, page_png, page_texts


def text_pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with a Helvetica text stream; pdfium tolerates the xref."""
    ops = (
        "BT /F1 12 Tf 50 750 Td 14 TL "
        + " T* ".join(f"({t}) Tj" for t in lines)
        + " ET"
    )
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = "%PDF-1.4\n" + "".join(
        f"{i} 0 obj\n{o}\nendobj\n" for i, o in enumerate(objs, 1)
    )
    return (body + "trailer\n<< /Root 1 0 R /Size 6 >>\n%%EOF").encode()


def scan_pdf() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(out, format="PDF")
    return out.getvalue()


async def test_text_layer_is_read_without_ocr():
    async def ocr(_: bytes) -> str:
        raise AssertionError("no OCR for a text page")

    text = await extract_text(
        text_pdf(
            [
                "Diagnostic: diabet zaharat tip 2, tratament cu insulina, control periodic la medic"
            ]
        ),
        ocr,
    )
    assert "diabet zaharat" in text


async def test_a_scanned_page_goes_to_ocr():
    seen = []

    async def ocr(png: bytes) -> str:
        seen.append(png[:8])
        return "Migrenă cronică"

    assert await extract_text(scan_pdf(), ocr) == "Migrenă cronică"
    assert seen == [b"\x89PNG\r\n\x1a\n"]


def test_unreadable_pdf_raises():
    with pytest.raises(ValueError):
        page_texts(b"%PDF-broken")


def test_a_huge_page_renders_within_the_pixel_cap():
    out = io.BytesIO()
    # 600x800 px at 1 dpi is a 43200x57600 pt page.
    Image.new("RGB", (600, 800), "white").save(out, format="PDF", resolution=1.0)
    size = Image.open(io.BytesIO(page_png(out.getvalue(), 0))).size
    assert max(size) <= MAX_SIDE
