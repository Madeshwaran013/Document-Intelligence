"""
Text extraction / OCR service.

Uses RapidOCR (onnxruntime-based) as the primary, ultra-lightweight OCR engine
(~40MB RAM footprint), ensuring fast and reliable extraction with zero OOM risk
on cloud platforms like Render (512MB RAM limit).

Strategy per page:
  1. Try native text extraction (pypdf) — fast, exact, no OCR errors.
  2. If a page has negligible native text or yields no extracted data,
     rasterise via PyMuPDF/pdftoppm and run RapidOCR.
  3. JPG/PNG uploads always run directly through RapidOCR.
"""
import io
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.logging import get_logger
from app.utils.exceptions import OCRFailedError

logger = get_logger(__name__)

_MIN_NATIVE_TEXT_CHARS = 20

# Cached RapidOCR singleton instance (initialised once on first use)
_rapid_engine = None


def _get_rapid_engine():
    """Return a cached RapidOCR instance (initialised on first call)."""
    global _rapid_engine
    if _rapid_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_engine = RapidOCR()
            logger.info("RapidOCR engine initialised successfully.")
        except Exception as exc:  # noqa: BLE001
            raise OCRFailedError(f"Failed to initialise RapidOCR engine: {exc}") from exc
    return _rapid_engine


@dataclass
class OCRResult:
    pages: list[str] = field(default_factory=list)
    ocr_used: bool = False
    ocr_provider: str | None = None

    @property
    def full_text(self) -> str:
        return "\n".join(
            f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(self.pages)
        )


def extract_text(filename: str, content: bytes, content_type: str) -> OCRResult:
    settings = get_settings()
    try:
        if content_type == "application/pdf":
            return _extract_from_pdf(content, settings)
        else:
            return _extract_from_image(content, settings)
    except OCRFailedError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR/text extraction failed for %s", filename)
        raise OCRFailedError(f"Failed to extract text from document: {exc}") from exc


def force_ocr_pdf(content: bytes) -> OCRResult:
    """Force rasterisation and RapidOCR on every page of a PDF."""
    settings = get_settings()
    images = _render_pdf_pages(content)
    pages_text = [_ocr_image(img, settings) for img in images]
    return OCRResult(pages=pages_text, ocr_used=True, ocr_provider="rapid")


def _extract_from_pdf(content: bytes, settings) -> OCRResult:
    reader = PdfReader(io.BytesIO(content))
    pages_text: list[str] = []
    ocr_used = False

    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        pages_text.append(text)

    needs_ocr_idx = [i for i, t in enumerate(pages_text) if len(t.strip()) < _MIN_NATIVE_TEXT_CHARS]
    if needs_ocr_idx:
        images = _render_pdf_pages(content)
        for idx in needs_ocr_idx:
            if idx < len(images):
                ocr_text = _ocr_image(images[idx], settings)
                pages_text[idx] = ocr_text
                ocr_used = True

    return OCRResult(
        pages=pages_text,
        ocr_used=ocr_used,
        ocr_provider="rapid" if ocr_used else None,
    )


def _render_pdf_pages(content: bytes) -> list[Image.Image]:
    """Rasterise every PDF page to a PIL image using PyMuPDF (or pdftoppm fallback)."""
    try:
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
        except ImportError:
            import pymupdf
            doc = pymupdf.open(stream=content, filetype="pdf")
        images: list[Image.Image] = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        if images:
            return images
    except Exception as exc:  # noqa: BLE001
        logger.debug("PyMuPDF rasterisation failed, trying pdftoppm: %s", exc)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "doc.pdf"
        pdf_path.write_bytes(content)
        out_prefix = Path(tmp) / "page"
        try:
            subprocess.run(
                ["pdftoppm", "-jpeg", "-r", "200", str(pdf_path), str(out_prefix)],
                check=True, capture_output=True, timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise OCRFailedError(f"Could not rasterise PDF for OCR: {exc}") from exc

        image_files = sorted(Path(tmp).glob("page-*.jpg"))
        return [Image.open(f).copy() for f in image_files]


def _extract_from_image(content: bytes, settings) -> OCRResult:
    image = Image.open(io.BytesIO(content))
    text = _ocr_image(image, settings)
    return OCRResult(pages=[text], ocr_used=True, ocr_provider="rapid")


def _ocr_image(image: Image.Image, settings) -> str:
    """Run OCR on a PIL Image and return the extracted text string."""
    if max(image.size) > 2000:
        image = image.copy()
        image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)

    if settings.OCR_PROVIDER == "ocr_space" and settings.OCR_SPACE_API_KEY:
        try:
            return _ocr_via_ocr_space(image, settings)
        except Exception:  # noqa: BLE001
            logger.warning("OCR.Space failed, falling back to RapidOCR")

    return _ocr_via_rapidocr(image)


def _ocr_via_rapidocr(image: Image.Image) -> str:
    """Run RapidOCR on a PIL image and return joined text."""
    engine = _get_rapid_engine()
    img_array = np.array(image.convert("RGB"))
    res, _ = engine(img_array)
    if res:
        return _format_rapidocr_result(res)
    return ""


def _format_rapidocr_result(res: list, line_threshold: float = 15.0) -> str:
    """Group RapidOCR bounding boxes into horizontal lines (sorted by Y then X)."""
    items = []
    for box, text, _score in res:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((min(ys), min(xs), text))
    items.sort(key=lambda item: item[0])

    lines: list[str] = []
    current_line: list[tuple[float, str]] = []
    current_y: float | None = None

    for y, x, text in items:
        if current_y is None or abs(y - current_y) <= line_threshold:
            current_line.append((x, text))
            if current_y is None:
                current_y = y
            else:
                current_y = (current_y * (len(current_line) - 1) + y) / len(current_line)
        else:
            current_line.sort(key=lambda item: item[0])
            lines.append(" ".join(item[1] for item in current_line))
            current_line = [(x, text)]
            current_y = y

    if current_line:
        current_line.sort(key=lambda item: item[0])
        lines.append(" ".join(item[1] for item in current_line))

    return "\n".join(lines)


def _ocr_via_ocr_space(image: Image.Image, settings) -> str:
    import requests

    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    buf.seek(0)
    response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": ("page.jpg", buf, "image/jpeg")},
        data={"apikey": settings.OCR_SPACE_API_KEY, "OCREngine": 2},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("IsErroredOnProcessing"):
        raise RuntimeError(payload.get("ErrorMessage"))
    return "\n".join(r["ParsedText"] for r in payload.get("ParsedResults", []))
