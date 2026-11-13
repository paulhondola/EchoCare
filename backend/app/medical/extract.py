"""Text of a medical record PDF: the text layer, OCR for scanned pages (design §5.3)."""

import asyncio
import base64
import io
from collections.abc import Awaitable, Callable

import openai
import pypdfium2 as pdfium

from app.core.llm import BASE_URL

MAX_PAGES = 10
MIN_CHARS = 50
DPI = 150

type Ocr = Callable[[bytes], Awaitable[str]]


def _open(pdf: bytes) -> pdfium.PdfDocument:
    try:
        doc = pdfium.PdfDocument(pdf)
    except pdfium.PdfiumError as e:
        raise ValueError("unreadable PDF") from e
    if len(doc) == 0:
        doc.close()
        raise ValueError("PDF has no pages")
    return doc


def page_texts(pdf: bytes) -> list[str]:
    """The text layers of the first MAX_PAGES pages."""
    doc = _open(pdf)
    try:
        texts = []
        for i in range(min(len(doc), MAX_PAGES)):
            page = doc[i]
            try:
                textpage = page.get_textpage()
                try:
                    texts.append(textpage.get_text_bounded())
                finally:
                    textpage.close()
            finally:
                page.close()
        return texts
    except pdfium.PdfiumError as e:
        raise ValueError("unreadable PDF") from e
    finally:
        doc.close()


def page_png(pdf: bytes, index: int) -> bytes:
    doc = _open(pdf)
    try:
        page = doc[index]
        try:
            image = page.render(scale=DPI / 72).to_pil()
        finally:
            page.close()
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    except pdfium.PdfiumError as e:
        raise ValueError("unreadable PDF") from e
    finally:
        doc.close()


async def extract_text(pdf: bytes, ocr: Ocr) -> str:
    texts = await asyncio.to_thread(page_texts, pdf)
    for i, text in enumerate(texts):
        if len("".join(text.split())) < MIN_CHARS:
            png = await asyncio.to_thread(page_png, pdf, i)
            texts[i] = await ocr(png)
    return "\n\n".join(texts)


def deepinfra_ocr(api_key: str, model: str) -> Ocr:
    client = openai.AsyncOpenAI(base_url=BASE_URL, api_key=api_key or "missing")

    async def ocr(png: bytes) -> str:
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": url}},
                        {
                            "type": "text",
                            "text": "Return the plain text of this page.",
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""

    return ocr
