"""Text of a medical record PDF: the text layer, OCR for scanned pages (design §5.3)."""

import asyncio
import base64
import io
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

import openai
import pypdfium2 as pdfium

from app.core.llm import BASE_URL

MAX_PAGES = 10
MIN_CHARS = 50
DPI = 150
MAX_SIDE = 2500  # px; a huge MediaBox must not become a gigabyte bitmap
OCR_TIMEOUT = 60  # seconds per page request: one slow page must not eat the analysis

# pdfium is not thread-safe: the lock guards direct callers, and one thread of its own
# keeps waiters off asyncio's default executor, which also sends the pushes.
_PDFIUM = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdfium")

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
    with _PDFIUM:
        return _page_texts(pdf)


def _page_texts(pdf: bytes) -> list[str]:
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
    with _PDFIUM:
        return _page_png(pdf, index)


def _page_png(pdf: bytes, index: int) -> bytes:
    doc = _open(pdf)
    try:
        page = doc[index]
        try:
            width, height = page.get_size()
            scale = min(DPI / 72, MAX_SIDE / max(width, height))
            image = page.render(scale=scale).to_pil()
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
    texts = await asyncio.get_running_loop().run_in_executor(_POOL, page_texts, pdf)
    for i, text in enumerate(texts):
        if len("".join(text.split())) < MIN_CHARS:
            png = await asyncio.get_running_loop().run_in_executor(
                _POOL, page_png, pdf, i
            )
            texts[i] = await ocr(png)
    return "\n\n".join(texts)


def deepinfra_ocr(api_key: str, model: str) -> Ocr:
    client = openai.AsyncOpenAI(
        base_url=BASE_URL,
        api_key=api_key or "missing",
        timeout=OCR_TIMEOUT,
        max_retries=1,
    )

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
